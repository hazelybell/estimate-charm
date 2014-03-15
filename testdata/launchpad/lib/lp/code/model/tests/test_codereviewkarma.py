# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for karma allocated for code reviews."""

__metaclass__ = type

from lp.registry.interfaces.karma import IKarmaAssignedEvent
from lp.registry.interfaces.person import IPerson
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.event import TestEventListener
from lp.testing.layers import DatabaseFunctionalLayer


class TestCodeReviewKarma(TestCaseWithFactory):
    """Test the allocation of karma for revisions.

    As part of the confirmation that karma is allocated, this also confirms
    that the events are being fired, and the appropriate karma allocation
    functions have been registered correctly in the zcml.
    """

    layer = DatabaseFunctionalLayer
    karma_listener = None

    def setUp(self):
        # Use an admin to get launchpad.Edit on all the branches to easily
        # approve and reject the proposals.
        super(TestCodeReviewKarma, self).setUp('admin@canonical.com')
        # The way the zope infrastructure works is that we can register
        # subscribers easily, but there is no way to unregister them (bug
        # 2338).  TestEventListener does this with by setting a property to
        # stop calling the callback function.  Instead of ending up with a
        # whole pile of registered inactive event listeners, we just
        # reactivate the one we have if there is one.
        if self.karma_listener is None:
            self.karma_listener = TestEventListener(
                IPerson, IKarmaAssignedEvent, self._on_karma_assigned)
        else:
            self.karma_listener._active = True

        self.karma_events = []

    def tearDown(self):
        self.karma_listener.unregister()
        super(TestCodeReviewKarma, self).tearDown()

    def _on_karma_assigned(self, object, event):
        # Store the karma event for checking in the test method.
        self.karma_events.append(event.karma)

    def assertOneKarmaEvent(self, receiver, action_name):
        # Make sure that there is one and only one karma event, and it is for
        # the right user and of the right type.
        self.assertEqual(1, len(self.karma_events))
        event = self.karma_events[0]
        self.assertEqual(receiver, event.person)
        self.assertEqual(action_name, event.action.name)

    def test_mergeProposalCreationAllocatesKarma(self):
        # Registering a branch merge proposal creates a karma event for the
        # registrant.
        source_branch = self.factory.makeProductBranch()
        target_branch = self.factory.makeProductBranch(
            product=source_branch.product)
        registrant = self.factory.makePerson()
        # We need to clear the karma event list before we add the landing
        # target as there would be other karma events for the branch
        # creations.
        self.karma_events = []
        # The normal SQLObject events use the logged in person.
        login_person(registrant)
        source_branch.addLandingTarget(registrant, target_branch)
        self.assertOneKarmaEvent(registrant, 'branchmergeproposed')

    def test_commentOnProposal(self):
        # Any person commenting on a code review gets a karma event.
        proposal = self.factory.makeBranchMergeProposal()
        commenter = self.factory.makePerson()
        self.karma_events = []
        login_person(commenter)
        proposal.createComment(commenter, "A comment", "The review.")
        self.assertOneKarmaEvent(commenter, 'codereviewcomment')

    def test_reviewerCommentingOnProposal(self):
        # A reviewer commenting on a code review gets a different karma event
        # to non-reviewers commenting.
        proposal = self.factory.makeBranchMergeProposal()
        commenter = proposal.target_branch.owner
        self.karma_events = []
        login_person(commenter)
        proposal.createComment(commenter, "A comment", "The review.")
        self.assertOneKarmaEvent(commenter, 'codereviewreviewercomment')

    def test_commentOnOwnProposal(self):
        # If the reviewer is also the registrant of the proposal, they just
        # get a normal code review comment karma event.
        commenter = self.factory.makePerson()
        target_branch = self.factory.makeProductBranch(owner=commenter)
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch, registrant=commenter)
        self.karma_events = []
        login_person(commenter)
        proposal.createComment(commenter, "A comment", "The review.")
        self.assertOneKarmaEvent(commenter, 'codereviewcomment')

    def test_approveCodeReview(self):
        # Approving a code review is a significant event, and as such gets its
        # own karma event.
        proposal = self.factory.makeBranchMergeProposal()
        reviewer = proposal.target_branch.owner
        self.karma_events = []
        proposal.approveBranch(reviewer, "A rev id.")
        self.assertOneKarmaEvent(reviewer, 'branchmergeapproved')

    def test_approvingOwnCodeReview(self):
        # Approving your own merge proposal isn't such a significant event.
        reviewer = self.factory.makePerson()
        target_branch = self.factory.makeProductBranch(owner=reviewer)
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch, registrant=reviewer)
        self.karma_events = []
        proposal.approveBranch(reviewer, "A rev id.")
        self.assertOneKarmaEvent(reviewer, 'branchmergeapprovedown')

    def test_rejectedCodeReview(self):
        # Rejecting a code review is also a significant event, and as such
        # gets its own karma event.
        proposal = self.factory.makeBranchMergeProposal()
        reviewer = proposal.target_branch.owner
        self.karma_events = []
        proposal.rejectBranch(reviewer, "A rev id.")
        self.assertOneKarmaEvent(reviewer, 'branchmergerejected')

    def test_rejectedOwnCodeReview(self):
        # Rejecting your own merge proposal isn't such a significant event
        # either, and I don't know why someone would, but hey, people are
        # strange.
        reviewer = self.factory.makePerson()
        target_branch = self.factory.makeProductBranch(owner=reviewer)
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=target_branch, registrant=reviewer)
        self.karma_events = []
        proposal.rejectBranch(reviewer, "A rev id.")
        self.assertOneKarmaEvent(reviewer, 'branchmergerejectedown')
