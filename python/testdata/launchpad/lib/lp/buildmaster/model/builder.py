# Copyright 2009,2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'Builder',
    'BuilderSet',
    ]

import logging

from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    Coalesce,
    Count,
    Sum,
    )
import transaction
from zope.component import getUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.buildmaster.interfaces.builder import (
    IBuilder,
    IBuilderSet,
    )
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJobSet
from lp.buildmaster.interfaces.buildqueue import IBuildQueueSet
from lp.buildmaster.model.buildqueue import (
    BuildQueue,
    specific_job_classes,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.interfaces import (
    ISlaveStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.propertycache import cachedproperty
# XXX Michael Nelson 2010-01-13 bug=491330
# These dependencies on soyuz will be removed when getBuildRecords()
# is moved.
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.buildrecords import (
    IHasBuildRecords,
    IncompatibleArguments,
    )
from lp.soyuz.model.processor import Processor


class Builder(SQLBase):

    implements(IBuilder, IHasBuildRecords)
    _table = 'Builder'

    _defaultOrder = ['id']

    processor = ForeignKey(dbName='processor', foreignKey='Processor',
                           notNull=True)
    url = StringCol(dbName='url', notNull=True)
    name = StringCol(dbName='name', notNull=True)
    title = StringCol(dbName='title', notNull=True)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    _builderok = BoolCol(dbName='builderok', notNull=True)
    failnotes = StringCol(dbName='failnotes')
    virtualized = BoolCol(dbName='virtualized', default=True, notNull=True)
    speedindex = IntCol(dbName='speedindex')
    manual = BoolCol(dbName='manual', default=False)
    vm_host = StringCol(dbName='vm_host')
    active = BoolCol(dbName='active', notNull=True, default=True)
    failure_count = IntCol(dbName='failure_count', default=0, notNull=True)

    # The number of times a builder can consecutively fail before we try
    # resetting it (if virtual) or marking it builderok=False (if not).
    RESET_THRESHOLD = 5

    # The number of times a virtual builder can reach its reset threshold
    # due to consecutive failures before we give up and mark it
    # builderok=False.
    RESET_FAILURE_THRESHOLD = 3

    def _getBuilderok(self):
        return self._builderok

    def _setBuilderok(self, value):
        self._builderok = value
        if value is True:
            self.resetFailureCount()

    builderok = property(_getBuilderok, _setBuilderok)

    def gotFailure(self):
        """See `IBuilder`."""
        self.failure_count += 1

    def resetFailureCount(self):
        """See `IBuilder`."""
        self.failure_count = 0

    @cachedproperty
    def currentjob(self):
        """See IBuilder"""
        return getUtility(IBuildQueueSet).getByBuilder(self)

    def failBuilder(self, reason):
        """See IBuilder"""
        # XXX cprov 2007-04-17: ideally we should be able to notify the
        # the buildd-admins about FAILED builders. One alternative is to
        # make the buildd_cronscript (slave-scanner, in this case) to exit
        # with error, for those cases buildd-sequencer automatically sends
        # an email to admins with the script output.
        self.builderok = False
        self.failnotes = reason

    def getBuildRecords(self, build_state=None, name=None, arch_tag=None,
                        user=None, binary_only=True):
        """See IHasBuildRecords."""
        if binary_only:
            return getUtility(IBinaryPackageBuildSet).getBuildsForBuilder(
                self.id, build_state, name, arch_tag, user)
        else:
            if arch_tag is not None or name is not None:
                raise IncompatibleArguments(
                    "The 'arch_tag' and 'name' parameters can be used only "
                    "with binary_only=True.")
            return getUtility(IBuildFarmJobSet).getBuildsForBuilder(
                self, status=build_state, user=user)

    def _getSlaveScannerLogger(self):
        """Return the logger instance from buildd-slave-scanner.py."""
        # XXX cprov 20071120: Ideally the Launchpad logging system
        # should be able to configure the root-logger instead of creating
        # a new object, then the logger lookups won't require the specific
        # name argument anymore. See bug 164203.
        logger = logging.getLogger('slave-scanner')
        return logger

    def acquireBuildCandidate(self):
        """See `IBuilder`."""
        candidate = self._findBuildCandidate()
        if candidate is not None:
            candidate.markAsBuilding(self)
            transaction.commit()
        return candidate

    def _findBuildCandidate(self):
        """Find a candidate job for dispatch to an idle buildd slave.

        The pending BuildQueue item with the highest score for this builder
        or None if no candidate is available.

        :return: A candidate job.
        """
        def qualify_subquery(job_type, sub_query):
            """Put the sub-query into a job type context."""
            qualified_query = """
                ((BuildQueue.job_type != %s) OR EXISTS(%%s))
            """ % sqlvalues(job_type)
            qualified_query %= sub_query
            return qualified_query

        logger = self._getSlaveScannerLogger()
        candidate = None

        general_query = """
            SELECT buildqueue.id FROM buildqueue, job
            WHERE
                buildqueue.job = job.id
                AND job.status = %s
                AND (
                    -- The processor values either match or the candidate
                    -- job is processor-independent.
                    buildqueue.processor = %s OR
                    buildqueue.processor IS NULL)
                AND (
                    -- The virtualized values either match or the candidate
                    -- job does not care about virtualization and the idle
                    -- builder *is* virtualized (the latter is a security
                    -- precaution preventing the execution of untrusted code
                    -- on native builders).
                    buildqueue.virtualized = %s OR
                    (buildqueue.virtualized IS NULL AND %s = TRUE))
                AND buildqueue.builder IS NULL
        """ % sqlvalues(
            JobStatus.WAITING, self.processor, self.virtualized,
            self.virtualized)
        order_clause = " ORDER BY buildqueue.lastscore DESC, buildqueue.id"

        extra_queries = []
        job_classes = specific_job_classes()
        for job_type, job_class in job_classes.iteritems():
            query = job_class.addCandidateSelectionCriteria(
                self.processor, self.virtualized)
            if query == '':
                # This job class does not need to refine candidate jobs
                # further.
                continue

            # The sub-query should only apply to jobs of the right type.
            extra_queries.append(qualify_subquery(job_type, query))
        query = ' AND '.join([general_query] + extra_queries) + order_clause

        store = IStore(self.__class__)
        candidate_jobs = store.execute(query).get_all()

        for (candidate_id,) in candidate_jobs:
            candidate = getUtility(IBuildQueueSet).get(candidate_id)
            job_class = job_classes[candidate.job_type]
            candidate_approved = job_class.postprocessCandidate(
                candidate, logger)
            if candidate_approved:
                return candidate

        return None

    def handleFailure(self, logger):
        """See IBuilder."""
        self.gotFailure()
        if self.currentjob is not None:
            build_farm_job = self.currentjob.specific_job.build
            build_farm_job.gotFailure()
            logger.info(
                "Builder %s failure count: %s, job '%s' failure count: %s" % (
                    self.name, self.failure_count,
                    build_farm_job.title, build_farm_job.failure_count))
        else:
            logger.info(
                "Builder %s failure count: %s" % (
                    self.name, self.failure_count))


class BuilderSet(object):
    """See IBuilderSet"""
    implements(IBuilderSet)

    def __init__(self):
        self.title = "The Launchpad build farm"

    def __iter__(self):
        return iter(Builder.select())

    def getByName(self, name):
        """See IBuilderSet."""
        try:
            return Builder.selectOneBy(name=name)
        except SQLObjectNotFound:
            raise NotFoundError(name)

    def __getitem__(self, name):
        return self.getByName(name)

    def new(self, processor, url, name, title, owner, active=True,
            virtualized=False, vm_host=None, manual=True):
        """See IBuilderSet."""
        return Builder(processor=processor, url=url, name=name, title=title,
                       owner=owner, active=active, virtualized=virtualized,
                       vm_host=vm_host, _builderok=True, manual=manual)

    def get(self, builder_id):
        """See IBuilderSet."""
        return Builder.get(builder_id)

    def count(self):
        """See IBuilderSet."""
        return Builder.select().count()

    def getBuilders(self):
        """See IBuilderSet."""
        return Builder.selectBy(
            active=True, orderBy=['virtualized', 'processor', 'name'])

    def getBuildQueueSizes(self):
        """See `IBuilderSet`."""
        results = ISlaveStore(BuildQueue).find((
            Count(),
            Sum(BuildQueue.estimated_duration),
            Processor,
            Coalesce(BuildQueue.virtualized, True)),
            Processor.id == BuildQueue.processorID,
            Job.id == BuildQueue.jobID,
            Job._status == JobStatus.WAITING).group_by(
                Processor, Coalesce(BuildQueue.virtualized, True))

        result_dict = {'virt': {}, 'nonvirt': {}}
        for size, duration, processor, virtualized in results:
            if virtualized is False:
                virt_str = 'nonvirt'
            else:
                virt_str = 'virt'
            result_dict[virt_str][processor.name] = (
                size, duration)

        return result_dict

    def getBuildersForQueue(self, processor, virtualized):
        """See `IBuilderSet`."""
        return Builder.selectBy(_builderok=True, processor=processor,
                                virtualized=virtualized)
