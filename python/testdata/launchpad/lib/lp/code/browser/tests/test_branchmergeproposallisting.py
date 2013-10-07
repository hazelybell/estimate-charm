# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for BranchMergeProposal listing views."""

__metaclass__ = type

from datetime import datetime

import pytz
from testtools.content import Content
from testtools.content_type import UTF8_TEXT
from testtools.matchers import Equals
import transaction
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.browser.branchmergeproposallisting import (
    ActiveReviewsView,
    BranchMergeProposalListingItem,
    )
from lp.code.enums import (
    BranchMergeProposalStatus,
    CodeReviewVote,
    )
from lp.registry.model.personproduct import PersonProduct
from lp.services.database.sqlbase import flush_database_caches
from lp.testing import (
    ANONYMOUS,
    BrowserTestCase,
    login,
    login_person,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.views import create_initialized_view


_default = object()


class TestProposalVoteSummary(TestCaseWithFactory):
    """The vote summary shows a summary of the current votes."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Use an admin so we don't have to worry about launchpad.Edit
        # permissions on the merge proposals for adding comments.
        TestCaseWithFactory.setUp(self, user="admin@canonical.com")

    def _createComment(self, proposal, reviewer=None, vote=None,
                       comment=_default):
        """Create a comment on the merge proposal."""
        if reviewer is None:
            reviewer = self.factory.makePerson()
        if comment is _default:
            comment = self.factory.getUniqueString()
        proposal.createComment(
            owner=reviewer, subject=self.factory.getUniqueString('subject'),
            content=comment, vote=vote)

    def _get_vote_summary(self, proposal):
        """Return the vote summary string for the proposal."""
        view = create_initialized_view(
            proposal.source_branch.owner, '+merges', rootsite='code')
        batch_navigator = view.proposals
        # There will only be one item in the list of proposals.
        [listing_item] = batch_navigator.proposals
        return (list(listing_item.vote_summary_items),
                listing_item.comment_count)

    def test_no_votes_or_comments(self):
        # If there are no votes or comments, then we show that.
        proposal = self.factory.makeBranchMergeProposal()
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual([], summary)
        self.assertEqual(0, comment_count)

    def test_no_votes_with_comments(self):
        # The comment count is shown.
        proposal = self.factory.makeBranchMergeProposal()
        self._createComment(proposal)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual([], summary)
        self.assertEqual(1, comment_count)

    def test_vote_without_comment(self):
        # If there are no comments we don't show a count.
        proposal = self.factory.makeBranchMergeProposal()
        self._createComment(
            proposal, vote=CodeReviewVote.APPROVE, comment=None)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'APPROVE', 'title':'Approve', 'count':1,
              'reviewers': ''}], summary)
        self.assertEqual(0, comment_count)

    def test_vote_with_comment(self):
        # A vote with a comment counts as a vote and a comment.
        proposal = self.factory.makeBranchMergeProposal()
        self._createComment(proposal, vote=CodeReviewVote.APPROVE)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'APPROVE', 'title':'Approve', 'count':1,
              'reviewers': ''}], summary)
        self.assertEqual(1, comment_count)

    def test_disapproval(self):
        # Shown as Disapprove: <count>.
        proposal = self.factory.makeBranchMergeProposal()
        self._createComment(proposal, vote=CodeReviewVote.DISAPPROVE)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'DISAPPROVE', 'title':'Disapprove', 'count':1,
              'reviewers': ''}], summary)
        self.assertEqual(1, comment_count)

    def test_abstain(self):
        # Shown as Abstain: <count>.
        proposal = self.factory.makeBranchMergeProposal()
        transaction.commit()
        self._createComment(proposal, vote=CodeReviewVote.ABSTAIN)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'ABSTAIN', 'title':'Abstain', 'count':1,
              'reviewers': ''}], summary)
        self.assertEqual(1, comment_count)

    def test_vote_ranking(self):
        # Votes go from best to worst.
        proposal = self.factory.makeBranchMergeProposal()
        self._createComment(proposal, vote=CodeReviewVote.DISAPPROVE)
        self._createComment(proposal, vote=CodeReviewVote.APPROVE)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'APPROVE', 'title':'Approve', 'count':1,
              'reviewers': ''},
             {'name': 'DISAPPROVE', 'title':'Disapprove', 'count':1,
              'reviewers': ''}], summary)
        self.assertEqual(2, comment_count)
        self._createComment(proposal, vote=CodeReviewVote.ABSTAIN)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'APPROVE', 'title':'Approve', 'count':1,
              'reviewers': ''},
             {'name': 'ABSTAIN', 'title':'Abstain', 'count':1,
              'reviewers': ''},
             {'name': 'DISAPPROVE', 'title':'Disapprove', 'count':1,
              'reviewers': ''}], summary)
        self.assertEqual(3, comment_count)

    def test_multiple_votes_for_type(self):
        # Multiple votes of a type are aggregated in the summary.
        proposal = self.factory.makeBranchMergeProposal()
        self._createComment(proposal, vote=CodeReviewVote.DISAPPROVE)
        self._createComment(proposal, vote=CodeReviewVote.APPROVE)
        self._createComment(proposal, vote=CodeReviewVote.DISAPPROVE)
        self._createComment(proposal, vote=CodeReviewVote.APPROVE)
        self._createComment(
            proposal, vote=CodeReviewVote.ABSTAIN, comment=None)
        self._createComment(
            proposal, vote=CodeReviewVote.APPROVE, comment=None)
        summary, comment_count = self._get_vote_summary(proposal)
        self.assertEqual(
            [{'name': 'APPROVE', 'title':'Approve', 'count':3,
              'reviewers': ''},
             {'name': 'ABSTAIN', 'title':'Abstain', 'count':1,
              'reviewers': ''},
             {'name': 'DISAPPROVE', 'title':'Disapprove', 'count':2,
              'reviewers': ''}], summary)
        self.assertEqual(4, comment_count)


class TestMerges(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_person_product(self):
        """The merges view should be enabled for PersonProduct."""
        personproduct = PersonProduct(
            self.factory.makePerson(), self.factory.makeProduct())
        self.getViewBrowser(personproduct, '+merges', rootsite='code')

    def test_DistributionSourcePackage(self):
        """The merges view should be enabled for DistributionSourcePackage."""
        package = self.factory.makeDistributionSourcePackage()
        self.getViewBrowser(package, '+merges', rootsite='code')

    def test_query_count(self):
        product = self.factory.makeProduct()
        target = self.factory.makeBranch(
            product=product, information_type=InformationType.USERDATA)
        for i in range(7):
            source = self.factory.makeBranch(
                product=product, information_type=InformationType.USERDATA)
            self.factory.makeBranchMergeProposal(
                source_branch=removeSecurityProxy(source),
                target_branch=target)
        flush_database_caches()
        with StormStatementRecorder() as recorder:
            self.getViewBrowser(
                product, '+merges', rootsite='code', user=product.owner)
        self.assertThat(recorder, HasQueryCount(Equals(41)))

    def test_productseries(self):
        target = self.factory.makeBranch()
        unique_name = target.unique_name
        with person_logged_in(target.product.owner):
            target.product.development_focus.branch = target
        self.factory.makeBranchMergeProposal(target_branch=target)
        view = self.getViewBrowser(target, '+merges', rootsite='code')
        self.assertIn(unique_name, view.contents)


class ActiveReviewGroupsTest(TestCaseWithFactory):
    """Tests for groupings used in for active reviews."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(ActiveReviewGroupsTest, self).setUp()
        self.bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)

    def assertReviewGroupForReviewer(self, reviewer, group):
        # Assert that the group for the reviewer is correct.
        login(ANONYMOUS)
        # The actual context of the view doesn't matter here as all the
        # parameters are passed in.
        view = create_initialized_view(
            self.factory.makeProduct(), '+activereviews', rootsite='code')
        self.assertEqual(
            group, view._getReviewGroup(self.bmp, self.bmp.votes, reviewer))

    def test_unrelated_reviewer(self):
        # If the reviewer is not otherwise related to the proposal, the group
        # is other.
        reviewer = self.factory.makePerson()
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.OTHER)

    def test_approved(self):
        # If the proposal is approved, then the group is approved.
        self.bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.CODE_APPROVED)
        self.assertReviewGroupForReviewer(None, ActiveReviewsView.APPROVED)

    def test_work_in_progress(self):
        # If the proposal is in progress, then the group is wip.
        self.bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        self.assertReviewGroupForReviewer(None, ActiveReviewsView.WIP)

    def test_source_branch_owner(self):
        # If the reviewer is the owner of the source branch, then the review
        # is MINE.  This occurs whether or not the user is the logged in or
        # not.
        reviewer = self.bmp.source_branch.owner
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.MINE)

    def test_proposal_registrant(self):
        # If the reviewer is the registrant of the proposal, then it is MINE
        # only if the registrant is a member of the team that owns the branch.
        reviewer = self.bmp.registrant
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.OTHER)

        team = self.factory.makeTeam(self.bmp.registrant)
        removeSecurityProxy(self.bmp.source_branch).owner = team
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.MINE)

    def test_target_branch_owner(self):
        # For the target branch owner, it is to_do since they are the default
        # reviewer.
        reviewer = self.bmp.target_branch.owner
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.TO_DO)

    def test_group_pending_review(self):
        # If the reviewer in user has a pending review request, it is a TO_DO.
        reviewer = self.factory.makePerson()
        login_person(self.bmp.registrant)
        self.bmp.nominateReviewer(reviewer, self.bmp.registrant)
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.TO_DO)

    def test_group_pending_team_review(self):
        # If the logged in user of a team that has a pending review request,
        # it is a CAN_DO.
        reviewer = self.factory.makePerson()
        login_person(self.bmp.registrant)
        team = self.factory.makeTeam(reviewer)
        self.bmp.nominateReviewer(team, self.bmp.registrant)
        self.assertReviewGroupForReviewer(reviewer, ActiveReviewsView.CAN_DO)

    def test_review_done(self):
        # If the logged in user has a completed review, then the review is
        # ARE_DOING.
        reviewer = self.bmp.target_branch.owner
        login_person(reviewer)
        self.bmp.createComment(
            reviewer, 'subject', vote=CodeReviewVote.APPROVE)
        self.assertReviewGroupForReviewer(
            reviewer, ActiveReviewsView.ARE_DOING)


class TestBranchMergeProposalListingItem(TestCaseWithFactory):
    """Tests specifically relating to the BranchMergeProposalListingItem."""

    layer = DatabaseFunctionalLayer

    def test_sort_key_needs_review(self):
        # If the proposal is in needs review, the sort_key will be the
        # date_review_requested.
        bmp = self.factory.makeBranchMergeProposal(
            date_created=datetime(2009, 6, 1, tzinfo=pytz.UTC))
        login_person(bmp.registrant)
        request_date = datetime(2009, 7, 1, tzinfo=pytz.UTC)
        bmp.requestReview(request_date)
        item = BranchMergeProposalListingItem(bmp, None, None)
        self.assertEqual(request_date, item.sort_key)

    def test_sort_key_approved(self):
        # If the proposal is approved, the sort_key will default to the
        # date_review_requested.
        bmp = self.factory.makeBranchMergeProposal(
            date_created=datetime(2009, 6, 1, tzinfo=pytz.UTC))
        login_person(bmp.target_branch.owner)
        request_date = datetime(2009, 7, 1, tzinfo=pytz.UTC)
        bmp.requestReview(request_date)
        bmp.approveBranch(
            bmp.target_branch.owner, 'rev-id',
            datetime(2009, 8, 1, tzinfo=pytz.UTC))
        item = BranchMergeProposalListingItem(bmp, None, None)
        self.assertEqual(request_date, item.sort_key)

    def test_sort_key_approved_from_wip(self):
        # If the proposal is approved and the review has been bypassed, the
        # date_reviewed is used.
        bmp = self.factory.makeBranchMergeProposal(
            date_created=datetime(2009, 6, 1, tzinfo=pytz.UTC))
        login_person(bmp.target_branch.owner)
        review_date = datetime(2009, 8, 1, tzinfo=pytz.UTC)
        bmp.approveBranch(
            bmp.target_branch.owner, 'rev-id', review_date)
        item = BranchMergeProposalListingItem(bmp, None, None)
        self.assertEqual(review_date, item.sort_key)

    def test_sort_key_wip(self):
        # If the proposal is a work in progress, the date_created is used.
        bmp = self.factory.makeBranchMergeProposal(
            date_created=datetime(2009, 6, 1, tzinfo=pytz.UTC))
        login_person(bmp.target_branch.owner)
        item = BranchMergeProposalListingItem(bmp, None, None)
        self.assertEqual(bmp.date_created, item.sort_key)


class ActiveReviewSortingTest(TestCaseWithFactory):
    """Test the sorting of the active review groups."""

    layer = DatabaseFunctionalLayer

    def test_oldest_first(self):
        # The oldest requested reviews should be first.
        product = self.factory.makeProduct()
        bmp1 = self.factory.makeBranchMergeProposal(product=product)
        login_person(bmp1.source_branch.owner)
        bmp1.requestReview(datetime(2009, 6, 1, tzinfo=pytz.UTC))
        bmp2 = self.factory.makeBranchMergeProposal(product=product)
        login_person(bmp2.source_branch.owner)
        bmp2.requestReview(datetime(2009, 3, 1, tzinfo=pytz.UTC))
        bmp3 = self.factory.makeBranchMergeProposal(product=product)
        login_person(bmp3.source_branch.owner)
        bmp3.requestReview(datetime(2009, 1, 1, tzinfo=pytz.UTC))
        login(ANONYMOUS)
        view = create_initialized_view(
            product, name='+activereviews', rootsite='code')
        self.assertEqual(
            [bmp3, bmp2, bmp1],
            [item.context for item in view.review_groups[view.OTHER]])


class ActiveReviewsWithPrivateBranches(TestCaseWithFactory):
    """Test the sorting of the active review groups."""

    layer = DatabaseFunctionalLayer

    def test_private_branch_owner(self):
        # Merge proposals against private branches are visible to
        # the branch owner.
        product = self.factory.makeProduct()
        branch = self.factory.makeBranch(
            product=product, information_type=InformationType.USERDATA)
        with person_logged_in(removeSecurityProxy(branch).owner):
            mp = self.factory.makeBranchMergeProposal(target_branch=branch)
            view = create_initialized_view(
                branch, name='+activereviews', rootsite='code')
            self.assertEqual([mp], list(view.getProposals()))


class PersonActiveReviewsPerformance(TestCaseWithFactory):
    """Test the performance of the person's active reviews page."""

    layer = LaunchpadFunctionalLayer

    def setupBMP(self, bmp):
        self.factory.makePreviewDiff(merge_proposal=bmp)
        login_person(bmp.source_branch.owner)
        bmp.requestReview()

    def createUserBMP(self, reviewer=None, target_branch_owner=None):
        target_branch = None
        if target_branch_owner is not None:
            target_branch = self.factory.makePackageBranch(
                owner=target_branch_owner)
        bmp = self.factory.makeBranchMergeProposal(
            reviewer=reviewer, target_branch=target_branch)
        self.setupBMP(bmp)
        return bmp

    def createUserBMPsAndRecordQueries(self, number_of_bmps):
        # Create {number_of_bmps} branch merge proposals related to a
        # user, render the person's +activereviews page, and return the
        # view and a recorder of the queries generated by this page
        # rendering.
        user = self.factory.makePerson()
        for i in xrange(number_of_bmps):
            # Create one of the two types of BMP which will be displayed
            # on a person's +activereviews page:
            # - A BMP for which the person is the reviewer.
            # - A BMP for which the person is the owner of the target
            # branch.
            if i % 2 == 0:
                self.createUserBMP(target_branch_owner=user)
            else:
                self.createUserBMP(reviewer=user)
        login_person(user)
        flush_database_caches()
        with StormStatementRecorder() as recorder:
            view = create_initialized_view(
                user, name='+activereviews', rootsite='code', principal=user)
            view.render()
        return recorder, view

    def test_person_activereviews_query_count(self):
        base_bmps = 3
        added_bmps = 4
        recorder1, view1 = self.createUserBMPsAndRecordQueries(base_bmps)
        self.assertEqual(base_bmps, view1.proposal_count)
        self.addDetail("r1tb", Content(UTF8_TEXT, lambda: [str(recorder1)]))
        recorder2, view2 = self.createUserBMPsAndRecordQueries(
            base_bmps + added_bmps)
        self.assertEqual(base_bmps + added_bmps, view2.proposal_count)
        self.assertThat(recorder2, HasQueryCount(Equals(recorder1.count)))

    def createProductBMP(self, product):
        target_branch = self.factory.makeStackedOnBranchChain(product=product)
        bmp = self.factory.makeBranchMergeProposal(
            product=product, target_branch=target_branch)
        self.setupBMP(bmp)
        return bmp

    def createProductBMPsAndRecordQueries(self, number_of_bmps):
        # Create {number_of_bmps} branch merge proposals related to a
        # product, render the product's +activereviews page, and return the
        # view and a recorder of the queries generated by this page
        # rendering.
        product = self.factory.makeProduct()
        for i in xrange(number_of_bmps):
            self.createProductBMP(product=product)
        login_person(product.owner)
        flush_database_caches()
        with StormStatementRecorder() as recorder:
            view = create_initialized_view(
                product, name='+activereviews', rootsite='code',
                principal=product.owner)
            view.render()
        return recorder, view

    def test_product_activereviews_query_count(self):
        # We keep the number of bmps created small (3 and 7), see above.
        base_bmps = 3
        added_bmps = 4
        recorder1, view1 = self.createProductBMPsAndRecordQueries(base_bmps)
        self.assertEqual(base_bmps, view1.proposal_count)
        self.addDetail("r1tb", Content(UTF8_TEXT, lambda: [str(recorder1)]))
        recorder2, view2 = self.createProductBMPsAndRecordQueries(
            base_bmps + added_bmps)
        self.assertEqual(base_bmps + added_bmps, view2.proposal_count)
        self.assertThat(recorder2, HasQueryCount(Equals(recorder1.count)))
