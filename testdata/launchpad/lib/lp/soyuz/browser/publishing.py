# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for Soyuz publishing records."""

__metaclass__ = type

__all__ = [
    'BinaryPublishingRecordView',
    'SourcePublicationURL',
    'SourcePublishingRecordSelectableView',
    'SourcePublishingRecordView',
    ]

from operator import attrgetter

from lazr.delegates import delegates
from zope.interface import implements

from lp.services.librarian.browser import (
    FileNavigationMixin,
    ProxiedLibraryFileAlias,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import Navigation
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ICanonicalUrlData
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    )
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.binarypackagebuild import BuildSetStatus
from lp.soyuz.interfaces.packagediff import IPackageDiff
from lp.soyuz.interfaces.publishing import (
    IBinaryPackagePublishingHistory,
    ISourcePackagePublishingHistory,
    )


class PublicationURLBase:
    """Dynamic URL declaration for `I*PackagePublishingHistory`"""
    implements(ICanonicalUrlData)
    rootsite = None

    def __init__(self, context):
        self.context = context

    @property
    def inside(self):
        return self.context.archive


class SourcePublicationURL(PublicationURLBase):
    """Dynamic URL declaration for `ISourcePackagePublishingHistory`"""
    @property
    def path(self):
        return u"+sourcepub/%s" % self.context.id


class BinaryPublicationURL(PublicationURLBase):
    """Dynamic URL declaration for `IBinaryPackagePublishingHistory`"""
    @property
    def path(self):
        return u"+binarypub/%s" % self.context.id


class SourcePackagePublishingHistoryNavigation(Navigation,
                                               FileNavigationMixin):
    usedfor = ISourcePackagePublishingHistory


class ProxiedPackageDiff:
    """A `PackageDiff` extension.

    Instead of `LibraryFileAlias` returns `ProxiedLibraryFileAlias`, so
    their 'http_url' attribute can be used in the template.
    """
    delegates(IPackageDiff)

    def __init__(self, context, parent):
        self.context = context
        self.parent = parent

    @property
    def diff_content(self):
        library_file = self.context.diff_content
        if library_file is None:
            return None
        return ProxiedLibraryFileAlias(library_file, self.parent)


class BasePublishingRecordView(LaunchpadView):
    """Base Publishing view class."""

    @property
    def is_source(self):
        return ISourcePackagePublishingHistory.providedBy(self.context)

    @property
    def is_binary(self):
        return IBinaryPackagePublishingHistory.providedBy(self.context)

    # The reason we define the map below outside the only function that uses
    # it (date_last_changed()) is that this allows us to test whether the map
    # covers all PackagePublishingStatus enumeration values.
    # The pertinent tests in doc/publishing-pages.txt will fail if we add a
    # new value to the PackagePublishingStatus enumeration but do not update
    # this map.
    timestamp_map = {
        PackagePublishingStatus.DELETED: 'dateremoved',
        PackagePublishingStatus.OBSOLETE: 'scheduleddeletiondate',
        PackagePublishingStatus.PENDING: 'datecreated',
        PackagePublishingStatus.PUBLISHED: 'datepublished',
        PackagePublishingStatus.SUPERSEDED: 'datesuperseded'
    }

    @property
    def date_last_changed(self):
        """Return the date of last change considering the publishing status.

        The date returned is as follows:
            * pending        -> datecreated
            * published      -> datepublished
            * superseded     -> datesuperseded
            * deleted        -> dateremoved
            * obsolete       -> scheduleddeletiondate
        """
        accessor = attrgetter(self.timestamp_map[self.context.status])
        return accessor(self.context)

    def wasDeleted(self):
        """Whether or not a publishing record deletion was requested.

        A publishing record deletion represents the explicit request from a
        archive-administrator (self.remove_by) to purge the published contents
        of this record from the archive for an arbitrary reason
        (self.removal_comment).
        """
        return self.context.status == PackagePublishingStatus.DELETED

    def wasSuperseded(self):
        """Whether or not a publishing record was superseded.

        'Superseded' means that a new and higher version of this package was
        uploaded/built after it was published or the publishing attributes
        (section, component, priority/urgency) was modified.
        """
        return self.context.supersededby is not None

    def isPendingRemoval(self):
        """Whether or not a publishing record is marked for removal.

        This package will be removed from the archive respecting the Soyuz
        'death row' quarantine period and the absence of file references in
        the target archive.
        """
        return self.context.scheduleddeletiondate is not None

    def isRemoved(self):
        """Whether or not a publishing records was removed from the archive.

        A publishing record (all files related to it) is removed from the
        archive disk once it pass through its quarantine period and it's not
        referred by any other archive publishing record.
        Archive removal represents the act of having its content purged from
        archive disk, such situation can be triggered for different
        status, each one representing a distinct step in the Soyuz
        publishing workflow:

         * SUPERSEDED -> the publication is not necessary since there is
           already a newer/higher/modified version available

         * DELETED -> the publishing was explicitly marked for removal by a
           archive-administrator, it's not wanted in the archive.

         * OBSOLETE -> the publication has become obsolete because its
           targeted distroseries has become obsolete (not supported by its
           developers).
        """
        return self.context.dateremoved is not None

    @property
    def removal_comment(self):
        """Return the removal comment or 'None provided'."""
        removal_comment = self.context.removal_comment
        if removal_comment is None or not removal_comment.strip():
            removal_comment = u'None provided.'

        return removal_comment

    @property
    def phased_update_percentage(self):
        """Return the formatted phased update percentage, or empty."""
        if (self.is_binary and
            self.context.phased_update_percentage is not None):
            return u"%d%% of users" % self.context.phased_update_percentage
        return u""


class SourcePublishingRecordView(BasePublishingRecordView):
    """View class for `ISourcePackagePublishingHistory`."""

    @cachedproperty
    def build_status_summary(self):
        """Returns a dict with a summary of the build status."""
        return self.context.getStatusSummaryForBuilds()

    @property
    def builds_successful_and_published(self):
        """Return whether all builds were successful and published."""
        status = self.build_status_summary['status']
        return status == BuildSetStatus.FULLYBUILT

    @property
    def builds_successful_and_pending(self):
        """Return whether builds were successful but not all published."""
        status = self.build_status_summary['status']
        return status == BuildSetStatus.FULLYBUILT_PENDING

    @property
    def pending_builds(self):
        """Return a list of successful builds pending publication."""
        if self.builds_successful_and_pending:
            return self.build_status_summary['builds']
        else:
            return []

    @property
    def build_status_img_src(self):
        """Return the image path for the current build status summary."""
        image_map = {
            BuildSetStatus.BUILDING: '/@@/processing',
            BuildSetStatus.NEEDSBUILD: '/@@/build-needed',
            BuildSetStatus.FAILEDTOBUILD: '/@@/no',
            BuildSetStatus.FULLYBUILT_PENDING: '/@@/build-success-publishing'
            }

        return image_map.get(self.build_status_summary['status'], '/@@/yes')

    def wasCopied(self):
        """Whether or not a source is published in its original location.

        A source is not in its original location when:

         * The publishing `Archive` is not the same than where the source
            was uploaded. (SSPPH -> SPR -> Archive != SSPPH -> Archive).
        Or

          * The publishing `DistroSeries` is not the same than where the
            source was uploaded (SSPPH -> SPR -> DS != SSPPH -> DS).
        """
        source = self.context.sourcepackagerelease

        if self.context.archive != source.upload_archive:
            return True

        if self.context.distroseries != source.upload_distroseries:
            return True

        return False

    @property
    def allow_selection(self):
        """Do not render the checkbox corresponding to this record."""
        return False

    @property
    def published_source_and_binary_files(self):
        """Return list of dictionaries representing published files."""
        files = sorted(
            (ProxiedLibraryFileAlias(lfa, self.context.archive)
             for lfa in self.context.getSourceAndBinaryLibraryFiles()),
            key=attrgetter('filename'))
        result = []
        urls = set()
        for library_file in files:
            url = library_file.http_url
            if url in urls:
                # Don't print out the same file multiple times. This
                # actually happens for arch-all builds, and is
                # particularly irritating for PPAs.
                continue
            urls.add(url)

            custom_dict = {}
            custom_dict["url"] = url
            custom_dict["filename"] = library_file.filename
            custom_dict["filesize"] = library_file.content.filesize
            if (library_file.filename.endswith('.deb') or
                library_file.filename.endswith('.udeb')):
                custom_dict['class'] = 'binary'
            else:
                custom_dict['class'] = 'source'

            result.append(custom_dict)

        return result

    @property
    def available_diffs(self):
        package_diffs = self.context.sourcepackagerelease.package_diffs
        return [
            ProxiedPackageDiff(package_diff, self.context.archive)
            for package_diff in package_diffs]

    @property
    def built_packages(self):
        """Return a list of dictionaries with package names and their summary.

        For each built package from this published source, return a
        dictionary with keys "binarypackagename" and "summary", where
        the binarypackagename is unique (i.e. it ignores the same package
        published in more than one place/architecture.)
        """
        results = []
        packagenames = set()
        for pub in self.context.getPublishedBinaries():
            package = pub.binarypackagerelease
            packagename = package.binarypackagename.name
            if packagename not in packagenames:
                entry = {
                    "binarypackagename": packagename,
                    "summary": package.summary,
                    }
                results.append(entry)
                packagenames.add(packagename)
        return results

    @cachedproperty
    def builds(self):
        """Return a list of Builds for the context published source."""
        return list(self.context.getBuilds())

    @property
    def linkify_source_archive(self):
        """Return True if the source's upload_archive should be linkified.

        The source archive is the upload_archive for any source that was
        copied.  It should be linkified only if it's a PPA and the user
        has permission to view that PPA.
        """
        archive = self.context.sourcepackagerelease.upload_archive

        if not archive.is_ppa:
            return False

        return check_permission('launchpad.View', archive)

    @property
    def recipe_build_details(self):
        """Return a linkified string containing details about a
        SourcePackageRecipeBuild.
        """
        sprb = self.context.sourcepackagerelease.source_package_recipe_build
        if sprb is not None:
            if sprb.recipe is None:
                recipe = 'deleted recipe'
            else:
                recipe = structured(
                    'recipe <a href="%s">%s</a>',
                    canonical_url(sprb.recipe), sprb.recipe.name)
            return structured(
                '<a href="%s">Built</a> by %s for <a href="%s">%s</a>',
                    canonical_url(sprb), recipe,
                    canonical_url(sprb.requester),
                    sprb.requester.displayname).escapedtext
        return None


class SourcePublishingRecordSelectableView(SourcePublishingRecordView):
    """View class for a selectable `ISourcePackagePublishingHistory`."""

    @property
    def allow_selection(self):
        """Allow the checkbox corresponding to this record to be rendered."""
        return True


class BinaryPublishingRecordView(BasePublishingRecordView):
    """View class for `IBinaryPackagePublishingHistory`."""

    def wasCopied(self):
        """Whether or not a binary is published in its original location.

        A binary is not in its original location when:

         * The publishing `Archive` is not the same than where the binary
           was built. (SBPPH -> BPR -> Build -> Archive != SBPPH -> Archive).
        Or

          * The publishing `DistroArchSeries` is not the same than where
            the binary was built (SBPPH -> BPR -> B -> DAS != SBPPH -> DAS).

        Or

          * The publishing pocket is not the same than where the binary was
            built (SBPPH -> BPR -> B -> Pocket != SBPPH -> Pocket).

        """
        build = self.context.binarypackagerelease.build

        if self.context.archive != build.archive:
            return True

        if self.context.distroarchseries != build.distro_arch_series:
            return True

        if self.context.pocket != build.pocket:
            return True

        return False
