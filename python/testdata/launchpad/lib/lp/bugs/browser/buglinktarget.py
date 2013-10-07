# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for IBugLinkTarget."""

__metaclass__ = type

__all__ = [
    'BugLinkView',
    'BugLinksListingView',
    'BugsUnlinkView',
    ]

from collections import defaultdict
from operator import attrgetter

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
from zope.component import getUtility
from zope.event import notify
from zope.interface import providedBy
from zope.security.interfaces import Unauthorized

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.widgets.itemswidgets import LabeledMultiCheckBoxWidget
from lp.bugs.browser.bugtask import BugListingBatchNavigator
from lp.bugs.interfaces.buglink import (
    IBugLinkForm,
    IUnlinkBugsForm,
    )
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.services.config import config
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.searchbuilder import any
from lp.services.webapp import canonical_url
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.publisher import LaunchpadView


class BugLinkView(LaunchpadFormView):
    """This view is used to link bugs to any IBugLinkTarget."""

    label = _('Link a bug report')
    schema = IBugLinkForm
    page_title = label

    focused_element_id = 'bug'

    @property
    def cancel_url(self):
        """See `LaunchpadFormview`."""
        return canonical_url(self.context)

    @action(_('Link'))
    def linkBug(self, action, data):
        """Link to the requested bug. Publish an ObjectModifiedEvent and
        display a notification.
        """
        response = self.request.response
        target_unmodified = Snapshot(
            self.context, providing=providedBy(self.context))
        bug = data['bug']
        try:
            self.context.linkBug(bug)
        except Unauthorized:
            # XXX flacoste 2006-08-23 bug=57470: This should use proper _().
            self.setFieldError(
                'bug',
                'You are not allowed to link to private bug #%d.' % bug.id)
            return
        bug_props = {'bugid': bug.id, 'title': bug.title}
        response.addNotification(
            _(u'Added link to bug #$bugid: '
              u'\N{left double quotation mark}$title'
              u'\N{right double quotation mark}.', mapping=bug_props))
        notify(ObjectModifiedEvent(
            self.context, target_unmodified, ['bugs']))
        self.next_url = canonical_url(self.context)


class BugLinksListingView(LaunchpadView):
    """View for displaying buglinks."""

    @cachedproperty
    def buglinks(self):
        """Return a list of dict with bug, title and can_see_bug keys
        for the linked bugs. It makes the Right Thing(tm) with private bug.
        """
        # Do a regular search to get the bugtasks so that visibility is
        # evaluated and eager loading is performed.
        bug_ids = map(attrgetter('bugID'), self.context.bug_links)
        if not bug_ids:
            return []
        bugtask_set = getUtility(IBugTaskSet)
        query = BugTaskSearchParams(user=self.user, bug=any(*bug_ids))
        bugtasks = list(bugtask_set.search(query))
        # collate by bug
        bugs = defaultdict(list)
        for task in bugtasks:
            bugs[task.bug].append(task)
        badges = bugtask_set.getBugTaskBadgeProperties(bugtasks)
        links = []
        columns_to_show = ["id", "summary", "bugtargetdisplayname",
            "importance", "status"]
        for bug, tasks in bugs.items():
            navigator = BugListingBatchNavigator(tasks, self.request,
                columns_to_show=columns_to_show,
                size=config.malone.buglist_batch_size)
            get_property_cache(navigator).bug_badge_properties = badges
            links.append({
                'bug': bug,
                'title': bug.title,
                'can_view_bug': True,
                'tasks': tasks,
                'batch_navigator': navigator,
                })
        return links


class BugsUnlinkView(LaunchpadFormView):
    """This view is used to remove bug links from any IBugLinkTarget."""

    label = _('Remove links to bug reports')
    schema = IUnlinkBugsForm
    custom_widget('bugs', LabeledMultiCheckBoxWidget)
    page_title = label

    @property
    def cancel_url(self):
        """See `LaunchpadFormview`."""
        return canonical_url(self.context)

    @action(_('Remove'))
    def unlinkBugs(self, action, data):
        response = self.request.response
        target_unmodified = Snapshot(
            self.context, providing=providedBy(self.context))
        for bug in data['bugs']:
            replacements = {'bugid': bug.id}
            try:
                self.context.unlinkBug(bug)
                response.addNotification(
                    _('Removed link to bug #$bugid.', mapping=replacements))
            except Unauthorized:
                response.addErrorNotification(
                    _('Cannot remove link to private bug #$bugid.',
                      mapping=replacements))
        notify(ObjectModifiedEvent(self.context, target_unmodified, ['bugs']))
        self.next_url = canonical_url(self.context)

    def bugsWithPermission(self):
        """Return the bugs that the user has permission to remove. This
        exclude private bugs to which the user doesn't have any permission.
        """
        return [bug for bug in self.context.bugs
                if check_permission('launchpad.View', bug)]
