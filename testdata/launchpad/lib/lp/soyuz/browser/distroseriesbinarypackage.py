# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistroSeriesBinaryPackageBreadcrumb',
    'DistroSeriesBinaryPackageFacets',
    'DistroSeriesBinaryPackageNavigation',
    'DistroSeriesBinaryPackageView',
    ]

from lazr.restful.utils import smartquote

from lp.services.webapp import (
    ApplicationMenu,
    LaunchpadView,
    Navigation,
    StandardLaunchpadFacets,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.soyuz.interfaces.distroseriesbinarypackage import (
    IDistroSeriesBinaryPackage,
    )


class DistroSeriesBinaryPackageFacets(StandardLaunchpadFacets):
    # XXX mpt 2006-10-04: A DistroArchSeriesBinaryPackage is not a structural
    # object. It should inherit all navigation from its distro series.

    usedfor = IDistroSeriesBinaryPackage
    enable_only = ['overview']


class DistroSeriesBinaryPackageOverviewMenu(ApplicationMenu):

    usedfor = IDistroSeriesBinaryPackage
    facet = 'overview'
    links = []


class DistroSeriesBinaryPackageNavigation(Navigation):

    usedfor = IDistroSeriesBinaryPackage


class DistroSeriesBinaryPackageBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `IDistroSeriesBinaryPackage`."""
    @property
    def text(self):
        return self.context.binarypackagename.name


class DistroSeriesBinaryPackageView(LaunchpadView):

    def __init__(self, context, request):
        self.context = context
        self.request = request

    @property
    def page_title(self):
        return smartquote(self.context.title)
