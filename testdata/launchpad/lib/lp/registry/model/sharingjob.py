# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job classes related to the sharing feature are in here."""

__metaclass__ = type


__all__ = [
    'RemoveArtifactSubscriptionsJob',
    ]

import contextlib
import logging

from lazr.delegates import delegates
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
import simplejson
from sqlobject import SQLObjectNotFound
from storm.expr import (
    And,
    In,
    Join,
    Not,
    Or,
    Select,
    )
from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.app.enums import InformationType
from lp.blueprints.interfaces.specification import ISpecification
from lp.blueprints.model.specification import Specification
from lp.blueprints.model.specificationsearch import (
    get_specification_privacy_filter,
    )
from lp.blueprints.model.specificationsubscription import (
    SpecificationSubscription,
    )
from lp.bugs.interfaces.bug import (
    IBug,
    IBugSet,
    )
from lp.bugs.model.bugsubscription import BugSubscription
from lp.bugs.model.bugtaskflat import BugTaskFlat
from lp.bugs.model.bugtasksearch import get_bug_privacy_filter_terms
from lp.code.interfaces.branch import IBranch
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.model.branch import (
    Branch,
    get_branch_privacy_filter,
    )
from lp.code.model.branchsubscription import BranchSubscription
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.sharingjob import (
    IRemoveArtifactSubscriptionsJob,
    IRemoveArtifactSubscriptionsJobSource,
    ISharingJob,
    ISharingJobSource,
    )
from lp.registry.model.distribution import Distribution
from lp.registry.model.person import Person
from lp.registry.model.product import Product
from lp.registry.model.teammembership import TeamParticipation
from lp.services.config import config
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.stormbase import StormBase
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.services.job.runner import BaseRunnableJob
from lp.services.mail.sendmail import format_address_for_person
from lp.services.webapp import errorlog


class SharingJobType(DBEnumeratedType):
    """Values that ISharingJob.job_type can take."""

    REMOVE_GRANTEE_SUBSCRIPTIONS = DBItem(0, """
        Remove subscriptions of artifacts which are inaccessible.

        This job removes subscriptions to artifacts when access is
        no longer possible because a user no longer has an access
        grant (either direct or indirect via team membership).
        """)

    REMOVE_ARTIFACT_SUBSCRIPTIONS = DBItem(1, """
        Remove subscriptions for users who can no longer access artifacts.

        This job removes subscriptions to an artifact (such as a bug or
        branch) when access is no longer possible because the subscriber
        no longer has an access grant (either direct or indirect via team
        membership).
        """)


class SharingJob(StormBase):
    """Base class for jobs related to sharing."""

    implements(ISharingJob)

    __storm_table__ = 'SharingJob'

    id = Int(primary=True)

    job_id = Int('job')
    job = Reference(job_id, Job.id)

    product_id = Int(name='product')
    product = Reference(product_id, Product.id)

    distro_id = Int(name='distro')
    distro = Reference(distro_id, Distribution.id)

    grantee_id = Int(name='grantee')
    grantee = Reference(grantee_id, Person.id)

    job_type = EnumCol(enum=SharingJobType, notNull=True)

    _json_data = Unicode('json_data')

    @property
    def metadata(self):
        return simplejson.loads(self._json_data)

    def __init__(self, job_type, pillar, grantee, metadata):
        """Constructor.

        :param job_type: The BranchMergeProposalJobType of this job.
        :param metadata: The type-specific variables, as a JSON-compatible
            dict.
        """
        super(SharingJob, self).__init__()
        json_data = simplejson.dumps(metadata)
        self.job = Job()
        self.job_type = job_type
        self.grantee = grantee
        self.product = self.distro = None
        if IProduct.providedBy(pillar):
            self.product = pillar
        else:
            self.distro = pillar
        # XXX AaronBentley 2009-01-29 bug=322819: This should be a bytestring,
        # but the DB representation is unicode.
        self._json_data = json_data.decode('utf-8')

    def destroySelf(self):
        Store.of(self).remove(self)

    def makeDerived(self):
        return SharingJobDerived.makeSubclass(self)


class SharingJobDerived(BaseRunnableJob):
    """Intermediate class for deriving from SharingJob."""

    __metaclass__ = EnumeratedSubclass

    delegates(ISharingJob)
    classProvides(ISharingJobSource)

    def __init__(self, job):
        self.context = job

    def __repr__(self):
        return '<%(job_type)s job %(desc)s>' % {
            'job_type': self.context.job_type.name,
            'desc': self.getOperationDescription(),
            }

    @property
    def pillar(self):
        if self.product:
            return self.product
        else:
            return self.distro

    @property
    def pillar_text(self):
        return self.pillar.displayname if self.pillar else 'all pillars'

    @property
    def log_name(self):
        return self.__class__.__name__

    @classmethod
    def create(cls, pillar, grantee, metadata):
        base_job = SharingJob(cls.class_job_type, pillar, grantee, metadata)
        job = cls(base_job)
        job.celeryRunOnCommit()
        return job

    @classmethod
    def get(cls, job_id):
        """Get a job by id.

        :return: the SharingJob with the specified id, as the
            current SharingJobDereived subclass.
        :raises: SQLObjectNotFound if there is no job with the specified id,
            or its job_type does not match the desired subclass.
        """
        job = SharingJob.get(job_id)
        if job.job_type != cls.class_job_type:
            raise SQLObjectNotFound(
                'No object found with id %d and type %s' % (job_id,
                cls.class_job_type.title))
        return cls(job)

    @classmethod
    def iterReady(cls):
        """See `IJobSource`.

        This version will emit any ready job based on SharingJob.
        """
        store = IStore(SharingJob)
        jobs = store.find(
            SharingJob,
            And(SharingJob.job_type == cls.class_job_type,
                SharingJob.job_id.is_in(Job.ready_jobs)))
        return (cls.makeSubclass(job) for job in jobs)

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BaseRunnableJob.getOopsVars(self)
        vars.extend([
            ('sharing_job_id', self.context.id),
            ('sharing_job_type', self.context.job_type.title)])
        if self.grantee:
            vars.append(('grantee', self.grantee.name))
        if self.product:
            vars.append(('product', self.product.name))
        if self.distro:
            vars.append(('distro', self.distro.name))
        return vars


class RemoveArtifactSubscriptionsJob(SharingJobDerived):
    """See `IRemoveArtifactSubscriptionsJob`."""

    implements(IRemoveArtifactSubscriptionsJob)
    classProvides(IRemoveArtifactSubscriptionsJobSource)
    class_job_type = SharingJobType.REMOVE_ARTIFACT_SUBSCRIPTIONS

    config = config.IRemoveArtifactSubscriptionsJobSource

    @classmethod
    def create(cls, requestor, artifacts=None, grantee=None, pillar=None,
               information_types=None):
        """See `IRemoveArtifactSubscriptionsJob`."""

        bug_ids = []
        branch_ids = []
        specification_ids = []
        if artifacts:
            for artifact in artifacts:
                if IBug.providedBy(artifact):
                    bug_ids.append(artifact.id)
                elif IBranch.providedBy(artifact):
                    branch_ids.append(artifact.id)
                elif ISpecification.providedBy(artifact):
                    specification_ids.append(artifact.id)
                else:
                    raise ValueError(
                        'Unsupported artifact: %r' % artifact)
        information_types = [
            info_type.value for info_type in information_types or []
        ]
        metadata = {
            'bug_ids': bug_ids,
            'branch_ids': branch_ids,
            'specification_ids': specification_ids,
            'information_types': information_types,
            'requestor.id': requestor.id
        }
        return super(RemoveArtifactSubscriptionsJob, cls).create(
            pillar, grantee, metadata)

    @property
    def requestor_id(self):
        return self.metadata['requestor.id']

    @property
    def requestor(self):
        return getUtility(IPersonSet).get(self.requestor_id)

    @property
    def bug_ids(self):
        return self.metadata.get('bug_ids', [])

    @property
    def bugs(self):
        return getUtility(IBugSet).getByNumbers(self.bug_ids)

    @property
    def branch_ids(self):
        return self.metadata.get('branch_ids', [])

    @property
    def branches(self):
        return [getUtility(IBranchLookup).get(id) for id in self.branch_ids]

    @property
    def specification_ids(self):
        return self.metadata.get('specification_ids', [])

    @property
    def information_types(self):
        if not 'information_types' in self.metadata:
            return []
        return [
            InformationType.items[value]
            for value in self.metadata['information_types']]

    def getErrorRecipients(self):
        # If something goes wrong we want to let the requestor know as well
        # as the pillar maintainer (if there is a pillar).
        result = set()
        result.add(format_address_for_person(self.requestor))
        for bug in self.bugs:
            for pillar in bug.affected_pillars:
                if pillar.owner.preferredemail:
                    result.add(format_address_for_person(pillar.owner))
        return list(result)

    def getOperationDescription(self):
        info = {
            'information_types': [t.name for t in self.information_types],
            'requestor': self.requestor.name,
            'bug_ids': self.bug_ids,
            'branch_ids': self.branch_ids,
            'specification_ids': self.specification_ids,
            'pillar': getattr(self.pillar, 'name', None),
            'grantee': getattr(self.grantee, 'name', None)
            }
        return (
            'reconciling subscriptions for %s' % ', '.join(
                '%s=%s' % (k, v) for (k, v) in sorted(info.items()) if v))

    def run(self):
        """See `IRemoveArtifactSubscriptionsJob`."""
        logger = logging.getLogger()
        logger.info(self.getOperationDescription())

        bug_filters = []
        branch_filters = []
        specification_filters = []

        if self.branch_ids:
            branch_filters.append(Branch.id.is_in(self.branch_ids))
        if self.specification_ids:
            specification_filters.append(Specification.id.is_in(
                self.specification_ids))
        if self.bug_ids:
            bug_filters.append(BugTaskFlat.bug_id.is_in(self.bug_ids))
        else:
            if self.information_types:
                bug_filters.append(
                    BugTaskFlat.information_type.is_in(
                        self.information_types))
                branch_filters.append(
                    Branch.information_type.is_in(self.information_types))
                specification_filters.append(
                    Specification.information_type.is_in(
                        self.information_types))
            if self.product:
                bug_filters.append(
                    BugTaskFlat.product == self.product)
                branch_filters.append(Branch.product == self.product)
                specification_filters.append(
                    Specification.product == self.product)
            if self.distro:
                bug_filters.append(
                    BugTaskFlat.distribution == self.distro)
                branch_filters.append(Branch.distribution == self.distro)
                specification_filters.append(
                    Specification.distribution == self.distro)

        if self.grantee:
            bug_filters.append(
                In(BugSubscription.person_id,
                    Select(
                        TeamParticipation.personID,
                        where=TeamParticipation.team == self.grantee)))
            branch_filters.append(
                In(BranchSubscription.personID,
                    Select(
                        TeamParticipation.personID,
                        where=TeamParticipation.team == self.grantee)))
            specification_filters.append(
                In(SpecificationSubscription.personID,
                    Select(
                        TeamParticipation.personID,
                        where=TeamParticipation.team == self.grantee)))

        if bug_filters:
            bug_filters.append(Not(
                Or(*get_bug_privacy_filter_terms(
                    BugSubscription.person_id))))
            bug_subscriptions = IStore(BugSubscription).using(
                BugSubscription,
                Join(BugTaskFlat,
                    BugTaskFlat.bug_id == BugSubscription.bug_id)
                ).find(BugSubscription, *bug_filters).config(distinct=True)
            for sub in bug_subscriptions:
                sub.bug.unsubscribe(
                    sub.person, self.requestor, ignore_permissions=True)
        if branch_filters:
            branch_filters.append(Not(
                Or(*get_branch_privacy_filter(BranchSubscription.personID))))
            branch_subscriptions = IStore(BranchSubscription).using(
                BranchSubscription,
                Join(Branch, Branch.id == BranchSubscription.branchID)
                ).find(BranchSubscription, *branch_filters).config(
                    distinct=True)
            for sub in branch_subscriptions:
                sub.branch.unsubscribe(
                    sub.person, self.requestor, ignore_permissions=True)
        if specification_filters:
            specification_filters.append(Not(*get_specification_privacy_filter(
                SpecificationSubscription.personID)))
            tables = (
                SpecificationSubscription,
                Join(
                    Specification,
                    Specification.id ==
                        SpecificationSubscription.specificationID))
            specifications_subscriptions = IStore(
                SpecificationSubscription).using(*tables).find(
                SpecificationSubscription, *specification_filters).config(
                distinct=True)
            for sub in specifications_subscriptions:
                sub.specification.unsubscribe(
                    sub.person, self.requestor, ignore_permissions=True)
