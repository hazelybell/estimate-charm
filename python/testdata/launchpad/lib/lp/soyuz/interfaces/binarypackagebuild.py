# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BinaryPackageBuild interfaces."""

__metaclass__ = type

__all__ = [
    'BuildSetStatus',
    'CannotBeRescored',
    'IBinaryPackageBuild',
    'IBuildRescoreForm',
    'IBinaryPackageBuildSet',
    'UnparsableDependencies',
    ]

import httplib

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from lazr.restful.declarations import (
    error_status,
    export_as_webservice_entry,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.buildfarmjob import ISpecificBuildFarmJobSource
from lp.buildmaster.interfaces.packagebuild import IPackageBuild
from lp.soyuz.interfaces.processor import IProcessor
from lp.soyuz.interfaces.publishing import ISourcePackagePublishingHistory
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease


@error_status(httplib.BAD_REQUEST)
class CannotBeRescored(Exception):
    """Raised when rescoring a build that cannot be rescored."""
    _message_prefix = "Cannot rescore build"


class UnparsableDependencies(Exception):
    """Raised when parsing invalid dependencies on a binary package."""


class IBinaryPackageBuildView(IPackageBuild):
    """A Build interface for items requiring launchpad.View."""
    id = Int(title=_('ID'), required=True, readonly=True)

    # Overridden from IBuildFarmJob to ensure required is True.
    processor = Reference(
        title=_("Processor"), schema=IProcessor,
        required=True, readonly=True,
        description=_("The Processor where this build should be built."))

    source_package_release = Reference(
        title=_('Source'), schema=ISourcePackageRelease,
        required=True, readonly=True,
        description=_("The SourcePackageRelease requested to build."))

    source_package_release_id = Int()

    distro_arch_series = Reference(
        title=_("Architecture"),
        # Really IDistroArchSeries
        schema=Interface,
        required=True, readonly=True,
        description=_("The DistroArchSeries context for this build."))

    distro_arch_series_id = Int()

    # Properties
    current_source_publication = exported(
        Reference(
            title=_("Source publication"),
            schema=ISourcePackagePublishingHistory,
            required=False, readonly=True,
            description=_("The current source publication for this build.")))

    distro_series = Attribute("Direct parent needed by CanonicalURL")
    arch_tag = exported(
        Text(title=_("Architecture tag"), required=False))
    distributionsourcepackagerelease = Attribute("The page showing the "
        "details for this sourcepackagerelease in this distribution.")
    binarypackages = Attribute(
        "A list of binary packages that resulted from this build, "
        "not limited and ordered by name.")
    distroarchseriesbinarypackages = Attribute(
        "A list of distroarchseriesbinarypackages that resulted from this"
        "build, ordered by name.")

    can_be_rescored = exported(
        Bool(
            title=_("Can Be Rescored"), required=False, readonly=True,
            description=_(
                "Whether or not this build record can be rescored "
                "manually.")))

    can_be_retried = exported(
        Bool(
            title=_("Can Be Retried"), required=False, readonly=True,
            description=_(
                "Whether or not this build record can be retried.")))

    can_be_cancelled = exported(
        Bool(
            title=_("Can Be Cancelled"), required=False, readonly=True,
            description=_(
                "Whether or not this build record can be cancelled.")))

    is_virtualized = Attribute(
        "Whether or not this build requires a virtual build host or not.")

    upload_changesfile = Attribute(
        "The `LibraryFileAlias` object containing the changes file which "
        "was originally uploaded with the results of this build. It's "
        "'None' if it is build imported by Gina.")

    changesfile_url = exported(
        TextLine(
            title=_("Changes File URL"), required=False,
            description=_("The URL for the changes file for this build. "
                          "Will be None if the build was imported by Gina.")))

    package_upload = Attribute(
        "The `PackageUpload` record corresponding to the original upload "
        "of the binaries resulted from this build. It's 'None' if it is "
        "a build imported by Gina.")

    api_score = exported(
        Int(
            title=_("Score of the related job (if any)"),
            readonly=True,
            ),
        exported_as="score")

    def updateDependencies():
        """Update the build-dependencies line within the targeted context."""

    def __getitem__(name):
        """Mapped to getBinaryPackageRelease."""

    def getBinaryPackageRelease(name):
        """Return the binary package from this build with the given name, or
        raise NotFoundError if no such package exists.
        """

    def createBinaryPackageRelease(
        binarypackagename, version, summary, description, binpackageformat,
        component, section, priority, installedsize, architecturespecific,
        shlibdeps=None, depends=None, recommends=None, suggests=None,
        conflicts=None, replaces=None, provides=None, pre_depends=None,
        enhances=None, breaks=None, essential=False, debug_package=None,
        user_defined_fields=None, homepage=None):
        """Create and return a `BinaryPackageRelease`.

        The binarypackagerelease will be attached to this specific build.
        """

    def getFileByName(filename):
        """Return the corresponding `ILibraryFileAlias` in this context.

        The following file types (and extension) can be looked up in the
        archive context:

         * Binary changesfile: '.changes';
         * Build logs: '.txt.gz';
         * Build upload logs: '_log.txt';

        :param filename: exactly filename to be looked up.

        :raises AssertionError if the given filename contains a unsupported
            filename and/or extension, see the list above.
        :raises NotFoundError if no file could not be found.

        :return the corresponding `ILibraryFileAlias` if the file was found.
        """

    def getBinaryPackageFileByName(filename):
        """Return the corresponding `IBinaryPackageFile` in this context.

        :param filename: the filename to look up.
        :return: the corresponding `IBinaryPackageFile` if it was found.
        """

    def getBinaryPackageNamesForDisplay():
        """Retrieve the build's binary package names for display purposes.

        :return: a result set of
            (`IBinaryPackageRelease`, `IBinaryPackageName`) ordered by name
            and `IBinaryPackageRelease.id`.
        """

    def getBinaryFilesForDisplay():
        """Retrieve the build's `IBinaryPackageFile`s for display purposes.

        Also prefetches other related objects needed for display.

        :return: a result set of (`IBinaryPackageRelease`,
            `IBinaryPackageFile`, `ILibraryFileAlias`, `ILibraryFileContent`).
        """


class IBinaryPackageBuildEdit(Interface):
    """A Build interface for items requiring launchpad.Edit."""

    @export_write_operation()
    def retry():
        """Restore the build record to its initial state.

        Build record loses its history, is moved to NEEDSBUILD and a new
        non-scored BuildQueue entry is created for it.
        """

    @export_write_operation()
    @operation_for_version("devel")
    def cancel():
        """Cancel the build if it is either pending or in progress.

        Call the can_be_cancelled() method prior to this one to find out if
        cancelling the build is possible.

        If the build is in progress, it is marked as CANCELLING until the
        buildd manager terminates the build and marks it CANCELLED. If the
        build is not in progress, it is marked CANCELLED immediately and is
        removed from the build queue.

        If the build is not in a cancellable state, this method is a no-op.
        """


class IBinaryPackageBuildAdmin(Interface):
    """A Build interface for items requiring launchpad.Admin."""

    @operation_parameters(score=Int(title=_("Score"), required=True))
    @export_write_operation()
    def rescore(score):
        """Change the build's score."""


class IBinaryPackageBuild(
    IBinaryPackageBuildView, IBinaryPackageBuildEdit,
    IBinaryPackageBuildAdmin):
    """A Build interface"""
    export_as_webservice_entry(singular_name='build', plural_name='builds')


class BuildSetStatus(EnumeratedType):
    """`IBuildSet` status type

    Builds exist in the database in a number of states such as 'complete',
    'needs build' and 'dependency wait'. We sometimes provide a summary
    status of a set of builds.
    """
    # Until access to the name, title and description of exported types
    # is available through the API, set the title of these statuses
    # to match the name. This enables the result of API calls (which is
    # currently the title) to be used programatically (for example, as a
    # css class name).
    NEEDSBUILD = Item(
        title='NEEDSBUILD',  # "Need building",
        description='There are some builds waiting to be built.')

    FULLYBUILT_PENDING = Item(
        title='FULLYBUILT_PENDING',
        description="All builds were built successfully but have not yet "
                    "been published.")

    FULLYBUILT = Item(title='FULLYBUILT',  # "Successfully built",
                      description="All builds were built successfully.")

    FAILEDTOBUILD = Item(title='FAILEDTOBUILD',  # "Failed to build",
                         description="There were build failures.")

    BUILDING = Item(title='BUILDING',  # "Currently building",
                    description="There are some builds currently building.")


class IBinaryPackageBuildSet(ISpecificBuildFarmJobSource):
    """Interface for BinaryPackageBuildSet"""

    def new(distro_arch_series, source_package_release, processor,
            archive, pocket, status=BuildStatus.NEEDSBUILD,
            date_created=None, builder=None):
        """Create a new `IBinaryPackageBuild`.

        :param distro_arch_series: An `IDistroArchSeries`.
        :param source_package_release: An `ISourcePackageRelease`.
        :param processor: An `IProcessor`.
        :param archive: An `IArchive` in which context the build is built.
        :param pocket: An item of `PackagePublishingPocket`.
        :param status: A `BuildStatus` item indicating the builds status.
        :param date_created: An optional datetime to ensure multiple builds
            in the same transaction don't all get the same UTC_NOW.
        :param builder: An optional `IBuilder`.
        """

    def getBuildsForBuilder(builder_id, status=None, name=None,
                            arch_tag=None):
        """Return build records touched by a builder.

        :param builder_id: The id of the builder for which to find builds.
        :param status: If status is provided, only builds with that status
            will be returned.
        :param name: If name is provided, only builds which correspond to a
            matching sourcepackagename will be returned (SQL LIKE).
        :param arch_tag: If arch_tag is provided, only builds for that
            architecture will be returned.
        :return: a `ResultSet` representing the requested builds.
        """

    def getBuildsForArchive(archive, status=None, name=None, pocket=None,
                            arch_tag=None):
        """Return build records targeted to a given IArchive.

        :param archive: The archive for which builds will be returned.
        :param status: If status is provided, only builders with that
            status will be returned.
        :param name: If name is passed, return only build which the
            sourcepackagename matches (SQL LIKE).
        :param pocket: If pocket is provided only builds for that pocket
            will be returned.
        :param arch_tag: If arch_tag is provided, only builds for that
            architecture will be returned.
        :return: a `ResultSet` representing the requested builds.
        """

    def getBuildsForDistro(context, status=None, name=None, pocket=None,
                           arch_tag=None):
        """Retrieve `IBinaryPackageBuild`s for a given Distribution/DS/DAS.

        Optionally, for a given status and/or pocket, if ommited return all
        records. If name is passed return only the builds which the
        sourcepackagename matches (SQL LIKE).
        """

    def getBuildsBySourcePackageRelease(sourcepackagerelease_ids,
                                        buildstate=None):
        """Return all builds related with the given list of source releases.

        Eager loads the PackageBuild and BuildFarmJob records for the builds.

        :param sourcepackagerelease_ids: list of `ISourcePackageRelease`s;
        :param buildstate: option build state filter.

        :return: a list of `IBuild` records not target to PPA archives.
        """

    def getStatusSummaryForBuilds(builds):
        """Return a summary of the build status for the given builds.

        The returned summary includes a status, a description of
        that status and the builds related to the status.

        :param builds: A list of build records.
        :type builds: ``list``
        :return: A dict consisting of the build status summary for the
            given builds. For example:
                {
                    'status': BuildSetStatus.FULLYBUILT,
                    'builds': [build1, build2]
                }
            or, an example where there are currently some builds building:
                {
                    'status': BuildSetStatus.BUILDING,
                    'builds':[build3]
                }
        :rtype: ``dict``.
        """

    def getByQueueEntry(queue_entry):
        """Return an IBuild instance for the given build queue entry.

        Retrieve the only one possible build record associated with the given
        build queue entry. If not found, return None.
        """

    def getQueueEntriesForBuildIDs(build_ids):
        """Return the IBuildQueue instances for the IBuild IDs at hand.

        Retrieve the build queue and related builder rows associated with the
        builds in question where they exist.
        """

    def preloadBuildsData(builds):
        """Prefetch the data related to the builds.

        """


class IBuildRescoreForm(Interface):
    """Form for rescoring a build."""

    priority = Int(
        title=_("Priority"), required=True, min=-2 ** 31, max=2 ** 31,
        description=_("Build priority, the build with the highest value will "
                      "be dispatched first."))
