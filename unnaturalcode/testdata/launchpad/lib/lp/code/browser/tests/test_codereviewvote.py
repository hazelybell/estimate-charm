# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for CodeReviewVoteReferences."""

__metaclass__ = type

from lp.services.webapp import canonical_url
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestReassignReviewer(TestCaseWithFactory):
    """Test functionality for changing the reviewer."""

    layer = DatabaseFunctionalLayer

    def test_reassign(self):
        # A reviewer can reassign their vote to someone else.
        bmp = self.factory.makeBranchMergeProposal()
        reviewer = self.factory.makePerson()
        with person_logged_in(bmp.registrant):
            vote = bmp.nominateReviewer(
                reviewer=reviewer, registrant=bmp.registrant)
        new_reviewer = self.factory.makePerson()
        with person_logged_in(reviewer):
            view = create_initialized_view(vote, '+reassign')
            view.reassign_action.success({'reviewer': new_reviewer})
        self.assertEqual(vote.reviewer, new_reviewer)

    def test_view_attributes(self):
        # Check various urls etc on view are correct.
        # At the moment, there's just the one: cancel_url
        bmp = self.factory.makeBranchMergeProposal()
        reviewer = self.factory.makePerson()
        with person_logged_in(bmp.registrant):
            vote = bmp.nominateReviewer(
                reviewer=reviewer, registrant=bmp.registrant)
        with person_logged_in(reviewer):
            view = create_initialized_view(vote, '+reassign')
        self.assertEqual(canonical_url(bmp), view.cancel_url)
