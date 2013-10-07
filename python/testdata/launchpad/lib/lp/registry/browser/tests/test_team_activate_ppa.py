# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    )
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import first_tag_by_class
from lp.testing.views import create_initialized_view


class TestTeamActivatePPA(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def create_view(self, team):
        with person_logged_in(team.teamowner):
            view = create_initialized_view(
                team, '+index', principal=team.teamowner,
                server_url=canonical_url(team), path_info='')
            return view()

    def test_closed_teams_has_link(self):
        # Exclusive teams (a membership policy of Moderated or Restricted)
        # have a link to create a new PPA.
        for policy in EXCLUSIVE_TEAM_POLICY:
            team = self.factory.makeTeam(membership_policy=policy)
            html = self.create_view(team)
            create_ppa = first_tag_by_class(html, 'menu-link-activate_ppa')
            self.assertEqual(
                create_ppa.get('href'),
                canonical_url(team, view_name='+activate-ppa'))
            message = first_tag_by_class(html, 'cannot-create-ppa-message')
            self.assertIs(None, message)

    def test_open_team_does_not_have_link(self):
        # Open teams (a membership policy of Open or Delegated) do not
        # have a link to create a new PPA.
        for policy in INCLUSIVE_TEAM_POLICY:
            team = self.factory.makeTeam(membership_policy=policy)
            html = self.create_view(team)
            create_ppa = first_tag_by_class(html, 'menu-link-activate_ppa')
            self.assertIs(None, create_ppa)
            message = first_tag_by_class(html, 'cannot-create-ppa-message')
            self.assertIsNot(None, message)
