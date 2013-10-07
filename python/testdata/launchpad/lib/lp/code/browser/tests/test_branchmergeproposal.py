# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


"""Unit tests for BranchMergeProposals."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from difflib import unified_diff

from lazr.restful.interfaces import IJSONRequestCache
import pytz
import simplejson
from soupmatchers import (
    HTMLContains,
    Tag,
    )
from testtools.matchers import (
    MatchesRegex,
    Not,
    )
import transaction
from zope.component import getMultiAdapter
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.browser.branch import RegisterBranchMergeProposalView
from lp.code.browser.branchmergeproposal import (
    BranchMergeProposalAddVoteView,
    BranchMergeProposalChangeStatusView,
    BranchMergeProposalContextMenu,
    BranchMergeProposalMergedView,
    BranchMergeProposalResubmitView,
    BranchMergeProposalVoteView,
    DecoratedCodeReviewVoteReference,
    ICodeReviewNewRevisions,
    latest_proposals_for_each_branch,
    )
from lp.code.browser.codereviewcomment import CodeReviewDisplayComment
from lp.code.enums import (
    BranchMergeProposalStatus,
    CodeReviewVote,
    )
from lp.code.model.diff import PreviewDiff
from lp.code.tests.helpers import (
    add_revision_to_branch,
    make_merge_proposal_without_reviewers,
    )
from lp.registry.enums import (
    PersonVisibility,
    TeamMembershipPolicy,
    )
from lp.services.librarian.interfaces.client import LibrarianServerError
from lp.services.messages.model.message import MessageSet
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import (
    BrowserNotificationLevel,
    IPrimaryContext,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    BrowserTestCase,
    feature_flags,
    login_person,
    monkey_patch,
    person_logged_in,
    set_feature_flag,
    TestCaseWithFactory,
    time_counter,
    verifyObject,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.views import create_initialized_view


class TestBranchMergeProposalPrimaryContext(TestCaseWithFactory):
    """Tests the adaptation of a merge proposal into a primary context."""

    layer = DatabaseFunctionalLayer

    def testPrimaryContext(self):
        # The primary context of a merge proposal is the same as the primary
        # context of the source_branch.
        bmp = self.factory.makeBranchMergeProposal()
        self.assertEqual(
            IPrimaryContext(bmp).context,
            IPrimaryContext(bmp.source_branch).context)


class TestBranchMergeProposalContextMenu(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_add_comment_enabled_when_not_mergeable(self):
        """It should be possible to comment on an unmergeable proposal."""
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.REJECTED)
        login_person(bmp.registrant)
        menu = BranchMergeProposalContextMenu(bmp)
        self.assertTrue(menu.add_comment().enabled)


class TestDecoratedCodeReviewVoteReference(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_commentEnabled(self):
        """It should be possible to review an unmergeable proposal."""
        request = self.factory.makeCodeReviewVoteReference()
        bmp = request.branch_merge_proposal
        bmp.rejectBranch(bmp.target_branch.owner, 'foo')
        d = DecoratedCodeReviewVoteReference(request, request.reviewer, None)
        self.assertTrue(d.user_can_review)
        self.assertTrue(d.can_change_review)


class TestBranchMergeProposalMergedView(TestCaseWithFactory):
    """Tests for `BranchMergeProposalMergedView`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Use an admin so we don't have to worry about launchpad.Edit
        # permissions on the merge proposals for adding comments, or
        # nominating reviewers.
        TestCaseWithFactory.setUp(self, user="admin@canonical.com")
        self.bmp = self.factory.makeBranchMergeProposal()

    def test_initial_values(self):
        # The default merged_revno is the head revno of the target branch.
        view = BranchMergeProposalMergedView(self.bmp, LaunchpadTestRequest())
        self.bmp.source_branch.revision_count = 1
        self.bmp.target_branch.revision_count = 2
        self.assertEqual(
            {'merged_revno': self.bmp.target_branch.revision_count},
            view.initial_values)


class TestBranchMergeProposalAddVoteView(TestCaseWithFactory):
    """Test the AddVote view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.bmp = self.factory.makeBranchMergeProposal()

    def _createView(self):
        # Construct the view and initialize it.
        view = BranchMergeProposalAddVoteView(
            self.bmp, LaunchpadTestRequest())
        view.initialize()
        return view

    def test_init_with_random_person(self):
        """Any random person ought to be able to vote."""
        login_person(self.factory.makePerson())
        self._createView()

    def test_init_with_anonymous(self):
        """Anonymous people cannot vote."""
        self.assertRaises(AssertionError, self._createView)


class TestBranchMergeProposalVoteView(TestCaseWithFactory):
    """Make sure that the votes are returned in the right order."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Use an admin so we don't have to worry about launchpad.Edit
        # permissions on the merge proposals for adding comments, or
        # nominating reviewers.
        TestCaseWithFactory.setUp(self, user="admin@canonical.com")
        self.bmp = make_merge_proposal_without_reviewers(self.factory)
        self.date_generator = time_counter(delta=timedelta(days=1))

    def _createComment(self, reviewer, vote):
        """Create a comment on the merge proposal."""
        self.bmp.createComment(
            owner=reviewer,
            subject=self.factory.getUniqueString('subject'),
            vote=vote,
            _date_created=self.date_generator.next())

    def _nominateReviewer(self, reviewer, registrant):
        """Nominate a reviewer for the merge proposal."""
        self.bmp.nominateReviewer(
            reviewer=reviewer, registrant=registrant,
            _date_created=self.date_generator.next())

    def testNoVotes(self):
        # No votes should return empty lists
        login_person(self.factory.makePerson())
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertEqual([], view.current_reviews)
        self.assertEqual([], view.requested_reviews)
        # The vote table should not be shown, because there are no votes, and
        # the logged-in user cannot request reviews.
        self.assertFalse(view.show_table)

    def _createPrivateVotes(self, is_branch_visible=True):
        # Create a branch with a public and private reviewer.
        owner = self.bmp.source_branch.owner
        if not is_branch_visible:
            branch = self.bmp.source_branch
            branch.transitionToInformationType(InformationType.USERDATA, owner)

        # Set up some review requests.
        public_person1 = self.factory.makePerson()
        private_team1 = self.factory.makeTeam(
            visibility=PersonVisibility.PRIVATE,
            membership_policy=TeamMembershipPolicy.MODERATED)
        self._nominateReviewer(public_person1, owner)
        self._nominateReviewer(private_team1, owner)

        return private_team1, public_person1

    def testPrivateVotesVisibleIfBranchVisible(self):
        # User can see votes for private teams if they can see the branch.
        private_team1, public_person1 = self._createPrivateVotes()
        login_person(self.factory.makePerson())
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())

        # Check the requested reviews.
        requested_reviews = view.requested_reviews
        self.assertEqual(2, len(requested_reviews))
        self.assertContentEqual(
            [public_person1, private_team1],
            [review.reviewer for review in requested_reviews])

    def testRequestedOrdering(self):
        # No votes should return empty lists
        # Request three reviews.
        albert = self.factory.makePerson(name='albert')
        bob = self.factory.makePerson(name='bob')
        charles = self.factory.makePerson(name='charles')

        owner = self.bmp.source_branch.owner

        self._nominateReviewer(albert, owner)
        self._nominateReviewer(bob, owner)
        self._nominateReviewer(charles, owner)

        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertEqual([], view.current_reviews)
        requested_reviews = view.requested_reviews
        self.assertEqual(3, len(requested_reviews))
        self.assertEqual(
            [charles, bob, albert],
            [review.reviewer for review in requested_reviews])

    def test_user_can_claim_self(self):
        """Someone cannot claim a review already assigned to them."""
        albert = self.factory.makePerson()
        owner = self.bmp.source_branch.owner
        self._nominateReviewer(albert, owner)
        login_person(albert)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertFalse(view.requested_reviews[0].user_can_claim)

    def test_user_can_claim_member(self):
        """Someone can claim a review already assigned to their team."""
        albert = self.factory.makePerson()
        review_team = self.factory.makeTeam()
        albert.join(review_team)
        owner = self.bmp.source_branch.owner
        self._nominateReviewer(review_team, owner)
        login_person(albert)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertTrue(view.requested_reviews[0].user_can_claim)

    def test_user_can_claim_nonmember(self):
        """A non-member cannot claim a team's review."""
        albert = self.factory.makePerson()
        review_team = self.factory.makeTeam()
        owner = self.bmp.source_branch.owner
        self._nominateReviewer(review_team, owner)
        login_person(albert)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertFalse(view.requested_reviews[0].user_can_claim)

    def makeReviewRequest(self, viewer=None, registrant=None):
        albert = self.factory.makePerson()
        if registrant is None:
            registrant = self.bmp.source_branch.owner
        self._nominateReviewer(albert, registrant)
        if viewer is None:
            viewer = albert
        login_person(viewer)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        return view.requested_reviews[0]

    def test_user_can_reassign_assignee(self):
        """The user can reassign if they are the assignee."""
        review_request = self.makeReviewRequest()
        self.assertTrue(review_request.user_can_reassign)

    def test_user_can_reassign_registrant(self):
        """The user can reassign if they are the registrant."""
        registrant = self.factory.makePerson()
        review_request = self.makeReviewRequest(registrant, registrant)
        self.assertTrue(review_request.user_can_reassign)

    def test_user_cannot_reassign_random_person(self):
        """Random people cannot reassign reviews."""
        viewer = self.factory.makePerson()
        review_request = self.makeReviewRequest(viewer)
        self.assertFalse(review_request.user_can_reassign)

    def testCurrentReviewOrdering(self):
        # Most recent first.
        # Request three reviews.
        albert = self.factory.makePerson(name='albert')
        bob = self.factory.makePerson(name='bob')
        charles = self.factory.makePerson(name='charles')
        self._createComment(albert, CodeReviewVote.APPROVE)
        self._createComment(bob, CodeReviewVote.ABSTAIN)
        self._createComment(charles, CodeReviewVote.DISAPPROVE)

        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())

        self.assertEqual(
            [charles, bob, albert],
            [review.reviewer for review in view.current_reviews])

    def testChangeOfVoteBringsToTop(self):
        # Changing the vote changes the vote date, so it comes to the top.
        # Request three reviews.
        albert = self.factory.makePerson(name='albert')
        bob = self.factory.makePerson(name='bob')
        self._createComment(albert, CodeReviewVote.ABSTAIN)
        self._createComment(bob, CodeReviewVote.APPROVE)
        self._createComment(albert, CodeReviewVote.APPROVE)

        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())

        self.assertEqual(
            [albert, bob],
            [review.reviewer for review in view.current_reviews])

    def addReviewTeam(self):
        review_team = self.factory.makeTeam(name='reviewteam')
        self.bmp.target_branch.reviewer = review_team

    def test_review_team_members_trusted(self):
        """Members of the target branch's review team are trusted."""
        self.addReviewTeam()
        albert = self.factory.makePerson(name='albert')
        albert.join(self.bmp.target_branch.reviewer)
        self._createComment(albert, CodeReviewVote.APPROVE)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertTrue(view.reviews[0].trusted)

    def test_review_team_nonmembers_untrusted(self):
        """Non-members of the target branch's review team are untrusted."""
        self.addReviewTeam()
        albert = self.factory.makePerson(name='albert')
        self._createComment(albert, CodeReviewVote.APPROVE)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertFalse(view.reviews[0].trusted)

    def test_no_review_team_untrusted(self):
        """If the target branch has no review team, everyone is untrusted."""
        albert = self.factory.makePerson(name='albert')
        self._createComment(albert, CodeReviewVote.APPROVE)
        view = BranchMergeProposalVoteView(self.bmp, LaunchpadTestRequest())
        self.assertFalse(view.reviews[0].trusted)

    def test_render_all_vote_types(self):
        # A smoke test that the view knows how to render all types of vote.
        for vote in CodeReviewVote.items:
            self._createComment(
                self.factory.makePerson(), vote)

        view = getMultiAdapter(
            (self.bmp, LaunchpadTestRequest()), name='+votes')
        self.failUnless(
            isinstance(view, BranchMergeProposalVoteView),
            "The +votes page for a BranchMergeProposal is expected to be a "
            "BranchMergeProposalVoteView")
        # We just test that rendering does not raise.
        view.render()


class TestRegisterBranchMergeProposalView(BrowserTestCase):
    """Test the merge proposal registration view."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.source_branch = self.factory.makeProductBranch()
        self.user = self.factory.makePerson()
        login_person(self.user)

    def _makeTargetBranch(self, **kwargs):
        return self.factory.makeProductBranch(
            product=self.source_branch.product, **kwargs)

    def _makeTargetBranchWithReviewer(self):
        albert = self.factory.makePerson(name='albert')
        target_branch = self.factory.makeProductBranch(
            reviewer=albert, product=self.source_branch.product)
        return target_branch, albert

    def _createView(self, request=None):
        # Construct the view and initialize it.
        if not request:
            request = LaunchpadTestRequest()
        view = RegisterBranchMergeProposalView(self.source_branch, request)
        view.initialize()
        return view

    def _getSourceProposal(self, target_branch):
        # There will only be one proposal.
        landing_targets = list(self.source_branch.landing_targets)
        self.assertEqual(1, len(landing_targets))
        proposal = landing_targets[0]
        self.assertEqual(target_branch, proposal.target_branch)
        return proposal

    def assertOnePendingReview(self, proposal, reviewer, review_type=None):
        # There should be one pending vote for the reviewer with the specified
        # review type.
        votes = list(proposal.votes)
        self.assertEqual(1, len(votes))
        self.assertEqual(reviewer, votes[0].reviewer)
        self.assertEqual(self.user, votes[0].registrant)
        self.assertIs(None, votes[0].comment)
        if review_type is None:
            self.assertIs(None, votes[0].review_type)
        else:
            self.assertEqual(review_type, votes[0].review_type)

    def test_register_simplest_case(self):
        # This simplest case is where the user only specifies the target
        # branch, and not an initial comment or reviewer. The reviewer will
        # therefore be set to the branch owner.
        target_branch = self._makeTargetBranch()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'needs_review': True})
        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, target_branch.owner)
        self.assertIs(None, proposal.description)

    def test_register_ajax_request_with_confirmation(self):
        # Ajax submits return json data containing info about what the visible
        # branches are if they are not all visible to the reviewer.

        # Make a branch the reviewer cannot see.
        owner = self.factory.makePerson()
        target_branch = self._makeTargetBranch(
            owner=owner, information_type=InformationType.USERDATA)
        reviewer = self.factory.makePerson()
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST', principal=owner, **extra)
        view = self._createView(request=request)
        with person_logged_in(owner):
            branches_to_check = [self.source_branch.unique_name,
                target_branch.unique_name]
            expected_data = {
                'person_name': reviewer.displayname,
                'branches_to_check': branches_to_check,
                'visible_branches': [self.source_branch.unique_name]}
            result_data = view.register_action.success(
                {'target_branch': target_branch,
                 'reviewer': reviewer,
                 'needs_review': True})
        self.assertEqual(
            '400 Branch Visibility',
            view.request.response.getStatusString())
        self.assertEqual(expected_data, simplejson.loads(result_data))

    def test_register_ajax_request_with_validation_errors(self):
        # Ajax submits where there is a validation error in the submitted data
        # return the expected json response containing the error info.
        owner = self.factory.makePerson()
        target_branch = self._makeTargetBranch(
            owner=owner, information_type=InformationType.USERDATA)
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        with person_logged_in(owner):
            request = LaunchpadTestRequest(
                method='POST', principal=owner,
                form={
                    'field.actions.register': 'Propose Merge',
                    'field.target_branch.target_branch':
                        target_branch.unique_name},
                **extra)
            view = create_initialized_view(
                target_branch,
                name='+register-merge',
                request=request)
        self.assertEqual(
            '400 Validation', view.request.response.getStatusString())
        self.assertEqual(
            {'error_summary': 'There is 1 error.',
            'errors': {
                'field.target_branch':
                    ('The target branch cannot be the same as the '
                    'source branch.')},
            'form_wide_errors': []},
            simplejson.loads(view.form_result))

    def test_register_ajax_request_with_no_confirmation(self):
        # Ajax submits where there is no confirmation required return a 201
        # with the new location.
        owner = self.factory.makePerson()
        target_branch = self._makeTargetBranch()
        reviewer = self.factory.makePerson()
        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST', principal=owner, **extra)
        view = self._createView(request=request)
        with person_logged_in(owner):
            result_data = view.register_action.success(
                {'target_branch': target_branch,
                 'reviewer': reviewer,
                 'needs_review': True})
        self.assertEqual(None, result_data)
        self.assertEqual(201, view.request.response.getStatus())
        mp = target_branch.getMergeProposals()[0]
        self.assertEqual(
            canonical_url(mp), view.request.response.getHeader('Location'))

    def test_register_work_in_progress(self):
        # The needs review checkbox can be unchecked to create a work in
        # progress proposal.
        target_branch = self._makeTargetBranch()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'needs_review': False})
        proposal = self._getSourceProposal(target_branch)
        self.assertEqual(
            BranchMergeProposalStatus.WORK_IN_PROGRESS,
            proposal.queue_status)

    def test_register_with_commit_message(self):
        # A commit message can also be set during the register process.
        target_branch = self._makeTargetBranch()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'needs_review': True,
             'commit_message': 'Fixed the bug!'})
        proposal = self._getSourceProposal(target_branch)
        self.assertEqual('Fixed the bug!', proposal.commit_message)

    def test_register_initial_comment(self):
        # If the user specifies a description, this is recorded on the
        # proposal.
        target_branch = self._makeTargetBranch()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'comment': "This is the description.",
             'needs_review': True})

        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, target_branch.owner)
        self.assertEqual(proposal.description, "This is the description.")

    def test_register_request_reviewer(self):
        # If the user requests a reviewer, then a pending vote is added to the
        # proposal.
        target_branch = self._makeTargetBranch()
        reviewer = self.factory.makePerson()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'reviewer': reviewer,
             'needs_review': True})

        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, reviewer)
        self.assertIs(None, proposal.description)

    def test_register_request_review_type(self):
        # We can request a specific review type of the reviewer.  If we do, it
        # is recorded along with the pending review.
        target_branch = self._makeTargetBranch()
        reviewer = self.factory.makePerson()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'reviewer': reviewer,
             'review_type': 'god-like',
             'needs_review': True})

        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, reviewer, 'god-like')
        self.assertIs(None, proposal.description)

    def test_register_comment_and_review(self):
        # The user can give a description and request a review from
        # someone.
        target_branch = self._makeTargetBranch()
        reviewer = self.factory.makePerson()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'reviewer': reviewer,
             'review_type': 'god-like',
             'comment': "This is the description.",
             'needs_review': True})

        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, reviewer, 'god-like')
        self.assertEqual(proposal.description, "This is the description.")

    def test_register_for_target_with_default_reviewer(self):
        # A simple case is where the user only specifies the target
        # branch, and not an initial comment or reviewer. The target branch
        # has a reviewer so that reviewer should be used
        target_branch, reviewer = self._makeTargetBranchWithReviewer()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'needs_review': True})
        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, reviewer)
        self.assertIs(None, proposal.description)

    def test_register_request_review_type_branch_reviewer(self):
        # We can ask for a specific review type. The target branch has a
        # reviewer so that reviewer should be used.
        target_branch, reviewer = self._makeTargetBranchWithReviewer()
        view = self._createView()
        view.register_action.success(
            {'target_branch': target_branch,
             'review_type': 'god-like',
             'needs_review': True})
        proposal = self._getSourceProposal(target_branch)
        self.assertOnePendingReview(proposal, reviewer, 'god-like')
        self.assertIs(None, proposal.description)

    def test_register_reviewer_not_hidden(self):
        branch = self.factory.makeBranch()
        browser = self.getViewBrowser(branch, '+register-merge')
        extra = Tag(
            'extra', 'fieldset', attrs={'id': 'mergeproposal-extra-options'})
        reviewer = Tag('reviewer', 'input', attrs={'id': 'field.reviewer'})
        matcher = Not(HTMLContains(reviewer.within(extra)))
        self.assertThat(browser.contents, matcher)

    def test_branch_visibility_notification(self):
        # If the reviewer cannot see the source and/or target branches, a
        # notification message is displayed.
        owner = self.factory.makePerson()
        target_branch = self._makeTargetBranch(
            owner=owner, information_type=InformationType.USERDATA)
        reviewer = self.factory.makePerson()
        with person_logged_in(owner):
            view = self._createView()
            view.register_action.success(
                {'target_branch': target_branch,
                 'reviewer': reviewer,
                 'needs_review': True})

        (notification,) = view.request.response.notifications
        self.assertThat(
            notification.message, MatchesRegex(
                'To ensure visibility, .* is now subscribed to:.*'))
        self.assertEqual(BrowserNotificationLevel.INFO, notification.level)


class TestBranchMergeProposalResubmitView(TestCaseWithFactory):
    """Test BranchMergeProposalResubmitView."""

    layer = DatabaseFunctionalLayer

    def createView(self):
        """Create the required view."""
        context = self.factory.makeBranchMergeProposal()
        self.useContext(person_logged_in(context.registrant))
        view = BranchMergeProposalResubmitView(
            context, LaunchpadTestRequest())
        view.initialize()
        return view

    def test_resubmit_action(self):
        """resubmit_action resubmits the proposal."""
        view = self.createView()
        context = view.context
        new_proposal = view.resubmit_action.success(
            {'source_branch': context.source_branch,
             'target_branch': context.target_branch,
             'prerequisite_branch': context.prerequisite_branch,
             'description': None,
             'break_link': False,
            })
        self.assertEqual(new_proposal.supersedes, context)
        self.assertEqual(new_proposal.source_branch, context.source_branch)
        self.assertEqual(new_proposal.target_branch, context.target_branch)
        self.assertEqual(
            new_proposal.prerequisite_branch, context.prerequisite_branch)

    def test_resubmit_action_change_branches(self):
        """Changing the branches changes the branches in the new proposal."""
        view = self.createView()
        target = view.context.source_branch.target
        new_source = self.factory.makeBranchTargetBranch(target)
        new_target = self.factory.makeBranchTargetBranch(target)
        new_prerequisite = self.factory.makeBranchTargetBranch(target)
        new_proposal = view.resubmit_action.success(
            {'source_branch': new_source, 'target_branch': new_target,
             'prerequisite_branch': new_prerequisite,
             'description': 'description',
             'break_link': False,
             })
        self.assertEqual(new_proposal.supersedes, view.context)
        self.assertEqual(new_proposal.source_branch, new_source)
        self.assertEqual(new_proposal.target_branch, new_target)
        self.assertEqual(new_proposal.prerequisite_branch, new_prerequisite)

    def test_resubmit_action_break_link(self):
        """Enabling break_link prevents linking the old and new proposals."""
        view = self.createView()
        new_proposal = self.resubmitDefault(view, break_link=True)
        self.assertIs(None, new_proposal.supersedes)

    @staticmethod
    def resubmitDefault(view, break_link=False, prerequisite_branch=None):
        context = view.context
        if prerequisite_branch is None:
            prerequisite_branch = context.prerequisite_branch
        return view.resubmit_action.success(
            {'source_branch': context.source_branch,
             'target_branch': context.target_branch,
             'prerequisite_branch': prerequisite_branch,
             'description': None,
             'break_link': break_link,
            })

    def test_resubmit_existing(self):
        """Resubmitting a proposal when another is active is a user error."""
        view = self.createView()
        first_bmp = view.context
        with person_logged_in(first_bmp.target_branch.owner):
            first_bmp.resubmit(first_bmp.registrant)
        self.resubmitDefault(view)
        (notification,) = view.request.response.notifications
        self.assertThat(
            notification.message, MatchesRegex('Cannot resubmit because'
            ' <a href=.*>a similar merge proposal</a> is already active.'))
        self.assertEqual(BrowserNotificationLevel.ERROR, notification.level)

    def test_resubmit_same_target_prerequisite(self):
        """User error if same branch is target and prerequisite."""
        view = self.createView()
        first_bmp = view.context
        self.resubmitDefault(
            view, prerequisite_branch=first_bmp.target_branch)
        self.assertEqual(
            view.errors,
            ['Target and prerequisite branches must be different.'])


class TestResubmitBrowser(BrowserTestCase):
    """Browser tests for resubmitting branch merge proposals."""

    layer = DatabaseFunctionalLayer

    def test_resubmit_text(self):
        """The text of the resubmit page is as expected."""
        bmp = self.factory.makeBranchMergeProposal(registrant=self.user)
        text = self.getMainText(bmp, '+resubmit')
        expected = (
            'Resubmit proposal to merge.*'
            'Source Branch:.*'
            'Target Branch:.*'
            'Prerequisite Branch:.*'
            'Description.*'
            'Start afresh.*')
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, text)

    def test_resubmit_controls(self):
        """Proposals can be resubmitted using the browser."""
        bmp = self.factory.makeBranchMergeProposal(registrant=self.user)
        browser = self.getViewBrowser(bmp, '+resubmit')
        browser.getControl('Description').value = 'flibble'
        browser.getControl('Resubmit').click()
        with person_logged_in(self.user):
            self.assertEqual('flibble', bmp.superseded_by.description)


class TestBranchMergeProposalView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.user = self.factory.makePerson()
        self.bmp = self.factory.makeBranchMergeProposal(registrant=self.user)
        login_person(self.user)

    def makeTeamReview(self):
        owner = self.bmp.source_branch.owner
        review_team = self.factory.makeTeam()
        return self.bmp.nominateReviewer(review_team, owner)

    def test_claim_action_team_member(self):
        """Claiming a review works for members of the requested team."""
        review = self.makeTeamReview()
        albert = self.factory.makePerson()
        removeSecurityProxy(albert).join(review.reviewer)
        login_person(albert)
        view = create_initialized_view(self.bmp, '+index')
        view.claim_action.success({'review_id': review.id})
        self.assertEqual(albert, review.reviewer)

    def test_claim_action_non_member(self):
        """Claiming a review does not work for non-members."""
        review = self.makeTeamReview()
        albert = self.factory.makePerson()
        login_person(albert)
        view = create_initialized_view(self.bmp, '+index')
        self.assertRaises(Unauthorized, view.claim_action.success,
                          {'review_id': review.id})

    def test_claim_no_oops(self):
        """"An invalid attempt to claim a review should not oops."""
        review = self.factory.makeCodeReviewVoteReference()
        view = create_initialized_view(review.branch_merge_proposal, '+index')
        view.claim_action.success({'review_id': review.id})
        self.assertEqual(
            ['Cannot claim non-team reviews.'],
            [n.message for n in view.request.response.notifications])

    def test_preview_diff_text_with_no_diff(self):
        """preview_diff_text should be None if context has no preview_diff."""
        view = create_initialized_view(self.bmp, '+index')
        self.assertIs(None, view.preview_diff_text)

    def test_preview_diff_utf8(self):
        """A preview_diff in utf-8 should decoded as utf-8."""
        text = ''.join(unichr(x) for x in range(255))
        diff_bytes = ''.join(unified_diff('', text)).encode('utf-8')
        self.setPreviewDiff(diff_bytes)
        transaction.commit()
        view = create_initialized_view(self.bmp, '+index')
        self.assertEqual(diff_bytes.decode('utf-8'),
                         view.preview_diff_text)
        self.assertTrue(view.diff_available)

    def test_preview_diff_all_chars(self):
        """preview_diff should work on diffs containing all possible bytes."""
        text = ''.join(chr(x) for x in range(255))
        diff_bytes = ''.join(unified_diff('', text))
        self.setPreviewDiff(diff_bytes)
        transaction.commit()
        view = create_initialized_view(self.bmp, '+index')
        self.assertEqual(diff_bytes.decode('windows-1252', 'replace'),
                         view.preview_diff_text)
        self.assertTrue(view.diff_available)

    def test_preview_diff_timeout(self):
        # The preview_diff will recover from a timeout set to get the
        # librarian content.
        text = ''.join(chr(x) for x in range(255))
        diff_bytes = ''.join(unified_diff('', text))
        preview_diff = self.setPreviewDiff(diff_bytes)
        transaction.commit()

        def fake_open(*args):
            raise LibrarianServerError

        lfa = preview_diff.diff.diff_text
        with monkey_patch(lfa, open=fake_open):
            view = create_initialized_view(preview_diff, '+diff')
            self.assertEqual('', view.preview_diff_text)
            self.assertFalse(view.diff_available)
            markup = view()
            self.assertIn('The diff is not available at this time.', markup)

    def setPreviewDiff(self, preview_diff_bytes):
        return PreviewDiff.create(
            self.bmp, preview_diff_bytes, u'a', u'b', None, u'')

    def test_linked_bugs_excludes_mutual_bugs(self):
        """List bugs that are linked to the source only."""
        bug = self.factory.makeBug()
        self.bmp.source_branch.linkBug(bug, self.bmp.registrant)
        self.bmp.target_branch.linkBug(bug, self.bmp.registrant)
        view = create_initialized_view(self.bmp, '+index')
        self.assertEqual([], view.linked_bugtasks)

    def test_linked_bugs_excludes_private_bugs(self):
        """List bugs that are linked to the source only."""
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        private_bug = self.factory.makeBug(
            owner=person, information_type=InformationType.USERDATA)
        self.bmp.source_branch.linkBug(bug, self.bmp.registrant)
        with person_logged_in(person):
            self.bmp.source_branch.linkBug(private_bug, self.bmp.registrant)
        view = create_initialized_view(self.bmp, '+index')
        self.assertEqual([bug.default_bugtask], view.linked_bugtasks)

    def makeRevisionGroups(self):
        review_date = datetime(2009, 9, 10, tzinfo=pytz.UTC)
        bmp = self.factory.makeBranchMergeProposal(
            date_created=review_date)
        first_commit = datetime(2009, 9, 9, tzinfo=pytz.UTC)
        add_revision_to_branch(
            self.factory, bmp.source_branch, first_commit)
        login_person(bmp.registrant)
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
        return bmp, revisions

    def test_getRevisionsIncludesIncrementalDiffs(self):
        bmp, revisions = self.makeRevisionGroups()
        diff = self.factory.makeIncrementalDiff(merge_proposal=bmp,
                old_revision=revisions[1].revision.getLefthandParent(),
                new_revision=revisions[3].revision)
        self.useContext(feature_flags())
        set_feature_flag(u'code.incremental_diffs.enabled', u'enabled')
        view = create_initialized_view(bmp, '+index')
        comments = view.conversation.comments
        self.assertEqual(
            [diff],
            [comment.diff for comment in comments])

    def test_CodeReviewNewRevisions_implements_ICodeReviewNewRevisions(self):
        # The browser helper class implements its interface.
        review_date = datetime(2009, 9, 10, tzinfo=pytz.UTC)
        revision_date = review_date + timedelta(days=1)
        bmp = self.factory.makeBranchMergeProposal(
            date_created=review_date)
        add_revision_to_branch(self.factory, bmp.source_branch, revision_date)

        view = create_initialized_view(bmp, '+index')
        new_revisions = view.conversation.comments[0]

        self.assertTrue(verifyObject(ICodeReviewNewRevisions, new_revisions))

    def test_include_superseded_comments(self):
        for x, time in zip(range(3), time_counter()):
            if x != 0:
                self.bmp = self.bmp.resubmit(self.user)
            self.bmp.createComment(
                self.user, 'comment %d' % x, _date_created=time)
        view = create_initialized_view(self.bmp, '+index')
        self.assertEqual(
            ['comment 0', 'comment 1', 'comment 2'],
            [comment.comment.message.subject for comment
             in view.conversation.comments])
        self.assertFalse(view.conversation.comments[2].from_superseded)
        self.assertTrue(view.conversation.comments[1].from_superseded)
        self.assertTrue(view.conversation.comments[0].from_superseded)

    def test_pending_diff_with_pending_branch(self):
        bmp = self.factory.makeBranchMergeProposal()
        bmp.next_preview_diff_job.start()
        bmp.next_preview_diff_job.fail()
        view = create_initialized_view(bmp, '+index')
        self.assertFalse(view.pending_diff)
        with person_logged_in(bmp.source_branch.owner):
            bmp.source_branch.branchChanged(None, 'rev-1', None, None, None)
        self.assertTrue(view.pending_diff)

    def test_subscribe_to_merge_proposal_events_flag_disabled(self):
        # If the longpoll.merge_proposals.enabled flag is not enabled the user
        # is *not* subscribed to events relating to the merge proposal.
        bmp = self.factory.makeBranchMergeProposal()
        view = create_initialized_view(bmp, '+index', current_request=True)
        cache = IJSONRequestCache(view.request)
        self.assertNotIn("longpoll", cache.objects)
        self.assertNotIn("merge_proposal_event_key", cache.objects)

    def test_subscribe_to_merge_proposal_events_flag_enabled(self):
        # If the longpoll.merge_proposals.enabled flag is enabled the user is
        # subscribed to events relating to the merge proposal.
        bmp = self.factory.makeBranchMergeProposal()
        self.useContext(feature_flags())
        set_feature_flag(u'longpoll.merge_proposals.enabled', u'enabled')
        view = create_initialized_view(bmp, '+index', current_request=True)
        cache = IJSONRequestCache(view.request)
        self.assertIn("longpoll", cache.objects)
        self.assertIn("merge_proposal_event_key", cache.objects)

    def test_description_is_meta_description(self):
        description = (
            "I'd like to make the bmp description appear as the meta "
            "description: this does that "
            + "abcdef " * 300)
        bmp = self.factory.makeBranchMergeProposal(
            description=description)
        browser = self.getUserBrowser(
            canonical_url(bmp, rootsite='code'))
        expected_meta = Tag(
            'meta description',
            'meta', attrs=dict(
                name='description',
                content=description[:497] + '...'))
        self.assertThat(browser.contents, HTMLContains(expected_meta))


class TestBranchMergeProposalChangeStatusOptions(TestCaseWithFactory):
    """Test the status vocabulary generated for then +edit-status view."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.user = self.factory.makePerson()
        login_person(self.user)
        self.proposal = self.factory.makeBranchMergeProposal(
            registrant=self.user)

    def _createView(self):
        # Construct the view and initialize it.
        view = BranchMergeProposalChangeStatusView(
            self.proposal, LaunchpadTestRequest())
        view.initialize()
        return view

    def assertStatusVocabTokens(self, tokens, user):
        # Assert that the tokens specified are the only tokens in the
        # generated vocabulary.
        login_person(user)
        vocabulary = self._createView()._createStatusVocabulary()
        vocab_tokens = sorted([term.token for term in vocabulary])
        self.assertEqual(
            sorted(tokens), vocab_tokens)

    def assertAllStatusesAvailable(self, user, except_for=None):
        # All options should be available to the user, except for SUPERSEDED,
        # which is only provided through resubmit.
        desired_statuses = set([
            'WORK_IN_PROGRESS', 'NEEDS_REVIEW', 'MERGED', 'CODE_APPROVED',
            'REJECTED'])
        if except_for is not None:
            desired_statuses -= set(except_for)
        self.assertStatusVocabTokens(desired_statuses, user)

    def test_createStatusVocabulary_non_reviewer(self):
        # Neither the source branch owner nor the registrant should be
        # able to approve or reject their own code (assuming they don't have
        # rights on the target branch).
        status_options = [
            'WORK_IN_PROGRESS', 'NEEDS_REVIEW', 'MERGED']
        self.assertStatusVocabTokens(
            status_options, user=self.proposal.source_branch.owner)
        self.assertStatusVocabTokens(
            status_options, user=self.proposal.registrant)

    def test_createStatusVocabulary_reviewer(self):
        # The registrant should not be able to approve or reject
        # their own code (assuming they don't have rights on the target
        # branch).
        self.assertAllStatusesAvailable(self.proposal.target_branch.owner)

    def test_createStatusVocabulary_non_reviewer_approved(self):
        # Once the branch has been approved, the source owner or the
        # registrant can queue the branch.
        self.proposal.approveBranch(
            self.proposal.target_branch.owner, 'some-revision')
        status_options = [
            'WORK_IN_PROGRESS', 'NEEDS_REVIEW', 'CODE_APPROVED', 'MERGED']
        self.assertStatusVocabTokens(
            status_options, user=self.proposal.source_branch.owner)
        self.assertStatusVocabTokens(
            status_options, user=self.proposal.registrant)

    def test_createStatusVocabulary_reviewer_approved(self):
        # The target branch owner's options are not changed by whether or not
        # the proposal is currently approved.
        self.proposal.approveBranch(
            self.proposal.target_branch.owner, 'some-revision')
        self.assertAllStatusesAvailable(
            user=self.proposal.target_branch.owner)

    def test_createStatusVocabulary_rejected(self):
        # Only reviewers can change rejected proposals to approved.  All other
        # options for rejected proposals are the same regardless of user.
        self.proposal.rejectBranch(
            self.proposal.target_branch.owner, 'some-revision')
        self.assertAllStatusesAvailable(
            user=self.proposal.source_branch.owner,
            except_for=['CODE_APPROVED', 'QUEUED'])
        self.assertAllStatusesAvailable(user=self.proposal.registrant,
            except_for=['CODE_APPROVED', 'QUEUED'])
        self.assertAllStatusesAvailable(
            user=self.proposal.target_branch.owner)

    def test_createStatusVocabulary_queued(self):
        # Queued proposals can go to any status, but only reviewers can set
        # them to REJECTED.
        self.proposal.enqueue(
            self.proposal.target_branch.owner, 'some-revision')

        self.assertAllStatusesAvailable(
            user=self.proposal.source_branch.owner, except_for=['REJECTED'])
        self.assertAllStatusesAvailable(user=self.proposal.registrant,
                                        except_for=['REJECTED'])
        self.assertAllStatusesAvailable(
            user=self.proposal.target_branch.owner)


class TestCommentAttachmentRendering(TestCaseWithFactory):
    """Test diff attachments are rendered correctly."""

    layer = LaunchpadFunctionalLayer

    def _makeCommentFromEmailWithAttachment(self, attachment_body):
        # Make an email message with an attachment, and create a code
        # review comment from it.
        bmp = self.factory.makeBranchMergeProposal()
        login_person(bmp.registrant)
        msg = self.factory.makeEmailMessage(
            body='testing',
            attachments=[('test.diff', 'text/plain', attachment_body)])
        message = MessageSet().fromEmail(msg.as_string())
        return CodeReviewDisplayComment(
            bmp.createCommentFromMessage(message, None, None, msg))

    def test_nonascii_in_attachment_renders(self):
        # The view should render without errors.
        comment = self._makeCommentFromEmailWithAttachment('\xe2\x98\x95')
        # Need to commit in order to read the diff out of the librarian.
        transaction.commit()
        view = create_initialized_view(comment, '+comment-body')
        view()

    def test_nonascii_in_attachment_decoded(self):
        # The diff_text should be a unicode string.
        comment = self._makeCommentFromEmailWithAttachment('\xe2\x98\x95')
        # Need to commit in order to read the diff out of the librarian.
        transaction.commit()
        view = create_initialized_view(comment, '+comment-body')
        [diff_attachment] = view.comment.display_attachments
        self.assertEqual(u'\u2615', diff_attachment.diff_text)


class TestBranchMergeCandidateView(TestCaseWithFactory):
    """Test the status title for the view."""

    layer = DatabaseFunctionalLayer

    def test_needs_review_title(self):
        # No title is set for a proposal needing review.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        view = create_initialized_view(bmp, '+link-summary')
        self.assertEqual('', view.status_title)

    def test_approved_shows_reviewer(self):
        # If the proposal is approved, the approver is shown in the title
        # along with when they approved it.
        bmp = self.factory.makeBranchMergeProposal()
        owner = bmp.target_branch.owner
        login_person(bmp.target_branch.owner)
        owner.displayname = 'Eric'
        bmp.approveBranch(owner, 'some-rev', datetime(
                year=2008, month=9, day=10, tzinfo=pytz.UTC))
        view = create_initialized_view(bmp, '+link-summary')
        self.assertEqual('Eric on 2008-09-10', view.status_title)

    def test_rejected_shows_reviewer(self):
        # If the proposal is rejected, the approver is shown in the title
        # along with when they approved it.
        bmp = self.factory.makeBranchMergeProposal()
        owner = bmp.target_branch.owner
        login_person(bmp.target_branch.owner)
        owner.displayname = 'Eric'
        bmp.rejectBranch(owner, 'some-rev', datetime(
                year=2008, month=9, day=10, tzinfo=pytz.UTC))
        view = create_initialized_view(bmp, '+link-summary')
        self.assertEqual('Eric on 2008-09-10', view.status_title)


class TestBranchMergeProposal(BrowserTestCase):

    layer = LaunchpadFunctionalLayer

    def test_conversation(self):
        source_branch = self.factory.makeBranch()
        parent = add_revision_to_branch(self.factory, source_branch,
            self.factory.getUniqueDate()).revision
        bmp = self.factory.makeBranchMergeProposal(registrant=self.user,
            date_created=self.factory.getUniqueDate(),
            source_branch=source_branch)
        revision = add_revision_to_branch(self.factory, bmp.source_branch,
            self.factory.getUniqueDate()).revision
        diff = self.factory.makeDiff()
        bmp.generateIncrementalDiff(parent, revision, diff)
        self.useContext(feature_flags())
        set_feature_flag(u'code.incremental_diffs.enabled', u'enabled')
        browser = self.getViewBrowser(bmp)
        assert 'unf_pbasyvpgf' in browser.contents

    def test_pending_diff_message_with_longpoll_enabled(self):
        # If the longpoll feature flag is enabled then the message
        # displayed for a pending diff indicates that it'll update
        # automatically. See also
        # lib/lp/code/stories/branches/xx-branchmergeproposals.txt
        self.useContext(feature_flags())
        set_feature_flag(u'longpoll.merge_proposals.enabled', u'enabled')
        bmp = self.factory.makeBranchMergeProposal()
        browser = self.getViewBrowser(bmp)
        self.assertIn(
            "An updated diff is being calculated and will appear "
                "automatically when ready.",
            browser.contents)

    def test_short_conversation_comments_not_truncated(self):
        """Short comments should not be truncated."""
        comment = self.factory.makeCodeReviewComment(body='x y' * 100)
        browser = self.getViewBrowser(comment.branch_merge_proposal)
        self.assertIn('x y' * 100, browser.contents)

    def has_read_more(self, comment):
        url = canonical_url(comment, force_local_path=True)
        read_more = Tag(
            'Read more link', 'a', {'href': url}, text='Read more...')
        return HTMLContains(read_more)

    def test_long_conversation_comments_truncated(self):
        """Long comments in a conversation should be truncated."""
        comment = self.factory.makeCodeReviewComment(body='x y' * 2000)
        has_read_more = self.has_read_more(comment)
        browser = self.getViewBrowser(comment.branch_merge_proposal)
        self.assertNotIn('x y' * 2000, browser.contents)
        self.assertThat(browser.contents, has_read_more)

    def test_short_conversation_comments_no_download(self):
        """Short comments should not have a download link."""
        comment = self.factory.makeCodeReviewComment(body='x y' * 100)
        download_url = canonical_url(comment, view_name='+download')
        browser = self.getViewBrowser(comment.branch_merge_proposal)
        body = Tag(
            'Download', 'a', {'href': download_url},
            text='Download full text')
        self.assertThat(browser.contents, Not(HTMLContains(body)))

    def test_long_conversation_comments_download_link(self):
        """Long comments in a conversation should be truncated."""
        comment = self.factory.makeCodeReviewComment(body='x y' * 2000)
        download_url = canonical_url(comment, view_name='+download')
        browser = self.getViewBrowser(comment.branch_merge_proposal)
        body = Tag(
            'Download', 'a', {'href': download_url},
            text='Download full text')
        self.assertThat(browser.contents, HTMLContains(body))

    def test_excessive_conversation_comments_no_redirect(self):
        """An excessive comment does not force a redict on proposal page."""
        comment = self.factory.makeCodeReviewComment(body='x' * 10001)
        mp_url = canonical_url(comment.branch_merge_proposal)
        has_read_more = self.has_read_more(comment)
        browser = self.getUserBrowser(mp_url)
        self.assertThat(browser.contents, Not(has_read_more))
        self.assertEqual(mp_url, browser.url)


class TestLatestProposalsForEachBranch(TestCaseWithFactory):
    """Confirm that the latest branch is returned."""

    layer = DatabaseFunctionalLayer

    def test_newest_first(self):
        # If each proposal targets a different branch, each will be returned.
        bmp1 = self.factory.makeBranchMergeProposal(
            date_created=(
                datetime(year=2008, month=9, day=10, tzinfo=pytz.UTC)))
        bmp2 = self.factory.makeBranchMergeProposal(
            date_created=(
                datetime(year=2008, month=10, day=10, tzinfo=pytz.UTC)))
        self.assertEqual(
            [bmp2, bmp1], latest_proposals_for_each_branch([bmp1, bmp2]))

    def test_visible_filtered_out(self):
        # If the proposal is not visible to the user, they are not returned.
        bmp1 = self.factory.makeBranchMergeProposal(
            date_created=(
                datetime(year=2008, month=9, day=10, tzinfo=pytz.UTC)))
        bmp2 = self.factory.makeBranchMergeProposal(
            date_created=(
                datetime(year=2008, month=10, day=10, tzinfo=pytz.UTC)))
        removeSecurityProxy(bmp2.source_branch).transitionToInformationType(
            InformationType.USERDATA, bmp2.source_branch.owner,
            verify_policy=False)
        self.assertEqual(
            [bmp1], latest_proposals_for_each_branch([bmp1, bmp2]))

    def test_same_target(self):
        # If the proposals target the same branch, then the most recent is
        # returned.
        bmp1 = self.factory.makeBranchMergeProposal(
            date_created=(
                datetime(year=2008, month=9, day=10, tzinfo=pytz.UTC)))
        bmp2 = self.factory.makeBranchMergeProposal(
            target_branch=bmp1.target_branch,
            date_created=(
                datetime(year=2008, month=10, day=10, tzinfo=pytz.UTC)))
        self.assertEqual(
            [bmp2], latest_proposals_for_each_branch([bmp1, bmp2]))
