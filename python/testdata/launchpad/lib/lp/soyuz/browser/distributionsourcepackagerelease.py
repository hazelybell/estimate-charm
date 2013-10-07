# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistributionSourcePackageReleaseBreadcrumb',
    'DistributionSourcePackageReleaseNavigation',
    'DistributionSourcePackageReleasePublishingHistoryView',
    'DistributionSourcePackageReleaseView',
    ]

import operator

from lazr.restful.utils import smartquote

from lp.archivepublisher.debversion import Version
from lp.registry.browser.distributionsourcepackage import (
    PublishingHistoryViewMixin,
    )
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    LaunchpadView,
    Navigation,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.soyuz.browser.build import BuildNavigationMixin
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.distributionsourcepackagerelease import (
    IDistributionSourcePackageRelease,
    )


class DistributionSourcePackageReleaseBreadcrumb(Breadcrumb):
    """A breadcrumb for `IDistributionSourcePackageRelease`."""

    @property
    def text(self):
        return self.context.version


class DistributionSourcePackageReleaseNavigation(Navigation,
                                                 BuildNavigationMixin):
    usedfor = IDistributionSourcePackageRelease


class DistributionSourcePackageReleaseView(LaunchpadView):
    """View logic for `DistributionSourcePackageRelease` objects. """

    usedfor = IDistributionSourcePackageRelease

    @property
    def label(self):
        return smartquote(self.context.title)

    @property
    def page_title(self):
        return self.label

    @cachedproperty
    def _cached_publishing_history(self):
        """Local copy of the context 'publishing_history' values."""
        return list(self.context.publishing_history)

    @property
    def currently_published(self):
        """A list of published publications for this release.

        :return: a `list` of `SourcePackagePublishingHistory` currently
            published in the main archives.
        """
        return [
            publishing
            for publishing in self._cached_publishing_history
            if publishing.status == PackagePublishingStatus.PUBLISHED
            ]

    @property
    def files(self):
        """The source package release files as `ProxiedLibraryFileAlias`."""
        last_publication = self._cached_publishing_history[0]
        return [
            ProxiedLibraryFileAlias(
                source_file.libraryfile, last_publication.archive)
            for source_file in self.context.files]

    @cachedproperty
    def sponsor(self):
        """This source package's sponsor.

        A source package was sponsored if the owner of the key used to sign
        its upload is different from its 'creator' (DSC 'Changed-by:')

        :return: the sponsor `IPerson`, or none if the upload was not
            sponsored.
        """
        upload = self.context.package_upload
        if upload is None:
            return None
        signing_key = upload.signing_key
        if signing_key is None:
            return None
        if signing_key.owner.id == self.context.creator.id:
            return None
        return signing_key.owner

    @cachedproperty
    def grouped_builds(self):
        """Builds for this source in the primary archive grouped by series.

        :return: a `list` of dictionaries containing 'distroseries' and its
             grouped 'builds' ordered by descending distroseries versions.
        """
        # Build a local list of `IBinaryPackageBuilds` ordered by ascending
        # 'architecture_tag'.
        cached_builds = sorted(
            self.context.builds, key=operator.attrgetter('arch_tag'))

        # Build a list of unique `IDistroSeries` related with the local
        # builds ordered by descending version.
        def distroseries_sort_key(item):
            return Version(item.version)
        sorted_distroseries = sorted(
            set(build.distro_series for build in cached_builds),
            key=distroseries_sort_key, reverse=True)

        # Group builds as dictionaries.
        distroseries_builds = []
        for distroseries in sorted_distroseries:
            builds = [
                build
                for build in cached_builds
                if build.distro_series == distroseries
                ]
            distroseries_builds.append(
                {'distroseries': distroseries, 'builds': builds})

        return distroseries_builds


class DistributionSourcePackageReleasePublishingHistoryView(
        LaunchpadView, PublishingHistoryViewMixin):
    """Presenting `DistributionSourcePackageRelease` publishing history."""

    usedfor = IDistributionSourcePackageRelease

    page_title = 'Publishing history'

    @property
    def label(self):
        return 'Publishing history of %s' % smartquote(self.context.title)
