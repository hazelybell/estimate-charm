# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Publishing interfaces."""

__metaclass__ = type

__all__ = [
    'DeletionError',
    'IArchiveSafePublisher',
    'IBinaryPackageFilePublishing',
    'IBinaryPackagePublishingHistory',
    'IBinaryPackagePublishingHistoryEdit',
    'IBinaryPackagePublishingHistoryPublic',
    'ICanPublishPackages',
    'IFilePublishing',
    'IPublishingEdit',
    'IPublishingSet',
    'ISourcePackageFilePublishing',
    'ISourcePackagePublishingHistory',
    'ISourcePackagePublishingHistoryEdit',
    'ISourcePackagePublishingHistoryPublic',
    'MissingSymlinkInPool',
    'NotInPool',
    'OverrideError',
    'PoolFileOverwriteError',
    'active_publishing_status',
    'inactive_publishing_status',
    'name_priority_map',
    ]

import httplib

from lazr.restful.declarations import (
    call_with,
    error_status,
    export_as_webservice_entry,
    export_operation_as,
    export_read_operation,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Date,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.enums import (
    PackagePublishingPriority,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.binarypackagerelease import (
    IBinaryPackageReleaseDownloadCount,
    )

#
# Exceptions
#


class NotInPool(Exception):
    """Raised when an attempt is made to remove a non-existent file."""


class PoolFileOverwriteError(Exception):
    """Raised when an attempt is made to overwrite a file in the pool.

    The proposed file has different content as the one in pool.
    This exception is unexpected and when it happens we keep the original
    file in pool and print a warning in the publisher log. It probably
    requires manual intervention in the archive.
    """


class MissingSymlinkInPool(Exception):
    """Raised when there is a missing symlink in pool.

    This condition is ignored, similarly to what we do for `NotInPool`,
    since the pool entry requested to be removed is not there anymore.

    The corresponding record is marked as removed and the process
    continues.
    """


@error_status(httplib.BAD_REQUEST)
class OverrideError(Exception):
    """Raised when an attempt to change an override fails."""


@error_status(httplib.BAD_REQUEST)
class DeletionError(Exception):
    """Raised when an attempt to delete a publication fails."""


name_priority_map = {
    'required': PackagePublishingPriority.REQUIRED,
    'important': PackagePublishingPriority.IMPORTANT,
    'standard': PackagePublishingPriority.STANDARD,
    'optional': PackagePublishingPriority.OPTIONAL,
    'extra': PackagePublishingPriority.EXTRA,
    '': None,
    }


#
# Base Interfaces
#


class ICanPublishPackages(Interface):
    """Denotes the ability to publish associated publishing records."""

    def getPendingPublications(archive, pocket, is_careful):
        """Return the specific group of records to be published.

        IDistroSeries -> ISourcePackagePublishing
        IDistroArchSeries -> IBinaryPackagePublishing

        'pocket' & 'archive' are mandatory arguments, they  restrict the
        results to the given value.

        If the distroseries is already released, it automatically refuses
        to publish records to RELEASE pocket.
        """

    def publish(diskpool, log, archive, pocket, careful=False):
        """Publish associated publishing records targeted for a given pocket.

        Require an initialized diskpool instance and a logger instance.
        Require an 'archive' which will restrict the publications.
        'careful' argument would cause the 'republication' of all published
        records if True (system will DTRT checking hash of all
        published files.)

        Consider records returned by the local implementation of
        getPendingPublications.
        """


class IArchiveSafePublisher(Interface):
    """Safe Publication methods"""

    def setPublished():
        """Set a publishing record to published.

        Basically set records to PUBLISHED status only when they
        are PENDING and do not update datepublished value of already
        published field when they were checked via 'careful'
        publishing.
        """


class IPublishingView(Interface):
    """Base interface for all Publishing classes"""

    files = Attribute("Files included in this publication.")
    displayname = exported(
        TextLine(
            title=_("Display Name"),
            description=_("Text representation of the current record.")),
        exported_as="display_name")
    age = Attribute("Age of the publishing record.")

    component_name = exported(
        TextLine(
            title=_("Component Name"),
            required=False, readonly=True))
    section_name = exported(
        TextLine(
            title=_("Section Name"),
            required=False, readonly=True))

    def publish(diskpool, log):
        """Publish or ensure contents of this publish record

        Skip records which attempt to overwrite the archive (same file paths
        with different content) and do not update the database.

        If all the files get published correctly update its status properly.
        """

    def getIndexStanza():
        """Return archive index stanza contents

        It's based on the locally provided buildIndexStanzaTemplate method,
        which differs for binary and source instances.
        """

    def buildIndexStanzaFields():
        """Build a map of fields and values to be in the Index file.

        The fields and values ae mapped into a dictionary, where the key is
        the field name and value is the value string.
        """

    def requestObsolescence():
        """Make this publication obsolete.

        :return: The obsoleted publishing record, either:
            `ISourcePackagePublishingHistory` or
            `IBinaryPackagePublishingHistory`.
        """


class IPublishingEdit(Interface):
    """Base interface for writeable Publishing classes."""

    def requestDeletion(removed_by, removal_comment=None):
        """Delete this publication.

        :param removed_by: `IPerson` responsible for the removal.
        :param removal_comment: optional text describing the removal reason.
        """

    @call_with(removed_by=REQUEST_USER)
    @operation_parameters(
        removal_comment=TextLine(title=_("Removal comment"), required=False))
    @export_operation_as("requestDeletion")
    @export_write_operation()
    def api_requestDeletion(removed_by, removal_comment=None):
        """Delete this source and its binaries.

        :param removed_by: `IPerson` responsible for the removal.
        :param removal_comment: optional text describing the removal reason.
        """
        # This is a special API method that allows a different code path
        # to the regular requestDeletion().  In the case of sources
        # getting deleted, it ensures source and binaries are both
        # deleted in tandem.


class IFilePublishing(Interface):
    """Base interface for *FilePublishing classes"""

    distribution = Int(
            title=_('Distribution ID'), required=True, readonly=True,
            )
    distroseriesname = TextLine(
            title=_('Series name'), required=True, readonly=True,
            )
    componentname = TextLine(
            title=_('Component name'), required=True, readonly=True,
            )
    publishingstatus = Int(
            title=_('Package publishing status'), required=True, readonly=True,
            )
    pocket = Int(
            title=_('Package publishing pocket'), required=True, readonly=True,
            )
    archive = Int(
            title=_('Archive ID'), required=True, readonly=True,
            )
    libraryfilealias = Int(
            title=_('Binarypackage file alias'), required=True, readonly=True,
            )
    libraryfilealiasfilename = TextLine(
            title=_('File name'), required=True, readonly=True,
            )
    archive_url = Attribute('The on-archive URL for the published file.')

    publishing_record = Attribute(
        "Return the Source or Binary publishing record "
        "(in the form of I{Source,Binary}PackagePublishingHistory).")

    def publish(diskpool, log):
        """Publish or ensure contents of this file in the archive.

        Create symbolic link to files already present in different component
        or add file from librarian if it's not present. Update the database
        to represent the current archive state.
        """

#
# Source package publishing
#


class ISourcePackageFilePublishing(IFilePublishing):
    """Source package release files and their publishing status"""
    file_type_name = Attribute(
        "The uploaded file's type; one of 'orig', 'dsc', 'diff' or 'other'")
    sourcepackagename = TextLine(
            title=_('Binary package name'), required=True, readonly=True,
            )
    sourcepackagepublishing = Int(
            title=_('Sourcepackage publishing record id'), required=True,
            readonly=True,
            )


class ISourcePackagePublishingHistoryPublic(IPublishingView):
    """A source package publishing history record."""
    id = Int(
            title=_('ID'), required=True, readonly=True,
            )
    sourcepackagenameID = Int(
        title=_('The DB id for the sourcepackagename.'),
        required=False, readonly=False)
    sourcepackagename = Attribute('The source package name being published')
    sourcepackagereleaseID = Int(
        title=_('The DB id for the sourcepackagerelease.'),
        required=False, readonly=False)
    sourcepackagerelease = Attribute(
        'The source package release being published')
    status = exported(
        Choice(
            title=_('Package Publishing Status'),
            description=_('The status of this publishing record'),
            vocabulary=PackagePublishingStatus,
            required=False, readonly=False,
            ))
    distroseriesID = Attribute("DB ID for distroseries.")
    distroseries = exported(
        Reference(
            IDistroSeries,
            title=_('The distro series being published into'),
            required=False, readonly=False,
            ),
        exported_as="distro_series")
    component = Int(
            title=_('The component being published into'),
            required=False, readonly=False,
            )
    sectionID = Attribute("DB ID for the section")
    section = Int(
            title=_('The section being published into'),
            required=False, readonly=False,
            )
    datepublished = exported(
        Datetime(
            title=_('The date on which this record was published'),
            required=False, readonly=False,
            ),
        exported_as="date_published")
    scheduleddeletiondate = exported(
        Datetime(
            title=_('The date on which this record is scheduled for '
                    'deletion'),
            required=False, readonly=False,
            ),
        exported_as="scheduled_deletion_date")
    pocket = exported(
        Choice(
            title=_('Pocket'),
            description=_('The pocket into which this entry is published'),
            vocabulary=PackagePublishingPocket,
            required=True, readonly=True,
            ))
    archive = exported(
        Reference(
            # Really IArchive (fixed in _schema_circular_imports.py).
            Interface,
            title=_('Archive ID'), required=True, readonly=True,
            ))
    supersededby = Int(
            title=_('The sourcepackagerelease which superseded this one'),
            required=False, readonly=False,
            )
    datesuperseded = exported(
        Datetime(
            title=_('The date on which this record was marked superseded'),
            required=False, readonly=False,
            ),
        exported_as="date_superseded")
    datecreated = exported(
        Datetime(
            title=_('The date on which this record was created'),
            required=True, readonly=False,
            ),
        exported_as="date_created")
    datemadepending = exported(
        Datetime(
            title=_('The date on which this record was set as pending '
                    'removal'),
            required=False, readonly=False,
            ),
        exported_as="date_made_pending")
    dateremoved = exported(
        Datetime(
            title=_('The date on which this record was removed from the '
                    'published set'),
            required=False, readonly=False,
            ),
        exported_as="date_removed")
    removed_byID = Attribute("DB ID for removed_by.")
    removed_by = exported(
        Reference(
            IPerson,
            title=_('The IPerson responsible for the removal'),
            required=False, readonly=False,
            ))
    removal_comment = exported(
        Text(
            title=_('Reason why this publication is going to be removed.'),
            required=False, readonly=False,
        ))

    meta_sourcepackage = Attribute(
        "Return an ISourcePackage meta object correspondent to the "
        "sourcepackagerelease attribute inside a specific distroseries")
    meta_sourcepackagerelease = Attribute(
        "Return an IDistributionSourcePackageRelease meta object "
        "correspondent to the sourcepackagerelease attribute")
    meta_supersededby = Attribute(
        "Return an IDistributionSourcePackageRelease meta object "
        "correspondent to the supersededby attribute. if supersededby "
        "is None return None.")
    meta_distroseriessourcepackagerelease = Attribute(
        "Return an IDistroSeriesSourcePackageRelease meta object "
        "correspondent to the sourcepackagerelease attribute inside "
        "a specific distroseries")

    source_package_name = exported(
        TextLine(
            title=_("Source Package Name"),
            required=False, readonly=True))
    source_package_version = exported(
        TextLine(
            title=_("Source Package Version"),
            required=False, readonly=True))

    package_creator = exported(
        Reference(
            IPerson,
            title=_('Package Creator'),
            description=_('The IPerson who created the source package.'),
            required=False, readonly=True,
        ))
    package_maintainer = exported(
        Reference(
            IPerson,
            title=_('Package Maintainer'),
            description=_('The IPerson who maintains the source package.'),
            required=False, readonly=True,
        ))
    package_signer = exported(
        Reference(
            IPerson,
            title=_('Package Signer'),
            description=_('The IPerson who signed the source package.'),
            required=False, readonly=True,
        ))

    newer_distroseries_version = Attribute(
        "An `IDistroSeriosSourcePackageRelease` with a newer version of this "
        "package that has been published in the main distribution series, "
        "if one exists, or None.")

    ancestor = Reference(
         # Really ISourcePackagePublishingHistory (fixed in
         # _schema_circular_imports.py).
        Interface,
        title=_('Ancestor'),
        description=_('The previous release of this source package.'),
        required=False, readonly=True)

    creatorID = Attribute("DB ID for creator.")
    creator = exported(
        Reference(
            IPerson,
            title=_('Publication Creator'),
            description=_('The IPerson who created this publication.'),
            required=False, readonly=True
        ))

    sponsorID = Attribute("DB ID for sponsor.")
    sponsor = exported(
        Reference(
            IPerson,
            title=_('Publication sponsor'),
            description=_('The IPerson who sponsored the creation of '
                'this publication.'),
            required=False, readonly=True
        ))

    packageupload = exported(
        Reference(
            # Really IPackageUpload, fixed in _schema_circular_imports.
            Interface,
            title=_('Package upload'),
            description=_('The Package Upload that caused the creation of '
                'this publication.'),
            required=False, readonly=True
        ))

    # Really IBinaryPackagePublishingHistory, see below.
    @operation_returns_collection_of(Interface)
    @export_read_operation()
    def getPublishedBinaries():
        """Return all resulted `IBinaryPackagePublishingHistory`.

        Follow the build record and return every PUBLISHED or PENDING
        binary publishing record for any `DistroArchSeries` in this
        `DistroSeries` and in the same `IArchive` and Pocket, ordered
        by architecture tag.

        :return: a list with all corresponding publishing records.
        """

    def getBuiltBinaries():
        """Return all unique binary publications built by this source.

        Follow the build record and return every unique binary publishing
        record in the context `DistroSeries` and in the same `IArchive`
        and Pocket.

        There will be only one entry for architecture independent binary
        publications.

        :return: a list containing all unique
            `IBinaryPackagePublishingHistory`.
        """

    # Really IBuild (fixed in _schema_circular_imports.py)
    @operation_returns_collection_of(Interface)
    @export_read_operation()
    def getBuilds():
        """Return a list of `IBuild` objects in this publishing context.

        The builds are ordered by `DistroArchSeries.architecturetag`.

        :return: a list of `IBuilds`.
        """

    def getFileByName(name):
        """Return the file with the specified name.

        Only supports 'changelog' at present.
        """

    @export_read_operation()
    def changesFileUrl():
        """The .changes file URL for this source publication.

        :return: the .changes file URL for this source (a string).
        """

    @export_read_operation()
    @operation_for_version('devel')
    def changelogUrl():
        """The URL for this source package release's changelog.

        :return: the changelog file URL for this source (a string).
        """

    def getUnpublishedBuilds(build_states=None):
        """Return a resultset of `IBuild` objects in this context that are
        not published.

        Note that this is convenience glue for
        PublishingSet.getUnpublishedBuildsForSources - and that method should
        be considered authoritative.

        :param build_states: list of build states to which the result should
            be limited. Defaults to BuildStatus.FULLYBUILT if none are
            specified.
        :return: a result set of `IBuilds`.
        """

    def createMissingBuilds(architectures_available=None, logger=None):
        """Create missing Build records for a published source.

        P-a-s should be used when accepting sources to the PRIMARY archive
        (in drescher). It explicitly ignores given P-a-s for sources
        targeted to PPAs.

        :param architectures_available: options list of `DistroArchSeries`
            that should be considered for build creation; if not given
            it will be calculated in place, all architectures for the
            context distroseries with available chroot.
        :param logger: optional context Logger object (used on DEBUG level).

        :return: a list of `Builds` created for this source publication.
        """

    def getSourceAndBinaryLibraryFiles():
        """Return a list of `LibraryFileAlias` for all source and binaries.

        All the source files and all binary files ever published to the
        same archive context are returned as a list of LibraryFileAlias
        records.

        :return: a list of `ILibraryFileAlias`.
        """

    def supersede(dominant=None, logger=None):
        """Supersede this publication.

        :param dominant: optional `ISourcePackagePublishingHistory` which is
            triggering the domination.
        :param logger: optional object to which debug information will be
            logged.
        """

    def copyTo(distroseries, pocket, archive, overrides=None, creator=None):
        """Copy this publication to another location.

        :param distroseries: The `IDistroSeries` to copy the source
            publication into.
        :param pocket: The `PackagePublishingPocket` to copy into.
        :param archive: The `IArchive` to copy the source publication into.
        :param overrides: A tuple of override data as returned from a
            `IOverridePolicy`.
        :param creator: the `IPerson` to use as the creator for the copied
            publication.
        :param packageupload: The `IPackageUpload` that caused this
            publication to be created.

        :return: a `ISourcePackagePublishingHistory` record representing the
            source in the destination location.
        """

    def getStatusSummaryForBuilds():
        """Return a summary of the build status for the related builds.

        This method augments IBuildSet.getBuildStatusSummaryForBuilds() by
        additionally checking to see if all the builds have been published
        before returning the fully-built status.

        :return: A dict consisting of the build status summary for the
            related builds. For example:
                {
                    'status': PackagePublishingStatus.PENDING,
                    'builds': [build1, build2]
                }
        """

    @export_read_operation()
    def sourceFileUrls():
        """URLs for this source publication's uploaded source files.

        :return: A collection of URLs for this source.
        """

    @export_read_operation()
    def binaryFileUrls():
        """URLs for this source publication's binary files.

        :return: A collection of URLs for this source.
        """

    @export_read_operation()
    @operation_parameters(
        to_version=TextLine(title=_("To Version"), required=True))
    def packageDiffUrl(to_version):
        """URL of the debdiff file between this and the supplied version.

        :param to_version: The version of the source package for which you
            want to get the diff to.
        :return: A URL to the librarian file containing the diff.
        """


class ISourcePackagePublishingHistoryEdit(IPublishingEdit):
    """A writeable source package publishing history record."""

    # Really ISourcePackagePublishingHistory, patched in
    # _schema_circular_imports.py.
    @operation_returns_entry(Interface)
    @operation_parameters(
        new_component=TextLine(title=u"The new component name."),
        new_section=TextLine(title=u"The new section name."))
    @export_write_operation()
    @operation_for_version("devel")
    def changeOverride(new_component=None, new_section=None):
        """Change the component and/or section of this publication.

        It is changed only if the argument is not None.

        Return the overridden publishing record, a
        `ISourcePackagePublishingHistory`.
        """


class ISourcePackagePublishingHistory(ISourcePackagePublishingHistoryPublic,
                                      ISourcePackagePublishingHistoryEdit):
    """A source package publishing history record."""
    export_as_webservice_entry(publish_web_link=False)


#
# Binary package publishing
#


class IBinaryPackageFilePublishing(IFilePublishing):
    """Binary package files and their publishing status"""
    # Note that it is really /source/ package name below, and not a
    # thinko; at least, that's what Celso tells me the code uses
    #   -- kiko, 2006-03-22
    sourcepackagename = TextLine(
            title=_('Source package name'), required=True, readonly=True,
            )
    binarypackagepublishing = Int(
            title=_('Binary Package publishing record id'), required=True,
            readonly=True,
            )


class IBinaryPackagePublishingHistoryPublic(IPublishingView):
    """A binary package publishing record."""

    id = Int(title=_('ID'), required=True, readonly=True)
    binarypackagenameID = Int(
        title=_('The DB id for the binarypackagename.'),
        required=False, readonly=False)
    binarypackagename = Attribute('The binary package name being published')
    binarypackagereleaseID = Int(
        title=_('The DB id for the binarypackagerelease.'),
        required=False, readonly=False)
    binarypackagerelease = Attribute(
        "The binary package release being published")
    distroarchseriesID = Int(
        title=_("The DB id for the distroarchseries."),
        required=False, readonly=False)
    distroarchseries = exported(
        Reference(
            # Really IDistroArchSeries (fixed in
            #_schema_circular_imports.py).
            Interface,
            title=_("Distro Arch Series"),
            description=_('The distroarchseries being published into'),
            required=False, readonly=False,
            ),
        exported_as="distro_arch_series")
    distroseries = Attribute("The distroseries being published into")
    component = Int(
            title=_('The component being published into'),
            required=False, readonly=False,
            )
    section = Int(
            title=_('The section being published into'),
            required=False, readonly=False,
            )
    priority = Int(
            title=_('The priority being published into'),
            required=False, readonly=False,
            )
    phased_update_percentage = exported(
        Int(
            title=_('The percentage of users for whom this package should be '
                    'recommended, or None to publish the update for everyone'),
            required=False, readonly=True,
            ))
    datepublished = exported(
        Datetime(
            title=_("Date Published"),
            description=_('The date on which this record was published'),
            required=False, readonly=False,
            ),
        exported_as="date_published")
    scheduleddeletiondate = exported(
        Datetime(
            title=_("Scheduled Deletion Date"),
            description=_('The date on which this record is scheduled for '
                    'deletion'),
            required=False, readonly=False,
            ),
        exported_as="scheduled_deletion_date")
    status = exported(
        Choice(
            title=_('Status'),
            description=_('The status of this publishing record'),
            vocabulary=PackagePublishingStatus,
            required=False, readonly=False,
            ))
    pocket = exported(
        Choice(
            title=_('Pocket'),
            description=_('The pocket into which this entry is published'),
            vocabulary=PackagePublishingPocket,
            required=True, readonly=True,
            ))
    supersededby = Int(
            title=_('The build which superseded this one'),
            required=False, readonly=False,
            )
    datecreated = exported(
        Datetime(
            title=_('Date Created'),
            description=_('The date on which this record was created'),
            required=True, readonly=False,
            ),
        exported_as="date_created")
    datesuperseded = exported(
        Datetime(
            title=_("Date Superseded"),
            description=_(
                'The date on which this record was marked superseded'),
            required=False, readonly=False,
            ),
        exported_as="date_superseded")
    datemadepending = exported(
        Datetime(
            title=_("Date Made Pending"),
            description=_(
                'The date on which this record was set as pending removal'),
            required=False, readonly=False,
            ),
        exported_as="date_made_pending")
    dateremoved = exported(
        Datetime(
            title=_("Date Removed"),
            description=_(
                'The date on which this record was removed from the '
                'published set'),
            required=False, readonly=False,
            ),
        exported_as="date_removed")
    archive = exported(
        Reference(
            # Really IArchive (fixed in _schema_circular_imports.py).
            Interface,
            title=_('Archive'),
            description=_("The context archive for this publication."),
            required=True, readonly=True,
            ))
    removed_by = exported(
        Reference(
            IPerson,
            title=_("Removed By"),
            description=_('The Person responsible for the removal'),
            required=False, readonly=False,
        ))
    removal_comment = exported(
        Text(
            title=_("Removal Comment"),
            description=_(
                'Reason why this publication is going to be removed.'),
            required=False, readonly=False))

    distroarchseriesbinarypackagerelease = Attribute("The object that "
        "represents this binarypackagerelease in this distroarchseries.")

    binary_package_name = exported(
        TextLine(
            title=_("Binary Package Name"),
            required=False, readonly=True))
    binary_package_version = exported(
        TextLine(
            title=_("Binary Package Version"),
            required=False, readonly=True))
    architecture_specific = exported(
        Bool(
            title=_("Architecture Specific"),
            required=False, readonly=True))
    priority_name = exported(
        TextLine(
            title=_("Priority Name"),
            required=False, readonly=True))
    is_debug = exported(
        Bool(
            title=_("Debug Package"),
            description=_("Is this a debug package publication?"),
            required=False, readonly=True),
        as_of="devel")

    def supersede(dominant=None, logger=None):
        """Supersede this publication.

        :param dominant: optional `IBinaryPackagePublishingHistory` which is
            triggering the domination.
        :param logger: optional object to which debug information will be
            logged.
        """

    def copyTo(distroseries, pocket, archive):
        """Copy this publication to another location.

        Architecture independent binary publications are copied to all
        supported architectures in the destination distroseries.

        :return: a list of `IBinaryPackagePublishingHistory` records
            representing the binaries copied to the destination location.
        """

    @export_read_operation()
    def getDownloadCount():
        """Get the download count of this binary package in this archive.

        This is currently only meaningful for PPAs."""

    @operation_parameters(
        start_date=Date(title=_("Start date"), required=False),
        end_date=Date(title=_("End date"), required=False))
    @operation_returns_collection_of(IBinaryPackageReleaseDownloadCount)
    @export_read_operation()
    def getDownloadCounts(start_date=None, end_date=None):
        """Get detailed download counts for this binary.

        :param start_date: The optional first date to return.
        :param end_date: The optional last date to return.
        """

    @operation_parameters(
        start_date=Date(title=_("Start date"), required=False),
        end_date=Date(title=_("End date"), required=False))
    @export_read_operation()
    def getDailyDownloadTotals(start_date=None, end_date=None):
        """Get the daily download counts for this binary.

        :param start_date: The optional first date to return.
        :param end_date: The optional last date to return.
        """

    @export_read_operation()
    @operation_parameters(
        include_meta=Bool(title=_("Include Metadata"), required=False))
    @operation_for_version("devel")
    def binaryFileUrls(include_meta=False):
        """URLs for this binary publication's binary files.

        :param include_meta: Return a list of dicts with keys url, size
            and sha1 for each url instead of a simple list.
        :return: A collection of URLs for this binary.
        """


class IBinaryPackagePublishingHistoryEdit(IPublishingEdit):
    """A writeable binary package publishing record."""

    # Really IBinaryPackagePublishingHistory, patched in
    # _schema_circular_imports.py.
    @operation_returns_entry(Interface)
    @operation_parameters(
        new_component=TextLine(title=u"The new component name."),
        new_section=TextLine(title=u"The new section name."),
        # XXX cjwatson 20120619: It would be nice to use copy_field here to
        # save manually looking up the priority name, but it doesn't work in
        # this case: the title is wrong, and tests fail when a string value
        # is passed over the webservice.
        new_priority=TextLine(title=u"The new priority name."),
        new_phased_update_percentage=Int(
            title=u"The new phased update percentage."))
    @export_write_operation()
    @operation_for_version("devel")
    def changeOverride(new_component=None, new_section=None,
                       new_priority=None, new_phased_update_percentage=None):
        """Change the component/section/priority/phase of this publication.

        It is changed only if the argument is not None.

        Passing new_phased_update_percentage=100 has the effect of setting
        the phased update percentage to None (i.e. recommended for all
        users).

        Return the overridden publishing record, a
        `IBinaryPackagePublishingHistory`.
        """


class IBinaryPackagePublishingHistory(IBinaryPackagePublishingHistoryPublic,
                                      IBinaryPackagePublishingHistoryEdit):
    """A binary package publishing record."""
    export_as_webservice_entry(publish_web_link=False)


class IPublishingSet(Interface):
    """Auxiliary methods for dealing with sets of publications."""

    def publishBinaries(archive, distroseries, pocket, binaries):
        """Efficiently publish multiple BinaryPackageReleases in an Archive.

        Creates `IBinaryPackagePublishingHistory` records for each
        binary, handling architecture-independent, avoiding creation of
        duplicate publications, and leaving disabled architectures
        alone.

        :param archive: The target `IArchive`.
        :param distroseries: The target `IDistroSeries`.
        :param pocket: The target `PackagePublishingPocket`.
        :param binaries: A dict mapping `BinaryPackageReleases` to their
            desired overrides as (`Component`, `Section`,
            `PackagePublishingPriority`, `phased_update_percentage`) tuples.

        :return: A list of new `IBinaryPackagePublishingHistory` records.
        """

    def copyBinaries(archive, distroseries, pocket, bpphs, policy=None):
        """Copy multiple binaries to a given destination.

        Efficiently copies the given `IBinaryPackagePublishingHistory`
        records to a new archive and suite, optionally overriding the
        original publications' component, section and priority using an
        `IOverridePolicy`.

        :param archive: The target `IArchive`.
        :param distroseries: The target `IDistroSeries`.
        :param pocket: The target `PackagePublishingPocket`.
        :param binaries: A list of `IBinaryPackagePublishingHistory`s to copy.
        :param policy: An optional `IOverridePolicy` to apply to the copy.

        :return: A result set of the created `IBinaryPackagePublishingHistory`
            records.
        """

    def newSourcePublication(archive, sourcepackagerelease, distroseries,
                             component, section, pocket, ancestor,
                             create_dsd_job=True):
        """Create a new `SourcePackagePublishingHistory`.

        :param archive: An `IArchive`
        :param sourcepackagerelease: An `ISourcePackageRelease`
        :param distroseries: An `IDistroSeries`
        :param component: An `IComponent`
        :param section: An `ISection`
        :param pocket: A `PackagePublishingPocket`
        :param ancestor: A `ISourcePackagePublishingHistory` for the previous
            version of this publishing record
        :param create_dsd_job: A boolean indicating whether or not a dsd job
             should be created for the new source publication.
        :param creator: An optional `IPerson`. If this is None, the
            sourcepackagerelease's creator will be used.
        :param sponsor: An optional `IPerson` indicating the sponsor of this
            publication.
        :param packageupload: An optional `IPackageUpload` that caused this
            publication to be created.

        datecreated will be UTC_NOW.
        status will be PackagePublishingStatus.PENDING
        """

    def getByIdAndArchive(id, archive, source=True):
        """Return the publication matching id AND archive.

        :param archive: The context `IArchive`.
        :param source: If true look for source publications, otherwise
            binary publications.
        """

    def getBuildsForSourceIds(source_ids, archive=None, build_states=None):
        """Return all builds related with each given source publication.

        The returned ResultSet contains entries with the wanted `Build`s
        associated with the corresponding source publication and its
        targeted `DistroArchSeries` in a 3-element tuple. This way the extra
        information will be cached and the callsites can group builds in
        any convenient form.

        The optional archive parameter, if provided, will ensure that only
        builds corresponding to the archive will be included in the results.

        The result is ordered by:

         1. Ascending `SourcePackagePublishingHistory.id`,
         2. Ascending `DistroArchSeries.architecturetag`.

        :param source_ids: list of or a single
            `SourcePackagePublishingHistory` object.
        :type source_ids: ``list`` or `SourcePackagePublishingHistory`
        :param archive: An optional archive with which to filter the source
            ids.
        :type archive: `IArchive`
        :param build_states: optional list of build states to which the
            result will be limited. Defaults to all states if ommitted.
        :type build_states: ``list`` or None
        :param need_build_farm_job: whether to include the `PackageBuild`
            and `BuildFarmJob` in the result.
        :return: a storm ResultSet containing tuples as
            (`SourcePackagePublishingHistory`, `Build`, `DistroArchSeries`)
        :rtype: `storm.store.ResultSet`.
        """

    def getBuildsForSources(one_or_more_source_publications):
        """Return all builds related with each given source publication.

        Extracts the source ids from one_or_more_source_publications and
        calls getBuildsForSourceIds.
        """

    def getUnpublishedBuildsForSources(one_or_more_source_publications,
                                       build_states=None):
        """Return all the unpublished builds for each source.

        :param one_or_more_source_publications: list of, or a single
            `SourcePackagePublishingHistory` object.
        :param build_states: list of build states to which the result should
            be limited. Defaults to BuildStatus.FULLYBUILT if none are
            specified.
        :return: a storm ResultSet containing tuples of
            (`SourcePackagePublishingHistory`, `Build`)
        """

    def getBinaryFilesForSources(one_or_more_source_publication):
        """Return binary files related to each given source publication.

        The returned ResultSet contains entries with the wanted
        `LibraryFileAlias`s (binaries only) associated with the
        corresponding source publication and its `LibraryFileContent`
        in a 3-element tuple. This way the extra information will be
        cached and the callsites can group files in any convenient form.

        :param one_or_more_source_publication: list of or a single
            `SourcePackagePublishingHistory` object.

        :return: a storm ResultSet containing triples as follows:
            (`SourcePackagePublishingHistory`, `LibraryFileAlias`,
             `LibraryFileContent`)
        """

    def getFilesForSources(one_or_more_source_publication):
        """Return all files related to each given source publication.

        The returned ResultSet contains entries with the wanted
        `LibraryFileAlias`s (source and binaries) associated with the
        corresponding source publication and its `LibraryFileContent`
        in a 3-element tuple. This way the extra information will be
        cached and the callsites can group files in any convenient form.

        Callsites should order this result after grouping by source,
        because SQL UNION can't be correctly ordered in SQL level.

        :param one_or_more_source_publication: list of or a single
            `SourcePackagePublishingHistory` object.

        :return: an *unordered* storm ResultSet containing tuples as
            (`SourcePackagePublishingHistory`, `LibraryFileAlias`,
             `LibraryFileContent`)
        """

    def getBinaryPublicationsForSources(one_or_more_source_publications):
        """Return all binary publication for the given source publications.

        The returned ResultSet contains entries with the wanted
        `BinaryPackagePublishingHistory`s associated with the corresponding
        source publication and its targeted `DistroArchSeries`,
        `BinaryPackageRelease` and `BinaryPackageName` in a 5-element tuple.
        This way the extra information will be cached and the callsites can
        group binary publications in any convenient form.

        The result is ordered by:

         1. Ascending `SourcePackagePublishingHistory.id`,
         2. Ascending `BinaryPackageName.name`,
         3. Ascending `DistroArchSeries.architecturetag`.
         4. Descending `BinaryPackagePublishingHistory.id`.

        :param one_or_more_source_publication: list of or a single
            `SourcePackagePublishingHistory` object.

        :return: a storm ResultSet containing tuples as
            (`SourcePackagePublishingHistory`,
             `BinaryPackagePublishingHistory`,
             `BinaryPackageRelease`, `BinaryPackageName`, `DistroArchSeries`)
        """

    def getPackageDiffsForSources(one_or_more_source_publications):
        """Return all `PackageDiff`s for each given source publication.

        The returned ResultSet contains entries with the wanted `PackageDiff`s
        associated with the corresponding source publication and its resulting
        `LibraryFileAlias` and `LibraryFileContent` in a 4-element tuple. This
        way the extra information will be cached and the callsites can group
        package-diffs in any convenient form.

        `LibraryFileAlias` and `LibraryFileContent` elements might be None in
        case the `PackageDiff` is not completed yet.

        The result is ordered by:

         1. Ascending `SourcePackagePublishingHistory.id`,
         2. Descending `PackageDiff.date_requested`.

        :param one_or_more_source_publication: list of or a single
            `SourcePackagePublishingHistory` object.

        :return: a storm ResultSet containing tuples as
            (`SourcePackagePublishingHistory`, `PackageDiff`,
             `LibraryFileAlias`, `LibraryFileContent`)
        """

    def getChangesFilesForSources(one_or_more_source_publications):
        """Return all changesfiles for each given source publication.

        The returned ResultSet contains entries with the wanted changesfiles
        as `LibraryFileAlias`es associated with the corresponding source
        publication and its corresponding `LibraryFileContent`,
        `PackageUpload` and `SourcePackageRelease` in a 5-element tuple.
        This way the extra information will be cached and the call sites can
        group changesfiles in any convenient form.

        The result is ordered by ascending `SourcePackagePublishingHistory.id`

        :param one_or_more_source_publication: list of or a single
            `SourcePackagePublishingHistory` object.

        :return: a storm ResultSet containing tuples as
            (`SourcePackagePublishingHistory`, `PackageUpload`,
             `SourcePackageRelease`, `LibraryFileAlias`, `LibraryFileContent`)
        """

    def getChangesFileLFA(spr):
        """The changes file for the given `SourcePackageRelease`.

        :param spr: the `SourcePackageRelease` for which to return the
            changes file `LibraryFileAlias`.

        :return: a `LibraryFileAlias` instance or None
        """

    def setMultipleDeleted(publication_class, ds, removed_by,
                           removal_comment=None):
        """Mark publications as deleted.

        This is a supporting operation for a deletion request.
        """

    def findCorrespondingDDEBPublications(pubs):
        """Find corresponding DDEB publications, given a list of publications.
        """

    def requestDeletion(pub, removed_by, removal_comment=None):
        """Delete the source and binary publications specified.

        This method deletes the source publications passed via the first
        parameter as well as their associated binary publications, and any
        binary publications passed in.

        :param pubs: list of `SourcePackagePublishingHistory` and
            `BinaryPackagePublishingHistory` objects.
        :param removed_by: `IPerson` responsible for the removal.
        :param removal_comment: optional text describing the removal reason.

        :return: The deleted publishing record, either:
            `ISourcePackagePublishingHistory` or
            `IBinaryPackagePublishingHistory`.
        """

    def getBuildStatusSummariesForSourceIdsAndArchive(source_ids, archive):
        """Return a summary of the build statuses for source publishing ids.

        This method collects all the builds for the provided source package
        publishing history ids, and returns the build status summary for
        the builds associated with each source package.

        See the `getStatusSummaryForBuilds()` method of `IBuildSet`.for
        details of the summary.

        :param source_ids: A list of source publishing history record ids.
        :type source_ids: ``list``
        :param archive: The archive which will be used to filter the source
                        ids.
        :type archive: `IArchive`
        :return: A dict consisting of the overall status summaries for the
            given ids that belong in the archive. For example:
                {
                    18: {'status': 'succeeded'},
                    25: {'status': 'building', 'builds':[building_builds]},
                    35: {'status': 'failed', 'builds': [failed_builds]}
                }
        :rtype: ``dict``.
        """

    def getBuildStatusSummaryForSourcePublication(source_publication):
        """Return a summary of the build statuses for this source
        publication.

        See `ISourcePackagePublishingHistory`.getStatusSummaryForBuilds()
        for details. The call is just proxied here so that it can also be
        used with an ArchiveSourcePublication passed in as
        the source_package_pub, allowing the use of the cached results.
        """

active_publishing_status = (
    PackagePublishingStatus.PENDING,
    PackagePublishingStatus.PUBLISHED,
    )


inactive_publishing_status = (
    PackagePublishingStatus.SUPERSEDED,
    PackagePublishingStatus.DELETED,
    PackagePublishingStatus.OBSOLETE,
    )


# Circular import problems fixed in _schema_circular_imports.py
