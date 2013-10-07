# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for IPoll views."""

__metaclass__ = type

import os

from lp.registry.interfaces.poll import PollAlgorithm
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_view


class TestPollVoteView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPollVoteView, self).setUp()
        self.team = self.factory.makeTeam()

    def test_simple_poll_template(self):
        poll = self.factory.makePoll(
            self.team, 'name', 'title', 'proposition',
            poll_type=PollAlgorithm.SIMPLE)
        view = create_view(poll, name='+vote')
        self.assertEqual(
            'poll-vote-simple.pt', os.path.basename(view.template.filename))

    def test_condorcet_poll_template(self):
        poll = self.factory.makePoll(
            self.team, 'name', 'title', 'proposition',
            poll_type=PollAlgorithm.CONDORCET)
        view = create_view(poll, name='+vote')
        self.assertEqual(
            'poll-vote-condorcet.pt',
            os.path.basename(view.template.filename))
