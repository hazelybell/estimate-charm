# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BranchPortletSubscribersContent',
    'BranchSubscriptionAddOtherView',
    'BranchSubscriptionAddView',
    'BranchSubscriptionEditOwnView',
    'BranchSubscriptionEditView',
    'BranchSubscriptionPrimaryContext',
    ]

from lazr.restful.utils import smartquote
from zope.component import getUtility
from zope.interface import implements

from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.interfaces.services import IService
from lp.code.enums import BranchSubscriptionNotificationLevel
from lp.code.interfaces.branchsubscription import IBranchSubscription
from lp.registry.interfaces.person import IPersonSet
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.authorization import (
    check_permission,
    precache_permission_for_objects,
    )
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import IPrimaryContext


class BranchSubscriptionPrimaryContext:
    """The primary context is the subscription is that of the branch."""

    implements(IPrimaryContext)

    def __init__(self, branch_subscription):
        self.context = IPrimaryContext(branch_subscription.branch).context


class BranchPortletSubscribersContent(LaunchpadView):
    """View for the contents for the subscribers portlet."""

    def subscriptions(self):
        """Return a decorated list of branch subscriptions."""

        # Cache permissions so private subscribers can be rendered.
        # The security adaptor will do the job also but we don't want or need
        # the expense of running several complex SQL queries.
        person_ids = [sub.personID for sub in self.context.subscriptions]
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            person_ids, need_validity=True))
        if self.user is not None:
            subscribers = [
                subscription.person
                for subscription in self.context.subscriptions]
            precache_permission_for_objects(
                self.request, "launchpad.LimitedView", subscribers)

        visible_subscriptions = [
            subscription for subscription in self.context.subscriptions
            if check_permission('launchpad.LimitedView', subscription.person)]
        return sorted(
            visible_subscriptions,
            key=lambda subscription: subscription.person.displayname)


class _BranchSubscriptionView(LaunchpadFormView):

    """Contains the common functionality of the Add and Edit views."""

    schema = IBranchSubscription
    field_names = ['notification_level', 'max_diff_lines', 'review_level']

    LEVELS_REQUIRING_LINES_SPECIFICATION = (
        BranchSubscriptionNotificationLevel.DIFFSONLY,
        BranchSubscriptionNotificationLevel.FULL)

    @property
    def user_is_subscribed(self):
        # Since it is technically possible to get to this page when
        # the user is not subscribed by hacking the URL, we should
        # handle the case nicely.
        return self.context.getSubscription(self.user) is not None

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    def add_notification_message(self, initial, notification_level,
                                 max_diff_lines, review_level):
        if notification_level in self.LEVELS_REQUIRING_LINES_SPECIFICATION:
            lines_message = '<li>%s</li>' % max_diff_lines.description
        else:
            lines_message = ''

        format_str = '%%s<ul><li>%%s</li>%s<li>%%s</li></ul>' % lines_message
        message = structured(
            format_str, initial, notification_level.description,
            review_level.description)
        self.request.response.addNotification(message)

    def optional_max_diff_lines(self, notification_level, max_diff_lines):
        if notification_level in self.LEVELS_REQUIRING_LINES_SPECIFICATION:
            return max_diff_lines
        else:
            return None


class BranchSubscriptionAddView(_BranchSubscriptionView):

    subscribing_self = True

    page_title = label = "Subscribe to branch"

    @action("Subscribe")
    def subscribe(self, action, data):
        # To catch the stale post problem, check that the user is not
        # subscribed before continuing.
        if self.context.hasSubscription(self.user):
            self.request.response.addNotification(
                'You are already subscribed to this branch.')
        else:
            notification_level = data['notification_level']
            max_diff_lines = self.optional_max_diff_lines(
                notification_level, data['max_diff_lines'])
            review_level = data['review_level']

            self.context.subscribe(
                self.user, notification_level, max_diff_lines, review_level,
                self.user)

            self.add_notification_message(
                'You have subscribed to this branch with: ',
                notification_level, max_diff_lines, review_level)


class BranchSubscriptionEditOwnView(_BranchSubscriptionView):

    @property
    def label(self):
        return "Edit subscription to branch"

    @property
    def page_title(self):
        return smartquote(
            'Edit subscription to branch "%s"' % self.context.displayname)

    @property
    def initial_values(self):
        subscription = self.context.getSubscription(self.user)
        if subscription is None:
            # This is the case of URL hacking or stale page.
            return {}
        else:
            return {'notification_level': subscription.notification_level,
                    'max_diff_lines': subscription.max_diff_lines,
                    'review_level': subscription.review_level}

    @action("Change")
    def change_details(self, action, data):
        # Be proactive in the checking to catch the stale post problem.
        if self.context.hasSubscription(self.user):
            subscription = self.context.getSubscription(self.user)
            subscription.notification_level = data['notification_level']
            subscription.max_diff_lines = self.optional_max_diff_lines(
                subscription.notification_level,
                data['max_diff_lines'])
            subscription.review_level = data['review_level']

            self.add_notification_message(
                'Subscription updated to: ',
                subscription.notification_level,
                subscription.max_diff_lines,
                subscription.review_level)
        else:
            self.request.response.addNotification(
                'You are not subscribed to this branch.')

    @action("Unsubscribe")
    def unsubscribe(self, action, data):
        # Be proactive in the checking to catch the stale post problem.
        if self.context.hasSubscription(self.user):
            self.context.unsubscribe(self.user, self.user)
            self.request.response.addNotification(
                "You have unsubscribed from this branch.")
        else:
            self.request.response.addNotification(
                'You are not subscribed to this branch.')


class BranchSubscriptionAddOtherView(_BranchSubscriptionView):
    """View used to subscribe someone other than the current user."""

    field_names = [
        'person', 'notification_level', 'max_diff_lines', 'review_level']
    for_input = True

    # Since we are subscribing other people, the current user
    # is never considered subscribed.
    user_is_subscribed = False
    subscribing_self = False

    page_title = label = "Subscribe to branch"

    def validate(self, data):
        if data.has_key('person'):
            person = data['person']
            subscription = self.context.getSubscription(person)
            if subscription is None and not self.context.userCanBeSubscribed(
                person):
                self.setFieldError('person', "Open and delegated teams "
                "cannot be subscribed to private branches.")

    @action("Subscribe", name="subscribe_action")
    def subscribe_action(self, action, data):
        """Subscribe the specified user to the branch.

        The user must be a member of a team in order to subscribe that team to
        the branch.  Launchpad Admins are special and they can subscribe any
        team.
        """
        notification_level = data['notification_level']
        max_diff_lines = self.optional_max_diff_lines(
            notification_level, data['max_diff_lines'])
        review_level = data['review_level']
        person = data['person']
        subscription = self.context.getSubscription(person)
        if subscription is None:
            self.context.subscribe(
                person, notification_level, max_diff_lines, review_level,
                self.user)
            self.add_notification_message(
                '%s has been subscribed to this branch with: '
                % person.displayname, notification_level, max_diff_lines,
                review_level)
        else:
            self.add_notification_message(
                '%s was already subscribed to this branch with: '
                % person.displayname,
                subscription.notification_level, subscription.max_diff_lines,
                review_level)


class BranchSubscriptionEditView(LaunchpadEditFormView):
    """The view for editing branch subscriptions.

    Used when traversed to the branch subscription itself rather than
    through the branch action item to edit the user's own subscription.
    This is the only current way to edit a team branch subscription.
    """
    schema = IBranchSubscription
    field_names = ['notification_level', 'max_diff_lines', 'review_level']

    @property
    def page_title(self):
        return smartquote(
            'Edit subscription to branch "%s"' % self.branch.displayname)

    @property
    def label(self):
        return "Edit subscription to branch for %s" % self.person.displayname

    def initialize(self):
        self.branch = self.context.branch
        self.person = self.context.person
        super(BranchSubscriptionEditView, self).initialize()

    @action("Change", name="change")
    def change_action(self, action, data):
        """Update the branch subscription."""
        self.updateContextFromData(data)

    @action("Unsubscribe", name="unsubscribe")
    def unsubscribe_action(self, action, data):
        """Unsubscribe the team from the branch."""
        self.branch.unsubscribe(self.person, self.user)
        self.request.response.addNotification(
            "%s has been unsubscribed from this branch."
            % self.person.displayname)

    @property
    def next_url(self):
        url = canonical_url(self.branch)
        # If the subscriber can no longer see the branch, redirect them away.
        service = getUtility(IService, 'sharing')
        ignored, branches, ignored = service.getVisibleArtifacts(
            self.person, branches=[self.branch], ignore_permissions=True)
        if not branches:
            url = canonical_url(self.branch.target)
        return url

    cancel_url = next_url
