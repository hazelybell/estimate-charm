# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Featured Project views."""

__metaclass__ = type

__all__ = [
    'FeaturedProjectsView',
    ]

from zope.component import getUtility
from zope.interface import Interface
from zope.schema import (
    Choice,
    Set,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.widgets.itemswidgets import LabeledMultiCheckBoxWidget
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.services.webapp import canonical_url


class FeaturedProjectForm(Interface):
    """Form that requires the user to choose a pillar to feature."""

    add = Choice(
        title=_("Add project"),
        description=_(
            "Choose a project to feature on the Launchpad home page."),
        required=False, vocabulary='DistributionOrProductOrProjectGroup')

    remove = Set(
        title=u'Remove projects',
        description=_(
            'Select projects that you would like to remove from the list.'),
        required=False,
        value_type=Choice(vocabulary="FeaturedProject"))


class FeaturedProjectsView(LaunchpadFormView):
    """A view for adding and removing featured projects."""

    label = 'Manage featured projects in Launchpad'
    page_title = label

    schema = FeaturedProjectForm
    custom_widget('remove', LabeledMultiCheckBoxWidget)

    @action(_('Update featured project list'), name='update')
    def update_action(self, action, data):
        """Add and remove featured projects."""

        add = data.get('add')
        if add is not None:
            getUtility(IPillarNameSet).add_featured_project(add)

        remove = data.get('remove')
        if remove is not None:
            for project in remove:
                getUtility(IPillarNameSet).remove_featured_project(project)

        self.next_url = canonical_url(self.context)

    @action(_("Cancel"), name="cancel", validator='validate_cancel')
    def action_cancel(self, action, data):
        self.next_url = canonical_url(self.context)

    @property
    def action_url(self):
        return "/+featuredprojects"


