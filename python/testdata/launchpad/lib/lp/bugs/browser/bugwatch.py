# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IBugWatch-related browser views."""

__metaclass__ = type
__all__ = [
    'BugWatchSetNavigation',
    'BugWatchActivityPortletView',
    'BugWatchEditView',
    'BugWatchView'
    ]

from zope.component import getUtility
from zope.interface import Interface

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.widgets.textwidgets import URIWidget
from lp.bugs.browser.bugtask import get_comments_for_bugtask
from lp.bugs.interfaces.bugwatch import (
    BUG_WATCH_ACTIVITY_SUCCESS_STATUSES,
    IBugWatch,
    IBugWatchSet,
    NoBugTrackerFound,
    UnrecognizedBugTrackerURL,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.fields import URIField
from lp.services.webapp import (
    canonical_url,
    GetitemNavigation,
    LaunchpadView,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag


class BugWatchSetNavigation(GetitemNavigation):

    usedfor = IBugWatchSet


class BugWatchView(LaunchpadView):
    """View for displaying a bug watch."""

    schema = IBugWatch

    @property
    def page_title(self):
        return 'Comments imported to bug #%d from %s bug #%s' % (
            self.context.bug.id, self.context.bugtracker.title,
            self.context.remotebug)

    @property
    def comments(self):
        """Return the comments to be displayed for a bug watch.

        If the current user is not a member of the Launchpad developers
        team, no comments will be returned.
        """
        bug_comments = get_comments_for_bugtask(self.context.bug.bugtasks[0],
            truncate=True)

        # Filter out those comments that don't pertain to this bug
        # watch.
        displayed_comments = []
        for bug_comment in bug_comments:
            if bug_comment.bugwatch == self.context:
                displayed_comments.append(bug_comment)

        return displayed_comments


class BugWatchEditForm(Interface):
    """Form definition for the bug watch edit view."""

    url = URIField(
        title=_('URL'), required=True,
        allowed_schemes=['http', 'https', 'mailto'],
        description=_("The URL at which to view the remote bug, or the "
                      "email address to which this bug has been "
                      "forwarded (as a mailto: URL)."))


class BugWatchEditView(LaunchpadFormView):
    """View for editing a bug watch."""

    schema = BugWatchEditForm
    field_names = ['url']
    custom_widget('url', URIWidget)

    @property
    def page_title(self):
        """The page title."""
        return 'Edit bug watch for bug %s in %s on bug #%d' % (
            self.context.remotebug, self.context.bugtracker.title,
            self.context.bug.id)

    @property
    def initial_values(self):
        """See `LaunchpadFormView.`"""
        return {'url' : self.context.url}

    @property
    def watch_has_activity(self):
        """Return True if there has been activity on the bug watch."""
        return not self.context.activity.is_empty()

    def validate(self, data):
        """See `LaunchpadFormView.`"""
        if 'url' not in data:
            return
        try:
            bugtracker, bug = getUtility(
                IBugWatchSet).extractBugTrackerAndBug(data['url'])
        except (NoBugTrackerFound, UnrecognizedBugTrackerURL):
            self.setFieldError('url', 'Invalid bug tracker URL.')

    @action('Change', name='change')
    def change_action(self, action, data):
        bugtracker, remote_bug = getUtility(
            IBugWatchSet).extractBugTrackerAndBug(data['url'])
        self.context.bugtracker = bugtracker
        self.context.remotebug = remote_bug

    def bugWatchIsUnlinked(self, action):
        """Return whether the bug watch is unlinked."""
        return (
            len(self.context.bugtasks) == 0 and
            self.context.getBugMessages().is_empty())

    @action('Delete Bug Watch', name='delete', condition=bugWatchIsUnlinked)
    def delete_action(self, action, data):
        bugwatch = self.context
        # Build the notification first, whilst we still have the data.
        notification_message = structured(
            'The <a href="%(url)s">%(bugtracker)s #%(remote_bug)s</a>'
            ' bug watch has been deleted.',
            url=bugwatch.url, bugtracker=bugwatch.bugtracker.name,
            remote_bug=bugwatch.remotebug)
        bugwatch.bug.removeWatch(bugwatch, self.user)
        self.request.response.addInfoNotification(notification_message)

    def showResetActionCondition(self, action):
        """Return True if the reset action can be shown to this user."""
        return check_permission('launchpad.Admin', self.context)

    @action('Reset this watch', name='reset',
            condition=showResetActionCondition)
    def reset_action(self, action, data):
        bug_watch = self.context
        bug_watch.reset()
        self.request.response.addInfoNotification(
            structured(
            'The <a href="%(url)s">%(bugtracker)s #%(remote_bug)s</a>'
            ' bug watch has been reset.',
            url=bug_watch.url, bugtracker=bug_watch.bugtracker.name,
            remote_bug=bug_watch.remotebug))

    @property
    def next_url(self):
        return canonical_url(getUtility(ILaunchBag).bug)

    cancel_url = next_url


class BugWatchActivityPortletView(LaunchpadFormView):
    """A portlet for displaying the activity of a bug watch."""

    schema = BugWatchEditForm

    def userCanReschedule(self, action=None):
        """Return True if the current user can reschedule the bug watch."""
        return self.context.can_be_rescheduled

    @action('Update Now', name='reschedule', condition=userCanReschedule)
    def reschedule_action(self, action, data):
        """Schedule the current bug watch for immediate checking."""
        bugwatch = self.context
        bugwatch.setNextCheck(UTC_NOW)
        self.request.response.addInfoNotification(
            structured(
                'The <a href="%(url)s">%(bugtracker)s #%(remote_bug)s</a> '
                'bug watch has been scheduled for immediate checking.',
                url=bugwatch.url, bugtracker=bugwatch.bugtracker.name,
                remote_bug=bugwatch.remotebug))

    @property
    def next_url(self):
        return canonical_url(getUtility(ILaunchBag).bug)

    cancel_url = next_url

    @property
    def recent_watch_activity(self):
        """Return a list of dicts representing recent watch activity."""
        activity_items = []
        for activity in self.context.activity:
            if activity.result in BUG_WATCH_ACTIVITY_SUCCESS_STATUSES:
                icon = "/@@/yes"
                completion_message = "completed successfully"
            else:
                icon = "/@@/no"
                completion_message = (
                    "failed with error '%s'" % activity.result.title)

            activity_items.append({
                'icon': icon,
                'date': activity.activity_date,
                'completion_message': completion_message,
                'result_text': activity.result.title,
                'oops_id': activity.oops_id,
                })

        return activity_items
