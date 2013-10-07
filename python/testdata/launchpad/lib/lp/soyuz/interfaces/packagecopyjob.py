# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "IPackageCopyJob",
    "IPackageCopyJobEdit",
    "IPackageCopyJobSource",
    "IPlainPackageCopyJob",
    "IPlainPackageCopyJobSource",
    "PackageCopyJobType",
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.services.job.interfaces.job import (
    IJob,
    IJobSource,
    IRunnableJob,
    )
from lp.soyuz.enums import PackageCopyPolicy
from lp.soyuz.interfaces.archive import IArchive


class IPackageCopyJobSource(Interface):
    """Utility for `IPackageCopyJob`-implementing types."""

    def wrap(package_copy_job):
        """Wrap a `PackageCopyJob` in its concrete implementation type.

        As a special case, `None` produces `None`.

        :param package_copy_job: A `PackageCopyJob`.
        :return: An `IPackageCopyJob` implementation based on
            `package_copy_job`, but of the job's specific concrete type
            (such as `PlainPackageCopyJob`).
        """


class IPackageCopyJobEdit(Interface):
    """Privileged access to an `IPackageCopyJob`."""

    def extendMetadata(metadata_dict):
        """Update the job's JSON metadata with items from `metadata_dict`."""


class IPackageCopyJobPublic(Interface):
    """The immutable data on an `IPackageCopyJob`, for normal use."""

    id = Int(
        title=_('DB ID'), required=True, readonly=True,
        description=_("The tracking number for this job."))

    source_archive_id = Int(
        title=_('Source Archive ID'),
        required=True, readonly=True)

    source_archive = Reference(
        schema=IArchive, title=_('Source Archive'),
        required=True, readonly=True)

    target_archive_id = Int(
        title=_('Target Archive ID'),
        required=True, readonly=True)

    target_archive = Reference(
        schema=IArchive, title=_('Target Archive'),
        required=True, readonly=True)

    target_distroseries = Reference(
        schema=IDistroSeries, title=_('Target DistroSeries.'),
        required=True, readonly=True)

    package_name = TextLine(
        title=_("Package name"), required=True, readonly=True)

    package_version = TextLine(
        title=_("Package version"), required=True, readonly=True)

    job = Reference(
        schema=IJob, title=_('The common Job attributes'),
        required=True, readonly=True)

    component_name = TextLine(
        title=_("Component override name"), required=False, readonly=True)

    section_name = TextLine(
        title=_("Section override name"), required=False, readonly=True)

    metadata = Attribute(_("A dict of data about the job."))


class IPackageCopyJob(IPackageCopyJobPublic, IPackageCopyJobEdit):
    """An `IJob` representing a copy of packages between places."""


class PackageCopyJobType(DBEnumeratedType):

    PLAIN = DBItem(1, """
        Copy packages between archives.

        This job copies one or more packages, optionally including binaries.
        """)


class IPlainPackageCopyJobSource(IJobSource):
    """An interface for acquiring `IPackageCopyJobs`."""

    def create(package_name, source_archive,
               target_archive, target_distroseries, target_pocket,
               include_binaries=False, package_version=None,
               copy_policy=PackageCopyPolicy.INSECURE, requester=None,
               sponsored=None, unembargo=False, auto_approve=False,
               source_distroseries=None, source_pocket=None,
               phased_update_percentage=None):
        """Create a new `IPlainPackageCopyJob`.

        :param package_name: The name of the source package to copy.
        :param source_archive: The `IArchive` in which `source_packages` are
            found.
        :param target_archive: The `IArchive` to which to copy the packages.
        :param target_distroseries: The `IDistroSeries` to which to copy the
            packages.
        :param target_pocket: The pocket into which to copy the packages. Must
            be a member of `PackagePublishingPocket`.
        :param include_binaries: See `do_copy`.
        :param package_version: The version string for the package version
            that is to be copied.
        :param copy_policy: Applicable `PackageCopyPolicy`.
        :param requester: The user requesting the copy.
        :param sponsored: The user who is being sponsored to make the copy.
            The person who is making this request then becomes the sponsor.
        :param unembargo: See `do_copy`.
        :param auto_approve: if True and the user requesting the sync has
            queue admin permissions on the target, accept the copy
            immediately rather than setting it to unapproved.
        :param source_distroseries: The `IDistroSeries` from which to copy
            the packages. If omitted, copy from any series with a matching
            version.
        :param source_pocket: The pocket from which to copy the packages.
            Must be a member of `PackagePublishingPocket`. If omitted, copy
            from any pocket with a matching version.
        :param phased_update_percentage: The phased update percentage to
            apply to the copied publication.
        """

    def createMultiple(target_distroseries, copy_tasks, requester,
                       copy_policy=PackageCopyPolicy.INSECURE,
                       include_binaries=False, unembargo=False,
                       auto_approve=False):
        """Create multiple new `IPlainPackageCopyJob`s at once.

        :param target_distroseries: The `IDistroSeries` to which to copy the
            packages.
        :param copy_tasks: A list of tuples describing the copies to be
            performed: (package name, package version, source archive,
            target archive, target pocket).
        :param requester: The user requesting the copy.
        :param copy_policy: Applicable `PackageCopyPolicy`.
        :param include_binaries: As in `do_copy`.
        :param unembargo: As in `do_copy`.
        :return: An iterable of `PackageCopyJob` ids.
        :param auto_approve: if True and the user requesting the sync has
            queue admin permissions on the target, accept the copy
            immediately rather than setting it to unapproved.
        """

    def getActiveJobs(target_archive):
        """Retrieve all active sync jobs for an archive."""

    def getPendingJobsPerPackage(target_series):
        """Find pending jobs for each package in `target_series`.

        This is meant for finding jobs that will resolve specific
        `DistroSeriesDifference`s.

        :param target_series: Target `DistroSeries`; this corresponds to
            `DistroSeriesDifference.derived_series`.
        :return: A dict containing as keys the (name, version) tuples for
            each `DistroSeriesDifference` that has a resolving
            `PlainPackageCopyJob` pending.  Each of these DSDs maps to its
            oldest pending job.  The `version` corresponds to
            `DistroSeriesDifference.parent_source_version`.
        """

    def getIncompleteJobsForArchive(archive):
        """Find incomplete jobs for each package in `archive`.

        Incomplete jobs are ones in status WAITING, RUNNING or FAILED.

        :param archive: The target `IArchive` for the job.
        :return: An iterable of `PackageCopyJob`.
        """


class IPlainPackageCopyJob(IRunnableJob):
    """A no-frills job to copy packages between `IArchive`s."""

    target_pocket = Int(
        title=_("Target package publishing pocket"), required=True,
        readonly=True)

    error_message = Int(
        title=_("Error message"), required=True, readonly=True)

    include_binaries = Bool(
        title=_("Copy binaries"),
        required=False, readonly=True)

    sponsored = Reference(
        schema=IPerson, title=_('Sponsored Person'),
        required=False, readonly=True)

    unembargo = Bool(
        title=_("Unembargo restricted files"),
        required=False, readonly=True)

    auto_approve = Bool(
        title=_("Automatic approval"),
        required=False, readonly=True)

    source_distroseries = Reference(
        schema=IDistroSeries, title=_('Source DistroSeries.'),
        required=False, readonly=True)

    source_pocket = Int(
        title=_("Source package publishing pocket"), required=False,
        readonly=True)

    phased_update_percentage = Int(
        title=_("Phased update percentage"), required=False, readonly=True)

    def addSourceOverride(override):
        """Add an `ISourceOverride` to the metadata."""

    def setErrorMessage(message):
        """Set the error message."""

    def getSourceOverride():
        """Get an `ISourceOverride` from the metadata."""

    def findSourcePublication():
        """Find the appropriate origin `ISourcePackagePublishingHistory`."""

    copy_policy = Choice(
        title=_("Applicable copy policy"),
        values=PackageCopyPolicy, required=True, readonly=True)

    def getOperationDescription():
        """Return a description of the copy operation."""

    def getErrorRecipients():
        """Return a list of email-ids to notify about copy errors."""
