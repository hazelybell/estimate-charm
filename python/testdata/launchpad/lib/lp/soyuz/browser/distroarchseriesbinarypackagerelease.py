# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistroArchSeriesBinaryPackageReleaseBreadcrumb',
    'DistroArchSeriesBinaryPackageReleaseNavigation',
    'DistroArchSeriesBinaryPackageReleaseView',
    ]

from lazr.restful.utils import smartquote

from lp.services.webapp import (
    ApplicationMenu,
    LaunchpadView,
    Navigation,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.soyuz.interfaces.distroarchseriesbinarypackagerelease import (
    IDistroArchSeriesBinaryPackageRelease,
    )


class DistroArchSeriesBinaryPackageReleaseBreadcrumb(Breadcrumb):
    """A breadcrumb for `DistroArchSeriesBinaryPackageRelease`."""

    @property
    def text(self):
        return self.context.version


class DistroArchSeriesBinaryPackageReleaseOverviewMenu(ApplicationMenu):

    usedfor = IDistroArchSeriesBinaryPackageRelease
    facet = 'overview'
    links = []


class DistroArchSeriesBinaryPackageReleaseNavigation(Navigation):
    usedfor = IDistroArchSeriesBinaryPackageRelease


class DistroArchSeriesBinaryPackageReleaseView(LaunchpadView):

    def __init__(self, context, request):
        self.context = context
        self.request = request

    @property
    def page_title(self):
        return smartquote(self.context.title)

    @property
    def phased_update_percentage(self):
        """Return the formatted phased update percentage, or empty."""
        if self.context.phased_update_percentage is not None:
            return u"%d%% of users" % self.context.phased_update_percentage
        return u""
