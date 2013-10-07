# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the lpsize monekypatches"""

from __future__ import with_statement

__metaclass__ = type
__all__ = []


from email.mime.application import MIMEApplication

from Mailman import Errors
from Mailman.Handlers import LPSize
from zope.security.proxy import removeSecurityProxy

from lp.services.config import config
from lp.services.mailman.tests import MailmanTestCase
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class TestLPSizeTestCase(MailmanTestCase):
    """Test LPSize.

    Mailman process() methods quietly return. They may set msg_data key-values
    or raise an error to end processing. These tests often check for errors,
    but that does not mean there is an error condition, it only means message
    processing has reached a final decision. Messages that do not cause a
    final decision pass through, and the process() methods ends without a
    return.
    """

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestLPSizeTestCase, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)
        self.subscriber_email = removeSecurityProxy(
            self.team.teamowner.preferredemail).email

    def tearDown(self):
        super(TestLPSizeTestCase, self).tearDown()
        self.cleanMailmanList(self.mm_list)

    def test_process_size_under_soft_limit(self):
        # Any message under 40kb is sent to the list.
        attachment = MIMEApplication(
            '\n'.join(['x' * 20] * 1000), 'octet-stream')
        message = self.makeMailmanMessage(
            self.mm_list, self.subscriber_email, 'subject', 'content',
            attachment=attachment)
        msg_data = {}
        silence = LPSize.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)

    def test_process_size_over_soft_limit_held(self):
        # Messages over 40kb held for moderation.
        self.assertEqual(40000, config.mailman.soft_max_size)
        attachment = MIMEApplication(
            '\n'.join(['x' * 40] * 1000), 'octet-stream')
        message = self.makeMailmanMessage(
            self.mm_list, self.subscriber_email, 'subject', 'content',
            attachment=attachment)
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.HoldMessage, LPSize.process, *args)
        self.assertEqual(1, self.mailing_list.getReviewableMessages().count())

    def test_process_size_over_hard_limit_discarded(self):
        # Messages over 1MB are discarded.
        self.assertEqual(1000000, config.mailman.hard_max_size)
        attachment = MIMEApplication(
            '\n'.join(['x' * 1000] * 1000), 'octet-stream')
        message = self.makeMailmanMessage(
            self.mm_list, self.subscriber_email, 'subject', 'content',
            attachment=attachment)
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.DiscardMessage, LPSize.process, *args)
        self.assertEqual(0, self.mailing_list.getReviewableMessages().count())


class TestTruncatedMessage(MailmanTestCase):
    """Test truncated_message helper."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTruncatedMessage, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)
        self.subscriber_email = removeSecurityProxy(
            self.team.teamowner.preferredemail).email

    def test_attchments_are_removed(self):
        # Plain-text and multipart are preserved, everything else is removed.
        attachment = MIMEApplication('binary gibberish', 'octet-stream')
        message = self.makeMailmanMessage(
            self.mm_list, self.subscriber_email, 'subject', 'content',
            attachment=attachment)
        moderated_message = LPSize.truncated_message(message)
        parts = [part for part in moderated_message.walk()]
        types = [part.get_content_type() for part in parts]
        self.assertEqual(['multipart/mixed', 'text/plain'], types)

    def test_small_text_is_preserved(self):
        # Text parts below the limit are unchanged.
        message = self.makeMailmanMessage(
            self.mm_list, self.subscriber_email, 'subject', 'content')
        moderated_message = LPSize.truncated_message(message, limit=1000)
        parts = [part for part in moderated_message.walk()]
        types = [part.get_content_type() for part in parts]
        self.assertEqual(['multipart/mixed', 'text/plain'], types)
        self.assertEqual('content', parts[1].get_payload())

    def test_large_text_is_truncated(self):
        # Text parts above the limit are truncated.
        message = self.makeMailmanMessage(
            self.mm_list, self.subscriber_email, 'subject', 'content excess')
        moderated_message = LPSize.truncated_message(message, limit=7)
        parts = [part for part in moderated_message.walk()]
        types = [part.get_content_type() for part in parts]
        self.assertEqual(['multipart/mixed', 'text/plain'], types)
        self.assertEqual(
            'content\n[truncated for moderation]', parts[1].get_payload())
