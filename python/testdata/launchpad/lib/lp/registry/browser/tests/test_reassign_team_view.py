# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for TeamReassignmentView view code."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.person import PersonVisibility
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import setupBrowserForUser
from lp.testing.views import create_initialized_view


class TestTeamReassignmentView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_non_owner_unauthorised(self):
        # Only team owners can reassign team ownership.
        team = self.factory.makeTeam()
        any_person = self.factory.makePerson()
        reassign_url = canonical_url(team, view_name='+reassign')
        browser = setupBrowserForUser(any_person)
        self.assertRaises(Unauthorized, browser.open, reassign_url)

    def test_view_navigation_links(self):
        # Check the navigation links get get to the change owner page.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(owner=owner)
        edit_url = canonical_url(team, view_name='+edit')
        reassign_url = canonical_url(team, view_name='+reassign')
        browser = setupBrowserForUser(owner)
        browser.open(edit_url)
        browser.getLink('Change owner').click()
        self.assertEqual(reassign_url, browser.url)

    def test_owner_change(self):
        # Test that the team owner change succeeds properly.
        orig_owner = self.factory.makePerson()
        new_owner = self.factory.makePerson(name='new-owner')
        team = self.factory.makeTeam(owner=orig_owner)

        form = {
            'field.owner': 'new-owner',
            'field.existing': 'existing',
            'field.actions.change': 'Change',
            }
        login_person(orig_owner)
        view = create_initialized_view(
            team, '+reassign', form=form, principal=orig_owner)
        self.assertEqual(
            canonical_url(team),
            view.request.response.getHeader('Location'))
        self.assertEqual(0, len(view.request.response.notifications))
        self.assertEqual(new_owner, team.teamowner)
        self.assertFalse(orig_owner.inTeam(team.teamowner))
        # The old owner is made a team administrator.
        self.assertIn(orig_owner, team.adminmembers)

    def test_private_team_becomes_hidden_after_owner_change(self):
        """ Reassign a private team which the user cannot see afterwards.

        A user can edit a team if they are the owner. However, if they are not
        an active member, they will not be able to see the team after
        assigning a new owner. We don't want any Unauthorised error to break
        things, so the user is instead redirected to their own home page with
        a suitable message.
        """
        orig_owner = self.factory.makePerson()
        new_owner = self.factory.makePerson(name='new-owner')
        private_team = self.factory.makeTeam(
            owner=orig_owner, visibility=PersonVisibility.PRIVATE)
        login_person(orig_owner)
        # The owner is automatically made an admin member so we deactivate
        # their membership.
        membership_set = getUtility(ITeamMembershipSet)
        tm = membership_set.getByPersonAndTeam(orig_owner, private_team)
        tm.setStatus(TeamMembershipStatus.DEACTIVATED, orig_owner)

        form = {
            'field.owner': 'new-owner',
            'field.existing': 'existing',
            'field.actions.change': 'Change',
            }
        view = create_initialized_view(
            private_team, '+reassign', form=form, principal=orig_owner)
        naked_team = removeSecurityProxy(private_team)
        self.assertEqual(new_owner, naked_team.teamowner)
        self.assertEqual(
            canonical_url(orig_owner),
            view.request.response.getHeader('Location'))
        self.assertEqual(1, len(view.request.response.notifications))
        notification = view.request.response.notifications[0].message
        self.assertEqual(
            "The owner of team %s was successfully changed but you are "
            "now no longer authorised to view the team."
                % naked_team.displayname,
            notification)


class TestTeamReassignmentViewErrors(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def _makeTeams(self):
        owner = self.factory.makePerson()
        login_person(owner)
        a_team = self.factory.makeTeam(
            owner=owner, name='a-team', displayname='A-Team')
        b_team = self.factory.makeTeam(
            owner=owner, name='b-team', displayname='B-Team')
        c_team = self.factory.makeTeam(
            owner=owner, name='c-team', displayname='C-Team')
        a_team.addMember(b_team, owner)
        b_team.addMember(c_team, owner)
        return a_team, b_team, c_team, owner

    def test_existing_team_error(self):
        """ Do not allow a new team with the same name as an existing team.

        The ObjectReassignmentView displays radio buttons that give you the
        option to create a team as opposed to using an existing team. If the
        user tries to create a new team with the same name as an existing
        team, an error is displayed.
        """
        a_team, b_team, c_team, owner = self._makeTeams()
        view = create_initialized_view(
            c_team, '+reassign', principal=owner)
        self.assertEqual(
            ['field.owner', 'field.existing'],
            list(w.name for w in view.widgets))

        form = {
            'field.owner': 'a-team',
            'field.existing': 'new',
            'field.actions.change': 'Change',
            }
        view = create_initialized_view(
            a_team, '+reassign', form=form, principal=owner)
        self.assertEqual(
            [html_escape(
                u"There's already a person/team with the name 'a-team' in "
                "Launchpad. Please choose a different name or select the "
                "option to make that person/team the new owner, if that's "
                "what you want.")],
            view.errors)

    def test_cyclical_direct_team_membership_error(self):
        """ Do not allow direct cyclical memberships.

        When a person or team becomes the owner of another team, they are also
        added as a member. Team memberships cannot be cyclical; therefore, the
        team can't have its owner be a team of which it is a direct or
        indirect member.
        """
        a_team, b_team, c_team, owner = self._makeTeams()
        form = {
            'field.owner': 'b-team',
            'field.existing': 'existing',
            'field.actions.change': 'Change',
            }
        view = create_initialized_view(
            c_team, '+reassign', form=form, principal=owner)
        self.assertEqual(1, len(view.widget_errors))
        self.assertTextMatchesExpressionIgnoreWhitespace(
            "Circular team memberships are not allowed. "
            "B-Team cannot be the new team owner, since C-Team is a direct "
            "member of B-Team.*",
            view.widget_errors['owner'])

    def test_cyclical_indirect_team_membership_error(self):
        """ Do not allow indirect cyclical memberships.

        If there is an indirect membership between the teams, the path
        between the teams is displayed so that the user has a better idea
        how to resolve the issue.
        """
        a_team, b_team, c_team, owner = self._makeTeams()
        form = {
            'field.owner': 'a-team',
            'field.existing': 'existing',
            'field.actions.change': 'Change',
            }
        view = create_initialized_view(
            c_team, '+reassign', form=form, principal=owner)
        self.assertEqual(1, len(view.widget_errors))
        self.assertTextMatchesExpressionIgnoreWhitespace(
            "Circular team memberships are not allowed. "
            "A-Team cannot be the new team owner, since C-Team is an "
            "indirect member of A-Team.*"
            "(C-Team&rArr;B-Team&rArr;A-Team).*",
            view.widget_errors['owner'])
