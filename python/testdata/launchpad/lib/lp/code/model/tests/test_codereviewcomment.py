# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for CodeReviewComment"""

from textwrap import dedent

from lp.code.enums import CodeReviewVote
from lp.code.event.branchmergeproposal import NewCodeReviewCommentEvent
from lp.code.model.codereviewcomment import quote_text_as_email
from lp.services.messages.model.message import MessageSet
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class TestCodeReviewComment(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, 'admin@canonical.com')
        source = self.factory.makeProductBranch(title='source-branch')
        target = self.factory.makeProductBranch(
            product=source.product, title='target-branch')
        self.bmp = source.addLandingTarget(source.owner, target)
        self.submitter = self.factory.makePerson()
        self.reviewer = self.factory.makePerson()
        self.bmp2 = self.factory.makeBranchMergeProposal()

    def test_createRootComment(self):
        comment = self.bmp.createComment(
            self.submitter, 'Message subject', 'Message content')
        self.assertEqual(None, comment.vote)
        self.assertEqual(None, comment.vote_tag)
        self.assertEqual(self.submitter, comment.message.owner)
        self.assertEqual('Message subject', comment.message.subject)
        self.assertEqual('Message content', comment.message.chunks[0].content)

    def test_createRootCommentNoSubject(self):
        comment = self.bmp.createComment(
            self.submitter, None, 'Message content')
        self.assertEqual(None, comment.vote)
        self.assertEqual(None, comment.vote_tag)
        self.assertEqual(self.submitter, comment.message.owner)
        self.assertEqual(
            'Re: [Merge] %s into %s' % (
                self.bmp.source_branch.bzr_identity,
                self.bmp.target_branch.bzr_identity), comment.message.subject)
        self.assertEqual('Message content', comment.message.chunks[0].content)

    def test_createReplyComment(self):
        comment = self.bmp.createComment(
            self.submitter, 'Message subject', 'Message content')
        reply = self.bmp.createComment(
            self.reviewer, 'Reply subject', 'Reply content',
            CodeReviewVote.ABSTAIN, 'My tag', comment)
        self.assertEqual(comment.message.id, reply.message.parent.id)
        self.assertEqual(comment.message, reply.message.parent)
        self.assertEqual('Reply subject', reply.message.subject)
        self.assertEqual('Reply content', reply.message.chunks[0].content)
        self.assertEqual(CodeReviewVote.ABSTAIN, reply.vote)
        self.assertEqual('my tag', reply.vote_tag)

    def test_createReplyCommentNoSubject(self):
        comment = self.bmp.createComment(
            self.submitter, 'Message subject', 'Message content')
        reply = self.bmp.createComment(
            self.reviewer, subject=None, parent=comment)
        self.assertEqual('Re: Message subject', reply.message.subject)

    def test_createReplyCommentNoSubjectExistingRe(self):
        comment = self.bmp.createComment(
            self.submitter, 'Re: Message subject', 'Message content')
        reply = self.bmp.createComment(
            self.reviewer, subject=None, parent=comment)
        self.assertEqual('Re: Message subject', reply.message.subject)

    def test_createNoParentComment(self):
        self.bmp.createComment(
            self.submitter, 'Message subject', 'Message content')
        new_comment = self.bmp.createComment(
            self.reviewer, 'New subject', 'New content',
            CodeReviewVote.ABSTAIN)
        self.assertEqual(None, new_comment.message.parent)

    def test_replyWithWrongMergeProposal(self):
        comment = self.bmp.createComment(
            self.submitter, 'Message subject', 'Message content')
        self.assertRaises(AssertionError, self.bmp2.createComment,
                          self.reviewer, 'Reply subject', 'Reply content',
                          CodeReviewVote.ABSTAIN, 'My tag', comment)

    def test_createCommentFromMessage(self):
        """Creating a CodeReviewComment from a message works."""
        message = self.factory.makeMessage(owner=self.submitter)
        comment = self.bmp.createCommentFromMessage(
            message, None, None, original_email=None, _validate=False)
        self.assertEqual(message, comment.message)

    def test_createCommentFromMessageNotifies(self):
        """Creating a CodeReviewComment should trigger a notification."""
        message = self.factory.makeMessage()
        self.assertNotifies(
            NewCodeReviewCommentEvent, self.bmp.createCommentFromMessage,
            message, None, None, original_email=None, _validate=False)


class TestCodeReviewCommentGetAttachments(TestCaseWithFactory):
    """Test the getAttachments method of code review comments."""

    # We need the librarian for storing the messages.
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, 'admin@canonical.com')
        self.bmp = self.factory.makeBranchMergeProposal()

    def test_getAttachments_no_attachments(self):
        # If there are no attachments, the getAttachments should return two
        # empty lists.
        comment = self.bmp.createComment(
            self.bmp.registrant, 'Subject', content='Some content')
        self.assertEqual(([], []), comment.getAttachments())

    def _makeCommentFromEmailWithAttachment(self, filename, content_type):
        # Make an email message with an attachment, and create a code
        # review comment from it.
        msg = self.factory.makeEmailMessage(
            body='This is the body of the email.',
            attachments=[
                (filename, content_type, 'Attachment body')])
        message = MessageSet().fromEmail(msg.as_string())
        return self.bmp.createCommentFromMessage(message, None, None, msg)

    def test_getAttachments_text_plain_are_displayed(self):
        # text/plain attachments are displayed.
        comment = self._makeCommentFromEmailWithAttachment(
            'some.txt', 'text/plain')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([attachment.blob], []), comment.getAttachments())

    def test_getAttachments_text_xdiff_are_displayed(self):
        # text/x-diff attachments are displayed.
        comment = self._makeCommentFromEmailWithAttachment(
            'some.txt', 'text/x-diff')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([attachment.blob], []), comment.getAttachments())

    def test_getAttachments_text_xpatch_are_displayed(self):
        # text/x-patch attachments are displayed.
        comment = self._makeCommentFromEmailWithAttachment(
            'some.txt', 'text/x-patch')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([attachment.blob], []), comment.getAttachments())

    def test_getAttachments_others(self):
        # Attachments with other content types are not considered display
        # attachments.
        comment = self._makeCommentFromEmailWithAttachment(
            'some.txt', 'application/octet-stream')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([], [attachment.blob]), comment.getAttachments())

        comment = self._makeCommentFromEmailWithAttachment(
            'pic.jpg', 'image/jpeg')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([], [attachment.blob]), comment.getAttachments())

    def test_getAttachments_diff_or_patch_filename_overrides(self):
        # If the filename ends with .diff or .patch, then we consider these
        # attachments good even if attached with the wrong content type.
        comment = self._makeCommentFromEmailWithAttachment(
            'some.diff', 'application/octet-stream')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([attachment.blob], []), comment.getAttachments())

        comment = self._makeCommentFromEmailWithAttachment(
            'some.patch', 'application/octet-stream')
        email_body, attachment = comment.message.chunks
        self.assertEqual(([attachment.blob], []), comment.getAttachments())


class TestQuoteTextAsEmail(TestCase):
    """Test the quote_text_as_email helper method."""

    def test_empty_string(self):
        # Nothing just gives us an empty string.
        self.assertEqual('', quote_text_as_email(''))

    def test_none_string(self):
        # If None is passed the quoted text is an empty string.
        self.assertEqual('', quote_text_as_email(None))

    def test_whitespace_string(self):
        # Just whitespace gives us an empty string.
        self.assertEqual('', quote_text_as_email('  \t '))

    def test_long_string(self):
        # Long lines are wrapped.
        long_line = ('This is a very long line that needs to be wrapped '
                     'onto more than one line given a short length.')
        self.assertEqual(
            dedent("""\
                > This is a very long line that needs to
                > be wrapped onto more than one line
                > given a short length."""),
            quote_text_as_email(long_line, 40))

    def test_code_sample(self):
        # Initial whitespace is not trimmed.
        code = """\
    def test_whitespace_string(self):
        # Nothing just gives us the prefix.
        self.assertEqual('', wrap_text('  \t '))"""
        self.assertEqual(
            dedent("""\
                >     def test_whitespace_string(self):
                >         # Nothing just gives us the prefix.
                >         self.assertEqual('', wrap_text('         '))"""),
            quote_text_as_email(code, 60))

    def test_empty_line_mid_string(self):
        # Lines in the middle of the string are quoted too.
        value = dedent("""\
            This is the first line.

            This is the second line.
            """)
        expected = dedent("""\
            > This is the first line.
            > 
            > This is the second line.""")
        self.assertEqual(expected, quote_text_as_email(value))

    def test_trailing_whitespace(self):
        # Trailing whitespace is removed.
        self.assertEqual('>   foo', quote_text_as_email('  foo  \n '))
