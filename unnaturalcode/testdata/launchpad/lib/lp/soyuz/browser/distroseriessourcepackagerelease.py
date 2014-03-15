# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistroSeriesSourcePackageReleaseNavigation',
    'DistroSeriesSourcePackageReleaseView',
    ]

from lazr.restful.utils import smartquote

from lp.services.webapp import (
    ApplicationMenu,
    LaunchpadView,
    Navigation,
    stepthrough,
    )
from lp.soyuz.interfaces.distroseriessourcepackagerelease import (
    IDistroSeriesSourcePackageRelease,
    )


class DistroSeriesSourcePackageReleaseOverviewMenu(ApplicationMenu):

    usedfor = IDistroSeriesSourcePackageRelease
    facet = 'overview'
    links = []


class DistroSeriesSourcePackageReleaseNavigation(Navigation):
    usedfor = IDistroSeriesSourcePackageRelease

    @stepthrough('+files')
    def traverse_files(self, name):
        """Traverse into a virtual +files subdirectory.

        This subdirectory is special in that it redirects filenames that
        match one of the SourcePackageRelease's files to the relevant
        librarian URL. This allows it to be used with dget, as suggested
        in https://bugs.launchpad.net/soyuz/+bug/130158
        """
        # If you are like me you'll ask yourself how it can be that we're
        # putting this traversal on IDistroSeriesSourcePackageRelease and
        # using it with sourcepackagerelease-files.pt. The reason is
        # that the canonical_url for SourcePackageRelease is actually an
        # IDistroSeriesSourcePackageRelease page. Weird.
        for file in self.context.files:
            if file.libraryfile.filename == name:
                return file.libraryfile
        return None


class DistroSeriesSourcePackageReleaseView(LaunchpadView):

    def __init__(self, context, request):
        self.context = context
        self.request = request

    @property
    def label(self):
        return smartquote(self.context.title)

    page_title = label
