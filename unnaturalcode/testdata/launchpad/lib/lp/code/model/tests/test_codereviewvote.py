# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.security.interfaces import Unauthorized

from lp.code.enums import CodeReviewVote
from lp.code.errors import (
    ClaimReviewFailed,
    ReviewNotPending,
    UserHasExistingReview,
    )
from lp.code.interfaces.codereviewvote import ICodeReviewVoteReference
from lp.code.tests.helpers import make_merge_proposal_without_reviewers
from lp.services.database.constants import UTC_NOW
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestCodeReviewVote(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_create_vote(self):
        """CodeReviewVotes can be created"""
        merge_proposal = make_merge_proposal_without_reviewers(self.factory)
        reviewer = self.factory.makePerson()
        login_person(merge_proposal.registrant)
        vote = merge_proposal.nominateReviewer(
            reviewer, merge_proposal.registrant)
        self.assertEqual(reviewer, vote.reviewer)
        self.assertEqual(merge_proposal.registrant, vote.registrant)
        self.assertEqual(merge_proposal, vote.branch_merge_proposal)
        self.assertEqual([vote], list(merge_proposal.votes))
        self.assertSqlAttributeEqualsDate(
            vote, 'date_created', UTC_NOW)
        self.assertProvides(vote, ICodeReviewVoteReference)


class TestCodeReviewVoteReferenceClaimReview(TestCaseWithFactory):
    """Tests for CodeReviewVoteReference.claimReview."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        # Setup the proposal, claimant and team reviewer.
        self.bmp = self.factory.makeBranchMergeProposal()
        self.claimant = self.factory.makePerson(name='eric')
        self.review_team = self.factory.makeTeam()

    def _addPendingReview(self):
        """Add a pending review for the review_team."""
        login_person(self.bmp.registrant)
        return self.bmp.nominateReviewer(
            reviewer=self.review_team,
            registrant=self.bmp.registrant)

    def _addClaimantToReviewTeam(self):
        """Add the claimant to the review team."""
        login_person(self.review_team.teamowner)
        self.review_team.addMember(
            person=self.claimant, reviewer=self.review_team.teamowner)

    def test_personal_completed_review(self):
        # If the claimant has a personal review already, then they can't claim
        # a pending team review.
        login_person(self.claimant)
        # Make sure that the personal review is done before the pending team
        # review, otherwise the pending team review will be claimed by this
        # one.
        self.bmp.createComment(
            self.claimant, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE)
        review = self._addPendingReview()
        self._addClaimantToReviewTeam()
        self.assertRaisesWithContent(
            UserHasExistingReview,
            'Eric (eric) has already reviewed this',
            review.claimReview, self.claimant)

    def test_personal_pending_review(self):
        # If the claimant has a pending review already, then they can't claim
        # a pending team review.
        review = self._addPendingReview()
        self._addClaimantToReviewTeam()
        login_person(self.bmp.registrant)
        self.bmp.nominateReviewer(
            reviewer=self.claimant, registrant=self.bmp.registrant)
        login_person(self.claimant)
        self.assertRaisesWithContent(
            UserHasExistingReview,
            'Eric (eric) has already been asked to review this',
            review.claimReview, self.claimant)

    def test_personal_not_in_review_team(self):
        # If the claimant is not in the review team, an error is raised.
        review = self._addPendingReview()
        # Since the claimant isn't in the review team, they don't have
        # launchpad.Edit on the review itself, hence Unauthorized.
        login_person(self.claimant)
        # Actually accessing claimReview triggers the security proxy.
        self.assertRaises(
            Unauthorized, getattr, review, 'claimReview')
        # The merge proposal registrant however does have edit permissions,
        # but isn't in the team, so they get ClaimReviewFailed.
        login_person(self.bmp.registrant)
        self.assertRaises(
            ClaimReviewFailed, review.claimReview, self.bmp.registrant)

    def test_success(self):
        # If the claimant is in the review team, and does not have a personal
        # review, pending or completed, then they can claim the team review.
        review = self._addPendingReview()
        self._addClaimantToReviewTeam()
        login_person(self.claimant)
        review.claimReview(self.claimant)
        self.assertEqual(self.claimant, review.reviewer)

    def test_repeat_claim(self):
        # Attempting to claim an already-claimed review works.
        review = self.factory.makeCodeReviewVoteReference()
        review.claimReview(review.reviewer)


class TestCodeReviewVoteReferenceDelete(TestCaseWithFactory):
    """Tests for CodeReviewVoteReference.delete."""

    layer = DatabaseFunctionalLayer

    def test_delete_pending_by_registrant(self):
        # A pending review can be deleted by the person requesting the review.
        reviewer = self.factory.makePerson()
        bmp = make_merge_proposal_without_reviewers(self.factory)
        login_person(bmp.registrant)
        review = bmp.nominateReviewer(
            reviewer=reviewer, registrant=bmp.registrant)
        review.delete()
        self.assertEqual([], list(bmp.votes))

    def test_delete_pending_by_reviewer(self):
        # A pending review can be deleted by the person requesting the review.
        reviewer = self.factory.makePerson()
        bmp = make_merge_proposal_without_reviewers(self.factory)
        login_person(bmp.registrant)
        review = bmp.nominateReviewer(
            reviewer=reviewer, registrant=bmp.registrant)
        login_person(reviewer)
        review.delete()
        self.assertEqual([], list(bmp.votes))

    def test_delete_pending_by_review_team_member(self):
        # A pending review can be deleted by the person requesting the review.
        review_team = self.factory.makeTeam()
        bmp = make_merge_proposal_without_reviewers(self.factory)
        login_person(bmp.registrant)
        review = bmp.nominateReviewer(
            reviewer=review_team, registrant=bmp.registrant)
        login_person(review_team.teamowner)
        review.delete()
        self.assertEqual([], list(bmp.votes))

    def test_delete_pending_by_target_branch_owner(self):
        # A pending review can be deleted by anyone with edit permissions on
        # the target branch.
        reviewer = self.factory.makePerson()
        bmp = make_merge_proposal_without_reviewers(self.factory)
        login_person(bmp.registrant)
        review = bmp.nominateReviewer(
            reviewer=reviewer, registrant=bmp.registrant)
        login_person(bmp.target_branch.owner)
        review.delete()
        self.assertEqual([], list(bmp.votes))

    def test_delete_by_others_unauthorized(self):
        # A pending review can be deleted by the person requesting the review.
        reviewer = self.factory.makePerson()
        bmp = self.factory.makeBranchMergeProposal()
        login_person(bmp.registrant)
        review = bmp.nominateReviewer(
            reviewer=reviewer, registrant=bmp.registrant)
        login_person(self.factory.makePerson())
        self.assertRaises(
            Unauthorized, getattr, review, 'delete')

    def test_delete_not_pending(self):
        # A non-pending review reference cannot be deleted.
        reviewer = self.factory.makePerson()
        bmp = make_merge_proposal_without_reviewers(self.factory)
        login_person(reviewer)
        bmp.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE)
        [review] = list(bmp.votes)
        self.assertRaises(ReviewNotPending, review.delete)


class TestCodeReviewVoteReferenceReassignReview(TestCaseWithFactory):
    """Tests for CodeReviewVoteReference.reassignReview."""

    layer = DatabaseFunctionalLayer

    def makeMergeProposalWithReview(self, completed=False):
        """Return a new merge proposal with a review."""
        bmp = make_merge_proposal_without_reviewers(self.factory)
        reviewer = self.factory.makePerson()
        if completed:
            login_person(reviewer)
            bmp.createComment(
                reviewer, 'Message subject', 'Message content',
                vote=CodeReviewVote.APPROVE)
            [review] = list(bmp.votes)
        else:
            login_person(bmp.registrant)
            review = bmp.nominateReviewer(
                reviewer=reviewer, registrant=bmp.registrant)
        return bmp, review

    def test_reassign_pending(self):
        # A pending review can be reassigned to someone else.
        bmp, review = self.makeMergeProposalWithReview()
        new_reviewer = self.factory.makePerson()
        review.reassignReview(new_reviewer)
        self.assertEqual(new_reviewer, review.reviewer)

    def test_reassign_completed_review(self):
        # A completed review cannot be reassigned
        bmp, review = self.makeMergeProposalWithReview(completed=True)
        self.assertRaises(
            ReviewNotPending, review.reassignReview, bmp.registrant)

    def test_reassign_to_user_existing_pending(self):
        # If a user has an existing pending review, they cannot have another
        # pending review assigned to them.
        bmp, review = self.makeMergeProposalWithReview()
        reviewer = self.factory.makePerson(name='eric')
        bmp.nominateReviewer(reviewer=reviewer, registrant=bmp.registrant)
        self.assertRaisesWithContent(
            UserHasExistingReview,
            'Eric (eric) has already been asked to review this',
            review.reassignReview, reviewer)

    def test_reassign_to_user_existing_completed(self):
        # If a user has an existing completed review, they cannot have another
        # pending review assigned to them.
        bmp, review = self.makeMergeProposalWithReview()
        reviewer = self.factory.makePerson(name='eric')
        bmp.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE)
        self.assertRaisesWithContent(
            UserHasExistingReview,
            'Eric (eric) has already reviewed this',
            review.reassignReview, reviewer)

    def test_reassign_to_team_existing(self):
        # If a team has an existing review, they can have another pending
        # review assigned to them.
        bmp, review = self.makeMergeProposalWithReview()
        reviewer_team = self.factory.makeTeam()
        bmp.nominateReviewer(
            reviewer=reviewer_team, registrant=bmp.registrant)
        review.reassignReview(reviewer_team)
        self.assertEqual(reviewer_team, review.reviewer)
