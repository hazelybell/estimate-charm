# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import httplib

from lazr.restfulclient.errors import (
    HTTPError,
    Unauthorized,
    )
import transaction

from lp.app.enums import InformationType
from lp.registry.enums import (
    PersonVisibility,
    TeamMembershipPolicy,
    )
from lp.testing import (
    ExpectedException,
    launchpadlib_for,
    login_person,
    logout,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    AppServerLayer,
    DatabaseFunctionalLayer,
    )


class TestTeamJoining(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_restricted_rejects_membership(self):
        # Calling person.join with a team that has a restricted membership
        # membership policy should raise an HTTP error with BAD_REQUEST
        self.person = self.factory.makePerson(name='test-person')
        self.team = self.factory.makeTeam(name='test-team')
        login_person(self.team.teamowner)
        self.team.membership_policy = TeamMembershipPolicy.RESTRICTED
        logout()

        launchpad = launchpadlib_for("test", self.person)
        person = launchpad.people['test-person']
        api_error = self.assertRaises(
            HTTPError,
            person.join,
            team='test-team')
        self.assertEqual(httplib.BAD_REQUEST, api_error.response.status)

    def test_open_accepts_membership(self):
        # Calling person.join with a team that has an open membership
        # membership policy should add that that user to the team.
        self.person = self.factory.makePerson(name='test-person')
        owner = self.factory.makePerson()
        self.team = self.factory.makeTeam(name='test-team', owner=owner)
        login_person(owner)
        self.team.membership_policy = TeamMembershipPolicy.OPEN
        logout()

        launchpad = launchpadlib_for("test", self.person)
        test_person = launchpad.people['test-person']
        test_team = launchpad.people['test-team']
        test_person.join(team=test_team.self_link)
        login_person(owner)
        self.assertEqual(
            ['test-team'],
            [membership.team.name
                for membership in self.person.team_memberships])
        logout()


class TeamObsoleteAPITestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_newTeam_obsolete_subscription_policy(self):
        # The subscription_policy kwarg can be passed instead of
        # membership_policy to suppport 1.0 API
        owner = self.factory.makePerson()
        launchpad = launchpadlib_for("test", owner)
        team = launchpad.people.newTeam(
            name='pting', display_name='Pting',
            subscription_policy="Open Team")
        self.assertEqual("Open Team", team.subscription_policy)
        self.assertEqual("Open Team", team.membership_policy)

    def test_subscription_policy_is_membership_policy(self):
        # The subcription_policy property wraps membership_policy.
        owner = self.factory.makePerson()
        self.factory.makeTeam(
            owner=owner, name='pting',
            membership_policy=TeamMembershipPolicy.MODERATED)
        launchpad = launchpadlib_for("test", owner)
        team = launchpad.people['pting']
        self.assertEqual("Moderated Team", team.subscription_policy)
        self.assertEqual("Moderated Team", team.membership_policy)
        team.subscription_policy = "Open Team"
        team.lp_save()
        self.assertEqual("Open Team", team.subscription_policy)
        self.assertEqual("Open Team", team.membership_policy)


class TestTeamLimitedViewAccess(TestCaseWithFactory):
    """Tests for team limitedView access via the webservice."""

    layer = AppServerLayer

    def setUp(self):
        super(TestTeamLimitedViewAccess, self).setUp()

        # Make a private team.
        team_owner = self.factory.makePerson()
        db_team = self.factory.makeTeam(
            name='private-team', owner=team_owner,
            visibility=PersonVisibility.PRIVATE,
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        # Create a P3A for the team.
        with person_logged_in(team_owner):
            self.factory.makeArchive(
                owner=db_team, private=True, name='private-ppa')
        # Create an authorised user with limitedView permission on the team.
        # We do that by subscribing the team and the user to the same
        # private bug.
        self.bug_owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            owner=self.bug_owner, information_type=InformationType.USERDATA)
        self.authorised_person = self.factory.makePerson()
        with person_logged_in(self.bug_owner):
            bug.subscribe(db_team, self.bug_owner)
            bug.subscribe(self.authorised_person, self.bug_owner)
            self.bug_id = bug.id
        self.factory.makeProduct(name='some-product', bug_supervisor=db_team)
        transaction.commit()

    def test_unauthorised_cannot_see_team(self):
        # Test that an unauthorised user cannot see the team.
        some_person = self.factory.makePerson()
        launchpad = self.factory.makeLaunchpadService(some_person)
        with ExpectedException(KeyError, '.*'):
            launchpad.people['private-team']

    def test_unauthorised_cannot_navigate_to_team_details(self):
        # Test that a user cannot get a team reference from another model
        # object and use that to access unauthorised details.
        some_person = self.factory.makePerson()
        launchpad = self.factory.makeLaunchpadService(some_person)
        team = launchpad.projects['some-product'].bug_supervisor
        failure_regex = '.*permission to see.*'
        with ExpectedException(ValueError, failure_regex):
            print team.name

    def test_authorised_user_can_see_team_limitedView_details(self):
        # Test that a user with limitedView permission can access the team and
        # see attributes/methods on the IPersonLimitedView interface.
        launchpad = self.factory.makeLaunchpadService(self.authorised_person)
        team = launchpad.people['private-team']
        self.assertEqual('private-team', team.name)
        ppa = team.getPPAByName(name='private-ppa')
        self.assertEqual('private-ppa', ppa.name)

    def test_authorised_user_cannot_see_restricted_team_details(self):
        # Test that a user with limitedView permission on a team cannot see
        # prohibited detail, like attributes on IPersonViewRestricted.
        launchpad = self.factory.makeLaunchpadService(self.authorised_person)
        team = launchpad.people['private-team']
        self.assertIn(':redacted', team.description)
        failure_regex = '(.|\n)*api_activemembers.*launchpad.View(.|\n)*'
        with ExpectedException(Unauthorized, failure_regex):
            members = team.members
            print members.total_size
