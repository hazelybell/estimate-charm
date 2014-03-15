# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'NameBlacklistAddView',
    'NameBlacklistEditView',
    'NameBlacklistNavigationMenu',
    'NameBlacklistSetNavigationMenu',
    'NameBlacklistSetView',
    ]

import re

from zope.component import (
    adapter,
    getUtility,
    )
from zope.formlib.widgets import TextWidget
from zope.interface import implements

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.registry.browser import RegistryEditFormView
from lp.registry.interfaces.nameblacklist import (
    INameBlacklist,
    INameBlacklistSet,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.interfaces import IBreadcrumb
from lp.services.webapp.menu import (
    ApplicationMenu,
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    Navigation,
    )


class NameBlacklistValidationMixin:
    """Validate regular expression when adding or editing."""

    def validate(self, data):
        """Validate regular expression."""
        regexp = data['regexp']
        try:
            re.compile(regexp)
            name_blacklist_set = getUtility(INameBlacklistSet)
            if (INameBlacklistSet.providedBy(self.context)
                or self.context.regexp != regexp):
                # Check if the regular expression already exists if a
                # new expression is being created or if an existing
                # regular expression has been modified.
                if name_blacklist_set.getByRegExp(regexp) is not None:
                    self.setFieldError(
                        'regexp',
                        'This regular expression already exists.')
        except re.error as e:
            self.setFieldError(
                'regexp',
                'Invalid regular expression: %s' % e)


class NameBlacklistEditView(NameBlacklistValidationMixin,
                            RegistryEditFormView):
    """View for editing a blacklist expression."""

    schema = INameBlacklist
    field_names = ['regexp', 'admin', 'comment']
    label = "Edit a blacklist expression"
    page_title = label

    @property
    def cancel_url(self):
        return canonical_url(getUtility(INameBlacklistSet))

    next_url = cancel_url


class NameBlacklistAddView(NameBlacklistValidationMixin, LaunchpadFormView):
    """View for adding a blacklist expression."""

    schema = INameBlacklist
    field_names = ['regexp', 'admin', 'comment']
    label = "Add a new blacklist expression"
    page_title = label

    custom_widget('regexp', TextWidget, displayWidth=60)

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    next_url = cancel_url

    @action("Add to blacklist", name='add')
    def add_action(self, action, data):
        name_blacklist_set = getUtility(INameBlacklistSet)
        name_blacklist_set.create(
            regexp=data['regexp'],
            comment=data['comment'],
            admin=data['admin'],
            )
        self.request.response.addInfoNotification(
            'Regular expression "%s" has been added to the name blacklist.'
            % data['regexp'])


class NameBlacklistSetView(LaunchpadView):
    """View for /+nameblacklists top level collection."""

    label = (
        'Blacklist for names of Launchpad pillars and persons')
    page_title = label


class NameBlacklistSetNavigation(Navigation):

    usedfor = INameBlacklistSet

    def traverse(self, name):
        return self.context.get(name)


class NameBlacklistSetNavigationMenu(NavigationMenu):
    """Action menu for NameBlacklistSet."""
    usedfor = INameBlacklistSet
    facet = 'overview'
    links = [
        'add_blacklist_expression',
        ]

    @enabled_with_permission('launchpad.Edit')
    def add_blacklist_expression(self):
        return Link('+add', 'Add blacklist expression', icon='add')


class NameBlacklistNavigationMenu(ApplicationMenu):
    """Action menu for NameBlacklist."""
    usedfor = INameBlacklist
    facet = 'overview'
    links = [
        'edit_blacklist_expression',
        ]

    @enabled_with_permission('launchpad.Edit')
    def edit_blacklist_expression(self):
        return Link('+edit', 'Edit blacklist expression', icon='edit')


@adapter(INameBlacklistSet)
class NameBlacklistSetBreadcrumb(Breadcrumb):
    """Return a breadcrumb for an `INameBlackListSet`."""

    implements(IBreadcrumb)

    text = "Name Blacklist"
