# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for BugSubscription."""

__metaclass__ = type
__all__ = [
    'AdvancedSubscriptionMixin',
    'BugMuteSelfView',
    'BugPortletSubscribersWithDetails',
    'BugSubscriptionAddView',
    'BugSubscriptionListView',
    ]

from lazr.delegates import delegates
from lazr.restful.interfaces import (
    IJSONRequestCache,
    IWebServiceClientRequest,
    )
from simplejson import dumps
from zope import formlib
from zope.formlib.itemswidgets import RadioWidget
from zope.formlib.widget import CustomWidgetFactory
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.proxy import removeSecurityProxy
from zope.traversing.browser import absoluteURL

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    ReturnToReferrerMixin,
    )
from lp.app.errors import SubscriptionPrivacyViolation
from lp.bugs.browser.structuralsubscription import (
    expose_structural_subscription_data_to_js,
    )
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bug import IBug
from lp.bugs.interfaces.bugsubscription import IBugSubscription
from lp.bugs.model.personsubscriptioninfo import PersonSubscriptions
from lp.bugs.model.structuralsubscription import (
    get_structural_subscriptions_for_bug,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.authorization import (
    check_permission,
    precache_permission_for_objects,
    )
from lp.services.webapp.escaping import structured


class BugSubscriptionAddView(LaunchpadFormView):
    """Browser view class for subscribing someone else to a bug."""

    schema = IBugSubscription

    field_names = ['person']

    def setUpFields(self):
        """Set up 'person' as an input field."""
        super(BugSubscriptionAddView, self).setUpFields()
        self.form_fields['person'].for_input = True

    @action('Subscribe user', name='add')
    def add_action(self, action, data):
        person = data['person']
        try:
            self.context.bug.subscribe(
                person, self.user, suppress_notify=False)
        except SubscriptionPrivacyViolation as error:
            self.setFieldError('person', unicode(error))
        else:
            if person.is_team:
                message = '%s team has been subscribed to this bug.'
            else:
                message = '%s has been subscribed to this bug.'
            self.request.response.addInfoNotification(
                message % person.displayname)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @property
    def label(self):
        return 'Subscribe someone else to bug #%i' % self.context.bug.id

    page_title = label


class AdvancedSubscriptionMixin:
    """A mixin of advanced subscription code for views.

    In order to use this mixin in a view the view must:
     - Define a current_user_subscription property which returns the
       current BugSubscription or StructuralSubscription for request.user.
       If there's no subscription for the given user in the given
       context, current_user_subscription must return None.
     - Define a dict, _bug_notification_level_descriptions, which maps
       BugNotificationLevel values to string descriptions for the
       current context (see `BugSubscriptionSubscribeSelfView` for an
       example).
     - Update the view's setUpFields() to call
       _setUpBugNotificationLevelField().
    """

    @cachedproperty
    def _bug_notification_level_field(self):
        """Return a custom form field for bug_notification_level."""
        # We rebuild the items that we show in the field so that the
        # labels shown are human readable and specific to the +subscribe
        # form. The BugNotificationLevel descriptions are too generic.
        bug_notification_level_terms = [
            SimpleTerm(
                level, level.title,
                self._bug_notification_level_descriptions[level])
            # We reorder the items so that COMMENTS comes first.
            for level in sorted(BugNotificationLevel.items, reverse=True)]
        bug_notification_vocabulary = SimpleVocabulary(
            bug_notification_level_terms)

        if self.current_user_subscription is not None:
            default_value = (
                self.current_user_subscription.bug_notification_level)
        else:
            default_value = BugNotificationLevel.COMMENTS

        bug_notification_level_field = Choice(
            __name__='bug_notification_level', title=_("Tell me when"),
            vocabulary=bug_notification_vocabulary, required=True,
            default=default_value)
        return bug_notification_level_field

    def _setUpBugNotificationLevelField(self):
        """Set up the bug_notification_level field."""
        self.form_fields = self.form_fields.omit('bug_notification_level')
        self.form_fields += formlib.form.Fields(
            self._bug_notification_level_field)
        self.form_fields['bug_notification_level'].custom_widget = (
            CustomWidgetFactory(RadioWidget))


class BugSubscriptionSubscribeSelfView(LaunchpadFormView,
                                       ReturnToReferrerMixin,
                                       AdvancedSubscriptionMixin):
    """A view to handle the +subscribe page for a bug."""

    schema = IBugSubscription
    page_title = 'Subscription options'

    # A mapping of BugNotificationLevel values to descriptions to be
    # shown on the +subscribe page.
    _bug_notification_level_descriptions = {
        BugNotificationLevel.COMMENTS: (
            "a change is made to this bug or a new comment is added, "),
        BugNotificationLevel.METADATA: (
            "any change is made to this bug, other than a new comment "
            "being added, or"),
        BugNotificationLevel.LIFECYCLE: (
            "this bug is fixed or re-opened."),
        }

    @property
    def field_names(self):
        return ['bug_notification_level']

    @property
    def next_url(self):
        """Provided so returning to the page they came from works."""
        referer = self._return_url
        context_url = canonical_url(self.context)

        # XXX bdmurray 2010-09-30 bug=98437: work around zope's test
        # browser setting referer to localhost.
        # We also ignore the current request URL and the context URL as
        # far as referrers are concerned so that we can handle privacy
        # issues properly.
        ignored_referrer_urls = (
            'localhost', self.request.getURL(), context_url)
        if referer and referer not in ignored_referrer_urls:
            next_url = referer
        elif self._redirecting_to_bug_list:
            next_url = canonical_url(self.context.target, view_name="+bugs")
        else:
            next_url = context_url
        return next_url

    cancel_url = next_url

    @cachedproperty
    def _subscribers_for_current_user(self):
        """Return a dict of the subscribers for the current user."""
        persons_for_user = {}
        person_count = 0
        bug = self.context.bug
        for person in bug.getSubscribersForPerson(self.user):
            if person.id not in persons_for_user:
                persons_for_user[person.id] = person
                person_count += 1

        self._subscriber_count_for_current_user = person_count
        return persons_for_user.values()

    def initialize(self):
        """See `LaunchpadFormView`."""
        self._subscriber_count_for_current_user = 0
        self._redirecting_to_bug_list = False
        super(BugSubscriptionSubscribeSelfView, self).initialize()

    @cachedproperty
    def current_user_subscription(self):
        return self.context.bug.getSubscriptionForPerson(self.user)

    @cachedproperty
    def _update_subscription_term(self):
        label = "update my current subscription"
        return SimpleTerm(
            'update-subscription', 'update-subscription', label)

    @cachedproperty
    def _unsubscribe_current_user_term(self):
        if self.user_is_muted:
            label = "unmute bug mail from this bug"
        else:
            label = 'unsubscribe me from this bug'
        return SimpleTerm(self.user, self.user.name, label)

    @cachedproperty
    def _unmute_user_term(self):
        if self.user_is_subscribed_directly:
            return SimpleTerm(
                'update-subscription', 'update-subscription',
                "unmute bug mail from this bug and restore my subscription")
        else:
            return SimpleTerm(self.user, self.user.name,
                              "unmute bug mail from this bug")

    @cachedproperty
    def _subscription_field(self):
        subscription_terms = []
        self_subscribed = False
        is_really_muted = self.user_is_muted
        if is_really_muted:
            subscription_terms.insert(0, self._unmute_user_term)
        for person in self._subscribers_for_current_user:
            if person.id == self.user.id:
                if is_really_muted:
                    # We've already added the unmute option.
                    continue
                else:
                    if self.user_is_subscribed_directly:
                        subscription_terms.append(
                            self._update_subscription_term)
                    subscription_terms.insert(
                        0, self._unsubscribe_current_user_term)
                    self_subscribed = True
            else:
                subscription_terms.append(
                    SimpleTerm(
                        person, person.name,
                        structured(
                            'unsubscribe <a href="%s">%s</a> from this bug',
                            canonical_url(person),
                            person.displayname).escapedtext))
        if not self_subscribed:
            if not is_really_muted:
                subscription_terms.insert(0,
                    SimpleTerm(
                        self.user, self.user.name,
                        'subscribe me to this bug'))
            elif not self.user_is_subscribed_directly:
                subscription_terms.insert(0,
                    SimpleTerm(
                        'update-subscription', 'update-subscription',
                        'unmute bug mail from this bug and subscribe me to '
                        'this bug'))

        # Add punctuation to the list of terms.
        if len(subscription_terms) > 1:
            for term in subscription_terms[:-1]:
                term.title += ','
            subscription_terms[-2].title += ' or'
            subscription_terms[-1].title += '.'

        subscription_vocabulary = SimpleVocabulary(subscription_terms)
        if self.user_is_subscribed_directly or self.user_is_muted:
            default_subscription_value = self._update_subscription_term.value
        else:
            default_subscription_value = (
                subscription_vocabulary.getTermByToken(self.user.name).value)

        subscription_field = Choice(
            __name__='subscription', title=_("Subscription options"),
            vocabulary=subscription_vocabulary, required=True,
            default=default_subscription_value)
        return subscription_field

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(BugSubscriptionSubscribeSelfView, self).setUpFields()
        if self.user is None:
            return

        self.form_fields += formlib.form.Fields(self._subscription_field)
        self._setUpBugNotificationLevelField()
        self.form_fields['subscription'].custom_widget = CustomWidgetFactory(
            RadioWidget)

    def setUpWidgets(self):
        """See `LaunchpadFormView`."""
        super(BugSubscriptionSubscribeSelfView, self).setUpWidgets()
        self.widgets['subscription'].widget_class = 'bug-subscription-basic'
        self.widgets['bug_notification_level'].widget_class = (
            'bug-notification-level-field')
        if (len(self.form_fields['subscription'].field.vocabulary) == 1):
            # We hide the subscription widget if the user isn't
            # subscribed, since we know who the subscriber is and we
            # don't need to present them with a single radio button.
            self.widgets['subscription'].visible = False
        else:
            # We show the subscription widget when the user is
            # subscribed via a team, because they can either
            # subscribe theirself or unsubscribe their team.
            self.widgets['subscription'].visible = True

        if self.user_is_subscribed_to_dupes_only:
            # If the user is subscribed via a duplicate but is not
            # directly subscribed, we hide the
            # bug_notification_level field, since it's not used.
            self.widgets['bug_notification_level'].visible = False

    @cachedproperty
    def user_is_muted(self):
        return self.context.bug.isMuted(self.user)

    @cachedproperty
    def user_is_subscribed_directly(self):
        """Is the user subscribed directly to this bug?"""
        return self.context.bug.isSubscribed(self.user)

    @cachedproperty
    def user_is_subscribed_to_dupes(self):
        """Is the user subscribed to dupes of this bug?"""
        return self.context.bug.isSubscribedToDupes(self.user)

    @property
    def user_is_subscribed(self):
        """Is the user subscribed to this bug?"""
        return (
            self.user_is_subscribed_directly or
            self.user_is_subscribed_to_dupes)

    @property
    def user_is_subscribed_to_dupes_only(self):
        """Is the user subscribed to this bug only via a dupe?"""
        return (
            self.user_is_subscribed_to_dupes and
            not self.user_is_subscribed_directly)

    def shouldShowUnsubscribeFromDupesWarning(self):
        """Should we warn the user about unsubscribing and duplicates?

        The warning should tell the user that, when unsubscribing, they
        will also be unsubscribed from dupes of this bug.
        """
        if self.user_is_subscribed:
            return True

        bug = self.context.bug
        for team in self.user.teams_participated_in:
            if bug.isSubscribed(team) or bug.isSubscribedToDupes(team):
                return True

        return False

    @action('Continue', name='continue')
    def subscribe_action(self, action, data):
        """Handle subscription requests."""
        subscription_person = self.widgets['subscription'].getInputValue()
        bug_notification_level = data.get('bug_notification_level', None)

        if (subscription_person == self._update_subscription_term.value and
            (self.user_is_subscribed or self.user_is_muted)):
            if self.user_is_muted:
                self._handleUnmute()
            if self.user_is_subscribed:
                self._handleUpdateSubscription(level=bug_notification_level)
            else:
                self._handleSubscribe(level=bug_notification_level)
        elif self.user_is_muted and subscription_person == self.user:
            self._handleUnmute()
        elif (not self.user_is_subscribed and
            (subscription_person == self.user)):
            self._handleSubscribe(bug_notification_level)
        else:
            self._handleUnsubscribe(subscription_person)
        self.request.response.redirect(self.next_url)

    def _handleSubscribe(self, level=None):
        """Handle a subscribe request."""
        self.context.bug.subscribe(self.user, self.user, level=level)
        self.request.response.addNotification(
            "You have subscribed to this bug report.")

    def _handleUnsubscribe(self, user):
        """Handle an unsubscribe request."""
        if user == self.user:
            self._handleUnsubscribeCurrentUser()
        else:
            self._handleUnsubscribeOtherUser(user)

    def _handleUnmute(self):
        """Handle an unmute request."""
        self.context.bug.unmute(self.user, self.user)

    def _handleUnsubscribeCurrentUser(self):
        """Handle the special cases for unsubscribing the current user."""
        # We call unsubscribeFromDupes() before unsubscribe(), because
        # if the bug is private, the current user will be prevented from
        # calling methods on the main bug after they unsubscribe from it.
        unsubed_dupes = self.context.bug.unsubscribeFromDupes(
            self.user, self.user)
        self.context.bug.unsubscribe(self.user, self.user)

        self.request.response.addNotification(
            structured(
                self._getUnsubscribeNotification(self.user, unsubed_dupes)))

        # Because the unsubscribe above may change what the security policy
        # says about the bug, we need to clear its cache.
        self.request.clearSecurityPolicyCache()

        if not check_permission("launchpad.View", self.context.bug):
            # Redirect the user to the bug listing, because they can no
            # longer see a private bug from which they've unsubscribed.
            self._redirecting_to_bug_list = True

    def _handleUnsubscribeOtherUser(self, user):
        """Handle unsubscribing someone other than the current user."""
        assert user != self.user, (
            "Expected a user other than the currently logged-in user.")

        # We'll also unsubscribe the other user from dupes of this bug,
        # otherwise they'll keep getting this bug's mail.
        self.context.bug.unsubscribe(user, self.user)
        unsubed_dupes = self.context.bug.unsubscribeFromDupes(user, user)
        self.request.response.addNotification(
            structured(
                self._getUnsubscribeNotification(user, unsubed_dupes)))

    def _handleUpdateSubscription(self, level):
        """Handle updating a user's subscription."""
        subscription = self.current_user_subscription
        subscription.bug_notification_level = level
        self.request.response.addNotification(
            "Your bug report subscription has been updated.")

    def _getUnsubscribeNotification(self, user, unsubed_dupes):
        """Construct and return the unsubscribe-from-bug feedback message.

        :user: The IPerson or ITeam that was unsubscribed from the bug.
        :unsubed_dupes: The list of IBugs that are dupes from which the
                        user was unsubscribed.
        """
        current_bug = self.context.bug
        current_user = self.user
        unsubed_dupes_msg_fragment = self._getUnsubscribedDupesMsgFragment(
            unsubed_dupes)

        if user == current_user:
            # Consider that the current user may have been "locked out"
            # of a bug if they unsubscribed themselves from a private
            # bug!
            if check_permission("launchpad.View", current_bug):
                # The user still has permission to see this bug, so no
                # special-casing needed.
                return structured(
                    "You have been unsubscribed from bug %s%s.",
                    current_bug.id, unsubed_dupes_msg_fragment).escapedtext
            else:
                return structured(
                    "You have been unsubscribed from bug %s%s. You no "
                    "longer have access to this private bug.",
                    current_bug.id, unsubed_dupes_msg_fragment).escapedtext
        else:
            return structured(
                "%s has been unsubscribed from bug %s%s.",
                user.displayname, current_bug.id,
                unsubed_dupes_msg_fragment).escapedtext

    def _getUnsubscribedDupesMsgFragment(self, unsubed_dupes):
        """Return the duplicates fragment of the unsubscription notification.

        This piece lists the duplicates from which the user was
        unsubscribed.
        """
        if not unsubed_dupes:
            return ""

        dupe_links = []
        for unsubed_dupe in unsubed_dupes:
            dupe_links.append(structured(
                '<a href="%s" title="%s">#%s</a>',
                canonical_url(unsubed_dupe), unsubed_dupe.title,
                unsubed_dupe.id))
        # We can't current join structured()s, so do it manually.
        dupe_links_string = structured(
            ", ".join(['%s'] * len(dupe_links)), *dupe_links)

        num_dupes = len(unsubed_dupes)
        if num_dupes > 1:
            plural_suffix = "s"
        else:
            plural_suffix = ""

        return structured(
            " and %(num_dupes)d duplicate%(plural_suffix)s "
            "(%(dupe_links_string)s)",
            num_dupes=num_dupes, plural_suffix=plural_suffix,
            dupe_links_string=dupe_links_string)


class BugPortletSubscribersWithDetails(LaunchpadView):
    """A view that returns a JSON dump of the subscriber details for a bug."""

    @cachedproperty
    def api_request(self):
        return IWebServiceClientRequest(self.request)

    def direct_subscriber_data(self, bug):
        """Get the direct subscriber data.

        This method is isolated from the subscriber_data_js so that query
        count testing can be done accurately and robustly.
        """
        data = []
        details = list(bug.getDirectSubscribersWithDetails())
        for person, subscribed_by, subscription in details:
            can_edit = subscription.canBeUnsubscribedByUser(self.user)
            if person == self.user:
                # Skip the current user viewing the page.
                continue
            if self.user is None and person.private:
                # Do not include private teams if there's no logged in user.
                continue

            # If we have made it to here then the logged in user can see the
            # bug, hence they can see any subscribers.
            # The security adaptor will do the job also but we don't want or
            # need the expense of running several complex SQL queries.
            precache_permission_for_objects(
                        self.request, 'launchpad.LimitedView', [person])
            subscriber = {
                'name': person.name,
                'display_name': person.displayname,
                'web_link': canonical_url(person, rootsite='mainsite'),
                'self_link': absoluteURL(person, self.api_request),
                'is_team': person.is_team,
                'can_edit': can_edit,
                'display_subscribed_by': subscription.display_subscribed_by,
                }
            record = {
                'subscriber': subscriber,
                'subscription_level': str(
                    removeSecurityProxy(subscription.bug_notification_level)),
                }
            data.append(record)
        return data

    @property
    def subscriber_data(self):
        """Return subscriber_ids in a form suitable for JavaScript use."""
        bug = IBug(self.context)
        data = self.direct_subscriber_data(bug)

        others = list(bug.getIndirectSubscribers())
        # If we have made it to here then the logged in user can see the
        # bug, hence they can see any indirect subscribers.
        include_private = self.user is not None
        if include_private:
            precache_permission_for_objects(
                self.request, 'launchpad.LimitedView', others)
        for person in others:
            if person == self.user:
                # Skip the current user viewing the page,
                continue
            if not include_private and person.private:
                # Do not include private teams if there's no logged in user.
                continue
            subscriber = {
                'name': person.name,
                'display_name': person.displayname,
                'web_link': canonical_url(person, rootsite='mainsite'),
                'self_link': absoluteURL(person, self.api_request),
                'is_team': person.is_team,
                'can_edit': False,
                }
            record = {
                'subscriber': subscriber,
                'subscription_level': 'Maybe',
                }
            data.append(record)
        return data

    @property
    def subscriber_data_js(self):
        return dumps(self.subscriber_data)

    def render(self):
        """Override the default render() to return only JSON."""
        self.request.response.setHeader('content-type', 'application/json')
        return self.subscriber_data_js


class SubscriptionAttrDecorator:
    """A BugSubscription with added attributes for HTML/JS."""
    delegates(IBugSubscription, 'subscription')

    def __init__(self, subscription):
        self.subscription = subscription

    @property
    def css_name(self):
        return 'subscriber-%s' % self.subscription.person.id


class BugSubscriptionListView(LaunchpadView):
    """A view to show all a person's subscriptions to a bug."""

    def initialize(self):
        super(BugSubscriptionListView, self).initialize()
        subscriptions = list(get_structural_subscriptions_for_bug(
            self.context.bug, self.user))
        expose_structural_subscription_data_to_js(
            self.context, self.request, self.user, subscriptions)
        subscriptions_info = PersonSubscriptions(
                self.user, self.context.bug)
        subdata, references = subscriptions_info.getDataForClient()
        cache = IJSONRequestCache(self.request).objects
        cache.update(references)
        cache['bug_subscription_info'] = subdata
        cache['bug_is_private'] = self.context.bug.private

    @property
    def label(self):
        return "Your subscriptions to bug %d" % self.context.bug.id

    page_title = label


class BugMuteSelfView(LaunchpadFormView):
    """A view to mute a user's bug mail for a given bug."""

    schema = IBugSubscription
    field_names = []

    @property
    def label(self):
        if self.context.bug.isMuted(self.user):
            return "Unmute bug mail for bug %s" % self.context.bug.id
        else:
            return "Mute bug mail for bug %s" % self.context.bug.id

    page_title = label

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    def initialize(self):
        self.is_muted = self.context.bug.isMuted(self.user)
        super(BugMuteSelfView, self).initialize()

    @action('Mute bug mail',
            name='mute',
            condition=lambda form, action: not form.is_muted)
    def mute_action(self, action, data):
        self.context.bug.mute(self.user, self.user)
        self.request.response.addInfoNotification(
            "Mail for bug #%s has been muted." % self.context.bug.id)

    @action('Unmute bug mail',
            name='unmute',
            condition=lambda form, action: form.is_muted)
    def unmute_action(self, action, data):
        self.context.bug.unmute(self.user, self.user)
        self.request.response.addInfoNotification(
            "Mail for bug #%s has been unmuted." % self.context.bug.id)
