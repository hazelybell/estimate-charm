# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BuildFarmJob',
    'BuildFarmJobMixin',
    'BuildFarmJobOld',
    ]

import datetime

import pytz
from storm.expr import (
    Desc,
    LeftJoin,
    Or,
    )
from storm.locals import (
    DateTime,
    Int,
    Reference,
    Storm,
    )
from storm.store import Store
from zope.interface import (
    classProvides,
    implements,
    )

from lp.buildmaster.enums import (
    BuildFarmJobType,
    BuildStatus,
    )
from lp.buildmaster.interfaces.buildfarmjob import (
    IBuildFarmJob,
    IBuildFarmJobOld,
    IBuildFarmJobSet,
    IBuildFarmJobSource,
    )
from lp.services.database.enumcol import DBEnum
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )


class BuildFarmJobOld:
    """Some common implementation for IBuildFarmJobOld."""

    implements(IBuildFarmJobOld)

    processor = None
    virtualized = None

    @staticmethod
    def preloadBuildFarmJobs(jobs):
        """Preload the build farm jobs to which the given jobs will delegate.

        """
        pass

    @classmethod
    def getByJob(cls, job):
        """See `IBuildFarmJobOld`."""
        return IStore(cls).find(cls, cls.job == job).one()

    @classmethod
    def getByJobs(cls, jobs):
        """See `IBuildFarmJobOld`."""
        job_ids = [job.id for job in jobs]
        return IStore(cls).find(cls, cls.job_id.is_in(job_ids))

    def score(self):
        """See `IBuildFarmJobOld`."""
        raise NotImplementedError

    def cleanUp(self):
        """See `IBuildFarmJob`.

        Classes that derive from BuildFarmJobOld need to clean up
        after themselves correctly.
        """
        Store.of(self).remove(self)

    @staticmethod
    def addCandidateSelectionCriteria(processor, virtualized):
        """See `IBuildFarmJobOld`."""
        return ('')

    @staticmethod
    def postprocessCandidate(job, logger):
        """See `IBuildFarmJobOld`."""
        return True

    def jobStarted(self):
        """See `IBuildFarmJobOld`."""
        # XXX wgrant: builder should be set here.
        self.build.updateStatus(BuildStatus.BUILDING)

    def jobReset(self):
        """See `IBuildFarmJob`."""
        self.build.updateStatus(BuildStatus.NEEDSBUILD)

    def jobCancel(self):
        """See `IBuildFarmJob`."""
        self.build.updateStatus(BuildStatus.CANCELLED)


class BuildFarmJob(Storm):
    """A base implementation for `IBuildFarmJob` classes."""
    __storm_table__ = 'BuildFarmJob'

    implements(IBuildFarmJob)
    classProvides(IBuildFarmJobSource)

    id = Int(primary=True)

    date_created = DateTime(
        name='date_created', allow_none=False, tzinfo=pytz.UTC)

    date_finished = DateTime(
        name='date_finished', allow_none=True, tzinfo=pytz.UTC)

    builder_id = Int(name='builder', allow_none=True)
    builder = Reference(builder_id, 'Builder.id')

    status = DBEnum(name='status', allow_none=False, enum=BuildStatus)

    job_type = DBEnum(
        name='job_type', allow_none=False, enum=BuildFarmJobType)

    archive_id = Int(name='archive')
    archive = Reference(archive_id, 'Archive.id')

    def __init__(self, job_type, status=BuildStatus.NEEDSBUILD,
                 date_created=None, builder=None, archive=None):
        super(BuildFarmJob, self).__init__()
        (self.job_type, self.status, self.builder, self.archive) = (
             job_type, status, builder, archive)
        if date_created is not None:
            self.date_created = date_created

    @classmethod
    def new(cls, job_type, status=BuildStatus.NEEDSBUILD, date_created=None,
            builder=None, archive=None):
        """See `IBuildFarmJobSource`."""
        build_farm_job = BuildFarmJob(
            job_type, status, date_created, builder, archive)
        store = IMasterStore(BuildFarmJob)
        store.add(build_farm_job)
        return build_farm_job


class BuildFarmJobMixin:

    @property
    def dependencies(self):
        return None

    @property
    def title(self):
        """See `IBuildFarmJob`."""
        return self.job_type.title

    @property
    def duration(self):
        """See `IBuildFarmJob`."""
        if self.date_started is None or self.date_finished is None:
            return None
        return self.date_finished - self.date_started

    def makeJob(self):
        """See `IBuildFarmJobOld`."""
        raise NotImplementedError

    @property
    def buildqueue_record(self):
        """See `IBuildFarmJob`."""
        return None

    @property
    def is_private(self):
        """See `IBuildFarmJob`.

        This base implementation assumes build farm jobs are public, but
        derived implementations can override as required.
        """
        return False

    @property
    def log_url(self):
        """See `IBuildFarmJob`.

        This base implementation of the property always returns None. Derived
        implementations need to override for their specific context.
        """
        return None

    @property
    def was_built(self):
        """See `IBuild`"""
        return self.status not in [BuildStatus.NEEDSBUILD,
                                   BuildStatus.BUILDING,
                                   BuildStatus.CANCELLED,
                                   BuildStatus.CANCELLING,
                                   BuildStatus.UPLOADING,
                                   BuildStatus.SUPERSEDED]

    def setLog(self, log):
        """See `IBuildFarmJob`."""
        self.log = log

    def updateStatus(self, status, builder=None, slave_status=None,
                     date_started=None, date_finished=None):
        """See `IBuildFarmJob`."""
        self.build_farm_job.status = self.status = status

        # If there's a builder provided, set it if we don't already have
        # one, or otherwise crash if it's different from the one we
        # expected.
        if builder is not None:
            if self.builder is None:
                self.build_farm_job.builder = self.builder = builder
            else:
                assert self.builder == builder

        # If we're starting to build, set date_started and
        # date_first_dispatched if required.
        if self.date_started is None and status == BuildStatus.BUILDING:
            self.date_started = date_started or datetime.datetime.now(pytz.UTC)
            if self.date_first_dispatched is None:
                self.date_first_dispatched = self.date_started

        # If we're in a final build state (or UPLOADING, which sort of
        # is), set date_finished if date_started is.
        if (self.date_started is not None and self.date_finished is None
            and status not in (
                BuildStatus.NEEDSBUILD, BuildStatus.BUILDING,
                BuildStatus.CANCELLING)):
            # XXX cprov 20060615 bug=120584: Currently buildduration includes
            # the scanner latency, it should really be asking the slave for
            # the duration spent building locally.
            self.build_farm_job.date_finished = self.date_finished = (
                date_finished or datetime.datetime.now(pytz.UTC))

    def gotFailure(self):
        """See `IBuildFarmJob`."""
        self.failure_count += 1


class BuildFarmJobSet:
    implements(IBuildFarmJobSet)

    def getBuildsForBuilder(self, builder_id, status=None, user=None):
        """See `IBuildFarmJobSet`."""
        # Imported here to avoid circular imports.
        from lp.soyuz.model.archive import (
            Archive, get_archive_privacy_filter)

        clauses = [
            BuildFarmJob.builder == builder_id,
            Or(Archive.id == None, get_archive_privacy_filter(user))]
        if status is not None:
            clauses.append(BuildFarmJob.status == status)

        # We need to ensure that we don't include any private builds.
        # Currently only package builds can be private (via their
        # related archive), but not all build farm jobs will have a
        # related package build - hence the left join.
        origin = [
            BuildFarmJob,
            LeftJoin(Archive, Archive.id == BuildFarmJob.archive_id),
            ]

        return IStore(BuildFarmJob).using(*origin).find(
            BuildFarmJob, *clauses).order_by(
                Desc(BuildFarmJob.date_finished), BuildFarmJob.id)

    def getBuildsForArchive(self, archive, status=None):
        """See `IBuildFarmJobSet`."""

        extra_exprs = []

        if status is not None:
            extra_exprs.append(BuildFarmJob.status == status)

        result_set = IStore(BuildFarmJob).find(
            BuildFarmJob, BuildFarmJob.archive == archive, *extra_exprs)

        # When we have a set of builds that may include pending or
        # superseded builds, we order by -date_created (as we won't
        # always have a date_finished). Otherwise we can order by
        # -date_finished.
        unfinished_states = [
            BuildStatus.NEEDSBUILD,
            BuildStatus.BUILDING,
            BuildStatus.UPLOADING,
            BuildStatus.SUPERSEDED,
            ]
        if status is None or status in unfinished_states:
            result_set.order_by(
                Desc(BuildFarmJob.date_created), BuildFarmJob.id)
        else:
            result_set.order_by(
                Desc(BuildFarmJob.date_finished), BuildFarmJob.id)

        return result_set
