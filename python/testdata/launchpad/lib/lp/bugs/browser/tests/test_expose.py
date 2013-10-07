# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for helpers that expose data about a user to on-page JavaScript."""

from operator import itemgetter

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.interfaces import (
    IJSONRequestCache,
    IWebServiceClientRequest,
    )
from testtools.matchers import (
    Equals,
    KeysEqual,
    )
from zope.interface import implements
from zope.traversing.browser import absoluteURL

from lp.bugs.browser.structuralsubscription import (
    expose_enum_to_js,
    expose_user_administered_teams_to_js,
    expose_user_subscriptions_to_js,
    )
from lp.registry.interfaces.person import PersonVisibility
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.registry.model.person import Person
from lp.services.database.interfaces import IStore
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.webapp.authorization import clear_cache
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import (
    Contains,
    HasQueryCount,
    )


class FakeRequest:
    """A request that implements some interfaces so adapting returns itself.
    """
    implements(IWebServiceClientRequest, IJSONRequestCache)

    def __init__(self):
        self.objects = {}


class FakeTeam:
    """A faux team that just implements enough for the test."""

    def __init__(self, title):
        self.title = title


class FakeUser:
    """A faux user that has a hard-coded set of administered teams."""

    administrated_teams = [FakeTeam('Team One'), FakeTeam('Team Two')]

    def getAdministratedTeams(self):
        return self.administrated_teams


def fake_absoluteURL(ob, request):
    """An absoluteURL implementation that doesn't require ZTK for testing."""
    return 'http://example.com/' + ob.title.replace(' ', '')


class DemoEnum(DBEnumeratedType):
    """An example enum.
    """

    UNO = DBItem(1, """One""")

    DOS = DBItem(2, """Two""")

    TRES = DBItem(3, """Three""")


class DemoContext:

    return_value = None

    def __init__(self, user):
        self.user = user

    def userHasBugSubscriptions(self, user):
        assert user is self.user
        return self.return_value


class TestExposeAdministeredTeams(TestCaseWithFactory):
    """Test the function to expose administered team."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestExposeAdministeredTeams, self).setUp()
        self.request = FakeRequest()
        self.user = self.factory.makePerson()

    def _setup_teams(self, owner):
        self.bug_super_team = self.factory.makeTeam(
            name='bug-supervisor-team', owner=owner)
        bug_super_subteam = self.factory.makeTeam(
            name='bug-supervisor-sub-team', owner=owner)
        self.factory.makeTeam(
            name='unrelated-team', owner=owner)
        with person_logged_in(owner):
            bug_super_subteam.join(
                self.bug_super_team, self.bug_super_team.teamowner)

    def _sort(self, team_info, key='title'):
        return sorted(team_info, key=itemgetter(key))

    def test_teams_preferredemail(self):
        # The function includes information about whether the team has a
        # preferred email.  This gives us information in JavaScript that tells
        # us whether the subscription can be muted for a particular member of
        # the team.  (If the team has a preferredemail, muting is not
        # possible).
        context = self.factory.makeProduct(owner=self.user)
        self.factory.makeTeam(name='team-1', owner=self.user)
        team2 = self.factory.makeTeam(name='team-2', owner=self.user)
        self.factory.makeEmail('foo@example.net',
                               team2,
                               email_status=EmailAddressStatus.PREFERRED)

        expose_user_administered_teams_to_js(self.request, self.user, context,
            absoluteURL=fake_absoluteURL)
        team_info = self._sort(self.request.objects['administratedTeams'])
        self.assertThat(
            team_info[0]['title'], Equals(u'\u201cTeam 1\u201d team'))
        self.assertThat(team_info[0]['has_preferredemail'], Equals(False))
        self.assertThat(
            team_info[1]['title'],
            Equals(u'\u201cTeam 2\u201d team'))
        self.assertThat(team_info[1]['has_preferredemail'], Equals(True))

    def test_teams_for_non_distro(self):
        # The expose_user_administered_teams_to_js function loads some data
        # about the teams the requesting user administers into the response to
        # be made available to JavaScript.

        context = self.factory.makeProduct(owner=self.user)
        self._setup_teams(self.user)

        expose_user_administered_teams_to_js(self.request, self.user, context,
            absoluteURL=fake_absoluteURL)

        # The team information should have been added to the request.
        self.assertThat(self.request.objects, Contains('administratedTeams'))
        team_info = self._sort(self.request.objects['administratedTeams'])
        # Since there are three teams, there should be three items in the
        # list of team info.
        expected_number_teams = 3
        self.assertThat(len(team_info), Equals(expected_number_teams))
        # The items info consist of a dictionary with link and title keys.
        for i in range(expected_number_teams):
            self.assertThat(
                team_info[i],
                KeysEqual('has_preferredemail', 'link', 'title', 'url'))
        # The link is the title of the team.
        self.assertThat(
            team_info[0]['title'],
            Equals(u'\u201cBug Supervisor Sub Team\u201d team'))
        self.assertThat(
            team_info[1]['title'],
            Equals(u'\u201cBug Supervisor Team\u201d team'))
        self.assertThat(
            team_info[2]['title'], Equals(u'\u201cUnrelated Team\u201d team'))
        # The link is the API link to the team.
        self.assertThat(team_info[0]['link'],
            Equals(u'http://example.com/\u201cBugSupervisorSubTeam\u201dteam'))

    def test_query_count(self):
        # The function issues a constant number of queries regardless of
        # team count.
        login_person(self.user)
        context = self.factory.makeProduct(owner=self.user)
        self._setup_teams(self.user)

        IStore(Person).invalidate()
        clear_cache()
        with StormStatementRecorder() as recorder:
            expose_user_administered_teams_to_js(
                self.request, self.user, context,
                absoluteURL=fake_absoluteURL)
        self.assertThat(recorder, HasQueryCount(Equals(4)))

        # Create some new public teams owned by the user, and a private
        # team administered by the user.
        for i in range(3):
            self.factory.makeTeam(owner=self.user)
        pt = self.factory.makeTeam(
            visibility=PersonVisibility.PRIVATE, members=[self.user])
        with person_logged_in(pt.teamowner):
            pt.addMember(
                self.user, pt.teamowner, status=TeamMembershipStatus.ADMIN)

        IStore(Person).invalidate()
        clear_cache()
        del IJSONRequestCache(self.request).objects['administratedTeams']
        with StormStatementRecorder() as recorder:
            expose_user_administered_teams_to_js(
                self.request, self.user, context,
                absoluteURL=fake_absoluteURL)
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_expose_user_administered_teams_to_js__uses_cached_teams(self):
        # The function expose_user_administered_teams_to_js uses a
        # cached list of administrated teams.
        context = self.factory.makeProduct(owner=self.user)
        self._setup_teams(self.user)

        # The first call requires one query to retrieve the administrated
        # teams.
        with StormStatementRecorder() as recorder:
            expose_user_administered_teams_to_js(
                self.request, self.user, context,
                absoluteURL=fake_absoluteURL)
        statements_for_admininstrated_teams = [
            statement for statement in recorder.statements
            if statement.startswith("SELECT *")]
        self.assertEqual(1, len(statements_for_admininstrated_teams))

        # Calling the function a second time does not require an
        # SQL call to retrieve the administrated teams.
        with StormStatementRecorder() as recorder:
            expose_user_administered_teams_to_js(
                self.request, self.user, context,
                absoluteURL=fake_absoluteURL)
        statements_for_admininstrated_teams = [
            statement for statement in recorder.statements
            if statement.startswith("SELECT *")]
        self.assertEqual(0, len(statements_for_admininstrated_teams))

    def test_teams_owned_but_not_joined_are_not_included(self):
        context = self.factory.makeProduct(owner=self.user)
        team = self.factory.makeTeam(
            name='bug-supervisor-team', owner=self.user)
        with person_logged_in(self.user):
            self.user.leave(team)
        expose_user_administered_teams_to_js(self.request, self.user, context,
            absoluteURL=fake_absoluteURL)
        team_info = self.request.objects['administratedTeams']
        self.assertEquals(len(team_info), 0)

    def test_teams_for_distro_with_bug_super(self):
        self._setup_teams(self.user)
        context = self.factory.makeDistribution(
            owner=self.user, members=self.bug_super_team)
        with person_logged_in(self.user):
            context.bug_supervisor = self.bug_super_team

        expose_user_administered_teams_to_js(self.request, self.user, context,
            absoluteURL=fake_absoluteURL)

        # The team information should have been added to the request.
        self.assertThat(self.request.objects, Contains('administratedTeams'))
        team_info = self._sort(self.request.objects['administratedTeams'])

        # Since the distro only returns teams that are members of the bug
        # supervisor team, we only expect two.
        expected_number_teams = 2
        self.assertThat(len(team_info), Equals(expected_number_teams))
        # The items info consist of a dictionary with link and title keys.
        for i in range(expected_number_teams):
            self.assertThat(
                team_info[i],
                KeysEqual('has_preferredemail', 'link', 'title', 'url'))
        # The link is the title of the team.
        self.assertThat(
            team_info[0]['title'],
            Equals(u'\u201cBug Supervisor Sub Team\u201d team'))
        self.assertThat(
            team_info[1]['title'],
            Equals(u'\u201cBug Supervisor Team\u201d team'))
        # The link is the API link to the team.
        self.assertThat(team_info[0]['link'],
            Equals(u'http://example.com/\u201cBugSupervisorSubTeam\u201dteam'))

    def test_teams_for_distro_with_no_bug_super(self):
        self._setup_teams(self.user)
        context = self.factory.makeDistribution(
            owner=self.user, members=self.bug_super_team)

        expose_user_administered_teams_to_js(self.request, self.user, context,
            absoluteURL=fake_absoluteURL)

        # The team information should have been added to the request.
        self.assertThat(self.request.objects, Contains('administratedTeams'))
        team_info = self._sort(self.request.objects['administratedTeams'])

        # Since the distro has no bug supervisor set, all administered teams
        # are returned.
        expected_number_teams = 3
        self.assertThat(len(team_info), Equals(expected_number_teams))
        # The items info consist of a dictionary with link and title keys.
        for i in range(expected_number_teams):
            self.assertThat(
                team_info[i],
                KeysEqual('has_preferredemail', 'link', 'title', 'url'))
        # The link is the title of the team.
        self.assertThat(
            team_info[0]['title'],
            Equals(u'\u201cBug Supervisor Sub Team\u201d team'))
        self.assertThat(
            team_info[1]['title'],
            Equals(u'\u201cBug Supervisor Team\u201d team'))
        self.assertThat(
            team_info[2]['title'], Equals(u'\u201cUnrelated Team\u201d team'))
        # The link is the API link to the team.
        self.assertThat(team_info[0]['link'],
            Equals(u'http://example.com/\u201cBugSupervisorSubTeam\u201dteam'))


class TestStructuralSubscriptionHelpers(TestCase):
    """Test the helpers used to add data that the on-page JS can use."""

    def test_expose_enum_to_js(self):
        # Loads the titles of an enum into the response.
        request = FakeRequest()
        expose_enum_to_js(request, DemoEnum, 'demo')
        self.assertEqual(request.objects['demo'], ['One', 'Two', 'Three'])

    def test_empty_expose_user_subscriptions_to_js(self):
        # This function is tested in integration more fully below, but we
        # can easily test the empty case with our stubs.
        request = FakeRequest()
        user = FakeUser()
        subscriptions = []
        expose_user_subscriptions_to_js(user, subscriptions, request)
        self.assertEqual(request.objects['subscription_info'], [])


class TestIntegrationExposeUserSubscriptionsToJS(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_team_admin_subscription(self):
        # Make a team subscription where the user is an admin, and see what
        # we record.
        user = self.factory.makePerson()
        target = self.factory.makeProduct()
        request = LaunchpadTestRequest()
        team = self.factory.makeTeam()
        with person_logged_in(team.teamowner):
            team.addMember(user, team.teamowner,
                           status=TeamMembershipStatus.ADMIN)
            sub = target.addBugSubscription(team, team.teamowner)
        expose_user_subscriptions_to_js(user, [sub], request)
        info = IJSONRequestCache(request).objects['subscription_info']
        self.assertEqual(len(info), 1)  # One target.
        target_info = info[0]
        self.assertEqual(target_info['target_title'], target.title)
        self.assertEqual(
            target_info['target_url'], canonical_url(
                target, rootsite='mainsite'))
        self.assertEqual(len(target_info['filters']), 1)  # One filter.
        filter_info = target_info['filters'][0]
        self.assertEqual(filter_info['filter'], sub.bug_filters[0])
        self.assertTrue(filter_info['subscriber_is_team'])
        self.assertTrue(filter_info['user_is_team_admin'])
        self.assertTrue(filter_info['can_mute'])
        self.assertFalse(filter_info['is_muted'])
        self.assertEqual(filter_info['subscriber_title'], team.title)
        self.assertEqual(
            filter_info['subscriber_link'],
            absoluteURL(team, IWebServiceClientRequest(request)))
        self.assertEqual(
            filter_info['subscriber_url'],
            canonical_url(team, rootsite='mainsite'))

    def test_team_member_subscription(self):
        # Make a team subscription where the user is not an admin, and
        # see what we record.
        user = self.factory.makePerson()
        target = self.factory.makeProduct()
        request = LaunchpadTestRequest()
        team = self.factory.makeTeam(members=[user])
        with person_logged_in(team.teamowner):
            sub = target.addBugSubscription(team, team.teamowner)
        expose_user_subscriptions_to_js(user, [sub], request)
        info = IJSONRequestCache(request).objects['subscription_info']
        filter_info = info[0]['filters'][0]
        self.assertTrue(filter_info['subscriber_is_team'])
        self.assertFalse(filter_info['user_is_team_admin'])
        self.assertTrue(filter_info['can_mute'])
        self.assertFalse(filter_info['is_muted'])
        self.assertEqual(filter_info['subscriber_title'], team.title)
        self.assertEqual(
            filter_info['subscriber_link'],
            absoluteURL(team, IWebServiceClientRequest(request)))
        self.assertEqual(
            filter_info['subscriber_url'],
            canonical_url(team, rootsite='mainsite'))

    def test_muted_team_member_subscription(self):
        # Show that a muted team subscription is correctly represented.
        user = self.factory.makePerson()
        target = self.factory.makeProduct()
        request = LaunchpadTestRequest()
        team = self.factory.makeTeam(members=[user])
        with person_logged_in(team.teamowner):
            sub = target.addBugSubscription(team, team.teamowner)
        sub.bug_filters.one().mute(user)
        expose_user_subscriptions_to_js(user, [sub], request)
        info = IJSONRequestCache(request).objects['subscription_info']
        filter_info = info[0]['filters'][0]
        self.assertTrue(filter_info['can_mute'])
        self.assertTrue(filter_info['is_muted'])

    def test_self_subscription(self):
        # Make a subscription directly for the user and see what we record.
        user = self.factory.makePerson()
        target = self.factory.makeProduct()
        request = LaunchpadTestRequest()
        with person_logged_in(user):
            sub = target.addBugSubscription(user, user)
        expose_user_subscriptions_to_js(user, [sub], request)
        info = IJSONRequestCache(request).objects['subscription_info']
        filter_info = info[0]['filters'][0]
        self.assertFalse(filter_info['subscriber_is_team'])
        self.assertEqual(filter_info['subscriber_title'], user.title)
        self.assertFalse(filter_info['can_mute'])
        self.assertFalse(filter_info['is_muted'])
        self.assertEqual(
            filter_info['subscriber_link'],
            absoluteURL(user, IWebServiceClientRequest(request)))
        self.assertEqual(
            filter_info['subscriber_url'],
            canonical_url(user, rootsite='mainsite'))

    def test_expose_user_subscriptions_to_js__uses_cached_teams(self):
        # The function expose_user_subscriptions_to_js() uses a
        # cached list of administrated teams.
        user = self.factory.makePerson()
        target = self.factory.makeProduct()
        request = LaunchpadTestRequest()
        with person_logged_in(user):
            sub = target.addBugSubscription(user, user)

        # The first call requires one query to retrieve the administrated
        # teams.
        with StormStatementRecorder() as recorder:
            expose_user_subscriptions_to_js(user, [sub], request)
        statements_for_admininstrated_teams = [
            statement for statement in recorder.statements
            if statement.startswith("SELECT *")]
        self.assertEqual(1, len(statements_for_admininstrated_teams))

        # Calling the function a second time does not require an
        # SQL call to retrieve the administrated teams.
        with person_logged_in(user):
            with StormStatementRecorder() as recorder:
                expose_user_subscriptions_to_js(user, [sub], request)
        statements_for_admininstrated_teams = [
            statement for statement in recorder.statements
            if statement.startswith("SELECT *")]
        self.assertEqual(0, len(statements_for_admininstrated_teams))
