# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import (
    datetime,
    timedelta,
    )

import pytz

from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestPoll(TestCaseWithFactory):
    layer = LaunchpadFunctionalLayer

    def test_getWinners_handle_polls_with_only_spoilt_votes(self):
        login('mark@example.com')
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(owner)
        poll = self.factory.makePoll(team, 'name', 'title', 'proposition')
        # Force opening of poll so that we can vote.
        poll.dateopens = datetime.now(pytz.UTC) - timedelta(minutes=2)
        poll.storeSimpleVote(owner, None)
        # Force closing of the poll so that we can call getWinners().
        poll.datecloses = datetime.now(pytz.UTC)
        self.failUnless(poll.getWinners() is None, poll.getWinners())
