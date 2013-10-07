# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test CodeReviewComment emailing functionality."""


import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.enums import (
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    CodeReviewVote,
    )
from lp.code.mail.codereviewcomment import CodeReviewCommentMailer
from lp.services.mail.sendmail import format_address
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp import canonical_url
from lp.testing import (
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestCodeReviewComment(TestCaseWithFactory):
    """Test that comments are generated as expected."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        """Prepare test fixtures."""
        TestCaseWithFactory.setUp(self, user='test@canonical.com')

    def makeCommentAndSubscriber(self, notification_level=None,
                                 body=None, as_reply=False, vote=None,
                                 vote_tag=None, subject=None):
        """Return a comment and a subscriber."""
        sender = self.factory.makePerson(
            displayname='Sender', email='sender@example.com')
        comment = self.factory.makeCodeReviewComment(
            sender, body=body, vote=vote, vote_tag=vote_tag, subject=subject)
        if as_reply:
            comment = self.factory.makeCodeReviewComment(
                sender, body=body, parent=comment, subject=subject)
        subscriber = self.factory.makePerson(
            displayname='Subscriber', email='subscriber@example.com')
        if notification_level is None:
            notification_level = CodeReviewNotificationLevel.FULL
        comment.branch_merge_proposal.source_branch.subscribe(
            subscriber, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            notification_level, subscriber)
        # Email is not sent on construction, so fake a root message id on the
        # merge proposal.
        login_person(comment.branch_merge_proposal.registrant)
        comment.branch_merge_proposal.root_message_id = 'fake-id'
        # Log our test user back in.
        login('test@canonical.com')
        return comment, subscriber

    def makeMailer(self, body=None, as_reply=False, vote=None, vote_tag=None):
        """Return a CodeReviewCommentMailer and the sole subscriber."""
        comment, subscriber = self.makeCommentAndSubscriber(
            body=body, as_reply=as_reply, vote=vote, vote_tag=vote_tag)
        return CodeReviewCommentMailer.forCreation(comment), subscriber

    def assertRecipientsMatches(self, recipients, mailer):
        """Assert that `mailer` will send to the people in `recipients`."""
        persons = zip(*(mailer._recipients.getRecipientPersons()))[1]
        self.assertEqual(set(recipients), set(persons))

    def test_forCreation(self):
        """Ensure that forCreation produces a mailer with expected values."""
        comment, subscriber = self.makeCommentAndSubscriber()
        mailer = CodeReviewCommentMailer.forCreation(comment)
        self.assertEqual(comment.message.subject,
                         mailer._subject_template)
        bmp = comment.branch_merge_proposal
        # The branch owners are implicitly subscribed to their branches
        # when the branches are created.
        self.assertRecipientsMatches(
            [subscriber, bmp.source_branch.owner, bmp.target_branch.owner],
            mailer)
        self.assertEqual(
            comment.branch_merge_proposal, mailer.merge_proposal)
        sender = comment.message.owner
        sender_address = format_address(sender.displayname,
            sender.preferredemail.email)
        self.assertEqual(sender_address, mailer.from_address)
        self.assertEqual(comment, mailer.code_review_comment)

    def test_forCreationStatusSubscriber(self):
        """Ensure that subscriptions with STATUS aren't used."""
        comment, subscriber = self.makeCommentAndSubscriber(
            CodeReviewNotificationLevel.STATUS)
        mailer = CodeReviewCommentMailer.forCreation(comment)
        bmp = comment.branch_merge_proposal
        # The branch owners are implicitly subscribed to their branches
        # when the branches are created.
        self.assertRecipientsMatches(
            [bmp.source_branch.owner, bmp.target_branch.owner], mailer)

    def test_forCreationStatusNoEmail(self):
        """Ensure that subscriptions with NOEMAIL aren't used."""
        comment, subscriber = self.makeCommentAndSubscriber(
            CodeReviewNotificationLevel.NOEMAIL)
        mailer = CodeReviewCommentMailer.forCreation(comment)
        bmp = comment.branch_merge_proposal
        # The branch owners are implicitly subscribed to their branches
        # when the branches are created.
        self.assertRecipientsMatches(
            [bmp.source_branch.owner, bmp.target_branch.owner], mailer)

    def test_subjectWithStringExpansions(self):
        # The mailer should not attempt to expand templates in the subject.
        comment, subscriber = self.makeCommentAndSubscriber(
            subject='A %(carefully)s constructed subject')
        mailer = CodeReviewCommentMailer.forCreation(comment)
        self.assertEqual(
            'A %(carefully)s constructed subject',
            mailer._getSubject(email=None, recipient=subscriber))

    def test_getReplyAddress(self):
        """Ensure that the reply-to address is reasonable."""
        mailer, subscriber = self.makeMailer()
        merge_proposal = mailer.code_review_comment.branch_merge_proposal
        expected = 'mp+%d@code.launchpad.dev' % merge_proposal.id
        self.assertEqual(expected, mailer._getReplyToAddress())

    def test_generateEmail(self):
        """Ensure mailer's generateEmail method produces expected values."""
        mailer, subscriber = self.makeMailer(as_reply=True)
        ctrl = mailer.generateEmail(
            subscriber.preferredemail.email, subscriber)
        message = mailer.code_review_comment.message
        self.assertEqual(ctrl.subject, message.subject)
        self.assertEqual(ctrl.body.splitlines()[:-3],
                         message.text_contents.splitlines())
        source_branch = mailer.merge_proposal.source_branch
        branch_name = source_branch.bzr_identity
        self.assertEqual(
            ctrl.body.splitlines()[-3:], ['-- ',
            canonical_url(mailer.merge_proposal),
            'You are subscribed to branch %s.' % branch_name])
        rationale = mailer._recipients.getReason('subscriber@example.com')[1]
        expected = {'X-Launchpad-Branch': source_branch.unique_name,
                    'X-Launchpad-Message-Rationale': rationale,
                    'X-Launchpad-Notification-Type': 'code-review',
                    'X-Launchpad-Project': source_branch.product.name,
                    'Message-Id': message.rfc822msgid,
                    'Reply-To': mailer._getReplyToAddress(),
                    'In-Reply-To': message.parent.rfc822msgid}
        for header, value in expected.items():
            self.assertEqual(value, ctrl.headers[header], header)
        self.assertEqual(expected, ctrl.headers)

    def test_useRootMessageId(self):
        """Ensure mailer's generateEmail method produces expected values."""
        mailer, subscriber = self.makeMailer(as_reply=False)
        ctrl = mailer.generateEmail(
            subscriber.preferredemail.email, subscriber)
        self.assertEqual(mailer.merge_proposal.root_message_id,
                         ctrl.headers['In-Reply-To'])

    def test_nonReplyCommentUsesRootMessageId(self):
        """Ensure mailer's generateEmail method produces expected values."""
        comment, subscriber = self.makeCommentAndSubscriber()
        second_comment = self.factory.makeCodeReviewComment(
            merge_proposal=comment.branch_merge_proposal)
        mailer = CodeReviewCommentMailer.forCreation(second_comment)
        ctrl = mailer.generateEmail(
            subscriber.preferredemail.email, subscriber)
        self.assertEqual(comment.branch_merge_proposal.root_message_id,
                         ctrl.headers['In-Reply-To'])

    def test_appendToFooter(self):
        """If there is an existing footer, we append to it."""
        mailer, subscriber = self.makeMailer(
            body='Hi!\n'
            '-- \n'
            'I am a wacky guy.\n')
        branch_name = mailer.merge_proposal.source_branch.bzr_identity
        body = mailer._getBody(subscriber.preferredemail.email, subscriber)
        self.assertEqual(body.splitlines()[1:],
            ['-- ', 'I am a wacky guy.', '',
             canonical_url(mailer.merge_proposal),
             'You are subscribed to branch %s.' % branch_name])

    def test_generateEmailWithVote(self):
        """Ensure that votes are displayed."""
        mailer, subscriber = self.makeMailer(
            vote=CodeReviewVote.APPROVE)
        ctrl = mailer.generateEmail(
            subscriber.preferredemail.email, subscriber)
        self.assertEqual('Review: Approve', ctrl.body.splitlines()[0])
        self.assertEqual(ctrl.body.splitlines()[2:-3],
                         mailer.message.text_contents.splitlines())

    def test_generateEmailWithVoteAndTag(self):
        """Ensure that vote tags are displayed."""
        mailer, subscriber = self.makeMailer(
            vote=CodeReviewVote.APPROVE, vote_tag='DBTAG')
        ctrl = mailer.generateEmail(
            subscriber.preferredemail.email, subscriber)
        self.assertEqual('Review: Approve dbtag', ctrl.body.splitlines()[0])
        self.assertEqual(ctrl.body.splitlines()[2:-3],
                         mailer.message.text_contents.splitlines())

    def makeComment(self, email_message):
        message = getUtility(IMessageSet).fromEmail(email_message.as_string())
        bmp = self.factory.makeBranchMergeProposal()
        comment = bmp.createCommentFromMessage(
            message, None, None, email_message)
        # We need to make sure the Librarian is up-to-date, so we commit.
        transaction.commit()
        return comment

    def test_mailer_attachments(self):
        # Ensure that the attachments are attached.
        # Only attachments that we would show in the web ui are attached,
        # so the diff should be attached, and the jpeg image not.
        msg = self.factory.makeEmailMessage(
            body='This is the body of the email.',
            attachments=[
                ('inc.diff', 'text/x-diff', 'This is a diff.'),
                ('pic.jpg', 'image/jpeg', 'Binary data')])
        comment = self.makeComment(msg)
        mailer = CodeReviewCommentMailer.forCreation(comment)
        # The attachments of the mailer should have only the diff.
        [outgoing_attachment] = mailer.attachments
        self.assertEqual('inc.diff', outgoing_attachment[1])
        self.assertEqual('text/x-diff', outgoing_attachment[2])
        # The attachments are attached to the outgoing message.
        person = comment.branch_merge_proposal.target_branch.owner
        message = mailer.generateEmail(
            person.preferredemail.email, person).makeMessage()
        self.assertTrue(message.is_multipart())
        attachment = message.get_payload()[1]
        self.assertEqual('inc.diff', attachment.get_filename())
        self.assertEqual('text/x-diff', attachment['content-type'])

    def test_encoded_attachments(self):
        msg = self.factory.makeEmailMessage(
            body='This is the body of the email.',
            attachments=[('inc.diff', 'text/x-diff', 'This is a diff.')],
            encode_attachments=True)
        comment = self.makeComment(msg)
        mailer = CodeReviewCommentMailer.forCreation(comment)
        person = comment.branch_merge_proposal.target_branch.owner
        message = mailer.generateEmail(
            person.preferredemail.email, person).makeMessage()
        attachment = message.get_payload()[1]
        self.assertEqual(
            'This is a diff.', attachment.get_payload(decode=True))

    def makeCommentAndParticipants(self):
        """Create a merge proposal and comment.

        Proposal registered by "Proposer" and comment added by "Commenter".
        """
        proposer = self.factory.makePerson(
            email='proposer@email.com', displayname='Proposer')
        bmp = self.factory.makeBranchMergeProposal(registrant=proposer)
        commenter = self.factory.makePerson(
            email='commenter@email.com', displayname='Commenter')
        bmp.source_branch.subscribe(commenter,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL, commenter)
        comment = bmp.createComment(commenter, 'hello')
        return comment

    def test_getToAddresses_no_parent(self):
        """To address for a comment with no parent should be the proposer."""
        comment = self.makeCommentAndParticipants()
        mailer = CodeReviewCommentMailer.forCreation(comment)
        to = mailer._getToAddresses(
            comment.message.owner, 'comment@gmail.com')
        self.assertEqual(['Proposer <proposer@email.com>'], to)
        to = mailer._getToAddresses(
            comment.branch_merge_proposal.registrant, 'propose@gmail.com')
        self.assertEqual(['Proposer <propose@gmail.com>'], to)

    def test_generateEmail_addresses(self):
        """The to_addrs but not envelope_to should follow getToAddress.

        We provide false to addresses to make filters happier, but this
        should not affect the actual recipient list.
        """
        comment = self.makeCommentAndParticipants()
        mailer = CodeReviewCommentMailer.forCreation(comment)
        ctrl = mailer.generateEmail('commenter@email.com',
                                    comment.message.owner)
        self.assertEqual(['Proposer <proposer@email.com>'], ctrl.to_addrs)
        self.assertEqual(['commenter@email.com'], ctrl.envelope_to)

    def test_getToAddresses_with_parent(self):
        """To address for a reply should be the parent comment author."""
        comment = self.makeCommentAndParticipants()
        second_commenter = self.factory.makePerson(
            email='commenter2@email.com', displayname='Commenter2')
        reply = comment.branch_merge_proposal.createComment(
            second_commenter, 'hello2', parent=comment)
        mailer = CodeReviewCommentMailer.forCreation(reply)
        to = mailer._getToAddresses(second_commenter, 'comment2@gmail.com')
        self.assertEqual(['Commenter <commenter@email.com>'], to)
        to = mailer._getToAddresses(
            comment.message.owner, 'comment@gmail.com')
        self.assertEqual(['Commenter <comment@gmail.com>'], to)

    def test_getToAddresses_with_hidden_address(self):
        """Don't show address if Person.hide_email_addresses."""
        comment = self.makeCommentAndParticipants()
        removeSecurityProxy(comment.message.owner).hide_email_addresses = True
        second_commenter = self.factory.makePerson(
            email='commenter2@email.com', displayname='Commenter2')
        reply = comment.branch_merge_proposal.createComment(
            second_commenter, 'hello2', parent=comment)
        mailer = CodeReviewCommentMailer.forCreation(reply)
        to = mailer._getToAddresses(second_commenter, 'comment2@gmail.com')
        self.assertEqual([mailer.merge_proposal.address], to)
