# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for branch-related components"""

from lazr.lifecycle.event import ObjectModifiedEvent

from lp.code.adapters.branch import BranchMergeProposalDelta
from lp.code.enums import BranchMergeProposalStatus
from lp.testing import (
    EventRecorder,
    login,
    TestCase,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class TestBranchMergeProposalDelta(TestCase):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        login('foo.bar@canonical.com')
        self.factory = LaunchpadObjectFactory()

    def test_snapshot(self):
        """Test that the snapshot method produces a reasonable snapshot"""
        merge_proposal = self.factory.makeBranchMergeProposal()
        merge_proposal.commit_message = 'foo'
        merge_proposal.whiteboard = 'bar'
        snapshot = BranchMergeProposalDelta.snapshot(merge_proposal)
        self.assertEqual('foo', snapshot.commit_message)
        self.assertEqual('bar', snapshot.whiteboard)

    def test_noModification(self):
        """When there are no modifications, no delta should be returned."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        old_merge_proposal = BranchMergeProposalDelta.snapshot(merge_proposal)
        delta = BranchMergeProposalDelta.construct(
            old_merge_proposal, merge_proposal)
        assert delta is None

    def test_Modification(self):
        """When there are modifications, the delta reflects them."""
        registrant = self.factory.makePerson(
            displayname='Baz Qux', email='baz.qux@example.com')
        merge_proposal = self.factory.makeBranchMergeProposal(
            registrant=registrant)
        old_merge_proposal = BranchMergeProposalDelta.snapshot(merge_proposal)
        merge_proposal.commit_message = 'Change foo into bar.'
        merge_proposal.description = 'Set the description.'
        merge_proposal.markAsMerged()
        delta = BranchMergeProposalDelta.construct(
            old_merge_proposal, merge_proposal)
        assert delta is not None
        self.assertEqual('Change foo into bar.', delta.commit_message)
        self.assertEqual('Set the description.', delta.description)
        self.assertEqual(
            {'old': BranchMergeProposalStatus.WORK_IN_PROGRESS,
            'new': BranchMergeProposalStatus.MERGED},
            delta.queue_status)

    def test_monitor(self):
        """\
        `monitor` observes changes to a given merge proposal and issues
        `ObjectModifiedEvent` events if there are any.
        """
        merge_proposal = self.factory.makeBranchMergeProposal()
        with EventRecorder() as event_recorder:
            # No event is issued when nothing is changed.
            with BranchMergeProposalDelta.monitor(merge_proposal):
                pass  # Don't make changes.
            self.assertEqual(0, len(event_recorder.events))
            # When one or more properties (of interest to
            # BranchMergeProposalDelta) are changed, a single event is issued.
            with BranchMergeProposalDelta.monitor(merge_proposal):
                merge_proposal.commit_message = "foo"
                merge_proposal.whiteboard = "bar"
            self.assertEqual(1, len(event_recorder.events))
            [event] = event_recorder.events
            self.assertIsInstance(event, ObjectModifiedEvent)
            self.assertEqual(merge_proposal, event.object)
            self.assertContentEqual(
                ["commit_message", "whiteboard"],
                event.edited_fields)
