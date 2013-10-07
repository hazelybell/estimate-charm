# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BranchMergeProposal mailings"""

from difflib import unified_diff
import operator
from textwrap import dedent

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
import transaction
from zope.interface import providedBy
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.mail.branch import RecipientReason
from lp.code.mail.branchmergeproposal import BMPMailer
from lp.code.model.branch import update_trigger_modified_fields
from lp.code.model.branchmergeproposaljob import (
    BranchMergeProposalJob,
    BranchMergeProposalJobType,
    MergeProposalUpdatedEmailJob,
    ReviewRequestedEmailJob,
    )
from lp.code.model.codereviewvote import CodeReviewVoteReference
from lp.code.model.diff import PreviewDiff
from lp.code.subscribers.branchmergeproposal import merge_proposal_modified
from lp.services.database.interfaces import IStore
from lp.services.webapp import canonical_url
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class TestMergeProposalMailing(TestCaseWithFactory):
    """Test that reasonable mailings are generated"""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestMergeProposalMailing, self).setUp('admin@canonical.com')

    def makeProposalWithSubscriber(self, diff_text=None, initial_comment=None,
                                   prerequisite=False, needs_review=True,
                                   reviewer=None):
        registrant = self.factory.makePerson(
            name='bazqux', displayname='Baz Qux', email='baz.qux@example.com')
        product = self.factory.makeProduct(name='super-product')
        if prerequisite:
            prerequisite_branch = self.factory.makeProductBranch(product)
        else:
            prerequisite_branch = None
        if needs_review:
            initial_status = BranchMergeProposalStatus.NEEDS_REVIEW
        else:
            initial_status = BranchMergeProposalStatus.WORK_IN_PROGRESS
        bmp = self.factory.makeBranchMergeProposal(
            registrant=registrant, product=product, set_state=initial_status,
            prerequisite_branch=prerequisite_branch,
            initial_comment=initial_comment, reviewer=reviewer)
        if diff_text:
            PreviewDiff.create(
                bmp, diff_text, unicode(self.factory.getUniqueString('revid')),
                unicode(self.factory.getUniqueString('revid')), None, None)
            transaction.commit()
        subscriber = self.factory.makePerson(displayname='Baz Quxx',
            email='baz.quxx@example.com')
        bmp.source_branch.subscribe(subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, subscriber)
        bmp.source_branch.owner.name = 'bob'
        bmp.source_branch.name = 'fix-foo-for-bar'
        bmp.target_branch.owner.name = 'mary'
        bmp.target_branch.name = 'bar'
        bmp.commit_message = 'commit message'
        # Call the function that is normally called through the event system
        # to auto reload the fields updated by the db triggers.
        update_trigger_modified_fields(bmp.source_branch)
        update_trigger_modified_fields(bmp.target_branch)
        return bmp, subscriber

    def test_generateCreationEmail(self):
        """Ensure that the contents of the mail are as expected"""
        bmp, subscriber = self.makeProposalWithSubscriber()
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        assert mailer.message_id is not None, 'Message-id should be set'
        mailer.message_id = '<foobar-example-com>'
        reason = mailer._recipients.getReason(
            subscriber.preferredemail.email)[0]
        bmp.root_message_id = None
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        reviewer = bmp.target_branch.owner
        expected = dedent("""\
        Baz Qux has proposed merging %(source)s into %(target)s.

        Commit message:
        %(commit_message)s

        Requested reviews:
          %(reviewer)s

        For more details, see:
        %(bmp)s
        --\x20
        %(bmp)s
        %(reason)s
        """) % {
            'source': bmp.source_branch.bzr_identity,
            'target': bmp.target_branch.bzr_identity,
            'commit_message': bmp.commit_message,
            'reviewer': reviewer.unique_displayname,
            'bmp': canonical_url(bmp),
            'reason': reason.getReason()}
        self.assertEqual(expected, ctrl.body)
        self.assertEqual('[Merge] '
            'lp://dev/~bob/super-product/fix-foo-for-bar into '
            'lp://dev/~mary/super-product/bar', ctrl.subject)
        self.assertEqual(
            {'X-Launchpad-Branch': bmp.source_branch.unique_name,
             'X-Launchpad-Message-Rationale': 'Subscriber',
             'X-Launchpad-Notification-Type': 'code-review',
             'X-Launchpad-Project': bmp.source_branch.product.name,
             'Reply-To': bmp.address,
             'Message-Id': '<foobar-example-com>'},
            ctrl.headers)
        self.assertEqual('Baz Qux <baz.qux@example.com>', ctrl.from_addr)
        reviewer_id = mailer._format_user_address(reviewer)
        self.assertEqual(set([reviewer_id, bmp.address]), set(ctrl.to_addrs))
        mailer.sendAll()

    def test_forCreation_without_commit_message(self):
        """If there is no commit message, email should say 'None Specified.'"""
        bmp, subscriber = self.makeProposalWithSubscriber()
        bmp.commit_message = None
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        self.assertNotIn('Commit message:', ctrl.body)

    def test_forCreation_with_bugs(self):
        """If there are related bugs, include 'Related bugs'."""
        bmp, subscriber = self.makeProposalWithSubscriber()
        bug = self.factory.makeBug(title='I am a bug')
        bugtask = bug.default_bugtask
        bmp.source_branch.linkBug(bug, bmp.registrant)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        expected = (
            'Related bugs:\n'
            '  %s\n'
            '  %s\n' % (bugtask.title, canonical_url(bugtask)))
        self.assertIn(expected, ctrl.body)

    def test_forCreation_without_bugs(self):
        """If there are no related bugs, omit 'Related bugs'."""
        bmp, subscriber = self.makeProposalWithSubscriber()
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        self.assertNotIn('Related bugs:\n', ctrl.body)

    def test_forCreation_with_review_request(self):
        """Correctly format list of reviewers."""
        reviewer = self.factory.makePerson(name='review-person')
        bmp, subscriber = self.makeProposalWithSubscriber(reviewer=reviewer)
        bmp.nominateReviewer(reviewer, bmp.registrant, None)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        self.assertIn(
            '\nRequested reviews:'
            '\n  Review-person (review-person)\n'
            '\n'
            'For more details, see:\n'
            '%s\n-- \n' % canonical_url(bmp),
            ctrl.body)

    def test_forCreation_with_review_request_and_bug(self):
        """Correctly format list of reviewers and bug info."""
        reviewer = self.factory.makePerson(name='review-person')
        bmp, subscriber = self.makeProposalWithSubscriber(reviewer=reviewer)
        bug = self.factory.makeBug(title='I am a bug')
        bugtask = bug.default_bugtask
        bmp.source_branch.linkBug(bug, bmp.registrant)
        bmp.nominateReviewer(reviewer, bmp.registrant, None)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        expected = (
            '\nRequested reviews:'
            '\n  Review-person (review-person)'
            '\nRelated bugs:'
            '\n  %s'
            '\n  %s\n'
            '\nFor more details, see:\n'
            '%s'
            '\n--' % (bugtask.title, canonical_url(bugtask),
                      canonical_url(bmp)))
        self.assertIn(expected, ctrl.body)

    def test_forCreation_with_review_request_and_private_bug(self):
        """Correctly format list of reviewers and bug info.

        Private bugs should not be listed in the email unless authorised.
        """
        reviewer = self.factory.makePerson(name='review-person')
        bmp, subscriber = self.makeProposalWithSubscriber(reviewer=reviewer)

        # Create and subscribe the owner of the private bug
        private_bug_owner = self.factory.makePerson(email="owner@example.com")
        bmp.source_branch.subscribe(private_bug_owner,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, private_bug_owner)

        # Create and link the bugs to the branch
        bug = self.factory.makeBug(title='I am a bug')
        bugtask = bug.default_bugtask
        bmp.source_branch.linkBug(bug, bmp.registrant)
        private_bug = self.factory.makeBug(
            title='I am a private bug', owner=private_bug_owner,
            information_type=InformationType.USERDATA)
        private_bugtask = private_bug.default_bugtask
        with person_logged_in(private_bug_owner):
            bmp.source_branch.linkBug(private_bug, bmp.registrant)

        # Set up the mailer
        bmp.nominateReviewer(reviewer, bmp.registrant, None)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)

        # A non authorised email recipient doesn't see the private bug.
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        expected = (
            '\nRequested reviews:'
            '\n  Review-person (review-person)'
            '\nRelated bugs:'
            '\n  %s'
            '\n  %s\n'
            '\nFor more details, see:\n'
            '%s'
            '\n--' % (bugtask.title, canonical_url(bugtask),
                      canonical_url(bmp)))
        self.assertIn(expected, ctrl.body)

        # An authorised email recipient does see the private bug.
        ctrl = mailer.generateEmail('owner@example.com', private_bug_owner)
        expected = (
            '\nRequested reviews:'
            '\n  Review-person (review-person)'
            '\nRelated bugs:'
            '\n  %s'
            '\n  %s'
            '\n  %s'
            '\n  %s\n'
            '\nFor more details, see:\n'
            '%s'
            '\n--' % (bugtask.title, canonical_url(bugtask),
                      private_bugtask.title, canonical_url(private_bugtask),
                      canonical_url(bmp)))
        self.assertIn(expected, ctrl.body)

    def test_forCreation_with_prerequisite_branch(self):
        """Correctly format list of reviewers."""
        bmp, subscriber = self.makeProposalWithSubscriber(prerequisite=True)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        prereq = bmp.prerequisite_branch.bzr_identity
        self.assertIn(' with %s as a prerequisite.' % prereq, ctrl.body)

    def test_to_addrs_includes_reviewers(self):
        """The addresses for the to header include requested reviewers"""
        request, requester = self.makeReviewRequest()
        bmp = request.merge_proposal
        bmp.source_branch.subscribe(
            bmp.registrant, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, bmp.registrant)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail(bmp.registrant.preferredemail.email,
                                    bmp.registrant)
        reviewer = request.recipient
        reviewer_id = mailer._format_user_address(reviewer)
        self.assertEqual(set([reviewer_id, bmp.address]), set(ctrl.to_addrs))

    def test_to_addrs_excludes_team_reviewers(self):
        """Addresses for the to header exclude requested team reviewers."""
        bmp, subscriber = self.makeProposalWithSubscriber()
        team = self.factory.makeTeam(email='group@team.com')
        CodeReviewVoteReference(
            branch_merge_proposal=bmp, reviewer=team, registrant=subscriber)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail(subscriber.preferredemail.email,
                                    subscriber)
        reviewer = bmp.target_branch.owner
        reviewer_id = mailer._format_user_address(reviewer)
        self.assertEqual(set([reviewer_id, bmp.address]), set(ctrl.to_addrs))

    def test_to_addrs_excludes_people_with_hidden_addresses(self):
        """The to header excludes those with hidden addresses."""
        request, requester = self.makeReviewRequest()
        request.recipient.hide_email_addresses = True
        bmp = request.merge_proposal
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail(request.recipient.preferredemail.email,
                                    request.recipient)
        self.assertEqual([bmp.address], ctrl.to_addrs)

    def test_RecordMessageId(self):
        """Ensure that the contents of the mail are as expected"""
        bmp, subscriber = self.makeProposalWithSubscriber()
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        mailer.message_id = '<foobar-example-com>'
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        self.assertEqual('<foobar-example-com>', ctrl.headers['Message-Id'])
        self.assertEqual('Baz Qux <baz.qux@example.com>', ctrl.from_addr)
        bmp.root_message_id = None
        pop_notifications()
        mailer.sendAll()
        for notification in pop_notifications():
            self.assertEqual('<foobar-example-com>',
                notification['Message-Id'])
        self.assertEqual('<foobar-example-com>', bmp.root_message_id)
        mailer.message_id = '<bazqux-example-com>'
        mailer.sendAll()
        self.assertEqual('<foobar-example-com>', bmp.root_message_id)

    def test_inReplyTo(self):
        """Ensure that messages are in reply to the root"""
        bmp, subscriber = self.makeProposalWithSubscriber()
        bmp.root_message_id = '<root-message-id>'
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        self.assertEqual('<root-message-id>', ctrl.headers['In-Reply-To'])

    def test_generateEmail_attaches_diff(self):
        """A diff should be attached, with the correct metadata.

        The attached diff should be inline, should have a filename,
        and should be of type text/x-diff (or text/x-patch), with no declared
        encoding.  (The only encoding in a diff is the encoding of the input
        files, which may be inconsistent.)
        """
        diff_text = ''.join(unified_diff('', 'Fake diff'))
        bmp, subscriber = self.makeProposalWithSubscriber(
            diff_text=diff_text)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        (attachment,) = ctrl.attachments
        self.assertEqual(
            'text/x-diff; charset="utf-8"', attachment['Content-Type'])
        self.assertEqual('inline; filename="review-diff.txt"',
                         attachment['Content-Disposition'])
        self.assertEqual(diff_text, attachment.get_payload(decode=True))

    def test_generateEmail_no_diff_for_status_only(self):
        """If the subscription is for status only, don't attach diffs."""
        diff_text = ''.join(unified_diff('', 'Fake diff'))
        bmp, subscriber = self.makeProposalWithSubscriber(
            diff_text=diff_text)
        bmp.source_branch.subscribe(subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.STATUS, subscriber)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        self.assertEqual(0, len(ctrl.attachments))

    def test_generateEmail_attaches_diff_oversize_truncated(self):
        """An oversized diff will be truncated, and the receiver informed."""
        self.pushConfig("diff", max_read_size=25)
        diff_text = ''.join(unified_diff('', "1234567890" * 10))
        bmp, subscriber = self.makeProposalWithSubscriber(
            diff_text=diff_text)
        mailer = BMPMailer.forCreation(bmp, bmp.registrant)
        ctrl = mailer.generateEmail('baz.quxx@example.com', subscriber)
        (attachment,) = ctrl.attachments
        self.assertEqual(
            'text/x-diff; charset="utf-8"', attachment['Content-Type'])
        self.assertEqual('inline; filename="review-diff.txt"',
                         attachment['Content-Disposition'])
        self.assertEqual(diff_text[:25], attachment.get_payload(decode=True))
        warning_text = (
            "The attached diff has been truncated due to its size.\n")
        self.assertTrue(warning_text in ctrl.body)

    def getProposalUpdatedEmailJob(self, merge_proposal):
        """Return the merge proposal updated email job."""
        jobs = list(
            IStore(BranchMergeProposalJob).find(
                BranchMergeProposalJob,
                BranchMergeProposalJob.branch_merge_proposal ==
                merge_proposal,
                BranchMergeProposalJob.job_type ==
                BranchMergeProposalJobType.MERGE_PROPOSAL_UPDATED))
        if len(jobs) == 0:
            return None
        elif len(jobs) == 1:
            return MergeProposalUpdatedEmailJob(jobs[0])
        else:
            self.fail('There are more than one jobs.')

    def test_no_job_created_if_no_delta(self):
        """Ensure None is returned if no change has been made."""
        merge_proposal, person = self.makeProposalWithSubscriber()
        old_merge_proposal = Snapshot(
            merge_proposal, providing=providedBy(merge_proposal))
        event = ObjectModifiedEvent(
            merge_proposal, old_merge_proposal, [], merge_proposal.registrant)
        merge_proposal_modified(merge_proposal, event)
        self.assertIs(None, self.getProposalUpdatedEmailJob(merge_proposal))

    def test_no_job_created_if_only_preview_diff_changed(self):
        """Ensure None is returned if only the preview diff has changed."""
        merge_proposal, person = self.makeProposalWithSubscriber()
        old_merge_proposal = Snapshot(
            merge_proposal, providing=providedBy(merge_proposal))
        merge_proposal.updatePreviewDiff(
            ''.join(unified_diff('', 'Fake diff')),
            unicode(self.factory.getUniqueString('revid')),
            unicode(self.factory.getUniqueString('revid')))
        event = ObjectModifiedEvent(
            merge_proposal, old_merge_proposal, [], merge_proposal.registrant)
        merge_proposal_modified(merge_proposal, event)
        self.assertIs(None, self.getProposalUpdatedEmailJob(merge_proposal))

    def test_no_job_created_if_work_in_progress(self):
        """Ensure None is returned if no change has been made."""
        merge_proposal, person = self.makeProposalWithSubscriber(
            needs_review=False)
        old_merge_proposal = Snapshot(
            merge_proposal, providing=providedBy(merge_proposal))
        merge_proposal.commit_message = 'new commit message'
        merge_proposal.description = 'change description'
        event = ObjectModifiedEvent(
            merge_proposal, old_merge_proposal, [], merge_proposal.registrant)
        merge_proposal_modified(merge_proposal, event)
        self.assertIs(None, self.getProposalUpdatedEmailJob(merge_proposal))

    def test_job_created_if_work_in_progress_merged(self):
        # If work in progress is merged, then that is email worthy.
        merge_proposal, person = self.makeProposalWithSubscriber(
            needs_review=False)
        old_merge_proposal = Snapshot(
            merge_proposal, providing=providedBy(merge_proposal))
        merge_proposal.setStatus(BranchMergeProposalStatus.MERGED)
        event = ObjectModifiedEvent(
            merge_proposal, old_merge_proposal, [], merge_proposal.registrant)
        merge_proposal_modified(merge_proposal, event)
        job = self.getProposalUpdatedEmailJob(merge_proposal)
        self.assertIsNot(None, job, 'Job was not created.')

    def makeProposalUpdatedEmailJob(self):
        """Fixture method providing a mailer for a modified merge proposal"""
        merge_proposal, subscriber = self.makeProposalWithSubscriber()
        old_merge_proposal = Snapshot(
            merge_proposal, providing=providedBy(merge_proposal))
        merge_proposal.requestReview()
        merge_proposal.commit_message = 'new commit message'
        merge_proposal.description = 'change description'
        event = ObjectModifiedEvent(
            merge_proposal, old_merge_proposal, [], merge_proposal.registrant)
        merge_proposal_modified(merge_proposal, event)
        job = self.getProposalUpdatedEmailJob(merge_proposal)
        self.assertIsNot(None, job, 'Job was not created.')
        return job, subscriber

    def test_forModificationHasMsgId(self):
        """Ensure the right delta is filled out if there is a change."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        mailer = BMPMailer.forModification(
            merge_proposal, 'the diff', merge_proposal.registrant)
        self.assertIsNot(None, mailer.message_id, 'message_id not set')

    def test_forModificationWithModificationTextDelta(self):
        """Ensure the right delta is filled out if there is a change."""
        job, subscriber = self.makeProposalUpdatedEmailJob()
        self.assertEqual(
            'Commit Message changed to:\n\nnew commit message\n\n'
            'Description changed to:\n\nchange description',
            job.delta_text)

    def test_merge_proposal_modified(self):
        """Should send emails when invoked with correct parameters."""
        job, subscriber = self.makeProposalUpdatedEmailJob()
        pop_notifications()
        job.run()
        emails = pop_notifications(
            sort_key=operator.itemgetter('x-launchpad-message-rationale'))
        self.assertEqual(3, len(emails),
                         'There should be three emails sent out.  One to the '
                         'explicit subscriber above, and one each to the '
                         'source branch owner and the target branch owner '
                         'who were implicitly subscribed to their branches.')
        email = emails[0]
        self.assertEqual('[Merge] '
            'lp://dev/~bob/super-product/fix-foo-for-bar into\n'
            ' lp://dev/~mary/super-product/bar',
            email['subject'].replace('\n\t', '\n '))
        bmp = job.branch_merge_proposal
        expected = dedent("""\
            The proposal to merge %(source)s into %(target)s has been updated.

            Commit Message changed to:

            new commit message

            Description changed to:

            change description

            For more details, see:
            %(bmp)s
            --\x20
            %(bmp)s
            You are the owner of lp://dev/~bob/super-product/fix-foo-for-bar.
            """) % {
                'source': bmp.source_branch.bzr_identity,
                'target': bmp.target_branch.bzr_identity,
                'bmp': canonical_url(bmp)}
        self.assertEqual(expected, email.get_payload(decode=True))

    def assertRecipientsMatches(self, recipients, mailer):
        """Assert that `mailer` will send to the people in `recipients`."""
        persons = zip(*(mailer._recipients.getRecipientPersons()))[1]
        self.assertEqual(set(recipients), set(persons))

    def makeReviewRequest(self):
        diff_text = ''.join(unified_diff('', "Make a diff."))
        candidate = self.factory.makePerson(
            displayname='Candidate', email='candidate@example.com')
        merge_proposal, subscriber_ = self.makeProposalWithSubscriber(
            diff_text=diff_text, initial_comment="Initial comment",
            reviewer=candidate)
        requester = self.factory.makePerson(
            displayname='Requester', email='requester@example.com')
        reason = RecipientReason.forReviewer(merge_proposal, True, candidate)
        return reason, requester

    def test_forReviewRequest(self):
        """Test creating a mailer for a review request."""
        request, requester = self.makeReviewRequest()
        mailer = BMPMailer.forReviewRequest(
            request, request.merge_proposal, requester)
        self.assertEqual(
            'Requester <requester@example.com>', mailer.from_address)
        self.assertEqual(
            request.merge_proposal.preview_diff,
            mailer.preview_diff)
        self.assertRecipientsMatches([request.recipient], mailer)

    def test_to_addrs_for_review_request(self):
        request, requester = self.makeReviewRequest()
        mailer = BMPMailer.forReviewRequest(
            request, request.merge_proposal, requester)
        ctrl = mailer.generateEmail(request.recipient.preferredemail.email,
                                    request.recipient)
        recipient_addr = mailer._format_user_address(request.recipient)
        self.assertEqual([recipient_addr], ctrl.to_addrs)

    def test_forReviewRequestMessageId(self):
        """Test creating a mailer for a review request."""
        request, requester = self.makeReviewRequest()
        mailer = BMPMailer.forReviewRequest(
            request, request.merge_proposal, requester)
        assert mailer.message_id is not None, 'message_id not set'


class TestBranchMergeProposalRequestReview(TestCaseWithFactory):
    """Tests for `BranchMergeProposalRequestReviewView`."""

    layer = DatabaseFunctionalLayer

    def getReviewEmailJobs(self, bmp):
        """Return the result set for the merge proposals review email jobs."""
        review_job = BranchMergeProposalJobType.REVIEW_REQUEST_EMAIL
        return IStore(BranchMergeProposalJob).find(
            BranchMergeProposalJob,
            BranchMergeProposalJob.branch_merge_proposal == bmp,
            BranchMergeProposalJob.job_type == review_job)

    def getReviewNotificationEmail(self, bmp):
        """Return the review requested email job for the test's proposal."""
        [job] = list(self.getReviewEmailJobs(bmp))
        return ReviewRequestedEmailJob(job)

    def test_nominateReview_no_job_if_work_in_progress(self):
        # When a reviewer is nominated for a proposal that is work in
        # progress, no email job is created.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.WORK_IN_PROGRESS)
        reviewer = self.factory.makePerson()
        pop_notifications()
        with person_logged_in(bmp.registrant):
            bmp.nominateReviewer(reviewer, bmp.registrant, None)
        # No email is sent.
        sent_mail = pop_notifications()
        self.assertEqual([], sent_mail)
        # No job created.
        job_count = self.getReviewEmailJobs(bmp).count()
        self.assertEqual(0, job_count)

    def test_nominateReview_creates_job(self):
        # When a reviewer is nominated, a job is created to send out the
        # review request email.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        reviewer = self.factory.makePerson()
        pop_notifications()
        with person_logged_in(bmp.registrant):
            bmp.nominateReviewer(reviewer, bmp.registrant, None)
        # No email is sent.
        sent_mail = pop_notifications()
        self.assertEqual([], sent_mail)
        # A job is created.
        review_request_job = self.getReviewNotificationEmail(bmp)
        self.assertEqual(bmp, review_request_job.branch_merge_proposal)
        self.assertEqual(reviewer, review_request_job.reviewer)
        self.assertEqual(bmp.registrant, review_request_job.requester)

    def test_nominateReview_email_content(self):
        # The email that is sent contains the description of the proposal, and
        # a link to the proposal.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        reviewer = self.factory.makePerson()
        with person_logged_in(bmp.registrant):
            bmp.description = 'This branch is awesome.'
            bmp.nominateReviewer(reviewer, bmp.registrant, None)
        review_request_job = self.getReviewNotificationEmail(bmp)
        review_request_job.run()
        [sent_mail] = pop_notifications()
        expected = dedent("""\
            You have been requested to review the proposed merge of"""
            """ %(source)s into %(target)s.

            For more details, see:
            %(bmp)s

            This branch is awesome.

            --\x20
            %(bmp)s
            You are requested to review the proposed merge of %(source)s"""
            """ into %(target)s.
            """ % {
                'source': bmp.source_branch.bzr_identity,
                'target': bmp.target_branch.bzr_identity,
                'bmp': canonical_url(bmp)})
        self.assertEqual(expected, sent_mail.get_payload(decode=True))

    def test_nominateReview_emails_team_address(self):
        # If a review request is made for a team, the members of the team are
        # sent an email.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        eric = self.factory.makePerson(
            displayname='Eric the Viking', email='eric@vikings.example.com')
        black_beard = self.factory.makePerson(
            displayname='Black Beard', email='black@pirates.example.com')
        review_team = self.factory.makeTeam(owner=eric, members=[black_beard])
        pop_notifications()
        with person_logged_in(bmp.registrant):
            bmp.nominateReviewer(review_team, bmp.registrant, None)
        review_request_job = self.getReviewNotificationEmail(bmp)
        review_request_job.run()
        sent_mail = pop_notifications()
        self.assertEqual(
            ['Black Beard <black@pirates.example.com>',
             'Eric the Viking <eric@vikings.example.com>'],
            sorted(mail['to'] for mail in sent_mail))

    def test_requestReviewWithPrivateEmail(self):
        # We can request a review, even when one of the parties involved has a
        # private email address.
        bmp = self.factory.makeBranchMergeProposal(
            set_state=BranchMergeProposalStatus.NEEDS_REVIEW)
        candidate = self.factory.makePerson(hide_email_addresses=True)
        # Request a review and prepare the mailer.
        with person_logged_in(bmp.registrant):
            bmp.nominateReviewer(candidate, bmp.registrant, None)
        # Send the mail.
        review_request_job = self.getReviewNotificationEmail(bmp)
        review_request_job.run()
        mails = pop_notifications()
        self.assertEqual(1, len(mails))
        candidate = removeSecurityProxy(candidate)
        expected_email = '%s <%s>' % (
            candidate.displayname, candidate.preferredemail.email)
        self.assertEmailHeadersEqual(expected_email, mails[0]['To'])
