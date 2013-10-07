# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BranchMergeProposals."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from difflib import unified_diff
from unittest import TestCase

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.restfulclient.errors import BadRequest
from pytz import UTC
from sqlobject import SQLObjectNotFound
from storm.locals import Store
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import IPrivacy
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    CodeReviewVote,
    )
from lp.code.errors import (
    BadStateTransition,
    BranchMergeProposalExists,
    WrongBranchMergeProposal,
    )
from lp.code.event.branchmergeproposal import (
    BranchMergeProposalNeedsReviewEvent,
    NewBranchMergeProposalEvent,
    NewCodeReviewCommentEvent,
    ReviewerNominatedEvent,
    )
from lp.code.interfaces.branchmergeproposal import (
    BRANCH_MERGE_PROPOSAL_FINAL_STATES as FINAL_STATES,
    IBranchMergeProposal,
    IBranchMergeProposalGetter,
    notify_modified,
    )
from lp.code.model.branchmergeproposal import (
    BranchMergeProposalGetter,
    is_valid_transition,
    )
from lp.code.model.branchmergeproposaljob import (
    BranchMergeProposalJob,
    MergeProposalNeedsReviewEmailJob,
    UpdatePreviewDiffJob,
    )
from lp.code.tests.helpers import (
    add_revision_to_branch,
    make_merge_proposal_without_reviewers,
    )
from lp.registry.enums import TeamMembershipPolicy
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.services.database.constants import UTC_NOW
from lp.services.webapp import canonical_url
from lp.testing import (
    ExpectedException,
    launchpadlib_for,
    login,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    WebServiceTestCase,
    ws_object,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class TestBranchMergeProposalInterface(TestCaseWithFactory):
    """Ensure that BranchMergeProposal implements its interface."""

    layer = DatabaseFunctionalLayer

    def test_BranchMergeProposal_implements_interface(self):
        """Ensure that BranchMergeProposal implements its interface."""
        bmp = self.factory.makeBranchMergeProposal()
        verifyObject(IBranchMergeProposal, bmp)


class TestBranchMergeProposalCanonicalUrl(TestCaseWithFactory):
    """Tests canonical_url for merge proposals."""

    layer = DatabaseFunctionalLayer

    def test_BranchMergeProposal_canonical_url_base(self):
        # The URL for a merge proposal starts with the source branch.
        bmp = self.factory.makeBranchMergeProposal()
        url = canonical_url(bmp)
        source_branch_url = canonical_url(bmp.source_branch)
        self.assertTrue(url.startswith(source_branch_url))

    def test_BranchMergeProposal_canonical_url_rest(self):
        # The rest of the URL for a merge proposal is +merge followed by the
        # db id.
        bmp = self.factory.makeBranchMergeProposal()
        url = canonical_url(bmp)
        source_branch_url = canonical_url(bmp.source_branch)
        rest = url[len(source_branch_url):]
        self.assertEqual('/+merge/%s' % bmp.id, rest)


class TestBranchMergeProposalPrivacy(TestCaseWithFactory):
    """Ensure that BranchMergeProposal implements privacy."""

    layer = DatabaseFunctionalLayer

    def test_BranchMergeProposal_implements_interface(self):
        """Ensure that BranchMergeProposal implements privacy."""
        bmp = self.factory.makeBranchMergeProposal()
        verifyObject(IPrivacy, bmp)

    @staticmethod
    def setPrivate(branch):
        """Force a branch to be private."""
        login_person(branch.owner)
        branch.setPrivate(True, branch.owner)

    def test_private(self):
        """Private flag should be True if True for any involved branch."""
        bmp = self.factory.makeBranchMergeProposal()
        self.assertFalse(bmp.private)
        self.setPrivate(bmp.source_branch)
        self.assertTrue(bmp.private)
        bmp.source_branch.setPrivate(False, bmp.source_branch.owner)
        self.setPrivate(bmp.target_branch)
        self.assertTrue(bmp.private)
        bmp.target_branch.setPrivate(False, bmp.target_branch.owner)
        removeSecurityProxy(bmp).prerequisite_branch = (
            self.factory.makeBranch(product=bmp.source_branch.product))
        self.setPrivate(bmp.prerequisite_branch)
        self.assertTrue(bmp.private)

    def test_open_reviewer_with_private_branch(self):
        """If the reviewer is an open team, and either of the branches are
        private, they are not subscribed."""
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        trunk = self.factory.makeBranch(product=product, owner=owner)
        team = self.factory.makeTeam()
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner,
            product=product)
        with person_logged_in(owner):
            trunk.reviewer = team
            self.factory.makeBranchMergeProposal(
                source_branch=branch, target_branch=trunk)
            subscriptions = [bsub.person for bsub in branch.subscriptions]
            self.assertEqual([owner], subscriptions)

    def test_closed_reviewer_with_private_branch(self):
        """If the reviewer is a exclusive team, they are subscribed."""
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        trunk = self.factory.makeBranch(product=product, owner=owner)
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED)
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner,
            product=product)
        with person_logged_in(owner):
            trunk.reviewer = team
            self.factory.makeBranchMergeProposal(
                source_branch=branch, target_branch=trunk)
            subscriptions = [bsub.person for bsub in branch.subscriptions]
            self.assertContentEqual([owner, team], subscriptions)


class TestBranchMergeProposalTransitions(TestCaseWithFactory):
    """Test the state transitions of branch merge proposals."""

    layer = DatabaseFunctionalLayer

    # All transitions between states are handled my method calls
    # on the proposal.
    transition_functions = {
        BranchMergeProposalStatus.WORK_IN_PROGRESS: 'setAsWorkInProgress',
        BranchMergeProposalStatus.NEEDS_REVIEW: 'requestReview',
        BranchMergeProposalStatus.CODE_APPROVED: 'approveBranch',
        BranchMergeProposalStatus.REJECTED: 'rejectBranch',
        BranchMergeProposalStatus.MERGED: 'markAsMerged',
        BranchMergeProposalStatus.MERGE_FAILED: 'setStatus',
        BranchMergeProposalStatus.QUEUED: 'enqueue',
        BranchMergeProposalStatus.SUPERSEDED: 'resubmit',
        }

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.target_branch = self.factory.makeProductBranch()
        login_person(self.target_branch.owner)

    def assertProposalState(self, proposal, state):
        """Assert that the `queue_status` of the `proposal` is `state`."""
        self.assertEqual(state, proposal.queue_status,
                         "Wrong state, expected %s, got %s"
                         % (state.title, proposal.queue_status.title))

    def _attemptTransition(self, proposal, to_state):
        """Try to transition the proposal into the state `to_state`."""
        kwargs = {}
        method = getattr(proposal, self.transition_functions[to_state])
        if to_state in (BranchMergeProposalStatus.CODE_APPROVED,
                        BranchMergeProposalStatus.REJECTED,
                        BranchMergeProposalStatus.QUEUED):
            args = [proposal.target_branch.owner, 'some_revision_id']
        elif to_state in (BranchMergeProposalStatus.SUPERSEDED, ):
            args = [proposal.registrant]
        elif to_state in (BranchMergeProposalStatus.MERGE_FAILED, ):
            # transition via setStatus.
            args = [to_state]
            kwargs = dict(user=proposal.target_branch.owner)
        else:
            args = []
        method(*args, **kwargs)

    def assertGoodTransition(self, from_state, to_state):
        """Assert that we can go from `from_state` to `to_state`."""
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=from_state)
        self.assertProposalState(proposal, from_state)
        self._attemptTransition(proposal, to_state)
        self.assertProposalState(proposal, to_state)

    def assertBadTransition(self, from_state, to_state):
        """Assert that trying to go from `from_state` to `to_state` fails."""
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=from_state)
        self.assertProposalState(proposal, from_state)
        self.assertRaises(BadStateTransition,
                          self._attemptTransition,
                          proposal, to_state)

    def prepareDupeTransition(self, from_state):
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=from_state)
        if from_state == BranchMergeProposalStatus.SUPERSEDED:
            # Setting a proposal SUPERSEDED has the side effect of creating
            # an active duplicate proposal, so make it inactive.
            proposal.superseded_by.rejectBranch(self.target_branch.owner,
                                                None)
        self.assertProposalState(proposal, from_state)
        self.factory.makeBranchMergeProposal(
            target_branch=proposal.target_branch,
            source_branch=proposal.source_branch)
        return proposal

    def assertBadDupeTransition(self, from_state, to_state):
        """Assert that trying to go from `from_state` to `to_state` fails."""
        proposal = self.prepareDupeTransition(from_state)
        self.assertRaises(BadStateTransition,
                          self._attemptTransition,
                          proposal, to_state)

    def assertGoodDupeTransition(self, from_state, to_state):
        """Trying to go from `from_state` to `to_state` succeeds."""
        proposal = self.prepareDupeTransition(from_state)
        self._attemptTransition(proposal, to_state)
        self.assertProposalState(proposal, to_state)

    def assertAllTransitionsGood(self, from_state):
        """Assert that we can go from `from_state` to any state."""
        for status in BranchMergeProposalStatus.items:
            self.assertGoodTransition(from_state, status)

    def test_transitions_from_wip(self):
        """We can go from work in progress to any other state."""
        self.assertAllTransitionsGood(
            BranchMergeProposalStatus.WORK_IN_PROGRESS)

    def test_transitions_from_needs_review(self):
        """We can go from needs review to any other state."""
        self.assertAllTransitionsGood(
            BranchMergeProposalStatus.NEEDS_REVIEW)

    def test_transitions_from_code_approved(self):
        """We can go from code_approved to any other state."""
        self.assertAllTransitionsGood(
            BranchMergeProposalStatus.CODE_APPROVED)

    def test_transitions_from_rejected(self):
        """Rejected proposals can only be resubmitted."""
        # Test the transitions from rejected.
        self.assertAllTransitionsGood(BranchMergeProposalStatus.REJECTED)

    def test_transition_from_final_with_dupes(self):
        """Proposals cannot be set active if there are similar active ones.

        So transitioning from a final state to an active one should cause
        an exception, but transitioning from a final state to a different
        final state should be fine.
        """
        for from_status in FINAL_STATES:
            for to_status in BranchMergeProposalStatus.items:
                if to_status == BranchMergeProposalStatus.SUPERSEDED:
                    continue
                if to_status in FINAL_STATES:
                    self.assertGoodDupeTransition(from_status, to_status)
                else:
                    self.assertBadDupeTransition(from_status, to_status)

    def assertValidTransitions(self, expected, proposal, to_state, by_user):
        # Check the valid transitions for the merge proposal by the specified
        # user.
        valid = set()
        for state in BranchMergeProposalStatus.items:
            if is_valid_transition(proposal, state, to_state, by_user):
                valid.add(state)
        self.assertEqual(expected, valid)

    def test_transition_to_rejected_by_reviewer(self):
        # A proposal should be able to go from any states to rejected if the
        # user is a reviewer.
        valid_transitions = set(BranchMergeProposalStatus.items)
        proposal = self.factory.makeBranchMergeProposal()
        self.assertValidTransitions(
            valid_transitions, proposal, BranchMergeProposalStatus.REJECTED,
            proposal.target_branch.owner)

    def test_transition_to_rejected_by_non_reviewer(self):
        # A non-reviewer should not be able to set a proposal as rejected.
        proposal = self.factory.makeBranchMergeProposal()
        # It is always valid to go to the same state.
        self.assertValidTransitions(
            set([BranchMergeProposalStatus.REJECTED]),
            proposal, BranchMergeProposalStatus.REJECTED,
            proposal.source_branch.owner)

    def test_transitions_from_merge_failed(self):
        """We can go from merge failed to any other state."""
        self.assertAllTransitionsGood(BranchMergeProposalStatus.MERGE_FAILED)

    def test_transition_from_merge_failed_to_queued_non_reviewer(self):
        # Contributors can requeue to retry after environmental issues fail a
        # merge.
        proposal = self.factory.makeBranchMergeProposal()
        self.assertFalse(proposal.target_branch.isPersonTrustedReviewer(
            proposal.source_branch.owner))
        self.assertValidTransitions(set([
                BranchMergeProposalStatus.MERGE_FAILED,
                BranchMergeProposalStatus.CODE_APPROVED,
                # It is always valid to go to the same state.
                BranchMergeProposalStatus.QUEUED]),
            proposal, BranchMergeProposalStatus.QUEUED,
            proposal.source_branch.owner)

    def test_transitions_from_queued_dequeue(self):
        # When a proposal is dequeued it is set to code approved, and the
        # queue position is reset.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.QUEUED)
        proposal.dequeue()
        self.assertProposalState(
            proposal, BranchMergeProposalStatus.CODE_APPROVED)
        self.assertIs(None, proposal.queue_position)
        self.assertIs(None, proposal.queuer)
        self.assertIs(None, proposal.queued_revision_id)
        self.assertIs(None, proposal.date_queued)

    def test_transitions_from_queued_to_merged(self):
        # When a proposal is marked as merged from queued, the queue_position
        # is reset.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.QUEUED)
        proposal.markAsMerged()
        self.assertProposalState(
            proposal, BranchMergeProposalStatus.MERGED)
        self.assertIs(None, proposal.queue_position)

    def test_transitions_from_queued_to_merge_failed(self):
        # When a proposal is marked as merged from queued, the queue_position
        # is reset.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.QUEUED)
        proposal.setStatus(BranchMergeProposalStatus.MERGE_FAILED)
        self.assertProposalState(
            proposal, BranchMergeProposalStatus.MERGE_FAILED)
        self.assertIs(None, proposal.queue_position)

    def test_transition_to_merge_failed_non_reviewer(self):
        # non reviewers cannot set merge-failed (target branch owners are
        # implicitly reviewers).
        proposal = self.factory.makeBranchMergeProposal()
        self.assertFalse(proposal.target_branch.isPersonTrustedReviewer(
            proposal.source_branch.owner))
        self.assertValidTransitions(set([
                # It is always valid to go to the same state.
                BranchMergeProposalStatus.MERGE_FAILED,
                BranchMergeProposalStatus.CODE_APPROVED,
                BranchMergeProposalStatus.QUEUED]),
            proposal, BranchMergeProposalStatus.MERGE_FAILED,
            proposal.source_branch.owner)

    def test_transitions_to_wip_resets_reviewer(self):
        # When a proposal was approved and is moved back into work in progress
        # the reviewer, date reviewed, and reviewed revision are all reset.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        self.assertIsNot(None, proposal.reviewer)
        self.assertIsNot(None, proposal.date_reviewed)
        self.assertIsNot(None, proposal.reviewed_revision_id)
        proposal.setAsWorkInProgress()
        self.assertIs(None, proposal.reviewer)
        self.assertIs(None, proposal.date_reviewed)
        self.assertIs(None, proposal.reviewed_revision_id)

    def test_transitions_from_rejected_to_merged_resets_reviewer(self):
        # When a rejected proposal ends up being merged anyway, reset the
        # reviewer details as they did not approve as is otherwise assumed.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.REJECTED)
        self.assertIsNot(None, proposal.reviewer)
        self.assertIsNot(None, proposal.date_reviewed)
        self.assertIsNot(None, proposal.reviewed_revision_id)
        proposal.markAsMerged()
        self.assertIs(None, proposal.reviewer)
        self.assertIs(None, proposal.date_reviewed)
        self.assertIs(None, proposal.reviewed_revision_id)


class TestBranchMergeProposalSetStatus(TestCaseWithFactory):
    """Test the setStatus method of BranchMergeProposal."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.target_branch = self.factory.makeProductBranch()
        login_person(self.target_branch.owner)

    def test_set_status_approved_to_queued(self):
        # setState can change an approved merge proposal to Work In Progress,
        # which will set the revision id to the reviewed revision id if not
        # supplied.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        proposal.approveBranch(proposal.target_branch.owner, '250')
        proposal.setStatus(BranchMergeProposalStatus.QUEUED)
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.QUEUED)
        self.assertEqual(proposal.queued_revision_id, '250')

    def test_set_status_approved_to_work_in_progress(self):
        # setState can change an approved merge proposal to Work In Progress.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        proposal.setStatus(BranchMergeProposalStatus.WORK_IN_PROGRESS)
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.WORK_IN_PROGRESS)

    def test_set_status_queued_to_merge_failed(self):
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.QUEUED)
        proposal.setStatus(BranchMergeProposalStatus.MERGE_FAILED)
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.MERGE_FAILED)
        self.assertEqual(proposal.queuer, None)
        self.assertEqual(proposal.queued_revision_id, None)
        self.assertEqual(proposal.date_queued, None)
        self.assertEqual(proposal.queue_position, None)

    def test_set_status_wip_to_needs_review(self):
        # setState can change the merge proposal to Needs Review.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        proposal.setStatus(BranchMergeProposalStatus.NEEDS_REVIEW)
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.NEEDS_REVIEW)

    def test_set_status_wip_to_code_approved(self):
        # setState can change the merge proposal to Approved, which will
        # also set the reviewed_revision_id to the approved revision id.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        proposal.setStatus(BranchMergeProposalStatus.CODE_APPROVED,
            user=self.target_branch.owner, revision_id='500')
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.CODE_APPROVED)
        self.assertEqual(proposal.reviewed_revision_id, '500')

    def test_set_status_wip_to_queued(self):
        # setState can change the merge proposal to Queued, which will
        # also set the queued_revision_id to the specified revision id.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        proposal.setStatus(BranchMergeProposalStatus.QUEUED,
            user=self.target_branch.owner, revision_id='250')
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.QUEUED)
        self.assertEqual(proposal.queued_revision_id, '250')

    def test_set_status_wip_to_rejected(self):
        # setState can change the merge proposal to Rejected, which also
        # marks the reviewed_revision_id to the rejected revision id.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        proposal.setStatus(BranchMergeProposalStatus.REJECTED,
            user=self.target_branch.owner, revision_id='1000')
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.REJECTED)
        self.assertEqual(proposal.reviewed_revision_id, '1000')

    def test_set_status_wip_to_merged(self):
        # setState can change the merge proposal to Merged.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        proposal.setStatus(BranchMergeProposalStatus.MERGED)
        self.assertEqual(proposal.queue_status,
            BranchMergeProposalStatus.MERGED)

    def test_set_status_invalid_status(self):
        # IBranchMergeProposal.setStatus doesn't work in the case of
        # superseded branches since a superseded branch requires more than
        # just changing a few settings.  Because it's unknown, it should
        # raise an AssertionError.
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        self.assertRaises(AssertionError, proposal.setStatus,
            BranchMergeProposalStatus.SUPERSEDED)


class TestBranchMergeProposalRequestReview(TestCaseWithFactory):
    """Test the resetting of date_review_reqeuested."""

    layer = DatabaseFunctionalLayer

    def _createMergeProposal(self, needs_review):
        # Create and return a merge proposal.
        source_branch = self.factory.makeProductBranch()
        target_branch = self.factory.makeProductBranch(
            product=source_branch.product)
        login_person(target_branch.owner)
        return source_branch.addLandingTarget(
            source_branch.owner, target_branch,
            date_created=datetime(2000, 1, 1, 12, tzinfo=UTC),
            needs_review=needs_review)

    def test_date_set_on_change(self):
        # When the proposal changes to needs review state the date is
        # recoreded.
        proposal = self._createMergeProposal(needs_review=False)
        self.assertEqual(
            BranchMergeProposalStatus.WORK_IN_PROGRESS,
            proposal.queue_status)
        self.assertIs(None, proposal.date_review_requested)
        # Requesting the merge then sets the date review requested.
        proposal.requestReview()
        self.assertSqlAttributeEqualsDate(
            proposal, 'date_review_requested', UTC_NOW)

    def test_date_not_reset_on_rerequest(self):
        # When the proposal changes to needs review state the date is
        # recoreded.
        proposal = self._createMergeProposal(needs_review=True)
        self.assertEqual(
            BranchMergeProposalStatus.NEEDS_REVIEW,
            proposal.queue_status)
        self.assertEqual(
            proposal.date_created, proposal.date_review_requested)
        # Requesting the merge again will not reset the date review requested.
        proposal.requestReview()
        self.assertEqual(
            proposal.date_created, proposal.date_review_requested)

    def test_date_not_reset_on_wip(self):
        # If a proposal has been in needs review state, and is moved back into
        # work in progress, the date_review_requested is not reset.
        proposal = self._createMergeProposal(needs_review=True)
        proposal.setAsWorkInProgress()
        self.assertIsNot(None, proposal.date_review_requested)


class TestCreateCommentNotifications(TestCaseWithFactory):
    """Test the notifications are raised at the right times."""

    layer = DatabaseFunctionalLayer

    def test_notify_on_nominate(self):
        # Ensure that a notification is emitted when a new comment is added.
        merge_proposal = self.factory.makeBranchMergeProposal()
        commenter = self.factory.makePerson()
        login_person(commenter)
        result, events = self.assertNotifies(
            NewCodeReviewCommentEvent,
            merge_proposal.createComment,
            owner=commenter,
            subject='A review.')
        self.assertEqual(result, events[0].object)

    def test_notify_on_nominate_suppressed_if_requested(self):
        # Ensure that the notification is supressed if the notify listeners
        # parameger is set to False.
        merge_proposal = self.factory.makeBranchMergeProposal()
        commenter = self.factory.makePerson()
        login_person(commenter)
        self.assertNoNotification(
            merge_proposal.createComment,
            owner=commenter,
            subject='A review.',
            _notify_listeners=False)


class TestMergeProposalAllComments(TestCase):
    """Tester for `BranchMergeProposal.all_comments`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        # Testing behavior, not permissions here.
        login('foo.bar@canonical.com')
        self.factory = LaunchpadObjectFactory()
        self.merge_proposal = self.factory.makeBranchMergeProposal()

    def test_all_comments(self):
        """Ensure all comments associated with the proposal are returned."""
        comment1 = self.merge_proposal.createComment(
            self.merge_proposal.registrant, "Subject")
        comment2 = self.merge_proposal.createComment(
            self.merge_proposal.registrant, "Subject")
        comment3 = self.merge_proposal.createComment(
            self.merge_proposal.registrant, "Subject")
        self.assertEqual(
            set([comment1, comment2, comment3]),
            set(self.merge_proposal.all_comments))


class TestMergeProposalGetComment(TestCase):
    """Tester for `BranchMergeProposal.getComment`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        # Testing behavior, not permissions here.
        login('foo.bar@canonical.com')
        self.factory = LaunchpadObjectFactory()
        self.merge_proposal = self.factory.makeBranchMergeProposal()
        self.merge_proposal2 = self.factory.makeBranchMergeProposal()
        self.comment = self.merge_proposal.createComment(
            self.merge_proposal.registrant, "Subject")

    def test_getComment(self):
        """Tests that we can get a comment."""
        self.assertEqual(
            self.comment, self.merge_proposal.getComment(self.comment.id))

    def test_getCommentWrongBranchMergeProposal(self):
        """Tests that we can get a comment."""
        self.assertRaises(WrongBranchMergeProposal,
                          self.merge_proposal2.getComment, self.comment.id)


class TestMergeProposalGetVoteReference(TestCaseWithFactory):
    """Tester for `BranchMergeProposal.getComment`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        # Testing behavior, not permissions here.
        login('foo.bar@canonical.com')
        self.merge_proposal = self.factory.makeBranchMergeProposal()
        self.merge_proposal2 = self.factory.makeBranchMergeProposal()
        self.vote = self.merge_proposal.nominateReviewer(
            reviewer=self.merge_proposal.registrant,
            registrant=self.merge_proposal.registrant)

    def test_getVoteReference(self):
        """Tests that we can get a comment."""
        self.assertEqual(
            self.vote, self.merge_proposal.getVoteReference(
                self.vote.id))

    def test_getVoteReferenceWrongBranchMergeProposal(self):
        """Tests that we can get a comment."""
        self.assertRaises(WrongBranchMergeProposal,
                          self.merge_proposal2.getVoteReference,
                          self.vote.id)


class TestMergeProposalNotification(TestCaseWithFactory):
    """Test that events are created when merge proposals are manipulated"""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, user='test@canonical.com')

    def test_notifyOnCreate_needs_review(self):
        # When a merge proposal is created needing review, the
        # BranchMergeProposalNeedsReviewEvent is raised as well as the usual
        # NewBranchMergeProposalEvent.
        source_branch = self.factory.makeProductBranch()
        target_branch = self.factory.makeProductBranch(
            product=source_branch.product)
        registrant = self.factory.makePerson()
        result, events = self.assertNotifies(
            [NewBranchMergeProposalEvent,
             BranchMergeProposalNeedsReviewEvent],
            source_branch.addLandingTarget, registrant, target_branch,
            needs_review=True)
        self.assertEqual(result, events[0].object)

    def test_notifyOnCreate_work_in_progress(self):
        # When a merge proposal is created as work in progress, the
        # BranchMergeProposalNeedsReviewEvent is not raised.
        source_branch = self.factory.makeProductBranch()
        target_branch = self.factory.makeProductBranch(
            product=source_branch.product)
        registrant = self.factory.makePerson()
        result, events = self.assertNotifies(
            [NewBranchMergeProposalEvent],
            source_branch.addLandingTarget, registrant, target_branch)
        self.assertEqual(result, events[0].object)

    def test_needs_review_from_work_in_progress(self):
        # Transitioning from work in progress to needs review raises the
        # BranchMergeProposalNeedsReviewEvent event.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        with person_logged_in(bmp.registrant):
            self.assertNotifies(
                [BranchMergeProposalNeedsReviewEvent],
                bmp.setStatus, BranchMergeProposalStatus.NEEDS_REVIEW)

    def test_needs_review_no_op(self):
        # Calling needs review when in needs review does not notify.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        with person_logged_in(bmp.registrant):
            self.assertNoNotification(
                bmp.setStatus, BranchMergeProposalStatus.NEEDS_REVIEW)

    def test_needs_review_from_approved(self):
        # Calling needs review when approved does not notify either.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        with person_logged_in(bmp.registrant):
            self.assertNoNotification(
                bmp.setStatus, BranchMergeProposalStatus.NEEDS_REVIEW)

    def test_getNotificationRecipients(self):
        """Ensure that recipients can be added/removed with subscribe"""
        bmp = self.factory.makeBranchMergeProposal()
        # Both of the branch owners are now subscribed to their own
        # branches with full code review notification level set.
        source_owner = bmp.source_branch.owner
        target_owner = bmp.target_branch.owner
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        subscriber_set = set([source_owner, target_owner])
        self.assertEqual(subscriber_set, set(recipients.keys()))
        source_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(
            source_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL,
            source_subscriber)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        subscriber_set.add(source_subscriber)
        self.assertEqual(subscriber_set, set(recipients.keys()))
        bmp.source_branch.subscribe(
            source_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.NOEMAIL,
            source_subscriber)
        # By specifying no email, they will no longer get email.
        subscriber_set.remove(source_subscriber)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        self.assertEqual(subscriber_set, set(recipients.keys()))

    def test_getNotificationRecipientLevels(self):
        """Ensure that only recipients with the right level are returned"""
        bmp = self.factory.makeBranchMergeProposal()
        full_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(full_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, full_subscriber)
        status_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(status_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.STATUS, status_subscriber)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        # Both of the branch owners are now subscribed to their own
        # branches with full code review notification level set.
        source_owner = bmp.source_branch.owner
        target_owner = bmp.target_branch.owner
        self.assertEqual(set([full_subscriber, status_subscriber,
                              source_owner, target_owner]),
                         set(recipients.keys()))
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.FULL)
        self.assertEqual(set([full_subscriber, source_owner, target_owner]),
                         set(recipients.keys()))

    def test_getNotificationRecipientsAnyBranch(self):
        prerequisite_branch = self.factory.makeProductBranch()
        bmp = self.factory.makeBranchMergeProposal(
            prerequisite_branch=prerequisite_branch)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.NOEMAIL)
        source_owner = bmp.source_branch.owner
        target_owner = bmp.target_branch.owner
        prerequisite_owner = bmp.prerequisite_branch.owner
        self.assertEqual(
            set([source_owner, target_owner, prerequisite_owner]),
            set(recipients.keys()))
        source_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(source_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, source_subscriber)
        target_subscriber = self.factory.makePerson()
        bmp.target_branch.subscribe(target_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, target_subscriber)
        prerequisite_subscriber = self.factory.makePerson()
        bmp.prerequisite_branch.subscribe(prerequisite_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, prerequisite_subscriber)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.FULL)
        self.assertEqual(
            set([source_subscriber, target_subscriber,
                 prerequisite_subscriber, source_owner, target_owner,
                 prerequisite_owner]),
            set(recipients.keys()))

    def test_getNotificationRecipientsIncludesReviewers(self):
        bmp = self.factory.makeBranchMergeProposal()
        # Both of the branch owners are now subscribed to their own
        # branches with full code review notification level set.
        source_owner = bmp.source_branch.owner
        target_owner = bmp.target_branch.owner
        login_person(source_owner)
        reviewer = self.factory.makePerson()
        bmp.nominateReviewer(reviewer, registrant=source_owner)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        subscriber_set = set([source_owner, target_owner, reviewer])
        self.assertEqual(subscriber_set, set(recipients.keys()))

    def test_getNotificationRecipientsIncludesTeamReviewers(self):
        # If the reviewer is a team, the team gets the email.
        bmp = self.factory.makeBranchMergeProposal()
        # Both of the branch owners are now subscribed to their own
        # branches with full code review notification level set.
        source_owner = bmp.source_branch.owner
        target_owner = bmp.target_branch.owner
        login_person(source_owner)
        reviewer = self.factory.makeTeam()
        bmp.nominateReviewer(reviewer, registrant=source_owner)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        subscriber_set = set([source_owner, target_owner, reviewer])
        self.assertEqual(subscriber_set, set(recipients.keys()))

    def test_getNotificationRecipients_Registrant(self):
        # If the registrant of the proposal is being notified of the
        # proposals, they get their rationale set to "Registrant".
        registrant = self.factory.makePerson()
        bmp = self.factory.makeBranchMergeProposal(registrant=registrant)
        # Make sure that the registrant is subscribed.
        bmp.source_branch.subscribe(registrant,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, registrant)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        reason = recipients[registrant]
        self.assertEqual("Registrant", reason.mail_header)
        self.assertEqual(
            "You proposed %s for merging." % bmp.source_branch.bzr_identity,
            reason.getReason())

    def test_getNotificationRecipients_Registrant_not_subscribed(self):
        # If the registrant of the proposal is not subscribed, we don't send
        # them any email.
        registrant = self.factory.makePerson()
        bmp = self.factory.makeBranchMergeProposal(registrant=registrant)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        self.assertFalse(registrant in recipients)

    def test_getNotificationRecipients_Owner(self):
        # If the owner of the source branch is subscribed (which is the
        # default), then they get a rationale telling them they are the Owner.
        bmp = self.factory.makeBranchMergeProposal()
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        reason = recipients[bmp.source_branch.owner]
        self.assertEqual("Owner", reason.mail_header)
        self.assertEqual(
            "You are the owner of %s." % bmp.source_branch.bzr_identity,
            reason.getReason())

    def test_getNotificationRecipients_team_owner(self):
        # If the owner of the source branch is subscribed (which is the
        # default), but the owner is a team, then none of the headers will say
        # Owner.
        team = self.factory.makeTeam()
        branch = self.factory.makeProductBranch(owner=team)
        bmp = self.factory.makeBranchMergeProposal(source_branch=branch)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        headers = set([reason.mail_header for reason in recipients.values()])
        self.assertFalse("Owner" in headers)

    def test_getNotificationRecipients_Owner_not_subscribed(self):
        # If the owner of the source branch has unsubscribed themselves, then
        # we don't send them eamil.
        bmp = self.factory.makeBranchMergeProposal()
        owner = bmp.source_branch.owner
        bmp.source_branch.unsubscribe(owner, owner)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        self.assertFalse(owner in recipients)

    def test_getNotificationRecipients_privacy(self):
        # If a user can see only one of the source and target branches, then
        # they do not get email about the proposal.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        source = self.factory.makeBranch(owner=owner, product=product)
        target = self.factory.makeBranch(owner=owner, product=product)
        bmp = self.factory.makeBranchMergeProposal(
            source_branch=source, target_branch=target)
        # Subscribe eric to the source branch only.
        eric = self.factory.makePerson()
        source.subscribe(
            eric, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, eric)
        # Subscribe bob to the target branch only.
        bob = self.factory.makePerson()
        target.subscribe(
            bob, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, bob)
        # Subscribe charlie to both.
        charlie = self.factory.makePerson()
        source.subscribe(
            charlie, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, charlie)
        target.subscribe(
            charlie, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, charlie)
        # Make both branches private.
        for branch in (source, target):
            removeSecurityProxy(branch).transitionToInformationType(
                InformationType.USERDATA, branch.owner, verify_policy=False)
        with person_logged_in(owner):
            recipients = bmp.getNotificationRecipients(
                CodeReviewNotificationLevel.FULL)
        self.assertNotIn(bob, recipients)
        self.assertNotIn(eric, recipients)
        self.assertIn(charlie, recipients)


class TestGetAddress(TestCaseWithFactory):
    """Test that the address property gives expected results."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, user='test@canonical.com')

    def test_address(self):
        merge_proposal = self.factory.makeBranchMergeProposal()
        expected = 'mp+%d@code.launchpad.dev' % merge_proposal.id
        self.assertEqual(expected, merge_proposal.address)


class TestBranchMergeProposalGetter(TestCaseWithFactory):
    """Test that the BranchMergeProposalGetter behaves as expected."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, user='test@canonical.com')

    def test_get(self):
        """Ensure the correct merge proposal is returned."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        self.assertEqual(merge_proposal,
            BranchMergeProposalGetter().get(merge_proposal.id))

    def test_get_as_utility(self):
        """Ensure the correct merge proposal is returned."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        utility = getUtility(IBranchMergeProposalGetter)
        retrieved = utility.get(merge_proposal.id)
        self.assertEqual(merge_proposal, retrieved)

    def test_getVotesForProposals(self):
        # Check the resulting format of the dict.  getVotesForProposals
        # returns a dict mapping merge proposals to a list of votes for that
        # proposal.
        mp_no_reviews = make_merge_proposal_without_reviewers(self.factory)
        reviewer = self.factory.makePerson()
        mp_with_reviews = self.factory.makeBranchMergeProposal(
            reviewer=reviewer)
        login_person(mp_with_reviews.registrant)
        [vote_reference] = list(mp_with_reviews.votes)
        self.assertEqual(
            {mp_no_reviews: [],
             mp_with_reviews: [vote_reference]},
            getUtility(IBranchMergeProposalGetter).getVotesForProposals(
                [mp_with_reviews, mp_no_reviews]))

    def test_activeProposalsForBranches_different_branches(self):
        """Only proposals for the correct branches are returned."""
        mp = self.factory.makeBranchMergeProposal()
        mp2 = self.factory.makeBranchMergeProposal()
        active = BranchMergeProposalGetter.activeProposalsForBranches(
            mp.source_branch, mp.target_branch)
        self.assertEqual([mp], list(active))
        active2 = BranchMergeProposalGetter.activeProposalsForBranches(
            mp2.source_branch, mp2.target_branch)
        self.assertEqual([mp2], list(active2))

    def test_activeProposalsForBranches_different_states(self):
        """Only proposals for active states are returned."""
        for state in BranchMergeProposalStatus.items:
            mp = self.factory.makeBranchMergeProposal(set_state=state)
            active = BranchMergeProposalGetter.activeProposalsForBranches(
                mp.source_branch, mp.target_branch)
            # If a proposal is superseded, there is an active proposal which
            # supersedes it.
            if state == BranchMergeProposalStatus.SUPERSEDED:
                self.assertEqual([mp.superseded_by], list(active))
            elif state in FINAL_STATES:
                self.assertEqual([], list(active))
            else:
                self.assertEqual([mp], list(active))


class TestBranchMergeProposalGetterGetProposals(TestCaseWithFactory):
    """Test the getProposalsForContext method."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Use an administrator so the permission checks for things
        # like adding landing targets and setting privacy on the branches
        # are allowed.
        TestCaseWithFactory.setUp(self, user='foo.bar@canonical.com')

    def _make_merge_proposal(self, owner_name, product_name, branch_name,
                             needs_review=False, registrant=None):
        # A helper method to make the tests readable.
        owner = getUtility(IPersonSet).getByName(owner_name)
        if owner is None:
            owner = self.factory.makePerson(name=owner_name)
        product = getUtility(IProductSet).getByName(product_name)
        if product is None:
            product = self.factory.makeProduct(name=product_name)
        stacked_on_branch = self.factory.makeProductBranch(
            product=product, owner=owner, registrant=registrant)
        branch = self.factory.makeProductBranch(
            product=product, owner=owner, registrant=registrant,
            name=branch_name, stacked_on=stacked_on_branch)
        if registrant is None:
            registrant = owner
        bmp = branch.addLandingTarget(
            registrant=registrant,
            target_branch=self.factory.makeProductBranch(product=product,
            owner=owner))
        if needs_review:
            bmp.requestReview()
        return bmp

    def _get_merge_proposals(self, context, status=None,
                             visible_by_user=None):
        # Helper method to return tuples of source branch details.
        results = BranchMergeProposalGetter.getProposalsForContext(
            context, status, visible_by_user)
        return sorted([bmp.source_branch.unique_name for bmp in results])

    def test_getProposalsForParticipant(self):
        # It's possible to get all the merge proposals for a single
        # participant.
        wally = self.factory.makePerson(name='wally')
        beaver = self.factory.makePerson(name='beaver')

        bmp1 = self._make_merge_proposal('wally', 'gokart', 'turbo', True)
        bmp1.nominateReviewer(beaver, wally)
        self._make_merge_proposal('beaver', 'gokart', 'brakes', True)

        getter = BranchMergeProposalGetter
        wally_proposals = getter.getProposalsForParticipant(
            wally, [BranchMergeProposalStatus.NEEDS_REVIEW], wally)
        self.assertEqual(wally_proposals.count(), 1)

        beave_proposals = getter.getProposalsForParticipant(
            beaver, [BranchMergeProposalStatus.NEEDS_REVIEW], beaver)
        self.assertEqual(beave_proposals.count(), 2)

        bmp1.rejectBranch(wally, '1')

        beave_proposals = getter.getProposalsForParticipant(
            beaver, [BranchMergeProposalStatus.NEEDS_REVIEW], beaver)
        self.assertEqual(beave_proposals.count(), 1)

        beave_proposals = getter.getProposalsForParticipant(
            beaver, [BranchMergeProposalStatus.REJECTED], beaver)
        self.assertEqual(beave_proposals.count(), 1)

    def test_created_proposal_default_status(self):
        # When we create a merge proposal using the helper method, the default
        # status of the proposal is work in progress.
        in_progress = self._make_merge_proposal('albert', 'november', 'work')
        self.assertEqual(
            BranchMergeProposalStatus.WORK_IN_PROGRESS,
            in_progress.queue_status)

    def test_created_proposal_review_status(self):
        # If needs_review is set to True, the created merge proposal is set in
        # the needs review state.
        needs_review = self._make_merge_proposal(
            'bob', 'november', 'work', needs_review=True)
        self.assertEqual(
            BranchMergeProposalStatus.NEEDS_REVIEW,
            needs_review.queue_status)

    def test_all_for_product_restrictions(self):
        # Queries on product should limit results to that product.
        self._make_merge_proposal('albert', 'november', 'work')
        self._make_merge_proposal('bob', 'november', 'work')
        # And make a proposal for another product to make sure that it doesn't
        # appear
        self._make_merge_proposal('charles', 'mike', 'work')

        self.assertEqual(
            ['~albert/november/work', '~bob/november/work'],
            self._get_merge_proposals(
                getUtility(IProductSet).getByName('november')))

    def test_wip_for_product_restrictions(self):
        # Check queries on product limited on status.
        self._make_merge_proposal('albert', 'november', 'work')
        self._make_merge_proposal(
            'bob', 'november', 'work', needs_review=True)
        self.assertEqual(
            ['~albert/november/work'],
            self._get_merge_proposals(
                getUtility(IProductSet).getByName('november'),
                status=[BranchMergeProposalStatus.WORK_IN_PROGRESS]))

    def test_all_for_person_restrictions(self):
        # Queries on person should limit results to that person.
        self._make_merge_proposal('albert', 'november', 'work')
        self._make_merge_proposal('albert', 'mike', 'work')
        # And make a proposal for another product to make sure that it doesn't
        # appear
        self._make_merge_proposal('charles', 'mike', 'work')

        self.assertEqual(
            ['~albert/mike/work', '~albert/november/work'],
            self._get_merge_proposals(
                getUtility(IPersonSet).getByName('albert')))

    def test_wip_for_person_restrictions(self):
        # If looking for the merge proposals for a person, and the status is
        # specified, then the resulting proposals will have one of the states
        # specified.
        self._make_merge_proposal('albert', 'november', 'work')
        self._make_merge_proposal(
            'albert', 'november', 'review', needs_review=True)
        self.assertEqual(
            ['~albert/november/work'],
            self._get_merge_proposals(
                getUtility(IPersonSet).getByName('albert'),
                status=[BranchMergeProposalStatus.WORK_IN_PROGRESS]))

    def test_private_branches(self):
        # The resulting list of merge proposals is filtered by the actual
        # proposals that the logged in user is able to see.
        proposal = self._make_merge_proposal('albert', 'november', 'work')
        # Mark the source branch private.
        proposal.source_branch.transitionToInformationType(
            InformationType.USERDATA, proposal.source_branch.owner,
            verify_policy=False)
        self._make_merge_proposal('albert', 'mike', 'work')

        albert = getUtility(IPersonSet).getByName('albert')
        # Albert can see his private branch.
        self.assertEqual(
            ['~albert/mike/work', '~albert/november/work'],
            self._get_merge_proposals(albert, visible_by_user=albert))
        # Anonymous people can't.
        self.assertEqual(
            ['~albert/mike/work'],
            self._get_merge_proposals(albert))
        # Other people can't.
        self.assertEqual(
            ['~albert/mike/work'],
            self._get_merge_proposals(
                albert, visible_by_user=self.factory.makePerson()))
        # A branch subscribers can.
        subscriber = self.factory.makePerson()
        proposal.source_branch.subscribe(
            subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.NOEMAIL, subscriber)
        self.assertEqual(
            ['~albert/mike/work', '~albert/november/work'],
            self._get_merge_proposals(albert, visible_by_user=subscriber))

    def test_team_private_branches(self):
        # If both charles and albert are a member team xray, and albert
        # creates a branch in the team namespace, charles will be able to see
        # it.
        albert = self.factory.makePerson(name='albert')
        charles = self.factory.makePerson(name='charles')
        xray = self.factory.makeTeam(name='xray', owner=albert)
        xray.addMember(person=charles, reviewer=albert)

        proposal = self._make_merge_proposal(
            'xray', 'november', 'work', registrant=albert)
        # Mark the source branch private.
        proposal.source_branch.transitionToInformationType(
            InformationType.USERDATA, proposal.source_branch.owner,
            verify_policy=False)

        november = getUtility(IProductSet).getByName('november')
        # The proposal is visible to charles.
        self.assertEqual(
            ['~xray/november/work'],
            self._get_merge_proposals(november, visible_by_user=charles))
        # Not visible to anonymous people.
        self.assertEqual([], self._get_merge_proposals(november))
        # Not visible to non team members.
        self.assertEqual(
            [],
            self._get_merge_proposals(
                november, visible_by_user=self.factory.makePerson()))


class TestBranchMergeProposalDeletion(TestCaseWithFactory):
    """Deleting a branch merge proposal deletes relevant objects."""

    layer = DatabaseFunctionalLayer

    def test_deleteProposal_deletes_job(self):
        """Deleting a branch merge proposal deletes all related jobs."""
        proposal = self.factory.makeBranchMergeProposal()
        job = MergeProposalNeedsReviewEmailJob.create(proposal)
        job.context.sync()
        job_id = job.context.id
        login_person(proposal.registrant)
        proposal.deleteProposal()
        self.assertRaises(
            SQLObjectNotFound, BranchMergeProposalJob.get, job_id)


class TestBranchMergeProposalBugs(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.user = self.factory.makePerson()
        login_person(self.user)

    def test_related_bugtasks_includes_source_bugtasks(self):
        """related_bugtasks includes bugtasks linked to the source branch."""
        bmp = self.factory.makeBranchMergeProposal()
        source_branch = bmp.source_branch
        bug = self.factory.makeBug()
        source_branch.linkBug(bug, bmp.registrant)
        self.assertEqual(
            bug.bugtasks, list(bmp.getRelatedBugTasks(self.user)))

    def test_related_bugtasks_excludes_target_bugs(self):
        """related_bugtasks ignores bugs linked to the source branch."""
        bmp = self.factory.makeBranchMergeProposal()
        bug = self.factory.makeBug()
        bmp.target_branch.linkBug(bug, bmp.registrant)
        self.assertEqual([], list(bmp.getRelatedBugTasks(self.user)))

    def test_related_bugtasks_excludes_mutual_bugs(self):
        """related_bugtasks ignores bugs linked to both branches."""
        bmp = self.factory.makeBranchMergeProposal()
        bug = self.factory.makeBug()
        bmp.source_branch.linkBug(bug, bmp.registrant)
        bmp.target_branch.linkBug(bug, bmp.registrant)
        self.assertEqual([], list(bmp.getRelatedBugTasks(self.user)))

    def test_related_bugtasks_excludes_private_bugs(self):
        """related_bugtasks ignores private bugs for non-authorised users."""
        bmp = self.factory.makeBranchMergeProposal()
        bug = self.factory.makeBug()
        bmp.source_branch.linkBug(bug, bmp.registrant)
        person = self.factory.makePerson()
        with person_logged_in(person):
            private_bug = self.factory.makeBug(
                owner=person, information_type=InformationType.USERDATA)
            bmp.source_branch.linkBug(private_bug, person)
            private_tasks = private_bug.bugtasks
        self.assertEqual(
            bug.bugtasks, list(bmp.getRelatedBugTasks(self.user)))
        all_bugtasks = list(bug.bugtasks)
        all_bugtasks.extend(private_tasks)
        self.assertEqual(
            all_bugtasks, list(bmp.getRelatedBugTasks(person)))


class TestNotifyModified(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_notify_modified_generates_notification(self):
        """notify_modified generates an event.

        notify_modified runs the callable with the specified args and kwargs,
        and generates a ObjectModifiedEvent.
        """
        bmp = self.factory.makeBranchMergeProposal()
        login_person(bmp.target_branch.owner)
        # Approve branch to prevent enqueue from approving it, which would
        # generate an undesired event.
        bmp.approveBranch(bmp.target_branch.owner, revision_id='abc')
        self.assertNotifies(
            ObjectModifiedEvent, notify_modified, bmp, bmp.enqueue,
            bmp.target_branch.owner, revision_id='abc')
        self.assertEqual(BranchMergeProposalStatus.QUEUED, bmp.queue_status)
        self.assertEqual('abc', bmp.queued_revision_id)


class TestBranchMergeProposalNominateReviewer(TestCaseWithFactory):
    """Test that the appropriate vote references get created."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, user='test@canonical.com')

    def test_notify_on_nominate(self):
        # Ensure that a notification is emitted on nomination.
        merge_proposal = self.factory.makeBranchMergeProposal()
        login_person(merge_proposal.source_branch.owner)
        reviewer = self.factory.makePerson()
        result, events = self.assertNotifies(
            ReviewerNominatedEvent,
            merge_proposal.nominateReviewer,
            reviewer=reviewer,
            registrant=merge_proposal.source_branch.owner)
        self.assertEqual(result, events[0].object)

    def test_notify_on_nominate_suppressed_if_requested(self):
        # Ensure that a notification is suppressed if notify listeners is set
        # to False.
        merge_proposal = self.factory.makeBranchMergeProposal()
        login_person(merge_proposal.source_branch.owner)
        reviewer = self.factory.makePerson()
        self.assertNoNotification(
            merge_proposal.nominateReviewer,
            reviewer=reviewer,
            registrant=merge_proposal.source_branch.owner,
            _notify_listeners=False)

    def test_one_initial_votes(self):
        """A new merge proposal has one vote of the default reviewer."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        self.assertEqual(1, len(list(merge_proposal.votes)))
        [vote] = list(merge_proposal.votes)
        self.assertEqual(
            merge_proposal.target_branch.owner, vote.reviewer)

    def makeProposalWithReviewer(self, reviewer=None, review_type=None,
                                 registrant=None):
        """Make a proposal and request a review from reviewer.

        If no reviewer is passed in, make a reviewer.
        """
        if reviewer is None:
            reviewer = self.factory.makePerson()
        if registrant is None:
            registrant = self.factory.makePerson()
        merge_proposal = make_merge_proposal_without_reviewers(
            factory=self.factory, registrant=registrant)
        login_person(merge_proposal.source_branch.owner)
        merge_proposal.nominateReviewer(
            reviewer=reviewer, registrant=registrant, review_type=review_type)
        return merge_proposal, reviewer

    def test_pending_review_registrant(self):
        # The registrant passed into the nominateReviewer call is the
        # registrant of the vote reference.
        registrant = self.factory.makePerson()
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            registrant=registrant)
        vote_reference = list(merge_proposal.votes)[0]
        self.assertEqual(registrant, vote_reference.registrant)

    def assertOneReviewPending(self, merge_proposal, reviewer, review_type):
        # Check that there is one and only one review pending with the
        # specified reviewer and review_type.
        votes = list(merge_proposal.votes)
        self.assertEqual(1, len(votes))
        vote_reference = votes[0]
        self.assertEqual(reviewer, vote_reference.reviewer)
        if review_type is None:
            self.assertIs(None, vote_reference.review_type)
        else:
            self.assertEqual(review_type, vote_reference.review_type)
        self.assertIs(None, vote_reference.comment)

    def test_nominate_creates_reference(self):
        # A new vote reference is created when a reviewer is nominated.
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            review_type='general')
        self.assertOneReviewPending(merge_proposal, reviewer, 'general')

    def test_nominate_with_None_review_type(self):
        # Reviews nominated with a review type of None, make vote references
        # with a review_type of None.
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            review_type=None)
        self.assertOneReviewPending(merge_proposal, reviewer, None)

    def test_nominate_with_whitespace_review_type(self):
        # A review nominated with a review type that just contains whitespace
        # or the empty string, makes a vote reference with a review_type of
        # None.
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            review_type='')
        self.assertOneReviewPending(merge_proposal, reviewer, None)
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            review_type='    ')
        self.assertOneReviewPending(merge_proposal, reviewer, None)
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            review_type='\t')
        self.assertOneReviewPending(merge_proposal, reviewer, None)

    def test_nominate_multiple_with_different_types(self):
        # While an individual can only be requested to do one review
        # (test_nominate_updates_reference) a team can have multiple
        # nominations for different review types.
        reviewer = self.factory.makePerson()
        review_team = self.factory.makeTeam(owner=reviewer)
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            reviewer=review_team, review_type='general-1')
        merge_proposal.nominateReviewer(
            reviewer=review_team,
            registrant=merge_proposal.registrant,
            review_type='general-2')

        votes = list(merge_proposal.votes)
        self.assertEqual(
            ['general-1', 'general-2'],
            sorted([review.review_type for review in votes]))

    def test_nominate_multiple_with_same_types(self):
        # There can be multiple reviews for a team with the same review_type.
        reviewer = self.factory.makePerson()
        review_team = self.factory.makeTeam(owner=reviewer)
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            reviewer=review_team, review_type='general')
        merge_proposal.nominateReviewer(
            reviewer=review_team,
            registrant=merge_proposal.registrant,
            review_type='general')

        votes = list(merge_proposal.votes)
        self.assertEqual(
            [(review_team, 'general'), (review_team, 'general')],
            [(review.reviewer, review.review_type) for review in votes])

    def test_nominate_multiple_team_reviews_with_no_type(self):
        # There can be multiple reviews for a team with no review type set.
        reviewer = self.factory.makePerson()
        review_team = self.factory.makeTeam(owner=reviewer)
        merge_proposal, reviewer = self.makeProposalWithReviewer(
            reviewer=review_team, review_type=None)
        merge_proposal.nominateReviewer(
            reviewer=review_team,
            registrant=merge_proposal.registrant,
            review_type=None)

        votes = list(merge_proposal.votes)
        self.assertEqual(
            [(review_team, None), (review_team, None)],
            [(review.reviewer, review.review_type) for review in votes])

    def test_nominate_updates_reference(self):
        """The existing reference is updated on re-nomination."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        login_person(merge_proposal.source_branch.owner)
        reviewer = self.factory.makePerson()
        reference = merge_proposal.nominateReviewer(
            reviewer=reviewer, registrant=merge_proposal.source_branch.owner,
            review_type='General')
        self.assertEqual('general', reference.review_type)
        merge_proposal.nominateReviewer(
            reviewer=reviewer, registrant=merge_proposal.source_branch.owner,
            review_type='Specific')
        # Note we're using the reference from the first call
        self.assertEqual('specific', reference.review_type)

    def _check_mp_branch_visibility(self, branch, reviewer):
        # The reviewer is subscribed to the branch and can see it.
        sub = branch.getSubscription(reviewer)
        self.assertEqual(
            BranchSubscriptionNotificationLevel.NOEMAIL,
            sub.notification_level)
        self.assertEqual(
            BranchSubscriptionDiffSize.NODIFF, sub.max_diff_lines)
        self.assertEqual(
            CodeReviewNotificationLevel.FULL, sub.review_level)
        # The reviewer can see the branch.
        self.assertTrue(branch.visibleByUser(reviewer))
        if branch.stacked_on is not None:
            self._check_mp_branch_visibility(branch.stacked_on, reviewer)

    def _test_nominate_grants_visibility(self, reviewer):
        """Nominated reviewers can see the source and target branches."""
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        # We make a source branch stacked on a private one.
        base_branch = self.factory.makeBranch(
            owner=owner, product=product,
            information_type=InformationType.USERDATA)
        source_branch = self.factory.makeBranch(
            stacked_on=base_branch, product=product, owner=owner)
        target_branch = self.factory.makeBranch(owner=owner, product=product)
        login_person(owner)
        merge_proposal = self.factory.makeBranchMergeProposal(
            source_branch=source_branch,
            target_branch=target_branch)
        target_branch.setPrivate(True, owner)
        # The reviewer can't see the source or target branches.
        self.assertFalse(source_branch.visibleByUser(reviewer))
        self.assertFalse(target_branch.visibleByUser(reviewer))
        merge_proposal.nominateReviewer(
            reviewer=reviewer,
            registrant=merge_proposal.source_branch.owner)
        for branch in [source_branch, target_branch]:
            self._check_mp_branch_visibility(branch, reviewer)

    def test_nominate_person_grants_visibility(self):
        reviewer = self.factory.makePerson()
        self._test_nominate_grants_visibility(reviewer)

    def test_nominate_team_grants_visibility(self):
        reviewer = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED)
        self._test_nominate_grants_visibility(reviewer)

    def _assertVoteReference(self, votes, reviewer, comment):
        self.assertEqual(1, len(votes))
        vote_reference = votes[0]
        self.assertEqual(reviewer, vote_reference.reviewer)
        self.assertEqual(reviewer, vote_reference.registrant)
        self.assertIsNone(vote_reference.review_type)
        self.assertEqual(comment, vote_reference.comment)

    def test_comment_with_vote_creates_reference(self):
        """A comment with a vote creates a vote reference."""
        reviewer = self.factory.makePerson()
        merge_proposal = self.factory.makeBranchMergeProposal(
            reviewer=reviewer, registrant=reviewer)
        comment = merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE)
        votes = list(merge_proposal.votes)
        self._assertVoteReference(votes, reviewer, comment)

    def test_comment_without_a_vote_does_not_create_reference(self):
        """A comment with a vote creates a vote reference."""
        reviewer = self.factory.makePerson()
        merge_proposal = make_merge_proposal_without_reviewers(self.factory)
        merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content')
        self.assertEqual([], list(merge_proposal.votes))

    def test_second_vote_by_person_just_alters_reference(self):
        """A second vote changes the comment reference only."""
        reviewer = self.factory.makePerson()
        merge_proposal = self.factory.makeBranchMergeProposal(
            reviewer=reviewer, registrant=reviewer)
        merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.DISAPPROVE)
        comment2 = merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE)
        votes = list(merge_proposal.votes)
        self._assertVoteReference(votes, reviewer, comment2)

    def test_vote_by_nominated_reuses_reference(self):
        """A comment with a vote for a nominated reviewer alters reference."""
        reviewer = self.factory.makePerson()
        merge_proposal, ignore = self.makeProposalWithReviewer(
            reviewer=reviewer, review_type='general')
        login(merge_proposal.source_branch.owner.preferredemail.email)
        comment = merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE, review_type='general')

        votes = list(merge_proposal.votes)
        self.assertEqual(1, len(votes))
        vote_reference = votes[0]
        self.assertEqual(reviewer, vote_reference.reviewer)
        self.assertEqual(merge_proposal.registrant,
                         vote_reference.registrant)
        self.assertEqual('general', vote_reference.review_type)
        self.assertEqual(comment, vote_reference.comment)

    def test_claiming_team_review(self):
        # A person in a team claims a team review of the same type.
        reviewer = self.factory.makePerson()
        team = self.factory.makeTeam(owner=reviewer)
        merge_proposal, ignore = self.makeProposalWithReviewer(
            reviewer=team, review_type='general')
        login(merge_proposal.source_branch.owner.preferredemail.email)
        [vote] = list(merge_proposal.votes)
        self.assertEqual(team, vote.reviewer)
        comment = merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE, review_type='general')
        self.assertEqual(reviewer, vote.reviewer)
        self.assertEqual('general', vote.review_type)
        self.assertEqual(comment, vote.comment)

    def test_claiming_tagless_team_review_with_tag(self):
        # A person in a team claims a team review of the same type, or if
        # there isn't a team review with that specified type, but there is a
        # team review that doesn't have a review type set, then claim that
        # one.
        reviewer = self.factory.makePerson()
        team = self.factory.makeTeam(owner=reviewer)
        merge_proposal = self.factory.makeBranchMergeProposal(reviewer=team)
        login(merge_proposal.source_branch.owner.preferredemail.email)
        [vote] = list(merge_proposal.votes)
        self.assertEqual(team, vote.reviewer)
        comment = merge_proposal.createComment(
            reviewer, 'Message subject', 'Message content',
            vote=CodeReviewVote.APPROVE, review_type='general')
        self.assertEqual(reviewer, vote.reviewer)
        self.assertEqual('general', vote.review_type)
        self.assertEqual(comment, vote.comment)
        # Still only one vote.
        self.assertEqual(1, len(list(merge_proposal.votes)))


class TestBranchMergeProposalResubmit(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_resubmit(self):
        """Ensure that resubmit performs its basic function.

        It should create a new merge proposal, mark the old one as superseded,
        and set its status to superseded.
        """
        bmp1 = self.factory.makeBranchMergeProposal()
        login_person(bmp1.registrant)
        bmp2 = bmp1.resubmit(bmp1.registrant)
        self.assertNotEqual(bmp1.id, bmp2.id)
        self.assertEqual(
            bmp1.queue_status, BranchMergeProposalStatus.SUPERSEDED)
        self.assertEqual(
            bmp2.queue_status, BranchMergeProposalStatus.NEEDS_REVIEW)
        self.assertEqual(
            bmp2, bmp1.superseded_by)
        self.assertEqual(bmp1.source_branch, bmp2.source_branch)
        self.assertEqual(bmp1.target_branch, bmp2.target_branch)
        self.assertEqual(bmp1.prerequisite_branch, bmp2.prerequisite_branch)

    def test_resubmit_re_requests_review(self):
        """Resubmit should request new reviews.

        Both those who have already reviewed and those who have been nominated
        to review should be requested to review the new proposal.
        """
        bmp1 = self.factory.makeBranchMergeProposal()
        nominee = self.factory.makePerson()
        login_person(bmp1.registrant)
        bmp1.nominateReviewer(nominee, bmp1.registrant, 'nominee')
        reviewer = self.factory.makePerson()
        bmp1.createComment(
            reviewer, 'I like', vote=CodeReviewVote.APPROVE,
            review_type='specious')
        bmp2 = bmp1.resubmit(bmp1.registrant)
        self.assertEqual(
            set([(bmp1.target_branch.owner, None), (nominee, 'nominee'),
                 (reviewer, 'specious')]),
            set((vote.reviewer, vote.review_type) for vote in bmp2.votes))

    def test_resubmit_no_reviewers(self):
        """Resubmitting a proposal with no reviewers should work."""
        bmp = make_merge_proposal_without_reviewers(self.factory)
        with person_logged_in(bmp.registrant):
            bmp.resubmit(bmp.registrant)

    def test_resubmit_changes_branches(self):
        """Resubmit changes branches, if specified."""
        original = self.factory.makeBranchMergeProposal()
        self.useContext(person_logged_in(original.registrant))
        branch_target = original.source_branch.target
        new_source = self.factory.makeBranchTargetBranch(branch_target)
        new_target = self.factory.makeBranchTargetBranch(branch_target)
        new_prerequisite = self.factory.makeBranchTargetBranch(branch_target)
        revised = original.resubmit(original.registrant, new_source,
                new_target, new_prerequisite)
        self.assertEqual(new_source, revised.source_branch)
        self.assertEqual(new_target, revised.target_branch)
        self.assertEqual(new_prerequisite, revised.prerequisite_branch)

    def test_resubmit_changes_description(self):
        """Resubmit changes description, if specified."""
        original = self.factory.makeBranchMergeProposal()
        self.useContext(person_logged_in(original.registrant))
        revised = original.resubmit(original.registrant, description='foo')
        self.assertEqual('foo', revised.description)

    def test_resubmit_breaks_link(self):
        """Resubmit breaks link, if specified."""
        original = self.factory.makeBranchMergeProposal()
        self.useContext(person_logged_in(original.registrant))
        original.resubmit(
            original.registrant, break_link=True)
        self.assertIs(None, original.superseded_by)

    def test_resubmit_with_active_retains_state(self):
        """Resubmit does not change proposal if an active proposal exists."""
        first_mp = self.factory.makeBranchMergeProposal()
        with person_logged_in(first_mp.registrant):
            first_mp.rejectBranch(first_mp.target_branch.owner, 'a')
            second_mp = self.factory.makeBranchMergeProposal(
                source_branch=first_mp.source_branch,
                target_branch=first_mp.target_branch)
            expected_exc = ExpectedException(
                BranchMergeProposalExists, 'There is already a branch merge'
                ' proposal registered for branch .* to land on .* that is'
                ' still active.')
            with expected_exc:
                first_mp.resubmit(first_mp.registrant)
            self.assertEqual(
                second_mp, expected_exc.caught_exc.existing_proposal)
            self.assertEqual(
                BranchMergeProposalStatus.REJECTED, first_mp.queue_status)

    def test_resubmit_on_inactive_retains_state_new_branches(self):
        """Resubmit with branches doesn't change proposal."""
        first_mp = self.factory.makeBranchMergeProposal()
        with person_logged_in(first_mp.registrant):
            first_mp.rejectBranch(first_mp.target_branch.owner, 'a')
            second_mp = self.factory.makeBranchMergeProposal()
            with ExpectedException(BranchMergeProposalExists, ''):
                first_mp.resubmit(
                    first_mp.registrant, second_mp.source_branch,
                    second_mp.target_branch)
            self.assertEqual(
                BranchMergeProposalStatus.REJECTED, first_mp.queue_status)


class TestUpdatePreviewDiff(TestCaseWithFactory):
    """Test the updateMergeDiff method of BranchMergeProposal."""

    layer = LaunchpadFunctionalLayer

    def _updatePreviewDiff(self, merge_proposal):
        # Update the preview diff for the merge proposal.
        diff_text = (
            "=== modified file 'sample.py'\n"
            "--- sample\t2009-01-15 23:44:22 +0000\n"
            "+++ sample\t2009-01-29 04:10:57 +0000\n"
            "@@ -19,7 +19,7 @@\n"
            " from zope.interface import implements\n"
            "\n"
            " from storm.expr import Desc, Join, LeftJoin\n"
            "-from storm.references import Reference\n"
            "+from storm.locals import Int, Reference\n"
            " from sqlobject import ForeignKey, IntCol\n"
            "\n"
            " from lp.services.config import config\n")
        diff_stat = {'sample': (1, 1)}
        login_person(merge_proposal.registrant)
        merge_proposal.updatePreviewDiff(
            diff_text, u"source_id", u"target_id")
        # Have to commit the transaction to make the Librarian file
        # available.
        transaction.commit()
        return diff_text, diff_stat

    def test_new_diff(self):
        # Test that both the PreviewDiff and the Diff get created.
        merge_proposal = self.factory.makeBranchMergeProposal()
        diff_text, diff_stat = self._updatePreviewDiff(merge_proposal)
        self.assertEqual(diff_text, merge_proposal.preview_diff.text)
        self.assertEqual(diff_stat, merge_proposal.preview_diff.diffstat)

    def test_update_diff(self):
        # Test that both the PreviewDiff and the Diff get updated.
        merge_proposal = self.factory.makeBranchMergeProposal()
        login_person(merge_proposal.registrant)
        diff_bytes = ''.join(unified_diff('', 'random text'))
        merge_proposal.updatePreviewDiff(diff_bytes, u"a", u"b")
        transaction.commit()
        # Extract the primary key ids for the preview diff and the diff to
        # show that we are not reusing the objects.
        preview_diff_id = removeSecurityProxy(merge_proposal.preview_diff).id
        diff_id = removeSecurityProxy(merge_proposal.preview_diff).diff_id
        diff_text, diff_stat = self._updatePreviewDiff(merge_proposal)
        self.assertEqual(diff_text, merge_proposal.preview_diff.text)
        self.assertEqual(diff_stat, merge_proposal.preview_diff.diffstat)
        self.assertNotEqual(
            preview_diff_id,
            removeSecurityProxy(merge_proposal.preview_diff).id)
        self.assertNotEqual(
            diff_id, removeSecurityProxy(merge_proposal.preview_diff).diff_id)


class TestNextPreviewDiffJob(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_returns_none_if_job_not_pending(self):
        """Jobs are shown while pending."""
        bmp = self.factory.makeBranchMergeProposal()
        job = bmp.next_preview_diff_job
        self.assertEqual(job, bmp.next_preview_diff_job)
        job.start()
        self.assertEqual(job, bmp.next_preview_diff_job)
        job.fail()
        self.assertIs(None, bmp.next_preview_diff_job)

    def makeBranchMergeProposalNoPending(self):
        bmp = self.factory.makeBranchMergeProposal()
        bmp.next_preview_diff_job.start()
        bmp.next_preview_diff_job.complete()
        return bmp

    def test_returns_update_preview_diff_job(self):
        """UpdatePreviewDiffJobs can be returned."""
        bmp = self.makeBranchMergeProposalNoPending()
        updatejob = UpdatePreviewDiffJob.create(bmp)
        Store.of(updatejob.context).flush()
        self.assertEqual(updatejob, bmp.next_preview_diff_job)

    def test_returns_first_job(self):
        """First-created job is returned."""
        bmp = self.makeBranchMergeProposalNoPending()
        updatejob = UpdatePreviewDiffJob.create(bmp)
        UpdatePreviewDiffJob.create(bmp)
        self.assertEqual(updatejob, bmp.next_preview_diff_job)

    def test_does_not_return_jobs_for_other_proposals(self):
        """Jobs for other merge proposals are not returned."""
        bmp = self.factory.makeBranchMergeProposal()
        bmp.next_preview_diff_job.start()
        bmp.next_preview_diff_job.complete()
        self.factory.makeBranchMergeProposal()
        self.assertIs(None, bmp.next_preview_diff_job)


class TestRevisionEndDate(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_revision_end_date_active(self):
        # An active merge proposal will have None as an end date.
        bmp = self.factory.makeBranchMergeProposal()
        self.assertIs(None, bmp.revision_end_date)

    def test_revision_end_date_merged(self):
        # An merged proposal will have the date merged as an end date.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.MERGED)
        self.assertEqual(bmp.date_merged, bmp.revision_end_date)

    def test_revision_end_date_rejected(self):
        # An rejected proposal will have the date reviewed as an end date.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.REJECTED)
        self.assertEqual(bmp.date_reviewed, bmp.revision_end_date)


class TestGetRevisionsSinceReviewStart(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def assertRevisionGroups(self, bmp, expected_groups):
        """Get the groups for the merge proposal and check them."""
        revision_groups = list(bmp.getRevisionsSinceReviewStart())
        self.assertEqual(expected_groups, revision_groups)

    def test_getRevisionsSinceReviewStart_no_revisions(self):
        # If there have been no revisions pushed since the start of the
        # review, the method returns an empty list.
        bmp = self.factory.makeBranchMergeProposal()
        self.assertRevisionGroups(bmp, [])

    def test_getRevisionsSinceReviewStart_groups(self):
        # Revisions that were scanned at the same time have the same
        # date_created.  These revisions are grouped together.
        review_date = datetime(2009, 9, 10, tzinfo=UTC)
        bmp = self.factory.makeBranchMergeProposal(
            date_created=review_date)
        with person_logged_in(bmp.registrant):
            bmp.requestReview(review_date)
        revision_date = review_date + timedelta(days=1)
        revisions = []
        for date in range(2):
            revisions.append(
                add_revision_to_branch(
                    self.factory, bmp.source_branch, revision_date))
            revisions.append(
                add_revision_to_branch(
                    self.factory, bmp.source_branch, revision_date))
            revision_date += timedelta(days=1)
        expected_groups = [
            [revisions[0], revisions[1], revisions[2], revisions[3]]]
        self.assertRevisionGroups(bmp, expected_groups)

    def test_getRevisionsSinceReviewStart_groups_with_comments(self):
        # Revisions that were scanned at the same time have the same
        # date_created.  These revisions are grouped together.
        bmp = self.factory.makeBranchMergeProposal(
            date_created=self.factory.getUniqueDate())
        revisions = []
        revisions.append(
            add_revision_to_branch(
                self.factory, bmp.source_branch,
                self.factory.getUniqueDate()))
        revisions.append(
            add_revision_to_branch(
                self.factory, bmp.source_branch,
                self.factory.getUniqueDate()))
        with person_logged_in(self.factory.makePerson()):
            self.factory.makeCodeReviewComment(
                merge_proposal=bmp,
                date_created=self.factory.getUniqueDate())
        revisions.append(
            add_revision_to_branch(
                self.factory, bmp.source_branch,
                self.factory.getUniqueDate()))

        expected_groups = [
            [revisions[0], revisions[1]], [revisions[2]]]
        self.assertRevisionGroups(bmp, expected_groups)


class TestBranchMergeProposalGetIncrementalDiffs(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_getIncrementalDiffs(self):
        """getIncrementalDiffs returns the requested values or None.

        None is returned if there is no IncrementalDiff for the requested
        revision pair and branch_merge_proposal.
        """
        bmp = self.factory.makeBranchMergeProposal()
        diff1 = self.factory.makeIncrementalDiff(merge_proposal=bmp)
        diff2 = self.factory.makeIncrementalDiff(merge_proposal=bmp)
        diff3 = self.factory.makeIncrementalDiff()
        result = bmp.getIncrementalDiffs([
            (diff1.old_revision, diff1.new_revision),
            (diff2.old_revision, diff2.new_revision),
            # Wrong merge proposal
            (diff3.old_revision, diff3.new_revision),
            # Mismatched revisions
            (diff1.old_revision, diff2.new_revision),
        ])
        self.assertEqual([diff1, diff2, None, None], result)

    def test_getIncrementalDiffs_respects_input_order(self):
        """The order of the output follows the input order."""
        bmp = self.factory.makeBranchMergeProposal()
        diff1 = self.factory.makeIncrementalDiff(merge_proposal=bmp)
        diff2 = self.factory.makeIncrementalDiff(merge_proposal=bmp)
        result = bmp.getIncrementalDiffs([
            (diff1.old_revision, diff1.new_revision),
            (diff2.old_revision, diff2.new_revision),
        ])
        self.assertEqual([diff1, diff2], result)
        result = bmp.getIncrementalDiffs([
            (diff2.old_revision, diff2.new_revision),
            (diff1.old_revision, diff1.new_revision),
        ])
        self.assertEqual([diff2, diff1], result)


class TestGetUnlandedSourceBranchRevisions(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_getUnlandedSourceBranchRevisions(self):
        # Revisions in the source branch but not in the target are shown
        # as unlanded.
        bmp = self.factory.makeBranchMergeProposal()
        self.factory.makeRevisionsForBranch(bmp.source_branch, count=5)
        r1 = bmp.source_branch.getBranchRevision(sequence=1)
        initial_revisions = list(bmp.getUnlandedSourceBranchRevisions())
        self.assertEquals(5, len(initial_revisions))
        self.assertIn(r1, initial_revisions)
        # If we push one of the revisions into the target, it disappears
        # from the unlanded list.
        bmp.target_branch.createBranchRevision(1, r1.revision)
        partial_revisions = list(bmp.getUnlandedSourceBranchRevisions())
        self.assertEquals(4, len(partial_revisions))
        self.assertNotIn(r1, partial_revisions)


class TestWebservice(WebServiceTestCase):
    """Tests for the webservice."""

    def test_getMergeProposals_with_merged_revnos(self):
        """Specifying merged revnos selects the correct merge proposal."""
        registrant = self.factory.makePerson()
        mp = self.factory.makeBranchMergeProposal(registrant=registrant)
        launchpad = launchpadlib_for(
            'test', registrant,
            service_root=self.layer.appserver_root_url('api'))

        with person_logged_in(registrant):
            mp.markAsMerged(merged_revno=123)
            transaction.commit()
            target = ws_object(launchpad, mp.target_branch)
            mp = ws_object(launchpad, mp)
        self.assertEqual(
            [mp], list(target.getMergeProposals(
                status=['Merged'], merged_revnos=[123])))

    def test_getRelatedBugTasks(self):
        """Test the getRelatedBugTasks API."""
        db_bmp = self.factory.makeBranchMergeProposal()
        db_bug = self.factory.makeBug()
        db_bmp.source_branch.linkBug(db_bug, db_bmp.registrant)
        transaction.commit()
        bmp = self.wsObject(db_bmp)
        bugtask = self.wsObject(db_bug.default_bugtask)
        self.assertEqual([bugtask], list(bmp.getRelatedBugTasks()))

    def test_setStatus_invalid_transition(self):
        """Emit BadRequest when an invalid transition is requested."""
        bmp = self.factory.makeBranchMergeProposal()
        with person_logged_in(bmp.registrant):
            bmp.resubmit(bmp.registrant)
        transaction.commit()
        ws_bmp = self.wsObject(bmp, user=bmp.target_branch.owner)
        with ExpectedException(
            BadRequest,
            '(.|\n)*Invalid state transition for merge proposal(.|\n)*'):
            ws_bmp.setStatus(status='Approved')

    def test_previewdiff_with_null_diffstat(self):
        # A previewdiff with an empty diffstat doesn't crash when fetched.
        previewdiff = self.factory.makePreviewDiff()
        previewdiff.diff.diffstat = None
        user = previewdiff.branch_merge_proposal.target_branch.owner
        ws_previewdiff = self.wsObject(previewdiff, user=user)
        self.assertIsNone(ws_previewdiff.diffstat)
