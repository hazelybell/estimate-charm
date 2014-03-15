# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for branch merge proposal jobs."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.interfaces import IObjectModifiedEvent
import pytz
from sqlobject import SQLObjectNotFound
from storm.locals import Select
from storm.store import Store
from testtools.matchers import Equals
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.adapters.branch import BranchMergeProposalNoPreviewDiffDelta
from lp.code.enums import BranchMergeProposalStatus
from lp.code.interfaces.branchmergeproposal import (
    IBranchMergeProposalJob,
    IBranchMergeProposalJobSource,
    ICodeReviewCommentEmailJob,
    ICodeReviewCommentEmailJobSource,
    IGenerateIncrementalDiffJob,
    IGenerateIncrementalDiffJobSource,
    IMergeProposalNeedsReviewEmailJob,
    IMergeProposalUpdatedEmailJob,
    IMergeProposalUpdatedEmailJobSource,
    IReviewRequestedEmailJob,
    IReviewRequestedEmailJobSource,
    IUpdatePreviewDiffJob,
    IUpdatePreviewDiffJobSource,
    )
from lp.code.model.branchmergeproposaljob import (
    BranchMergeProposalJob,
    BranchMergeProposalJobDerived,
    BranchMergeProposalJobType,
    CodeReviewCommentEmailJob,
    GenerateIncrementalDiffJob,
    MergeProposalNeedsReviewEmailJob,
    MergeProposalUpdatedEmailJob,
    ReviewRequestedEmailJob,
    UpdatePreviewDiffJob,
    )
from lp.code.model.tests.test_diff import (
    create_example_merge,
    DiffTestCase,
    )
from lp.code.subscribers.branchmergeproposal import merge_proposal_modified
from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.job.runner import JobRunner
from lp.services.job.tests import (
    block_on_job,
    pop_remote_notifications,
    )
from lp.services.osutils import override_environ
from lp.testing import (
    EventRecorder,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    CeleryBzrsyncdJobLayer,
    CeleryJobLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class TestBranchMergeProposalJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_providesInterface(self):
        """BranchMergeProposalJob implements expected interfaces."""
        bmp = self.factory.makeBranchMergeProposal()
        job = BranchMergeProposalJob(
            bmp, BranchMergeProposalJobType.MERGE_PROPOSAL_NEEDS_REVIEW, {})
        job.sync()
        verifyObject(IBranchMergeProposalJob, job)


class TestBranchMergeProposalJobDerived(TestCaseWithFactory):
    """Test the behaviour of the BranchMergeProposalJobDerived base class."""

    layer = LaunchpadZopelessLayer

    def test_get(self):
        """Ensure get returns or raises appropriately.

        It's an error to call get on BranchMergeProposalJobDerived-- it must
        be called on a subclass.  An object is returned only if the job id
        and job type match the request.  If no suitable object can be found,
        SQLObjectNotFound is raised.
        """
        bmp = self.factory.makeBranchMergeProposal()
        job = MergeProposalNeedsReviewEmailJob.create(bmp)
        transaction.commit()
        self.assertRaises(
            AttributeError, BranchMergeProposalJobDerived.get, job.id)
        self.assertRaises(SQLObjectNotFound, UpdatePreviewDiffJob.get, job.id)
        self.assertRaises(
            SQLObjectNotFound, MergeProposalNeedsReviewEmailJob.get,
            job.id + 1)
        self.assertEqual(job, MergeProposalNeedsReviewEmailJob.get(job.id))


class TestMergeProposalNeedsReviewEmailJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_providesInterface(self):
        """MergeProposalNeedsReviewEmailJob provides expected interfaces."""
        bmp = self.factory.makeBranchMergeProposal()
        job = MergeProposalNeedsReviewEmailJob.create(bmp)
        verifyObject(IMergeProposalNeedsReviewEmailJob, job)
        verifyObject(IBranchMergeProposalJob, job)

    def test_getOperationDescription(self):
        bmp = self.factory.makeBranchMergeProposal()
        job = MergeProposalNeedsReviewEmailJob.create(bmp)
        self.assertTrue(
            job.getOperationDescription().startswith(
                'notifying people about the proposal to merge'))

    def checkDiff(self, diff):
        self.assertNotIn('+bar', diff.diff.text)
        self.assertIn('+qux', diff.diff.text)

    def createProposalWithEmptyBranches(self):
        target_branch, tree = self.create_branch_and_tree()
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit('test')
        source_branch = self.factory.makeProductBranch(
            product=target_branch.product)
        self.createBzrBranch(source_branch, tree.branch)
        return self.factory.makeBranchMergeProposal(
            source_branch=source_branch, target_branch=target_branch)

    def test_run_sends_email(self):
        """MergeProposalCreationJob.run sends an email."""
        self.useBzrBranches(direct_database=True)
        bmp = self.createProposalWithEmptyBranches()
        job = MergeProposalNeedsReviewEmailJob.create(bmp)
        self.assertEqual([], pop_notifications())
        job.run()
        self.assertEqual(2, len(pop_notifications()))

    def test_getOopsMailController(self):
        """The registrant is notified about merge proposal creation issues."""
        bmp = self.factory.makeBranchMergeProposal()
        job = MergeProposalNeedsReviewEmailJob.create(bmp)
        ctrl = job.getOopsMailController('1234')
        self.assertEqual([bmp.registrant.preferredemail.email], ctrl.to_addrs)
        message = (
            'notifying people about the proposal to merge %s into %s' %
            (bmp.source_branch.bzr_identity, bmp.target_branch.bzr_identity))
        self.assertIn(message, ctrl.body)

    def test_MergeProposalCreateJob_with_sourcepackage_branch(self):
        """Jobs for merge proposals with sourcepackage branches work."""
        self.useBzrBranches(direct_database=True)
        bmp = self.factory.makeBranchMergeProposal(
            target_branch=self.factory.makePackageBranch())
        tree = self.create_branch_and_tree(db_branch=bmp.target_branch)[1]
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            tree.commit('Initial commit')
        self.createBzrBranch(bmp.source_branch, tree.branch)
        self.factory.makeRevisionsForBranch(bmp.source_branch, count=1)
        job = MergeProposalNeedsReviewEmailJob.create(bmp)
        with dbuser("merge-proposal-jobs"):
            job.run()


class TestUpdatePreviewDiffJob(DiffTestCase):

    layer = LaunchpadZopelessLayer

    def test_implement_interface(self):
        """UpdatePreviewDiffJob implements IUpdatePreviewDiffJobSource."""
        verifyObject(IUpdatePreviewDiffJobSource, UpdatePreviewDiffJob)

    def test_providesInterface(self):
        """MergeProposalNeedsReviewEmailJob provides expected interfaces."""
        bmp = self.factory.makeBranchMergeProposal()
        job = UpdatePreviewDiffJob.create(bmp)
        verifyObject(IUpdatePreviewDiffJob, job)
        verifyObject(IBranchMergeProposalJob, job)

    def test_getOperationDescription(self):
        bmp = self.factory.makeBranchMergeProposal()
        job = UpdatePreviewDiffJob.create(bmp)
        self.assertEqual(
            'generating the diff for a merge proposal',
            job.getOperationDescription())

    def test_run(self):
        self.useBzrBranches(direct_database=True)
        bmp = create_example_merge(self)[0]
        job = UpdatePreviewDiffJob.create(bmp)
        self.factory.makeRevisionsForBranch(bmp.source_branch, count=1)
        bmp.source_branch.next_mirror_time = None
        with dbuser("merge-proposal-jobs"):
            JobRunner([job]).runAll()
        self.checkExampleMerge(bmp.preview_diff.text)

    def test_run_object_events(self):
        # While the job runs a single IObjectModifiedEvent is issued when the
        # preview diff has been calculated.
        self.useBzrBranches(direct_database=True)
        bmp = create_example_merge(self)[0]
        job = UpdatePreviewDiffJob.create(bmp)
        self.factory.makeRevisionsForBranch(bmp.source_branch, count=1)
        bmp.source_branch.next_mirror_time = None
        with dbuser("merge-proposal-jobs"):
            with EventRecorder() as event_recorder:
                JobRunner([job]).runAll()
        bmp_object_events = [
            event for event in event_recorder.events
            if (IObjectModifiedEvent.providedBy(event) and
                event.object == bmp)]
        self.assertEqual(
            1, len(bmp_object_events),
            "Expected one event, got: %r" % bmp_object_events)
        self.assertEqual(
            ["preview_diff"], bmp_object_events[0].edited_fields)

    def test_run_branches_empty(self):
        """If the branches are empty, we tell the user."""
        # If the job has been waiting for a significant period of time (15
        # minutes for now), we run the job anyway.  The checkReady method
        # then raises and this is caught as a user error by the job system,
        # and as such sends an email to the error recipients, which for this
        # job is the merge proposal registrant.
        eric = self.factory.makePerson(name='eric', email='eric@example.com')
        bmp = self.factory.makeBranchMergeProposal(registrant=eric)
        job = UpdatePreviewDiffJob.create(bmp)
        pop_notifications()
        JobRunner([job]).runAll()
        [email] = pop_notifications()
        self.assertEqual('Eric <eric@example.com>', email['to'])
        self.assertEqual(
            'Launchpad error while generating the diff for a merge proposal',
            email['subject'])
        self.assertEqual(
            'Launchpad encountered an error during the following operation: '
            'generating the diff for a merge proposal.  '
            'The source branch has no revisions.',
            email.get_payload(decode=True))

    def test_run_branches_pending_writes(self):
        """If the branches are being written, we retry but don't complain."""
        eric = self.factory.makePerson(name='eric', email='eric@example.com')
        bmp = self.factory.makeBranchMergeProposal(registrant=eric)
        self.factory.makeRevisionsForBranch(bmp.source_branch, count=1)
        self.factory.makeRevisionsForBranch(bmp.target_branch, count=1)
        # Kludge a branch being a bit out of date in a way that will make
        # pending_writes true, without anything else failing.
        removeSecurityProxy(bmp.source_branch).last_mirrored_id = \
            self.factory.getUniqueString()
        job = UpdatePreviewDiffJob.create(bmp)
        # pop_notifications()
        JobRunner([job]).runAll()
        emails = pop_notifications()
        self.assertThat(emails, Equals([]))
        self.assertThat(job.status, Equals(JobStatus.WAITING))
        self.assertThat(job.attempt_count, Equals(1))
        self.assertThat(job.max_retries, Equals(20))

    def test_10_minute_lease(self):
        self.useBzrBranches(direct_database=True)
        bmp = create_example_merge(self)[0]
        job = UpdatePreviewDiffJob.create(bmp)
        job.acquireLease()
        expiry_delta = job.lease_expires - datetime.now(pytz.UTC)
        self.assertTrue(500 <= expiry_delta.seconds, expiry_delta)


def make_runnable_incremental_diff_job(test_case):
    test_case.useBzrBranches(direct_database=True)
    bmp, source_rev_id, target_rev_id = create_example_merge(test_case)
    repository = bmp.source_branch.getBzrBranch().repository
    parent_id = repository.get_revision(source_rev_id).parent_ids[0]
    test_case.factory.makeRevision(rev_id=source_rev_id)
    test_case.factory.makeRevision(rev_id=parent_id)
    return GenerateIncrementalDiffJob.create(bmp, parent_id, source_rev_id)


class TestGenerateIncrementalDiffJob(DiffTestCase):

    layer = LaunchpadZopelessLayer

    def test_implement_interface(self):
        """GenerateIncrementalDiffJob implements its interface."""
        verifyObject(
            IGenerateIncrementalDiffJobSource, GenerateIncrementalDiffJob)

    def test_providesInterface(self):
        """MergeProposalCreatedJob provides the expected interfaces."""
        bmp = self.factory.makeBranchMergeProposal()
        job = GenerateIncrementalDiffJob.create(bmp, 'old', 'new')
        verifyObject(IGenerateIncrementalDiffJob, job)
        verifyObject(IBranchMergeProposalJob, job)

    def test_getOperationDescription(self):
        """The description of the job is sane."""
        bmp = self.factory.makeBranchMergeProposal()
        job = GenerateIncrementalDiffJob.create(bmp, 'old', 'new')
        self.assertEqual(
            'generating an incremental diff for a merge proposal',
            job.getOperationDescription())

    def test_run(self):
        """The job runs successfully, and its results can be committed."""
        job = make_runnable_incremental_diff_job(self)
        with dbuser("merge-proposal-jobs"):
            job.run()

    def test_run_all(self):
        """The job can be run under the JobRunner successfully."""
        job = make_runnable_incremental_diff_job(self)
        with dbuser("merge-proposal-jobs"):
            runner = JobRunner([job])
            runner.runAll()
        self.assertEqual([job], runner.completed_jobs)

    def test_10_minute_lease(self):
        """Newly-created jobs have a ten-minute lease."""
        self.useBzrBranches(direct_database=True)
        bmp = create_example_merge(self)[0]
        job = GenerateIncrementalDiffJob.create(bmp, 'old', 'new')
        with dbuser("merge-proposal-jobs"):
            job.acquireLease()
        expiry_delta = job.lease_expires - datetime.now(pytz.UTC)
        self.assertTrue(500 <= expiry_delta.seconds, expiry_delta)


class TestBranchMergeProposalJobSource(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.job_source = getUtility(IBranchMergeProposalJobSource)

    def test_utility_provides_interface(self):
        # The utility that is registered as the job source needs to implement
        # the methods is says it does.
        self.assertProvides(self.job_source, IBranchMergeProposalJobSource)

    def test_iterReady_new_merge_proposal_update_unready(self):
        # A new merge proposal has two jobs, one for the diff, and one for the
        # email.  The diff email is always returned first, providing that it
        # is ready.  The diff job is ready if both the source and target have
        # revisions, and the source branch doesn't have a pending scan.
        self.factory.makeBranchMergeProposal()
        jobs = self.job_source.iterReady()
        self.assertEqual([], jobs)

    def test_iterReady_new_merge_proposal_update_diff_timeout(self):
        # Even if the update preview diff would not normally be considered
        # ready, if the job is older than 15 minutes, it is considered ready.
        # The job itself will attempt to run, and if it isn't ready, will send
        # an email to the branch registrant.  This is tested in above in
        # TestUpdatePreviewDiff.
        bmp = self.factory.makeBranchMergeProposal()
        bmp_jobs = Store.of(bmp).find(
            Job,
            Job.id.is_in(
                Select(
                    BranchMergeProposalJob.jobID,
                    BranchMergeProposalJob.branch_merge_proposal == bmp.id)))
        minutes = config.codehosting.update_preview_diff_ready_timeout + 1
        a_while_ago = datetime.now(pytz.UTC) - timedelta(minutes=minutes)
        bmp_jobs.set(date_created=a_while_ago)
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, UpdatePreviewDiffJob)

    def test_iterReady_new_merge_proposal_target_revisions(self):
        # The target branch having revisions is not enough for the job to be
        # considered ready.
        bmp = self.factory.makeBranchMergeProposal()
        self.factory.makeRevisionsForBranch(bmp.target_branch)
        jobs = self.job_source.iterReady()
        self.assertEqual([], jobs)

    def test_iterReady_new_merge_proposal_source_revisions(self):
        # The source branch having revisions is not enough for the job to be
        # considered ready.
        bmp = self.factory.makeBranchMergeProposal()
        self.factory.makeRevisionsForBranch(bmp.source_branch)
        jobs = self.job_source.iterReady()
        self.assertEqual([], jobs)

    def test_iterReady_new_merge_proposal_pending_source_scan(self):
        # If the source branch has a pending scan, it stops the job from being
        # ready.
        bmp = self.makeBranchMergeProposal()
        bmp.source_branch.last_mirrored_id = 'last-rev-id'
        jobs = self.job_source.iterReady()
        self.assertEqual([], jobs)

    def test_iterReady_new_merge_proposal_pending_target_scan(self):
        # If the target branch has a pending scan, it does not affect the jobs
        # readiness.
        bmp = self.makeBranchMergeProposal()
        bmp.target_branch.last_mirrored_id = 'last-rev-id'
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, UpdatePreviewDiffJob)

    def test_iterReady_new_merge_proposal_update_diff_first(self):
        # A new merge proposal has two jobs, one for the diff, and one for the
        # email.  The diff email is always returned first.
        bmp = self.makeBranchMergeProposal()
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, UpdatePreviewDiffJob)

    def test_iterReady_new_merge_proposal_update_diff_running(self):
        # If the update preview diff job is running, then iterReady does not
        # return any other jobs for that merge proposal.
        self.makeBranchMergeProposal()
        [job] = self.job_source.iterReady()
        job.start()
        jobs = self.job_source.iterReady()
        self.assertEqual(0, len(jobs))

    def makeBranchMergeProposal(self, set_state=None):
        # Make a merge proposal that would have a ready update diff job.
        bmp = self.factory.makeBranchMergeProposal(set_state=set_state)
        self.factory.makeRevisionsForBranch(bmp.source_branch)
        self.factory.makeRevisionsForBranch(bmp.target_branch)
        return bmp

    def test_iterReady_new_merge_proposal_update_diff_finished(self):
        # Once the update preview diff job has finished running, then
        # iterReady returns the next job for the merge proposal, which is in
        # this case the initial email job.
        bmp = self.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        [update_diff] = self.job_source.iterReady()
        update_diff.start()
        update_diff.complete()
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, MergeProposalNeedsReviewEmailJob)

    def completePendingJobs(self):
        # Mark all current pending jobs as complete
        while True:
            jobs = self.job_source.iterReady()
            if len(jobs) == 0:
                break
            for job in jobs:
                job.start()
                job.complete()

    def test_iterReady_supports_review_requested(self):
        # iterReady will also return pending ReviewRequestedEmailJobs.
        bmp = self.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        self.completePendingJobs()
        reviewer = self.factory.makePerson()
        bmp.nominateReviewer(reviewer, bmp.registrant)
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, ReviewRequestedEmailJob)
        self.assertEqual(reviewer, job.reviewer)
        self.assertEqual(bmp.registrant, job.requester)

    def test_iterReady_supports_code_review_comment(self):
        # iterReady will also return pending CodeReviewCommentEmailJob.
        bmp = self.makeBranchMergeProposal()
        self.completePendingJobs()
        commenter = self.factory.makePerson()
        comment = bmp.createComment(commenter, '', 'Interesting idea.')
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, CodeReviewCommentEmailJob)
        self.assertEqual(comment, job.code_review_comment)

    def test_iterReady_supports_updated_emails(self):
        # iterReady will also return pending MergeProposalUpdatedEmailJob.
        bmp = self.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        self.completePendingJobs()
        old_merge_proposal = (
            BranchMergeProposalNoPreviewDiffDelta.snapshot(bmp))
        bmp.commit_message = 'new commit message'
        event = ObjectModifiedEvent(
            bmp, old_merge_proposal, [], bmp.registrant)
        merge_proposal_modified(bmp, event)
        [job] = self.job_source.iterReady()
        self.assertEqual(job.branch_merge_proposal, bmp)
        self.assertIsInstance(job, MergeProposalUpdatedEmailJob)


class TestCodeReviewCommentEmailJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_implement_interface(self):
        """UpdatePreviewDiffJob implements IUpdatePreviewDiffJobSource."""
        verifyObject(
            ICodeReviewCommentEmailJobSource, CodeReviewCommentEmailJob)

    def test_providesInterface(self):
        """CodeReviewCommentEmailJob provides the expected interfaces."""
        comment = self.factory.makeCodeReviewComment()
        job = CodeReviewCommentEmailJob.create(comment)
        verifyObject(ICodeReviewCommentEmailJob, job)
        verifyObject(IBranchMergeProposalJob, job)

    def test_getOperationDescription(self):
        comment = self.factory.makeCodeReviewComment()
        job = CodeReviewCommentEmailJob.create(comment)
        self.assertEqual(
            'emailing a code review comment',
            job.getOperationDescription())


class TestReviewRequestedEmailJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_implement_interface(self):
        """UpdatePreviewDiffJob implements IUpdatePreviewDiffJobSource."""
        verifyObject(IReviewRequestedEmailJobSource, ReviewRequestedEmailJob)

    def test_providesInterface(self):
        """ReviewRequestedEmailJob provides the expected interfaces."""
        request = self.factory.makeCodeReviewVoteReference()
        job = ReviewRequestedEmailJob.create(request)
        verifyObject(IReviewRequestedEmailJob, job)
        verifyObject(IBranchMergeProposalJob, job)

    def test_getOperationDescription(self):
        request = self.factory.makeCodeReviewVoteReference()
        job = ReviewRequestedEmailJob.create(request)
        self.assertEqual(
            'emailing a reviewer requesting a review',
            job.getOperationDescription())

    def test_run_sends_mail(self):
        request = self.factory.makeCodeReviewVoteReference()
        job = ReviewRequestedEmailJob.create(request)
        job.run()
        (notification,) = pop_notifications()
        self.assertIn(
            'You have been requested to review the proposed merge',
            notification.get_payload(decode=True))


class TestMergeProposalUpdatedEmailJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_class_implements_interface(self):
        verifyObject(
            IMergeProposalUpdatedEmailJobSource, MergeProposalUpdatedEmailJob)

    def test_providesInterface(self):
        """MergeProposalUpdatedEmailJob provides the expected interfaces."""
        bmp = self.factory.makeBranchMergeProposal()
        job = MergeProposalUpdatedEmailJob.create(
            bmp, 'change', bmp.registrant)
        verifyObject(IMergeProposalUpdatedEmailJob, job)
        verifyObject(IBranchMergeProposalJob, job)

    def test_getOperationDescription(self):
        bmp = self.factory.makeBranchMergeProposal()
        job = MergeProposalUpdatedEmailJob.create(
            bmp, 'change', bmp.registrant)
        self.assertEqual(
            'emailing subscribers about merge proposal changes',
            job.getOperationDescription())


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_MergeProposalNeedsReviewEmailJob(self):
        """MergeProposalNeedsReviewEmailJob runs under Celery."""
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes':
             'MergeProposalNeedsReviewEmailJob'}))
        bmp = self.factory.makeBranchMergeProposal()
        with block_on_job():
            MergeProposalNeedsReviewEmailJob.create(bmp)
            transaction.commit()
        self.assertEqual(2, len(pop_remote_notifications()))

    def test_CodeReviewCommentEmailJob(self):
        """CodeReviewCommentEmailJob runs under Celery."""
        comment = self.factory.makeCodeReviewComment()
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'CodeReviewCommentEmailJob'}))
        with block_on_job():
            CodeReviewCommentEmailJob.create(comment)
            transaction.commit()
        self.assertEqual(2, len(pop_remote_notifications()))

    def test_ReviewRequestedEmailJob(self):
        """ReviewRequestedEmailJob runs under Celery."""
        request = self.factory.makeCodeReviewVoteReference()
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'ReviewRequestedEmailJob'}))
        with block_on_job():
            ReviewRequestedEmailJob.create(request)
            transaction.commit()
        self.assertEqual(1, len(pop_remote_notifications()))

    def test_MergeProposalUpdatedEmailJob(self):
        """MergeProposalUpdatedEmailJob runs under Celery."""
        bmp = self.factory.makeBranchMergeProposal()
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'MergeProposalUpdatedEmailJob'}))
        with block_on_job():
            MergeProposalUpdatedEmailJob.create(
                bmp, 'change', bmp.registrant)
            transaction.commit()
        self.assertEqual(2, len(pop_remote_notifications()))


class TestViaBzrsyncdCelery(TestCaseWithFactory):

    layer = CeleryBzrsyncdJobLayer

    def test_UpdatePreviewDiffJob(self):
        """UpdatePreviewDiffJob runs under Celery."""
        self.useBzrBranches(direct_database=True)
        bmp = create_example_merge(self)[0]
        self.factory.makeRevisionsForBranch(bmp.source_branch, count=1)
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'UpdatePreviewDiffJob'}))
        with block_on_job():
            UpdatePreviewDiffJob.create(bmp)
            transaction.commit()
        self.assertIsNot(None, bmp.preview_diff)

    def test_GenerateIncrementalDiffJob(self):
        """GenerateIncrementalDiffJob runs under Celery."""
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'GenerateIncrementalDiffJob'}))
        with block_on_job():
            job = make_runnable_incremental_diff_job(self)
            transaction.commit()
        self.assertEqual(JobStatus.COMPLETED, job.status)
