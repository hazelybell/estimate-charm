# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for SpecificationSubscription."""

__metaclass__ = type
__all__ = [
    'SpecificationSubscriptionAddView',
    'SpecificationSubscriptionAddSubscriberView',
    'SpecificationSubscriptionEditView',
    ]

from lazr.delegates import delegates
from simplejson import dumps
from zope.component import getUtility

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.blueprints.interfaces.specificationsubscription import (
    ISpecificationSubscription,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import canonical_url
from lp.services.webapp.authorization import precache_permission_for_objects
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import LaunchpadView


class SpecificationSubscriptionAddView(LaunchpadFormView):
    """Used to subscribe the current user to a blueprint."""

    schema = ISpecificationSubscription
    field_names = ['essential']
    label = 'Subscribe to blueprint'

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    next_url = cancel_url

    def _subscribe(self, person, essential):
        self.context.subscribe(person, self.user, essential)

    @action(_('Subscribe'), name='subscribe')
    def subscribe_action(self, action, data):
        self._subscribe(self.user, data['essential'])
        self.request.response.addInfoNotification(
            "You have subscribed to this blueprint.")


class SpecificationSubscriptionAddSubscriberView(
    SpecificationSubscriptionAddView):
    """Used to subscribe someone else to a blueprint."""

    field_names = ['person', 'essential']
    label = 'Subscribe someone else'
    for_input = True

    @action(_('Subscribe'), name='subscribe')
    def subscribe_action(self, action, data):
        person = data['person']
        self._subscribe(person, data['essential'])
        self.request.response.addInfoNotification(
            "%s has been subscribed to this blueprint." % person.displayname)


class SpecificationSubscriptionDeleteView(LaunchpadFormView):
    """Used to unsubscribe someone from a blueprint."""

    schema = ISpecificationSubscription
    field_names = []

    @property
    def label(self):
        return ("Unsubscribe %s from %s"
                    % (self.context.person.displayname,
                       self.context.specification.title))

    page_title = label

    @property
    def cancel_url(self):
        return canonical_url(self.context.specification)

    next_url = cancel_url

    @action('Unsubscribe', name='unsubscribe')
    def unsubscribe_action(self, action, data):
        self.context.specification.unsubscribe(self.context.person, self.user)
        if self.context.person == self.user:
            self.request.response.addInfoNotification(
                "You have unsubscribed from this blueprint.")
        else:
            self.request.response.addInfoNotification(
                "%s has been unsubscribed from this blueprint."
                % self.context.person.displayname)


class SpecificationSubscriptionEditView(LaunchpadEditFormView):

    schema = ISpecificationSubscription
    field_names = ['essential']

    @property
    def label(self):
        return "Modify subscription to %s" % self.context.specification.title

    @property
    def cancel_url(self):
        return canonical_url(self.context.specification)

    next_url = cancel_url

    @action(_('Change'), name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)
        is_current_user_subscription = self.user == self.context.person
        if is_current_user_subscription:
            self.request.response.addInfoNotification(
                "Your subscription has been updated.")
        else:
            self.request.response.addInfoNotification(
                "The subscription for %s has been updated."
                % self.context.person.displayname)


class SpecificationPortletSubcribersContents(LaunchpadView):
    """View for the contents for the subscribers portlet."""

    @property
    def subscription(self):
        """Return a decorated subscription with added attributes."""
        return SubscriptionAttrDecorator(self.context)

    @property
    def sorted_subscriptions(self):
        """Get the list of subscriptions to the specification.

        The list is sorted such that subscriptions you can unsubscribe appear
        before all other subscriptions.
        """
        can_unsubscribe = []
        cannot_unsubscribe = []
        subscribers = []
        for subscription in self.context.subscriptions:
            subscribers.append(subscription.person)
            if subscription.person == self.user:
                can_unsubscribe = [subscription] + can_unsubscribe
            elif subscription.canBeUnsubscribedByUser(self.user):
                can_unsubscribe.append(subscription)
            else:
                cannot_unsubscribe.append(subscription)
        # Cache permission so private subscribers can be viewed.
        # The security adaptor will do the job also but we don't want or need
        # the expense of running several complex SQL queries.
        precache_permission_for_objects(
                    self.request, 'launchpad.LimitedView', subscribers)

        sorted_subscriptions = can_unsubscribe + cannot_unsubscribe
        return sorted_subscriptions

    @property
    def current_user_subscription_class(self):
        is_subscribed = self.context.isSubscribed(self.user)
        if is_subscribed:
            return 'subscribed-true'
        else:
            return 'subscribed-false'


class SpecificationPortletSubcribersIds(LaunchpadView):
    """A view returning a JSON dump of the subscriber IDs for a blueprint."""

    @cachedproperty
    def subscriber_ids(self):
        """Return a dictionary mapping a css_name to user name."""
        subscribers = set(self.context.subscribers)

        # The current user has to be in subscribers_id so
        # in case the id is needed for a new subscription.
        user = getUtility(ILaunchBag).user
        if user is not None:
            subscribers.add(user)

        ids = {}
        for sub in subscribers:
            ids[sub.name] = 'subscriber-%s' % sub.id
        return ids

    @property
    def subscriber_ids_js(self):
        """Return subscriber_ids in a form suitable for JavaScript use."""
        return dumps(self.subscriber_ids)

    def render(self):
        """Override the default render() to return only JSON."""
        self.request.response.setHeader('content-type', 'application/json')
        return self.subscriber_ids_js


class SubscriptionAttrDecorator:
    """A SpecificationSubscription with added attributes for HTML/JS."""
    delegates(ISpecificationSubscription, 'subscription')

    def __init__(self, subscription):
        self.subscription = subscription

    @property
    def css_name(self):
        return 'subscriber-%s' % self.subscription.person.id
