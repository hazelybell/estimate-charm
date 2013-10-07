# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the scanner's merge detection."""

__metaclass__ = type

import logging

from bzrlib.revision import NULL_REVISION
import transaction
from zope.component import getUtility
from zope.event import notify

from lp.code.enums import (
    BranchLifecycleStatus,
    BranchMergeProposalStatus,
    )
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.model.branchmergeproposaljob import (
    BranchMergeProposalJob,
    BranchMergeProposalJobType,
    )
from lp.codehosting.scanner import (
    events,
    mergedetection,
    )
from lp.codehosting.scanner.tests.test_bzrsync import (
    BzrSyncTestCase,
    run_as_db_user,
    )
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.osutils import override_environ
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.mail_helpers import pop_notifications


class TestAutoMergeDetectionForMergeProposals(BzrSyncTestCase):
    """Test the scanner's ability to mark merge proposals as merged."""

    def setUp(self):
        BzrSyncTestCase.setUp(self)

    @run_as_db_user(config.launchpad.dbuser)
    def createProposal(self, source, target):
        # The scanner doesn't have insert rights, so do it here.
        source.addLandingTarget(source.owner, target)
        transaction.commit()

    def _createBranchesAndProposal(self):
        # Create two branches where the trunk has the branch as a merge.  Also
        # create a merge proposal from the branch to the trunk.
        (db_trunk, trunk_tree), (db_branch, branch_tree) = (
            self.makeBranchWithMerge('base', 'trunk', 'branch', 'merge'))
        trunk_id = db_trunk.id
        branch_id = db_branch.id
        self.createProposal(db_branch, db_trunk)
        # Reget the objects due to transaction boundary.
        branch_lookup = getUtility(IBranchLookup)
        db_trunk = branch_lookup.get(trunk_id)
        db_branch = branch_lookup.get(branch_id)
        proposal = list(db_branch.landing_targets)[0]
        return proposal, db_trunk, db_branch, branch_tree

    def _scanTheBranches(self, branch1, branch2):
        for branch in (branch1, branch2):
            scanner = self.makeBzrSync(branch)
            scanner.syncBranchAndClose()

    def test_auto_merge_proposals_real_merge(self):
        # If there is a merge proposal where the tip of the source is in the
        # ancestry of the target, mark it as merged.
        proposal, db_trunk, db_branch, branch_tree = (
            self._createBranchesAndProposal())

        self._scanTheBranches(db_branch, db_trunk)
        # The proposal should now be merged.
        self.assertEqual(
            BranchMergeProposalStatus.MERGED,
            proposal.queue_status)
        self.assertEqual(3, proposal.merged_revno)

    def test_auto_merge_proposals_real_merge_target_scanned_first(self):
        # If there is a merge proposal where the tip of the source is in the
        # ancestry of the target, mark it as merged.
        proposal, db_trunk, db_branch, branch_tree = (
            self._createBranchesAndProposal())

        self._scanTheBranches(db_trunk, db_branch)
        # The proposal should now be merged.
        self.assertEqual(
            BranchMergeProposalStatus.MERGED,
            proposal.queue_status)

    def test_auto_merge_proposals_rejected_proposal(self):
        # If there is a merge proposal where the tip of the source is in the
        # ancestry of the target but the proposal is in a final state the
        # proposal is not marked as merged.

        proposal, db_trunk, db_branch, branch_tree = (
            self._createBranchesAndProposal())

        proposal.rejectBranch(db_trunk.owner, 'branch')

        self._scanTheBranches(db_branch, db_trunk)

        # The proposal should stay rejected..
        self.assertEqual(
            BranchMergeProposalStatus.REJECTED,
            proposal.queue_status)

    def test_auto_merge_proposals_rejected_proposal_target_scanned_first(
                                                                        self):
        # If there is a merge proposal where the tip of the source is in the
        # ancestry of the target but the proposal is in a final state the
        # proposal is not marked as merged.

        proposal, db_trunk, db_branch, branch_tree = (
            self._createBranchesAndProposal())

        proposal.rejectBranch(db_trunk.owner, 'branch')

        self._scanTheBranches(db_trunk, db_branch)

        # The proposal should stay rejected..
        self.assertEqual(
            BranchMergeProposalStatus.REJECTED,
            proposal.queue_status)

    def test_auto_merge_proposals_not_merged_proposal(self):
        # If there is a merge proposal where the tip of the source is not in
        # the ancestry of the target it is not marked as merged.

        proposal, db_trunk, db_branch, branch_tree = (
            self._createBranchesAndProposal())

        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            branch_tree.commit(u'another revision', rev_id='another-rev')
        current_proposal_status = proposal.queue_status
        self.assertNotEqual(
            current_proposal_status,
            BranchMergeProposalStatus.MERGED)

        self._scanTheBranches(db_branch, db_trunk)

        # The proposal should stay in the same state.
        self.assertEqual(current_proposal_status, proposal.queue_status)

    def test_auto_merge_proposals_not_merged_with_updated_source(self):
        # If there is a merge proposal where the tip of the source is not in
        # the ancestry of the target it is not marked as merged.

        proposal, db_trunk, db_branch, branch_tree = (
            self._createBranchesAndProposal())

        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            branch_tree.commit(u'another revision', rev_id='another-rev')
        current_proposal_status = proposal.queue_status
        self.assertNotEqual(
            current_proposal_status,
            BranchMergeProposalStatus.MERGED)

        self._scanTheBranches(db_trunk, db_branch)

        # The proposal should stay in the same state.
        self.assertEqual(current_proposal_status, proposal.queue_status)


class TestMergeDetection(TestCaseWithFactory):
    """Test that the merges are detected, and the handler called."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.product = self.factory.makeProduct()
        self.db_branch = self.factory.makeProductBranch(product=self.product)
        # Replace the built-in merge_detected with our test stub.
        self._original_merge_detected = mergedetection.merge_detected
        mergedetection.merge_detected = self.mergeDetected
        # Reset the recorded branches.
        self.merges = []

    def tearDown(self):
        mergedetection.merge_detected = self._original_merge_detected
        TestCaseWithFactory.tearDown(self)

    def autoMergeBranches(self, db_branch, new_ancestry):
        mergedetection.auto_merge_branches(
            events.ScanCompleted(
                db_branch=db_branch, bzr_branch=None,
                logger=None, new_ancestry=new_ancestry))

    def mergeDetected(self, logger, source, target):
        # Record the merged branches
        self.merges.append((source, target))

    def test_own_branch_not_emitted(self):
        # A merge is never emitted with the source branch being the same as
        # the target branch.
        self.db_branch.last_scanned_id = 'revid'
        self.autoMergeBranches(self.db_branch, ['revid'])
        self.assertEqual([], self.merges)

    def test_branch_tip_in_ancestry(self):
        # If there is another branch with their tip revision id in the
        # ancestry passed in, the merge detection is emitted.
        source = self.factory.makeProductBranch(product=self.product)
        source.last_scanned_id = 'revid'
        self.autoMergeBranches(self.db_branch, ['revid'])
        self.assertEqual([(source, self.db_branch)], self.merges)

    def test_branch_tip_in_ancestry_status_merged(self):
        # Branches that are already merged do emit events.
        source = self.factory.makeProductBranch(
            product=self.product,
            lifecycle_status=BranchLifecycleStatus.MERGED)
        source.last_scanned_id = 'revid'
        self.autoMergeBranches(self.db_branch, ['revid'])
        self.assertEqual([], self.merges)

    def test_other_branch_with_no_last_scanned_id(self):
        # Other branches for the product are checked, but if the tip revision
        # of the branch is not yet been set no merge event is emitted for that
        # branch.
        self.factory.makeProductBranch(product=self.product)
        self.autoMergeBranches(self.db_branch, ['revid'])
        self.assertEqual([], self.merges)

    def test_other_branch_with_NULL_REVISION_last_scanned_id(self):
        # Other branches for the product are checked, but if the tip revision
        # of the branch is the NULL_REVISION no merge event is emitted for
        # that branch.
        source = self.factory.makeProductBranch(product=self.product)
        source.last_scanned_id = NULL_REVISION
        self.autoMergeBranches(self.db_branch, ['revid'])
        self.assertEqual([], self.merges)

    def test_other_branch_same_tip_revision_not_emitted(self):
        # If two different branches have the same tip revision, then they are
        # conceptually the same branch, not one merged into the other.
        source = self.factory.makeProductBranch(product=self.product)
        source.last_scanned_id = 'revid'
        self.db_branch.last_scanned_id = 'revid'
        self.autoMergeBranches(self.db_branch, ['revid'])
        self.assertEqual([], self.merges)


class TestBranchMergeDetectionHandler(TestCaseWithFactory):
    """Test the merge_detected handler."""

    layer = LaunchpadZopelessLayer

    def test_mergeProposalMergeDetected(self):
        # A merge proposal that is merged has the proposal itself marked as
        # merged, and the source branch lifecycle status set as merged.
        product = self.factory.makeProduct()
        proposal = self.factory.makeBranchMergeProposal(product=product)
        product.development_focus.branch = proposal.target_branch
        self.assertNotEqual(
            BranchMergeProposalStatus.MERGED, proposal.queue_status)
        self.assertNotEqual(
            BranchLifecycleStatus.MERGED,
            proposal.source_branch.lifecycle_status)
        mergedetection.merge_detected(
            logging.getLogger(),
            proposal.source_branch, proposal.target_branch, proposal)
        self.assertEqual(
            BranchMergeProposalStatus.MERGED, proposal.queue_status)
        self.assertEqual(
            BranchLifecycleStatus.MERGED,
            proposal.source_branch.lifecycle_status)
        job = IStore(proposal).find(
            BranchMergeProposalJob,
            BranchMergeProposalJob.branch_merge_proposal == proposal,
            BranchMergeProposalJob.job_type ==
            BranchMergeProposalJobType.MERGE_PROPOSAL_UPDATED).one()
        derived_job = job.makeDerived()
        derived_job.run()
        notifications = pop_notifications()
        self.assertIn('Work in progress => Merged',
                      notifications[0].get_payload(decode=True))
        self.assertEqual(
            config.canonical.noreply_from_address, notifications[0]['From'])
        recipients = set(msg['x-envelope-to'] for msg in notifications)
        expected = set(
            [proposal.source_branch.registrant.preferredemail.email,
             proposal.target_branch.registrant.preferredemail.email])
        self.assertEqual(expected, recipients)

    def test_mergeProposalMergeDetected_not_series(self):
        # If the target branch is not a series branch, then the merge proposal
        # is still marked as merged, but the lifecycle status of the source
        # branch is not updated.
        proposal = self.factory.makeBranchMergeProposal()
        self.assertNotEqual(
            BranchMergeProposalStatus.MERGED, proposal.queue_status)
        self.assertNotEqual(
            BranchLifecycleStatus.MERGED,
            proposal.source_branch.lifecycle_status)
        mergedetection.merge_detected(
            logging.getLogger(),
            proposal.source_branch, proposal.target_branch, proposal)
        self.assertEqual(
            BranchMergeProposalStatus.MERGED, proposal.queue_status)
        self.assertNotEqual(
            BranchLifecycleStatus.MERGED,
            proposal.source_branch.lifecycle_status)

    def test_mergeOfTwoBranches_target_not_dev_focus(self):
        # The target branch must be the development focus in order for the
        # lifecycle status of the source branch to be updated to merged.
        source = self.factory.makeProductBranch()
        target = self.factory.makeProductBranch()
        mergedetection.merge_detected(logging.getLogger(), source, target)
        self.assertNotEqual(
            BranchLifecycleStatus.MERGED, source.lifecycle_status)

    def test_mergeOfTwoBranches_target_dev_focus(self):
        # If the target branch is the development focus branch of the product,
        # then the source branch gets its lifecycle status set to merged.
        product = self.factory.makeProduct()
        source = self.factory.makeProductBranch(product=product)
        target = self.factory.makeProductBranch(product=product)
        product.development_focus.branch = target
        mergedetection.merge_detected(logging.getLogger(), source, target)
        self.assertEqual(
            BranchLifecycleStatus.MERGED, source.lifecycle_status)

    def test_mergeOfTwoBranches_source_series_branch(self):
        # If the source branch is associated with a series, its lifecycle
        # status is not updated.
        product = self.factory.makeProduct()
        source = self.factory.makeProductBranch(product=product)
        target = self.factory.makeProductBranch(product=product)
        product.development_focus.branch = target
        series = product.newSeries(product.owner, 'new', '')
        series.branch = source

        mergedetection.merge_detected(logging.getLogger(), source, target)
        self.assertNotEqual(
            BranchLifecycleStatus.MERGED, source.lifecycle_status)

    def test_auto_merge_branches_subscribed(self):
        """Auto merging is triggered by ScanCompleted."""
        source = self.factory.makeBranch()
        source.last_scanned_id = '23foo'
        target = self.factory.makeBranchTargetBranch(source.target)
        target.product.development_focus.branch = target
        logger = logging.getLogger('test')
        notify(events.ScanCompleted(target, None, logger, ['23foo']))
        self.assertEqual(
            BranchLifecycleStatus.MERGED, source.lifecycle_status)


class TestFindMergedRevno(TestCase):
    """Tests for find_merged_revno."""

    def get_merge_graph(self):
        # Create a fake merge graph.
        return [
            ('rev-3', 0, (3,), False),
            ('rev-3a', 1, (15, 4, 8), False),
            ('rev-3b', 1, (15, 4, 7), False),
            ('rev-3c', 1, (15, 4, 6), False),
            ('rev-2', 0, (2,), False),
            ('rev-2a', 1, (4, 4, 8), False),
            ('rev-2b', 1, (4, 4, 7), False),
            ('rev-2-1a', 2, (7, 2, 47), False),
            ('rev-2-1b', 2, (7, 2, 45), False),
            ('rev-2-1c', 2, (7, 2, 42), False),
            ('rev-2c', 1, (4, 4, 6), False),
            ('rev-1', 0, (1,), False),
            ]

    def assertFoundRevisionNumber(self, expected, rev_id):
        merge_sorted = self.get_merge_graph()
        revno = mergedetection.find_merged_revno(merge_sorted, rev_id)
        if expected is None:
            self.assertIs(None, revno)
        else:
            self.assertEqual(expected, revno)

    def test_not_found(self):
        # If the rev_id passed into the function isn't in the merge sorted
        # graph, None is returned.
        self.assertFoundRevisionNumber(None, 'not-there')

    def test_existing_revision(self):
        # If a revision is found, the last mainline revision is returned.
        self.assertFoundRevisionNumber(3, 'rev-3b')
        self.assertFoundRevisionNumber(2, 'rev-2-1c')
        self.assertFoundRevisionNumber(1, 'rev-1')
