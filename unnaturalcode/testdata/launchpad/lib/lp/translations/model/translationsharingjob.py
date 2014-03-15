# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job for merging translations."""

__metaclass__ = type

__all__ = [
    'TranslationSharingJob',
    'TranslationSharingJobType',
    'TranslationSharingJobDerived',
    ]

from lazr.delegates import delegates
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from storm.locals import (
    Int,
    Reference,
    )

from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.productseries import ProductSeries
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.stormbase import StormBase
from lp.services.job.interfaces.job import (
    IJob,
    JobStatus,
    )
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.translations.interfaces.translationsharingjob import (
    ITranslationSharingJob,
    )
from lp.translations.model.potemplate import POTemplate


class TranslationSharingJobType(DBEnumeratedType):
    """Types of translation sharing Job."""

    PACKAGING_MERGE = DBItem(0, """
        Merge translations betweeen productseries and sourcepackage.

        Merge translations betweeen productseries and sourcepackage.
        """)

    PACKAGING_SPLIT = DBItem(1, """
        Split translations between productseries and sourcepackage.

        Split translations between productseries and sourcepackage.
        """)

    TEMPLATE_CHANGE = DBItem(2, """
        Split/merge translations for a single translation template.

        Split/merge translations for a single translation template.
        """)


class TranslationSharingJob(StormBase):
    """Base class for jobs related to a packaging."""

    __storm_table__ = 'PackagingJob'

    id = Int(primary=True)

    job_id = Int('job')

    job = Reference(job_id, Job.id)

    delegates(IJob, 'job')

    job_type = EnumCol(enum=TranslationSharingJobType, notNull=True)

    productseries_id = Int('productseries')

    productseries = Reference(productseries_id, ProductSeries.id)

    distroseries_id = Int('distroseries')

    distroseries = Reference(distroseries_id, DistroSeries.id)

    sourcepackagename_id = Int('sourcepackagename')

    sourcepackagename = Reference(sourcepackagename_id, SourcePackageName.id)

    potemplate_id = Int('potemplate')

    potemplate = Reference(potemplate_id, POTemplate.id)

    def __init__(self, job, job_type, productseries, distroseries,
                 sourcepackagename, potemplate=None):
        """"Constructor.

        :param job: The `Job` to use for storing basic job state.
        :param productseries: The ProductSeries side of the Packaging.
        :param distroseries: The distroseries of the Packaging sourcepackage.
        :param sourcepackagename: The name of the Packaging sourcepackage.
        """
        self.job = job
        self.job_type = job_type
        self.distroseries = distroseries
        self.sourcepackagename = sourcepackagename
        self.productseries = productseries
        self.potemplate = potemplate

    def makeDerived(self):
        return TranslationSharingJobDerived.makeSubclass(self)


class TranslationSharingJobDerived:
    """Base class for specialized TranslationTemplate Job types."""

    __metaclass__ = EnumeratedSubclass

    delegates(ITranslationSharingJob, 'job')

    def getDBClass(self):
        return TranslationSharingJob

    _event_types = {}

    @property
    def sourcepackage(self):
        return self.distroseries.getSourcePackage(self.sourcepackagename)

    @staticmethod
    def _register_subclass(cls):
        """Register this class with its enumeration."""
        # This would be a classmethod, except that subclasses (e.g.
        # TranslationPackagingJob) need to be able to override it and call
        # into it, and there's no syntax to call a base class's version of a
        # classmethod with the subclass as the first parameter.
        event_type = getattr(cls, 'create_on_event', None)
        if event_type is not None:
            cls._event_types.setdefault(event_type, []).append(cls)

    def __init__(self, job):
        assert job.job_type == self.class_job_type, (
            "Attempting to create a %s using a %s TranslationSharingJob" %
            (self.__class__.__name__, job.job_type))
        self.job = job

    @classmethod
    def create(cls, productseries=None, distroseries=None,
               sourcepackagename=None, potemplate=None):
        """"Create a TranslationPackagingJob backed by TranslationSharingJob.

        :param productseries: The ProductSeries side of the Packaging.
        :param distroseries: The distroseries of the Packaging sourcepackage.
        :param sourcepackagename: The name of the Packaging sourcepackage.
        :param potemplate: POTemplate to restrict to (if any).
        """
        context = TranslationSharingJob(
            Job(), cls.class_job_type, productseries,
            distroseries, sourcepackagename, potemplate)
        derived = cls(context)
        derived.celeryRunOnCommit()
        return derived

    @classmethod
    def schedulePackagingJob(cls, packaging, event):
        """Event subscriber to create a TranslationSharingJob on events.

        :param packaging: The `Packaging` to create a `TranslationMergeJob`
            for.
        :param event: The event itself.
        """
        for event_type, job_classes in cls._event_types.iteritems():
            if not event_type.providedBy(event):
                continue
            for job_class in job_classes:
                job_class.forPackaging(packaging)

    @classmethod
    def schedulePOTemplateJob(cls, potemplate, event):
        """Event subscriber to create a TranslationSharingJob on events.

        :param potemplate: The `POTemplate` to create
            a `TranslationSharingJob` for.
        :param event: The event itself.
        """
        if ('name' not in event.edited_fields and
            'productseries' not in event.edited_fields and
            'distroseries' not in event.edited_fields and
            'sourcepackagename' not in event.edited_fields):
            # Ignore changes to POTemplates that are neither renames,
            # nor moves to a different package/project.
            return
        for event_type, job_classes in cls._event_types.iteritems():
            if not event_type.providedBy(event):
                continue
            for job_class in job_classes:
                job_class.forPOTemplate(potemplate)

    @classmethod
    def iterReady(cls, extra_clauses):
        """See `IJobSource`.

        This version will emit any ready job based on TranslationSharingJob.
        :param extra_clauses: Extra clauses to reduce the selections.
        """
        store = IStore(TranslationSharingJob)
        jobs = store.find(
            (TranslationSharingJob),
            TranslationSharingJob.job == Job.id,
            Job.id.is_in(Job.ready_jobs),
            *extra_clauses)
        return (cls.makeSubclass(job) for job in jobs)

    @classmethod
    def getNextJobStatus(cls, packaging):
        """Return the status of the next job to run."""
        store = IStore(TranslationSharingJob)
        result = store.find(
            Job, Job.id == TranslationSharingJob.job_id,
            (TranslationSharingJob.distroseries_id ==
             packaging.distroseries.id),
            TranslationSharingJob.sourcepackagename_id ==
                packaging.sourcepackagename.id,
            (TranslationSharingJob.productseries_id ==
             packaging.productseries.id),
            TranslationSharingJob.job_type == cls.class_job_type,
            Job._status.is_in([JobStatus.WAITING, JobStatus.RUNNING]))
        result.order_by(TranslationSharingJob.id)
        job = result.first()
        if job is None:
            return None
        return job.status


#make accessible to zcml
schedule_packaging_job = TranslationSharingJobDerived.schedulePackagingJob
schedule_potemplate_job = TranslationSharingJobDerived.schedulePOTemplateJob
