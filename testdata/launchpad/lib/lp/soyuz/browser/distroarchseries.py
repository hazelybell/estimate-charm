# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistroArchSeriesActionMenu',
    'DistroArchSeriesAddView',
    'DistroArchSeriesAdminView',
    'DistroArchSeriesBreadcrumb',
    'DistroArchSeriesPackageSearchView',
    'DistroArchSeriesNavigation',
    'DistroArchSeriesView',
    ]

from lazr.restful.utils import smartquote
from zope.interface import (
    implements,
    Interface,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.services.webapp import GetitemNavigation
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.menu import (
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import canonical_url
from lp.soyuz.browser.packagesearch import PackageSearchViewBase
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries


class DistroArchSeriesNavigation(GetitemNavigation):

    usedfor = IDistroArchSeries


class DistroArchSeriesBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for `DistroArchSeries`."""

    @property
    def text(self):
        return self.context.architecturetag


class IDistroArchSeriesActionMenu(Interface):
    """Marker interface for the action menu."""


class DistroArchSeriesActionMenu(NavigationMenu):
    """Action menu for distro arch series."""
    usedfor = IDistroArchSeriesActionMenu
    facet = "overview"
    links = ['admin', 'builds']

    @enabled_with_permission('launchpad.Admin')
    def admin(self):
        text = 'Administer'
        return Link('+admin', text, icon='edit')

    # Search link not necessary, because there's a search form on
    # the overview page.

    def builds(self):
        text = 'Show builds'
        return Link('+builds', text, icon='info')


class DistroArchSeriesPackageSearchView(PackageSearchViewBase):
    """Customised PackageSearchView for DistroArchSeries"""

    def contextSpecificSearch(self):
        """See `AbstractPackageSearchView`."""
        return self.context.searchBinaryPackages(self.text)


class DistroArchSeriesView(DistroArchSeriesPackageSearchView):
    """Default DistroArchSeries view class."""
    implements(IDistroArchSeriesActionMenu)

    @property
    def page_title(self):
        return self.context.title


class DistroArchSeriesAddView(LaunchpadFormView):

    schema = IDistroArchSeries
    field_names = [
        'architecturetag', 'processor', 'official', 'supports_virtualized']

    @property
    def label(self):
        """See `LaunchpadFormView`"""
        return 'Add a port of %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action(_('Continue'), name='continue')
    def create_action(self, action, data):
        """Create a new Port."""
        distroarchseries = self.context.newArch(
            data['architecturetag'], data['processor'],
            data['official'], self.user, data['supports_virtualized'])
        self.next_url = canonical_url(distroarchseries)


class DistroArchSeriesAdminView(LaunchpadEditFormView):
    """View class for admin of DistroArchSeries."""

    schema = IDistroArchSeries

    field_names = [
        'architecturetag', 'official', 'supports_virtualized',
        'enabled',
        ]

    @action(_('Change'), name='update')
    def change_details(self, action, data):
        """Update with details from the form."""
        modified = self.updateContextFromData(data)

        if modified:
            self.request.response.addNotification(
                "Successfully updated")

        return modified

    @property
    def next_url(self):
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        return self.next_url

    @property
    def page_title(self):
        return smartquote("Administer %s" % self.context.title)

    @property
    def label(self):
        return self.page_title
