# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lazr.restfulclient.errors import HTTPError
from zope.component import getUtility

from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.testing import (
    launchpadlib_for,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestTeamMembershipTransitions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTeamMembershipTransitions, self).setUp()
        self.person = self.factory.makePerson(name='some-person')
        owner = self.factory.makePerson()
        self.team = self.factory.makeTeam(
            name='some-team',
            owner=owner)
        membership_set = getUtility(ITeamMembershipSet)
        membership_set.new(
            self.person,
            self.team,
            TeamMembershipStatus.APPROVED,
            self.person)
        self.launchpad = launchpadlib_for("test", owner.name)

    def test_no_such_status(self):
        # An error should be thrown when transitioning to a status that
        # doesn't exist.
        team = self.launchpad.people['some-team']
        team_membership = team.members_details[1]
        # The error in this instance should be a valueerror, b/c the
        # WADL used by launchpadlib will enforce the method args.
        self.assertRaises(
            ValueError,
            team_membership.setStatus,
            status='NOTVALIDSTATUS')

    def test_invalid_transition(self):
        # An error should be thrown when transitioning to a status that
        # isn't a valid move.
        team = self.launchpad.people['some-team']
        team_membership = team.members_details[1]
        # The error used here should be an HTTPError, since it is being
        # passed back by the server across the API.
        api_exception = self.assertRaises(
            HTTPError,
            team_membership.setStatus,
            status='Proposed')
        self.assertEqual(400, api_exception.response.status)
