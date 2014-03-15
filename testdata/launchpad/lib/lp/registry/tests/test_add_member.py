# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test team membership changes."""

__metaclass__ = type

from lp.registry.interfaces.teammembership import CyclicalTeamMembershipError
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class CircularMemberAdditionTestCase(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(CircularMemberAdditionTestCase, self).setUp()
        self.a_team = self.factory.makeTeam(name="a")
        self.b_team = self.factory.makeTeam(name="b")

    def test_circular_invite(self):
        """Two teams can invite each other without horrifying results."""
        # Make the criss-cross invitations.
        with person_logged_in(self.a_team.teamowner):
            self.a_team.addMember(self.b_team, self.a_team.teamowner)
        with person_logged_in(self.b_team.teamowner):
            self.b_team.addMember(self.a_team, self.b_team.teamowner)

        # A-team accepts B's kind invitation.
        with person_logged_in(self.a_team.teamowner):
            self.a_team.acceptInvitationToBeMemberOf(
                self.b_team, None)
        # B-team accepts A's kind invitation.
        with person_logged_in(self.b_team.teamowner):
            self.assertRaises(
                CyclicalTeamMembershipError,
                self.b_team.acceptInvitationToBeMemberOf,
                self.a_team, None)
