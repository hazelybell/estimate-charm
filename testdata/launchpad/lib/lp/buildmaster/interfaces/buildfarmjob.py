# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for Soyuz build farm jobs."""

__metaclass__ = type

__all__ = [
    'IBuildFarmJob',
    'IBuildFarmJobOld',
    'IBuildFarmJobSet',
    'IBuildFarmJobSource',
    'InconsistentBuildFarmJobError',
    'ISpecificBuildFarmJobSource',
    ]

from lazr.enum import DBEnumeratedType
from lazr.restful.declarations import exported
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    TextLine,
    Timedelta,
    )

from lp import _
from lp.buildmaster.enums import BuildFarmJobType
from lp.buildmaster.interfaces.builder import IBuilder
from lp.services.librarian.interfaces import ILibraryFileAlias
from lp.soyuz.interfaces.processor import IProcessor


class InconsistentBuildFarmJobError(Exception):
    """Raised when a BuildFarmJob is in an inconsistent state.

    For example, if a BuildFarmJob has a job type for which no adapter
    is yet implemented. Or when adapting the BuildFarmJob to a specific
    type of build job (such as a BinaryPackageBuild) fails.
    """


class IBuildFarmJobOld(Interface):
    """Defines the previous non-database BuildFarmJob interface.

    This interface is still used by the temporary build queue related
    classes (TranslationTemplatesBuildJob, SourcePackageRecipeBuildJob
    and BuildPackageJob).

    XXX 2010-04-28 michael.nelson bug=567922
    This class can be removed (merging all the attributes directly into
    IBuildFarmJob) once all the corresponding *Build classes and the
    BuildQueue have been transitioned to the new database schema.
    """

    processor = Reference(
        IProcessor, title=_("Processor"), required=False, readonly=True,
        description=_(
            "The Processor required by this build farm job. "
            "This should be None for processor-independent job types."))

    virtualized = Bool(
        title=_('Virtualized'), required=False, readonly=True,
        description=_(
            "The virtualization setting required by this build farm job. "
            "This should be None for job types that do not care whether "
            "they run virtualized."))

    def score():
        """Calculate a job score appropriate for the job type in question."""

    def jobStarted():
        """'Job started' life cycle event, handle as appropriate."""

    def jobReset():
        """'Job reset' life cycle event, handle as appropriate."""

    def jobCancel():
        """'Job cancel' life cycle event."""

    def addCandidateSelectionCriteria(processor, virtualized):
        """Provide a sub-query to refine the candidate job selection.

        Return a sub-query to narrow down the list of candidate jobs.
        The sub-query will become part of an "outer query" and is free to
        refer to the `BuildQueue` and `Job` tables already utilized in the
        latter.

        Example (please see the `BuildPackageJob` implementation for a
        complete example):

            SELECT TRUE
            FROM Archive, Build, BuildPackageJob, DistroArchSeries
            WHERE
            BuildPackageJob.job = Job.id AND
            ..

        :param processor: the type of processor that the candidate jobs are
            expected to run on.
        :param virtualized: whether the candidate jobs are expected to run on
            the `processor` natively or inside a virtual machine.
        :return: a string containing a sub-query that narrows down the list of
            candidate jobs.
        """

    def postprocessCandidate(job, logger):
        """True if the candidate job is fine and should be dispatched
        to a builder, False otherwise.

        :param job: The `BuildQueue` instance to be scrutinized.
        :param logger: The logger to use.

        :return: True if the candidate job should be dispatched
            to a builder, False otherwise.
        """

    def getByJob(job):
        """Get the specific `IBuildFarmJob` for the given `Job`.

        Invoked on the specific `IBuildFarmJob`-implementing class that
        has an entry associated with `job`.
        """

    def getByJobs(jobs):
        """Get the specific `IBuildFarmJob`s for the given `Job`s.

        Invoked on the specific `IBuildFarmJob`-implementing class that
        has entries associated with `job`s.
        """

    def cleanUp():
        """Job's finished.  Delete its supporting data."""


class IBuildFarmJobDB(Interface):
    """Operations on a `BuildFarmJob` DB row.

    This is deprecated while it's flattened into the concrete implementations.
    """

    id = Attribute('The build farm job ID.')

    job_type = Choice(
        title=_("Job type"), required=True, readonly=True,
        vocabulary=BuildFarmJobType,
        description=_("The specific type of job."))


class IBuildFarmJob(Interface):
    """Operations that jobs for the build farm must implement."""

    id = Attribute('The build farm job ID.')

    build_farm_job = Attribute('Generic build farm job record')

    processor = Reference(
        IProcessor, title=_("Processor"), required=False, readonly=True,
        description=_(
            "The Processor required by this build farm job. "
            "This should be None for processor-independent job types."))

    virtualized = Bool(
        title=_('Virtualized'), required=False, readonly=True,
        description=_(
            "The virtualization setting required by this build farm job. "
            "This should be None for job types that do not care whether "
            "they run virtualized."))

    date_created = exported(
        Datetime(
            title=_("Date created"), required=True, readonly=True,
            description=_(
                "The timestamp when the build farm job was created.")),
        ("1.0", dict(exported_as="datecreated")),
        as_of="beta",
        )

    date_started = exported(
        Datetime(
            title=_("Date started"), required=False, readonly=True,
            description=_(
                "The timestamp when the build farm job was started.")),
        as_of="devel")

    date_finished = exported(
        Datetime(
            title=_("Date finished"), required=False, readonly=True,
            description=_(
                "The timestamp when the build farm job was finished.")),
        ("1.0", dict(exported_as="datebuilt")),
        as_of="beta",
        )

    duration = exported(
        Timedelta(
            title=_("Duration"), required=False, readonly=True,
            description=_("Duration interval, calculated when the "
                          "result gets collected.")),
        as_of="devel")

    date_first_dispatched = exported(
        Datetime(
            title=_("Date finished"), required=False, readonly=True,
            description=_("The actual build start time. Set when the build "
                          "is dispatched the first time and not changed in "
                          "subsequent build attempts.")))

    builder = exported(
        Reference(
            title=_("Builder"), schema=IBuilder, required=False, readonly=True,
            description=_("The builder assigned to this job.")))

    buildqueue_record = Reference(
        # Really IBuildQueue, set in _schema_circular_imports to avoid
        # circular import.
        schema=Interface, required=True,
        title=_("Corresponding BuildQueue record"))

    status = exported(
        Choice(
            title=_('Status'), required=True,
            # Really BuildStatus, patched in
            # _schema_circular_imports.py
            vocabulary=DBEnumeratedType,
            description=_("The current status of the job.")),
        ("1.0", dict(exported_as="buildstate")),
        as_of="beta",
        )

    log = Reference(
        schema=ILibraryFileAlias, required=False,
        title=_(
            "The LibraryFileAlias containing the entire log for this job."))

    log_url = exported(
        TextLine(
            title=_("Build Log URL"), required=False,
            description=_("A URL for the build log. None if there is no "
                          "log available.")),
        ("1.0", dict(exported_as="build_log_url")),
        as_of="beta",
        )

    is_private = Bool(
        title=_("is private"), required=False, readonly=True,
        description=_("Whether the build should be treated as private."))

    job_type = Choice(
        title=_("Job type"), required=True, readonly=True,
        vocabulary=BuildFarmJobType,
        description=_("The specific type of job."))

    failure_count = Int(
        title=_("Failure Count"), required=False, readonly=True,
        default=0,
        description=_("Number of consecutive failures for this job."))

    def makeJob():
        """Create the specific job relating this with an lp.services.job.

        XXX 2010-04-26 michael.nelson bug=567922
        Once all *Build classes are using BuildFarmJob we can lose the
        'specific_job' attributes and simply have a reference to the
        services job directly on the BuildFarmJob.
        """

    def setLog(log):
        """Set the `LibraryFileAlias` that contains the job log."""

    def updateStatus(status, builder=None, slave_status=None,
                     date_started=None, date_finished=None):
        """Update job metadata when the build status changes.

        This automatically handles setting status, date_finished, builder,
        dependencies. Later it will manage the denormalised search schema.

        date_started and date_finished override the default (now).
        """

    def gotFailure():
        """Increment the failure_count for this job."""

    title = exported(TextLine(title=_("Title"), required=False),
                     as_of="beta")

    was_built = Attribute("Whether or not modified by the builddfarm.")

    # This doesn't belong here.  It really belongs in IPackageBuild, but
    # the TAL assumes it can read this directly.
    dependencies = exported(
        TextLine(
            title=_('Dependencies'), required=False,
            description=_(
                'Debian-like dependency line that must be satisfied before '
                'attempting to build this request.')),
        as_of="beta")


class ISpecificBuildFarmJobSource(Interface):
    """A utility for retrieving objects of a specific IBuildFarmJob type.

    Implementations are registered with their BuildFarmJobType's name.
    """

    def getByID(id):
        """Look up a concrete `IBuildFarmJob` by ID.

        :param id: An ID of the concrete job class to look up.
        """

    def getByBuildFarmJobs(build_farm_jobs):
        """"Look up the concrete `IBuildFarmJob`s for a list of BuildFarmJobs.

        :param build_farm_jobs: A list of BuildFarmJobs for which to get the
            concrete jobs.
        """

    def getByBuildFarmJob(build_farm_job):
        """"Look up the concrete `IBuildFarmJob` for a BuildFarmJob.

        :param build_farm_job: A BuildFarmJob for which to get the concrete
            job.
        """


class IBuildFarmJobSource(Interface):
    """A utility of BuildFarmJob used to create _things_."""

    def new(job_type, status=None, processor=None, virtualized=None,
            builder=None):
        """Create a new `IBuildFarmJob`.

        :param job_type: A `BuildFarmJobType` item.
        :param status: A `BuildStatus` item, defaulting to PENDING.
        :param processor: An optional processor for this job.
        :param virtualized: An optional boolean indicating whether
            this job should be run virtualized.
        :param builder: An optional `IBuilder`.
        """


class IBuildFarmJobSet(Interface):
    """A utility representing a set of build farm jobs."""

    def getBuildsForBuilder(builder_id, status=None, user=None):
        """Return `IBuildFarmJob` records touched by a builder.

        :param builder_id: The id of the builder for which to find builds.
        :param status: If given, limit the search to builds with this status.
        :param user: If given, this will be used to determine private builds
            that should be included.
        :return: a `ResultSet` representing the requested builds.
        """

    def getBuildsForArchive(archive, status=None):
        """Return `IBuildFarmJob` records targeted to a given `IArchive`.

        :param archive: The archive for which builds will be returned.
        :param status: If status is provided, only builders with that
            status will be returned.
        :return: a `ResultSet` representing the requested `IBuildFarmJobs`.
        """
