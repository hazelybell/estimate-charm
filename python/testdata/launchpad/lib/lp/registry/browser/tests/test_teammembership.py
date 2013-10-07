# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from testtools.matchers import LessThan
from zope.component import getUtility

from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.testing import (
    login_celebrity,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.views import create_view


class TestTeamMenu(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamMenu, self).setUp()
        login_celebrity('admin')
        self.membership_set = getUtility(ITeamMembershipSet)
        self.team = self.factory.makeTeam()
        self.member = self.factory.makeTeam()

    def test_deactivate_member_query_count(self):
        # Only these queries should be run, no matter what the
        # membership tree looks like, although the number of queries
        # could change slightly if a different user is logged in.
        #   1. Check whether the user is the team owner.
        #   2. Deactivate the membership in the TeamMembership table.
        #   3. Delete from TeamParticipation table.
        #   (Queries #4, #5, #6, #7, and #10 are run because the storm
        #    objects have been invalidated.)
        #   4. Get the TeamMembership entry.
        #   5. Verify that the member exists in the db, but don't load
        #   the refresh the rest of its data, since we just need the id.
        #   6. Verify that the user exists in the db.
        #   7. Verify that the team exists in the db.
        #   8. Insert into Job table.
        #   9. Insert into PersonTransferJob table to schedule sending
        #      email. (This requires the data from queries #5, #6, and
        #      #7.)
        #   10.Query the rest of the team data for the invalidated
        #      object in order to generate the canonical url.
        self.team.addMember(
            self.member, self.team.teamowner, force_team_add=True)
        form = {
            'editactive': 1,
            'expires': 'never',
            'deactivate': 'Deactivate',
            }
        membership = self.membership_set.getByPersonAndTeam(
            self.member, self.team)
        view = create_view(
            membership, "+index", method='POST', form=form)
        with StormStatementRecorder() as recorder:
            view.processForm()
        self.assertEqual('', view.errormessage)
        self.assertEqual(TeamMembershipStatus.DEACTIVATED, membership.status)
        self.assertThat(recorder, HasQueryCount(LessThan(11)))
