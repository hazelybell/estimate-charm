# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for visibility of private teams.

Private teams restrict the visibility of their attributes to select
sets of users in order to prevent leaking confidential data.

Private teams restrict the viewing of the membership list
to team administrators, other members of the team, and Launchpad
administrators. However, private teams may place themselves in a public role
by subscribing to bug, blueprints or branches, or being bug assignee etc.
In these cases, users who can view those artifacts are allowed to know of a
private team's existence, and basic properties like name, displayname etc, by
being granted launchpad.limitedView permission.
"""

__metaclass__ = type

from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.app.enums import InformationType
from lp.registry.enums import (
    PersonVisibility,
    TeamMembershipPolicy,
    )
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.services.webapp.authorization import (
    check_permission,
    clear_cache,
    precache_permission_for_objects,
    )
from lp.services.webapp.interaction import ANONYMOUS
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login,
    login_celebrity,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestPrivateTeamVisibility(TestCaseWithFactory):
    """Tests for visibility of private teams."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPrivateTeamVisibility, self).setUp()
        self.priv_owner = self.factory.makePerson(name="priv-owner")
        self.priv_member = self.factory.makePerson(name="priv-member")
        self.priv_team = self.factory.makeTeam(
            owner=self.priv_owner, name="priv-team",
            visibility=PersonVisibility.PRIVATE,
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        login_person(self.priv_owner)
        self.priv_team.addMember(self.priv_member, reviewer=self.priv_owner)

    def test_limitedView_visible_attributes(self):
        """Users with LimitedView can know identifying information like name,
        displayname, and unique_name, but cannot know other information like
        team members.
        """
        some_person = self.factory.makePerson()
        request = LaunchpadTestRequest()
        # First login as a person who has limitedView permission.
        precache_permission_for_objects(
            request, 'launchpad.LimitedView', [self.priv_team])
        login_person(some_person, participation=request)
        self.assertEqual('priv-team', self.priv_team.name)
        self.assertEqual('Priv Team', self.priv_team.displayname)
        self.assertEqual(
            'Priv Team (priv-team)', self.priv_team.unique_displayname)
        self.assertIsNone(self.priv_team.icon)
        self.assertRaises(Unauthorized, getattr, self.priv_team, 'allmembers')

    def test_anonymous_users_have_no_limitedView_permission(self):
        login(ANONYMOUS)
        self.assertFalse(
            check_permission('launchpad.LimitedView', self.priv_team))

    def test_some_person_cannot_see_team_details(self):
        # A person who is not in the team cannot see the membership and cannot
        # see other details of the team, such as the name.
        some_person = self.factory.makePerson()
        with person_logged_in(some_person):
            self.assertRaises(Unauthorized, getattr, self.priv_team, 'name')
            self.assertRaises(
                Unauthorized, getattr, self.priv_team, 'activemembers')

    def test_team_owner_can_see_members(self):
        login_person(self.priv_owner)
        members = self.priv_team.activemembers
        self.assertContentEqual(
            ['priv-member', 'priv-owner'],
            [member.name for member in members])

    def test_team_member_can_see_members(self):
        login_person(self.priv_member)
        members = self.priv_team.activemembers
        self.assertContentEqual(
            ['priv-member', 'priv-owner'],
            [member.name for member in members])

    def test_commercial_admin_can_see_team_and_members(self):
        login_celebrity('commercial_admin')
        self.assertTrue(check_permission('launchpad.View', self.priv_team))
        team_membership = self.priv_member.team_memberships[0]
        self.assertTrue(check_permission('launchpad.View', team_membership))

    def team_owner_can_see_team_details(self):
        """A team owner must be able to access the team even if they are not a
        team member. When a team is created, the owner is automatically made
        an admin member. So we revoke that membership and check that they
        still have access.
        """
        membership_set = getUtility(ITeamMembershipSet)
        login_person(self.priv_owner)
        tm = membership_set.getByPersonAndTeam(
            self.priv_owner, self.priv_team)
        tm.setStatus(TeamMembershipStatus.DEACTIVATED, self.priv_owner)
        self.assertFalse(self.priv_owner.inTeam(self.priv_team))
        self.assertTrue(check_permission('launchpad.View', self.priv_team))

    def test_invited_team_admins_can_see_team(self):
        """Public teams can join private teams.  When adding one team to
        another the team is invited to join and that invitation must be
        accepted by one of the invited team's admins.  Normally the admin of
        the invited team is not a member of the private team and therefore
        cannot even see the page to accept the invitation!  To resolve that
        situation the rules for viewing a private team include admins of
        invited teams.
        """
        pub_owner = self.factory.makePerson(name="pub-owner")
        pub_member = self.factory.makePerson(name="pub-member")
        pub_team = self.factory.makeTeam(owner=pub_owner, name="pubteam")
        with person_logged_in(pub_owner):
            pub_team.addMember(pub_member, reviewer=pub_owner)
            # At this point the public team owner cannot see the priv-team's
            # bits.
            self.assertRaises(Unauthorized, getattr, self.priv_team, 'name')
        login_person(self.priv_owner)
        self.priv_team.addMember(pub_team, reviewer=self.priv_owner)

        # The public team is not yet a member of the priv-team.
        self.assertFalse(pub_team in self.priv_team.activemembers)
        self.assertFalse(pub_owner in self.priv_team.activemembers)

        # The public team's owner can now see the priv-team's bits since his
        # team has been invited to join.
        login_person(pub_owner)
        self.assertEqual('priv-team', self.priv_team.name)

        # But a non-admin member of the public team still cannot see anything
        # about the team.
        login_person(pub_member)
        self.assertRaises(Unauthorized, getattr, self.priv_team, 'name')

    def _check_permission(self, user, visible):
        login_person(user)
        self.assertEqual(
            visible,
            check_permission('launchpad.LimitedView', self.priv_team))
        clear_cache()

    def _test_subscriber_to_branch_owned_by_team(self, private=True):
        """A person with visibility to any of the branches owned by the
        private team will be granted limited view permission on the team.

        For private branches, a user needs to be subscribed to the branch for
        the branch (and hence team) to be visible.
        """
        login_person(self.priv_owner)
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        private_team_branch = self.factory.makeBranch(
            owner=self.priv_team, information_type=information_type)
        some_person = self.factory.makePerson()
        # All users can see public branches, so in that case, the team is
        # now visible, else team is still not visible.
        self._check_permission(some_person, not private)
        # Subscribe the user to the branch.
        login_person(self.priv_owner)
        self.factory.makeBranchSubscription(
            branch=private_team_branch, person=some_person,
            subscribed_by=self.priv_owner)
        # The team is now visible.
        self._check_permission(some_person, True)

    def test_subscriber_to_public_branch_owned_by_team(self):
        self._test_subscriber_to_branch_owned_by_team(private=False)

    def test_subscriber_to_private_branch_owned_by_team(self):
        self._test_subscriber_to_branch_owned_by_team()

    def _test_subscriber_to_branch_subscribed_to_by_team(self, private=True):
        """A person with visibility to any of the branches subscribed to by
        the private team will be granted limited view permission on the team.
        """
        branch_owner = self.factory.makePerson()
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        private_branch = self.factory.makeBranch(
            owner=branch_owner, information_type=information_type)
        some_person = self.factory.makePerson()
        # Initially no visibility.
        self._check_permission(some_person, False)
        # Subscribe the team to the branch.
        login_person(branch_owner)
        self.factory.makeBranchSubscription(
            branch=private_branch, person=self.priv_team,
            subscribed_by=branch_owner)
        # All users can see public branches, so in that case, the team is
        # now visible, else team is still not visible.
        self._check_permission(some_person, not private)
        # Subscribe the user to the branch.
        login_person(branch_owner)
        self.factory.makeBranchSubscription(
            branch=private_branch, person=some_person,
            subscribed_by=branch_owner)
        # The team is now visible.
        self._check_permission(some_person, True)

    def test_subscriber_to_public_branch_subscribed_to_by_team(self):
        self._test_subscriber_to_branch_subscribed_to_by_team(private=False)

    def test_subscriber_to_private_branch_subscribed_to_by_team(self):
        self._test_subscriber_to_branch_subscribed_to_by_team()

    def _test_teams_with_branch_review_requests(self, private=True):
        # Users who can see a branch can also see private teams for which
        # reviews have been requested.

        # Make the merge proposal.
        login_person(self.priv_owner)
        product = self.factory.makeProduct()
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        target_branch = self.factory.makeBranch(
            owner=self.priv_owner, product=product,
            information_type=information_type)
        source_branch = self.factory.makeBranch(
            owner=self.priv_owner, product=product)
        self.factory.makeBranchMergeProposal(
            source_branch=source_branch, target_branch=target_branch,
            reviewer=self.priv_team, registrant=self.priv_owner)

        # All users can see public branches, so in that case, the team is
        # now visible, else team is still not visible.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, not private)
        # Subscribe the user to the branch.
        login_person(self.priv_owner)
        self.factory.makeBranchSubscription(
            branch=target_branch, person=some_person,
            subscribed_by=self.priv_owner)
        # The team is now visible.
        self._check_permission(some_person, True)

    def test_teams_with_public_branch_review_requests(self, private=True):
        self._test_teams_with_branch_review_requests(private=False)

    def test_teams_with_private_branch_review_requests(self, private=True):
        self._test_teams_with_branch_review_requests()

    def test_private_ppa_subscriber(self):
        # Subscribers to the team's private PPA have limited view permission.
        login_person(self.priv_owner)
        archive = self.factory.makeArchive(private=True, owner=self.priv_team)
        # Initially no visibility.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, False)
        # Subscribe the user.
        login_person(self.priv_owner)
        archive.newSubscription(
            some_person, registrant=self.priv_owner)
        # The team is now visible.
        self._check_permission(some_person, True)

    def test_team_subscribed_to_blueprint(self):
        # Users can see teams subscribed to blueprints.
        spec = self.factory.makeSpecification()
        # Initially no visibility.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, False)
        # Subscribe the private team to the spec.
        login_person(spec.owner)
        spec.subscribe(self.priv_team, spec.owner)
        self._check_permission(some_person, True)

    def _test_team_subscribed_to_bug(self, private=True):
        # Users can see teams subscribed to bugs.
        bug_owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=bug_owner)
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        bug = self.factory.makeBug(
            owner=bug_owner, target=product,
            information_type=information_type)
        # Initially no visibility.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, False)
        clear_cache()
        # Subscribe the private team to the bug.
        login_person(bug_owner)
        bug.subscribe(self.priv_team, bug_owner)
        # All users can see public bugs, so in that case, the team is
        # now visible, else team is still not visible.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, not private)
        # Subscribe the user to the bug.
        login_person(bug_owner)
        bug.subscribe(some_person, bug_owner)
        # The team is now visible.
        self._check_permission(some_person, True)

    def test_team_subscribed_to_public_bug(self):
        self._test_team_subscribed_to_bug(private=False)

    def test_team_subscribed_to_private_bug(self):
        self._test_team_subscribed_to_bug()

    def _test_team_assigned_to_bug(self, private=True):
        # Users can see teams assigned to bugs.
        bug_owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=bug_owner)
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        bug = self.factory.makeBug(
            owner=bug_owner, target=product,
            information_type=information_type)
        # Initially no visibility.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, False)
        clear_cache()
        # Assign the private team to a bugtask.
        login_person(bug_owner)
        bug.default_bugtask.transitionToAssignee(self.priv_team)
        # All users can see public bugs, so in that case, the team is
        # now visible, else team is still not visible.
        some_person = self.factory.makePerson()
        self._check_permission(some_person, not private)
        # Subscribe the user to the bug.
        login_person(bug_owner)
        bug.subscribe(some_person, bug_owner)
        # The team is now visible.
        self._check_permission(some_person, True)

    def test_team_assigned_to_public_bug(self):
        self._test_team_assigned_to_bug(private=False)

    def test_team_assigned_to_private_bug(self):
        self._test_team_assigned_to_bug()
