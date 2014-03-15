# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BugSubscription views."""

__metaclass__ = type

from lazr.restful.interfaces import IWebServiceClientRequest
from simplejson import dumps
from storm.store import Store
from testtools.matchers import Equals
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy
from zope.traversing.browser import absoluteURL

from lp.bugs.browser.bugsubscription import (
    BugPortletSubscribersWithDetails,
    BugSubscriptionAddView,
    BugSubscriptionListView,
    BugSubscriptionSubscribeSelfView,
    )
from lp.bugs.enums import BugNotificationLevel
from lp.registry.enums import (
    PersonVisibility,
    TeamMembershipPolicy,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.services.webapp import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.deprecated import LaunchpadFormHarness
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class BugsubscriptionPrivacyTests(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(BugsubscriptionPrivacyTests, self).setUp()
        self.user = self.factory.makePerson()
        self.bug = self.factory.makeBug(owner=self.user)
        removeSecurityProxy(self.bug).setPrivate(True, self.user)

    def _assert_subscription_fails(self, team):
        with person_logged_in(self.user):
            harness = LaunchpadFormHarness(
                self.bug.default_bugtask, BugSubscriptionAddView)
            form_data = {'field.person': team.name}
            harness.submit('add', form_data)
        subscription = removeSecurityProxy(self.bug).getSubscriptionForPerson(
            team)
        error_msg = harness.getFieldError('person')
        expected_msg = (u'Open and delegated teams cannot be subscribed to '
            'private bugs.')
        self.assertEqual(expected_msg, error_msg)
        self.assertIs(None, subscription)

    def test_open_team_cannot_be_subscribed_to_private_bug(self):
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.OPEN)
        self._assert_subscription_fails(team)

    def test_delegated_team_cannot_be_subscribed_to_private_bug(self):
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.DELEGATED)
        self._assert_subscription_fails(team)


class BugSubscriptionAdvancedFeaturesTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(BugSubscriptionAdvancedFeaturesTestCase, self).setUp()
        self.bug = self.factory.makeBug()
        self.person = self.factory.makePerson()

    def test_subscribe_uses_bug_notification_level(self):
        # When a user subscribes to a bug using the advanced features on
        # the Bug +subscribe page, the bug notification level they
        # choose is taken into account.
        bug = self.factory.makeBug()
        # We unsubscribe the bug's owner because if we don't there will
        # be two COMMENTS-level subscribers.
        with person_logged_in(bug.owner):
            bug.unsubscribe(bug.owner, bug.owner)

        displayed_levels = [
            level for level in BugNotificationLevel.items]
        for level in displayed_levels:
            person = self.factory.makePerson()
            with person_logged_in(person):
                harness = LaunchpadFormHarness(
                    bug.default_bugtask, BugSubscriptionSubscribeSelfView)
                form_data = {
                    'field.subscription': person.name,
                    'field.bug_notification_level': level.title,
                    }
                harness.submit('continue', form_data)

            subscription = bug.getSubscriptionForPerson(person)
            self.assertEqual(
                level, subscription.bug_notification_level,
                "Bug notification level of subscription should be %s, is "
                "actually %s." % (
                    level.title,
                    subscription.bug_notification_level.title))

    def test_user_can_update_subscription(self):
        # A user can update their bug subscription using the
        # BugSubscriptionSubscribeSelfView.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            bug.subscribe(person, person, BugNotificationLevel.COMMENTS)
            # Now the person updates their subscription so they're
            # subscribed at the METADATA level.
            level = BugNotificationLevel.METADATA
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            form_data = {
                'field.subscription': 'update-subscription',
                'field.bug_notification_level': level.title,
                }
            harness.submit('continue', form_data)
            self.assertFalse(harness.hasErrors())

        subscription = bug.getSubscriptionForPerson(person)
        self.assertEqual(
            BugNotificationLevel.METADATA,
            subscription.bug_notification_level,
            "Bug notification level of subscription should be METADATA, is "
            "actually %s." % subscription.bug_notification_level.title)

    def test_user_can_unsubscribe(self):
        # A user can unsubscribe from a bug using the
        # BugSubscriptionSubscribeSelfView.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            bug.subscribe(person, person)
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            form_data = {
                'field.subscription': person.name,
                }
            harness.submit('continue', form_data)

        subscription = bug.getSubscriptionForPerson(person)
        self.assertIs(
            None, subscription,
            "There should be no BugSubscription for this person.")

    def test_field_values_set_correctly_for_existing_subscriptions(self):
        # When a user who is already subscribed to a bug visits the
        # BugSubscriptionSubscribeSelfView, its bug_notification_level
        # field will be set according to their current susbscription
        # level.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            # We subscribe using the harness rather than doing it
            # directly so that we don't have to commit() between
            # subscribing and checking the default value.
            level = BugNotificationLevel.METADATA
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            form_data = {
                'field.subscription': person.name,
                'field.bug_notification_level': level.title,
                }
            harness.submit('continue', form_data)

            # The default value for the bug_notification_level field
            # should now be the same as the level used to subscribe
            # above.
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            bug_notification_level_widget = (
                harness.view.widgets['bug_notification_level'])
            default_notification_level_value = (
                bug_notification_level_widget._getDefault())
            self.assertEqual(
                BugNotificationLevel.METADATA,
                default_notification_level_value,
                "Default value for bug_notification_level should be "
                "METADATA, is actually %s"
                % default_notification_level_value)

    def test_update_subscription_fails_if_user_not_subscribed(self):
        # If the user is not directly subscribed to the bug, trying to
        # update the subscription will fail (since you can't update a
        # subscription that doesn't exist).
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            subscription_field = (
                harness.view.form_fields['subscription'].field)
            # The update-subscription option won't appear.
            self.assertNotIn(
                'update-subscription',
                subscription_field.vocabulary.by_token)

    def test_update_subscription_fails_for_users_subscribed_via_teams(self):
        # If the user is not directly subscribed, but is subscribed via
        # a team, they will not be able to use the "Update my
        # subscription" option.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        team = self.factory.makeTeam(owner=person)
        with person_logged_in(person):
            bug.subscribe(team, person)
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            subscription_field = (
                harness.view.form_fields['subscription'].field)
            # The update-subscription option won't appear.
            self.assertNotIn(
                'update-subscription',
                subscription_field.vocabulary.by_token)

    def test_bug_673288(self):
        # If the user is not directly subscribed, but is subscribed via
        # a team and via a duplicate, they will not be able to use the
        # "Update my subscription" option.
        # This is a regression test for bug 673288.
        bug = self.factory.makeBug()
        duplicate = self.factory.makeBug()
        person = self.factory.makePerson()
        team = self.factory.makeTeam(owner=person)
        with person_logged_in(person):
            duplicate.markAsDuplicate(bug)
            duplicate.subscribe(person, person)
            bug.subscribe(team, person)

            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            subscription_field = (
                harness.view.form_fields['subscription'].field)
            # The update-subscription option won't appear.
            self.assertNotIn(
                'update-subscription',
                subscription_field.vocabulary.by_token)

    def test_bug_notification_level_field_hidden_for_dupe_subs(self):
        # If the user is subscribed to the bug via a duplicate, the
        # bug_notification_level field won't be visible on the form.
        bug = self.factory.makeBug()
        duplicate = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            duplicate.markAsDuplicate(bug)
            duplicate.subscribe(person, person)
            harness = LaunchpadFormHarness(
                bug.default_bugtask, BugSubscriptionSubscribeSelfView)
            self.assertFalse(
                harness.view.widgets['bug_notification_level'].visible)

    def test_muted_subs_have_subscribe_option_and_unmute_option(self):
        # If a user has a muted subscription, but no previous
        # direct bug subscription, the BugSubscriptionSubscribeSelfView's
        # subscription field will show an "Unmute" option.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)

        with person_logged_in(self.person):
            subscribe_view = create_initialized_view(
                self.bug.default_bugtask, name='+subscribe')
            subscription_widget = (
                subscribe_view.widgets['subscription'])
            update_term = subscription_widget.vocabulary.getTermByToken(
                'update-subscription')
            self.assertEqual(
                "unmute bug mail from this bug and subscribe me to this "
                "bug, or",
                update_term.title)
            self.assertEqual(
                "unmute bug mail from this bug.",
                subscription_widget.vocabulary.getTerm(self.person).title)

    def test_muted_subs_have_unmute_and_restore_option(self):
        # If a user has a muted subscription, the
        # BugSubscriptionSubscribeSelfView's subscription field will
        # show an option to unmute the subscription and restore it to a
        # previous or new BugNotificationLevel.
        with person_logged_in(self.person):
            self.bug.subscribe(self.person, self.person,
                               level=BugNotificationLevel.COMMENTS)
            self.bug.mute(self.person, self.person)

        with person_logged_in(self.person):
            subscribe_view = create_initialized_view(
                self.bug.default_bugtask, name='+subscribe')
            subscription_widget = (
                subscribe_view.widgets['subscription'])
            update_term = subscription_widget.vocabulary.getTermByToken(
                'update-subscription')
            self.assertEqual(
                "unmute bug mail from this bug and restore my "
                "subscription",
                update_term.title)

    def test_unmute_unmutes(self):
        # Using the "Unmute bug mail" option when the user has muted their
        # email will unmute.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)

        with person_logged_in(self.person):
            form_data = {
                'field.subscription': self.person.name,
                # Although this isn't used we must pass it for the
                # sake of form validation.
                'field.actions.continue': 'Continue',
                }
            create_initialized_view(
                self.bug.default_bugtask, form=form_data,
                name='+subscribe')
            self.assertFalse(self.bug.isMuted(self.person))
        subscription = self.bug.getSubscriptionForPerson(self.person)
        self.assertIs(
            None, subscription,
            "There should be no BugSubscription for this person.")

    def test_unmute_and_subscribe(self):
        # Using the "unmute bug mail from this bug and subscribe me to this
        # bug" option when the user has muted their email will unmute and
        # subscribe.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            level = BugNotificationLevel.METADATA
            form_data = {
                'field.subscription': 'update-subscription',
                'field.bug_notification_level': level.title,
                # Although this isn't used we must pass it for the
                # sake of form validation.
                'field.actions.continue': 'Continue',
                }
            create_initialized_view(
                self.bug.default_bugtask, form=form_data,
                name='+subscribe')
            self.assertFalse(self.bug.isMuted(self.person))
        subscription = self.bug.getSubscriptionForPerson(self.person)
        self.assertEqual(
            BugNotificationLevel.METADATA,
            subscription.bug_notification_level,
            "Bug notification level of subscription should be METADATA, is "
            "actually %s." % (subscription.bug_notification_level.title
                              if subscription is not None
                              else '[not subscribed!]'))

    def test_bug_notification_level_field_has_widget_class(self):
        # The bug_notification_level widget has a widget_class property
        # that can be used to manipulate it with JavaScript.
        with person_logged_in(self.person):
            subscribe_view = create_initialized_view(
                self.bug.default_bugtask, name='+subscribe')
        widget_class = (
            subscribe_view.widgets['bug_notification_level'].widget_class)
        self.assertEqual(
            'bug-notification-level-field', widget_class)


class BugSubscriptionsListViewTestCase(TestCaseWithFactory):
    """Tests for the BugSubscriptionsListView."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(BugSubscriptionsListViewTestCase, self).setUp()
        self.product = self.factory.makeProduct(
            name='widgetsrus', displayname='Widgets R Us')
        self.bug = self.factory.makeBug(target=self.product)
        self.subscriber = self.factory.makePerson()

    def test_form_initializes(self):
        # It's a start.
        with person_logged_in(self.subscriber):
            self.product.addBugSubscription(
                self.subscriber, self.subscriber)
            harness = LaunchpadFormHarness(
                self.bug.default_bugtask, BugSubscriptionListView)
            harness.view.initialize()


class BugMuteSelfViewTestCase(TestCaseWithFactory):
    """Tests for the BugMuteSelfView."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(BugMuteSelfViewTestCase, self).setUp()
        self.bug = self.factory.makeBug()
        self.person = self.factory.makePerson()

    def test_is_muted_false(self):
        # BugMuteSelfView initialization sets the is_muted property.
        # When the person has not muted the bug, it's false.
        with person_logged_in(self.person):
            self.assertFalse(self.bug.isMuted(self.person))
            view = create_initialized_view(
                self.bug.default_bugtask, name="+mute")
            self.assertFalse(view.is_muted)

    def test_is_muted_true(self):
        # BugMuteSelfView initialization sets the is_muted property.
        # When the person has muted the bug, it's true.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.assertTrue(self.bug.isMuted(self.person))
            view = create_initialized_view(
                self.bug.default_bugtask, name="+mute")
            self.assertTrue(view.is_muted)

    def test_label_nonmuted(self):
        # Label to use for the button.
        with person_logged_in(self.person):
            self.assertFalse(self.bug.isMuted(self.person))
            expected_label = "Mute bug mail for bug %s" % self.bug.id
            view = create_initialized_view(
                self.bug.default_bugtask, name="+mute")
            self.assertEqual(expected_label, view.label)

    def test_label_muted(self):
        # Label to use for the button.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.assertTrue(self.bug.isMuted(self.person))
            expected_label = "Unmute bug mail for bug %s" % self.bug.id
            view = create_initialized_view(
                self.bug.default_bugtask, name="+mute")
            self.assertEqual(expected_label, view.label)

    def test_bug_mute_self_view_mutes_bug(self):
        # The BugMuteSelfView mutes bug mail for the current user when
        # its form is submitted.
        with person_logged_in(self.person):
            self.assertFalse(self.bug.isMuted(self.person))
            create_initialized_view(
                self.bug.default_bugtask, name="+mute",
                form={'field.actions.mute': 'Mute bug mail'})
            self.assertTrue(self.bug.isMuted(self.person))

    def test_bug_mute_self_view_unmutes_bug(self):
        # The BugMuteSelfView unmutes bug mail for the current user when
        # its form is submitted and the bug was already muted.
        with person_logged_in(self.person):
            self.bug.mute(self.person, self.person)
            self.assertTrue(self.bug.isMuted(self.person))
            create_initialized_view(
                self.bug.default_bugtask, name="+mute",
                form={'field.actions.unmute': 'Unmute bug mail'})
            self.assertFalse(self.bug.isMuted(self.person))


class BugPortletSubscribersWithDetailsTests(TestCaseWithFactory):
    """Tests for IBug:+bug-portlet-subscribers-details view."""
    layer = LaunchpadFunctionalLayer

    def test_content_type(self):
        bug = self.factory.makeBug()

        # It works even for anonymous users, so no log-in is needed.
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        harness.view.render()

        self.assertEqual(
            harness.request.response.getHeader('content-type'),
            'application/json')

    def test_bugtask(self):
        # This view works for the bug-task as well, when it renders
        # the same data as for the bug.
        bug = self.factory.makeBug()

        # It works even for anonymous users, so no log-in is needed.
        harness_bug = LaunchpadFormHarness(
            bug, BugPortletSubscribersWithDetails)
        bug_content = harness_bug.view.render()

        # It works even for anonymous users, so no log-in is needed.
        harness_bugtask = LaunchpadFormHarness(
            bug.default_bugtask, BugPortletSubscribersWithDetails)
        bugtask_content = harness_bugtask.view.render()

        self.assertEqual(bug_content, bugtask_content)

    def _makeBugWithNoSubscribers(self):
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            # Unsubscribe the bug reporter to ensure we have no subscribers.
            bug.unsubscribe(bug.owner, bug.owner)
        return bug

    def test_data_no_subscriptions(self):
        bug = self._makeBugWithNoSubscribers()
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        self.assertEqual(dumps([]), harness.view.subscriber_data_js)

    def test_data_person_subscription(self):
        # subscriber_data_js returns JSON string of a list
        # containing all subscriber information needed for
        # subscribers_list.js subscribers loading.
        bug = self._makeBugWithNoSubscribers()
        subscriber = self.factory.makePerson(
            name='user', displayname='Subscriber Name')
        with person_logged_in(subscriber):
            bug.subscribe(subscriber, subscriber,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Subscriber Name',
                'is_team': False,
                'can_edit': False,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': 'Self-subscribed',
                },
            'subscription_level': "Lifecycle",
            }
        self.assertEqual(
            dumps([expected_result]), harness.view.subscriber_data_js)

    def test_data_person_subscription_other_subscriber(self):
        # Ensure subscriber_data_js does the correct thing when the person who
        # did the subscribing is someone else.
        bug = self._makeBugWithNoSubscribers()
        subscribed_by = self.factory.makePerson(
            name="someone", displayname='Someone')
        subscriber = self.factory.makePerson(
            name='user', displayname='Subscriber Name')
        with person_logged_in(subscriber):
            bug.subscribe(person=subscriber,
                          subscribed_by=subscribed_by,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Subscriber Name',
                'is_team': False,
                'can_edit': False,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': 'Subscribed by Someone (someone)',
                },
            'subscription_level': "Lifecycle",
            }
        self.assertEqual(
            dumps([expected_result]), harness.view.subscriber_data_js)

    def test_data_person_subscription_other_subscriber_query_count(self):
        # All subscriber data should be retrieved with a single query.
        bug = self._makeBugWithNoSubscribers()
        subscribed_by = self.factory.makePerson(
            name="someone", displayname='Someone')
        subscriber = self.factory.makePerson(
            name='user', displayname='Subscriber Name')
        with person_logged_in(subscriber):
            bug.subscribe(person=subscriber,
                          subscribed_by=subscribed_by,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        # Invoke the view method, ignoring the results.
        Store.of(bug).invalidate()
        with StormStatementRecorder() as recorder:
            harness.view.direct_subscriber_data(bug)
        self.assertThat(recorder, HasQueryCount(Equals(1)))

    def test_data_team_subscription(self):
        # For a team subscription, subscriber_data_js has is_team set
        # to true.
        bug = self._makeBugWithNoSubscribers()
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        subscriber = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner)
        with person_logged_in(subscriber.teamowner):
            bug.subscribe(subscriber, subscriber.teamowner,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'team',
                'display_name': 'Team Name',
                'is_team': True,
                'can_edit': False,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': \
                    'Subscribed by Team Owner (team-owner)',
                },
            'subscription_level': "Lifecycle",
            }
        self.assertEqual(
            dumps([expected_result]), harness.view.subscriber_data_js)

    def _test_data_private_team_subscription(self, authenticated_user):
        # For a private team subscription, the team name and url are rendered
        # for authenticated users.
        bug = self._makeBugWithNoSubscribers()

        # Set up a private direct subscriber.
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        direct_subscriber = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner,
            visibility=PersonVisibility.PRIVATE)
        with person_logged_in(teamowner):
            bug.subscribe(direct_subscriber, direct_subscriber.teamowner,
                          level=BugNotificationLevel.LIFECYCLE)

        # Set up a private indirect subscriber.
        indirect_teamowner = self.factory.makePerson(
            name="indirect-team-owner", displayname="Indirect Team Owner")
        indirect_subscriber = self.factory.makeTeam(
            name='indirect-team', displayname='Indirect Team Name',
            owner=indirect_teamowner, visibility=PersonVisibility.PRIVATE)
        with person_logged_in(indirect_teamowner):
            bug.default_bugtask.target.addSubscription(
                indirect_subscriber, indirect_teamowner)

        request = LaunchpadTestRequest()
        expected_result = []
        view = create_initialized_view(
            bug, '+bug-portlet-subscribers-details', request=request)
        if authenticated_user:
            any_person = self.factory.makePerson()
            login_person(any_person, request)
            api_request = IWebServiceClientRequest(request)
            naked_subscriber = removeSecurityProxy(direct_subscriber)
            naked_indirect_subscriber = removeSecurityProxy(
                indirect_subscriber)
            expected_result = [{
                'subscriber': {
                    'name': 'team',
                    'display_name': 'Team Name',
                    'is_team': True,
                    'can_edit': False,
                    'web_link': canonical_url(naked_subscriber,
                        rootsite='mainsite'),
                    'self_link': absoluteURL(naked_subscriber, api_request),
                    'display_subscribed_by': \
                        'Subscribed by Team Owner (team-owner)',
                    },
                'subscription_level': "Lifecycle",
                },
                {
                'subscriber': {
                    'name': 'indirect-team',
                    'display_name': 'Indirect Team Name',
                    'is_team': True,
                    'can_edit': False,
                    'web_link': canonical_url(naked_indirect_subscriber,
                        rootsite='mainsite'),
                    'self_link': absoluteURL(
                        naked_indirect_subscriber, api_request),
                    },
                'subscription_level': "Maybe",
                }]
        self.assertEqual(
            dumps(expected_result), view.subscriber_data_js)

    def test_data_private_team_subscription_authenticated_user(self):
        # For a logged in user, private team subscriptions are rendered.
        self._test_data_private_team_subscription(authenticated_user=True)

    def test_data_private_team_subscription_no_user(self):
        # For a user with no login, private team subscriptions are hidden.
        self._test_data_private_team_subscription(authenticated_user=False)

    def test_data_team_subscription_owner_looks(self):
        # For a team subscription, subscriber_data_js has can_edit
        # set to true for team owner.
        bug = self._makeBugWithNoSubscribers()
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        subscriber = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner)
        with person_logged_in(subscriber.teamowner):
            bug.subscribe(subscriber, subscriber.teamowner,
                          level=BugNotificationLevel.LIFECYCLE)
            harness = LaunchpadFormHarness(
                bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'team',
                'display_name': 'Team Name',
                'is_team': True,
                'can_edit': True,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': \
                    'Subscribed by Team Owner (team-owner)',
                },
            'subscription_level': "Lifecycle",
            }
        with person_logged_in(subscriber.teamowner):
            self.assertEqual(
                dumps([expected_result]), harness.view.subscriber_data_js)

    def test_data_team_subscription_member_looks(self):
        # For a team subscription, subscriber_data_js has can_edit
        # set to true for team member.
        bug = self._makeBugWithNoSubscribers()
        member = self.factory.makePerson()
        teamowner = self.factory.makePerson(
            name="team-owner", displayname="Team Owner")
        subscriber = self.factory.makeTeam(
            name='team', displayname='Team Name', owner=teamowner,
            members=[member])
        with person_logged_in(subscriber.teamowner):
            bug.subscribe(subscriber, subscriber.teamowner,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(
            bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'team',
                'display_name': 'Team Name',
                'is_team': True,
                'can_edit': True,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': \
                    'Subscribed by Team Owner (team-owner)',
                },
            'subscription_level': "Lifecycle",
            }
        with person_logged_in(subscriber.teamowner):
            self.assertEqual(
                dumps([expected_result]), harness.view.subscriber_data_js)

    def test_data_subscription_lp_admin(self):
        # For a subscription, subscriber_data_js has can_edit
        # set to true for a Launchpad admin.
        bug = self._makeBugWithNoSubscribers()
        member = self.factory.makePerson()
        subscriber = self.factory.makePerson(
            name='user', displayname='Subscriber Name')
        with person_logged_in(member):
            bug.subscribe(subscriber, subscriber,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(
            bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Subscriber Name',
                'is_team': False,
                'can_edit': True,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': 'Self-subscribed',
                },
            'subscription_level': "Lifecycle",
            }

        # Login as admin
        admin = getUtility(IPersonSet).find(ADMIN_EMAIL).any()
        with person_logged_in(admin):
            self.assertEqual(
                dumps([expected_result]), harness.view.subscriber_data_js)

    def test_data_person_subscription_subscriber(self):
        # For a subscription, subscriber_data_js has can_edit
        # set to true for the subscriber.
        bug = self._makeBugWithNoSubscribers()
        subscriber = self.factory.makePerson(
            name='user', displayname='Subscriber Name')
        subscribed_by = self.factory.makePerson(
            name='someone', displayname='Someone')
        with person_logged_in(subscriber):
            bug.subscribe(subscriber, subscribed_by,
                          level=BugNotificationLevel.LIFECYCLE)
        harness = LaunchpadFormHarness(bug, BugPortletSubscribersWithDetails)
        api_request = IWebServiceClientRequest(harness.request)

        expected_result = {
            'subscriber': {
                'name': 'user',
                'display_name': 'Subscriber Name',
                'is_team': False,
                'can_edit': True,
                'web_link': canonical_url(subscriber),
                'self_link': absoluteURL(subscriber, api_request),
                'display_subscribed_by': 'Subscribed by Someone (someone)',
                },
            'subscription_level': "Lifecycle",
            }
        with person_logged_in(subscribed_by):
            self.assertEqual(
                dumps([expected_result]), harness.view.subscriber_data_js)

    def test_data_person_subscription_user_excluded(self):
        # With the subscriber logged in, he is not included in the results.
        bug = self._makeBugWithNoSubscribers()
        subscriber = self.factory.makePerson(
            name='a-person', displayname='Subscriber Name')

        with person_logged_in(subscriber):
            bug.subscribe(subscriber, subscriber,
                          level=BugNotificationLevel.LIFECYCLE)
            harness = LaunchpadFormHarness(
                bug, BugPortletSubscribersWithDetails)
            self.assertEqual(dumps([]), harness.view.subscriber_data_js)
