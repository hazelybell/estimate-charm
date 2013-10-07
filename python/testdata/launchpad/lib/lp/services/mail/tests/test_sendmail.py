# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite
import email.header
from email.Message import Message
import unittest

from zope.interface import implements
from zope.sendmail.interfaces import IMailDelivery

from lp.services.encoding import is_ascii_only
from lp.services.mail import sendmail
from lp.services.mail.sendmail import MailController
from lp.testing import TestCase
from lp.testing.fixture import (
    CaptureTimeline,
    ZopeUtilityFixture,
    )


class TestMailController(TestCase):

    def test_constructor(self):
        """Test the default construction behavior.

        Defaults should be empty.  The 'to' should be converted to a list.
        """
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', 'body')
        self.assertEqual('from@example.com', ctrl.from_addr)
        self.assertEqual(['to@example.com'], ctrl.to_addrs)
        self.assertEqual('subject', ctrl.subject)
        self.assertEqual({}, ctrl.headers)
        self.assertEqual('body', ctrl.body)
        self.assertEqual([], ctrl.attachments)

    def test_constructor2(self):
        """Test the explicit construction behavior.

        Since to is a list, it is not converted into a list.
        """
        ctrl = MailController(
            'from@example.com', ['to1@example.com', 'to2@example.com'],
            'subject', 'body', {'key': 'value'})
        self.assertEqual(
            ['to1@example.com', 'to2@example.com'], ctrl.to_addrs)
        self.assertEqual({'key': 'value'}, ctrl.headers)
        self.assertEqual('body', ctrl.body)
        self.assertEqual([], ctrl.attachments)

    def test_long_subject_wrapping(self):
        # Python2.6 prefixes continuation lines with '\t', 2.7 uses a single
        # space instead. Catch any change in this behaviour to avoid having to
        # redo the full diagnosis in the future.
        before = '0123456789' * 6 + 'before'
        after = 'after' + '0123456789'
        hdr = email.header.Header(before + ' ' + after, header_name='Subject')
        encoded = hdr.encode()
        self.assertTrue(('before\n after' in encoded)
                        or ('before\n\t after' in encoded),
                        'Header.encode() changed continuation lines again')

    def test_addAttachment(self):
        """addAttachment should add a part to the list of attachments."""
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', 'body')
        ctrl.addAttachment('content1')
        attachment = ctrl.attachments[0]
        self.assertEqual(
            'application/octet-stream', attachment['Content-Type'])
        self.assertEqual(
            'attachment', attachment['Content-Disposition'])
        self.assertEqual(
            'content1', attachment.get_payload(decode=True))
        ctrl.addAttachment(
            'content2', 'text/plain', inline=True, filename='name1')
        attachment = ctrl.attachments[1]
        self.assertEqual(
            'text/plain', attachment['Content-Type'])
        self.assertEqual(
            'inline; filename="name1"', attachment['Content-Disposition'])
        self.assertEqual(
            'content2', attachment.get_payload(decode=True))
        ctrl.addAttachment(
            'content2', 'text/plain', inline=True, filename='name1')

    def test_MakeMessageSpecialChars(self):
        """A message should have its to and from addrs converted to ascii."""
        to_addr = u'\u1100to@example.com'
        from_addr = u'\u1100from@example.com'
        ctrl = MailController(from_addr, to_addr, 'subject', 'body')
        message = ctrl.makeMessage()
        self.assertEqual('=?utf-8?b?4YSAZnJvbUBleGFtcGxlLmNvbQ==?=',
            message['From'])
        self.assertEqual('=?utf-8?b?4YSAdG9AZXhhbXBsZS5jb20=?=',
            message['To'])
        self.assertEqual('subject', message['Subject'])
        self.assertEqual('body', message.get_payload(decode=True))

    def test_MakeMessage_long_address(self):
        # Long email addresses are not wrapped if very long.  These are due to
        # the paranoid checks that are in place to make sure that there are no
        # carriage returns in the to or from email addresses.
        to_addr = (
            'Launchpad Community Help Rotation team '
            '<long.email.address+devnull@example.com>')
        from_addr = (
            'Some Random User With Many Public Names '
            '<some.random.user.with.many.public.names@example.com')
        ctrl = MailController(from_addr, to_addr, 'subject', 'body')
        message = ctrl.makeMessage()
        self.assertEqual(from_addr, message['From'])
        self.assertEqual(to_addr, message['To'])

    def test_MakeMessage_no_attachment(self):
        """A message without an attachment should have a single body."""
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', 'body')
        message = ctrl.makeMessage()
        self.assertEqual('from@example.com', message['From'])
        self.assertEqual('to@example.com', message['To'])
        self.assertEqual('subject', message['Subject'])
        self.assertEqual('body', message.get_payload(decode=True))

    def test_MakeMessage_unicode_body(self):
        # A message without an attachment with a unicode body gets sent as
        # UTF-8 encoded MIME text, and the message as a whole can be flattened
        # to a string with Unicode errors.
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', u'Bj\xf6rn')
        message = ctrl.makeMessage()
        # Make sure that the message can be flattened to a string as sendmail
        # does without raising a UnicodeEncodeError.
        message.as_string()
        self.assertEqual('Bj\xc3\xb6rn', message.get_payload(decode=True))

    def test_MakeMessage_unicode_body_with_attachment(self):
        # A message with an attachment with a unicode body gets sent as
        # UTF-8 encoded MIME text, and the message as a whole can be flattened
        # to a string with Unicode errors.
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', u'Bj\xf6rn')
        ctrl.addAttachment('attach')
        message = ctrl.makeMessage()
        # Make sure that the message can be flattened to a string as sendmail
        # does without raising a UnicodeEncodeError.
        message.as_string()
        body, attachment = message.get_payload()
        self.assertEqual('Bj\xc3\xb6rn', body.get_payload(decode=True))
        self.assertTrue(is_ascii_only(message.as_string()))

    def test_MakeMessage_with_binary_attachment(self):
        """Message should still encode as ascii with non-ascii attachments."""
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', u'Body')
        ctrl.addAttachment('\x00\xffattach')
        message = ctrl.makeMessage()
        self.assertTrue(
            is_ascii_only(message.as_string()), "Non-ascii message string.")

    def test_MakeMessage_with_non_binary_attachment(self):
        """Simple ascii attachments should not be encoded."""
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', u'Body')
        ctrl.addAttachment('Hello, I am ascii')
        message = ctrl.makeMessage()
        body, attachment = message.get_payload()
        self.assertEqual(
            attachment.get_payload(), attachment.get_payload(decode=True))

    def test_MakeMessage_with_attachment(self):
        """A message with an attachment should be multipart."""
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', 'body')
        ctrl.addAttachment('attach')
        message = ctrl.makeMessage()
        self.assertEqual('from@example.com', message['From'])
        self.assertEqual('to@example.com', message['To'])
        self.assertEqual('subject', message['Subject'])
        body, attachment = message.get_payload()
        self.assertEqual('body', body.get_payload(decode=True))
        self.assertEqual('attach', attachment.get_payload(decode=True))
        self.assertEqual(
            'application/octet-stream', attachment['Content-Type'])
        self.assertEqual('attachment', attachment['Content-Disposition'])

    def test_MakeMessage_with_specific_attachment(self):
        """Explicit attachment params should be obeyed."""
        ctrl = MailController(
            'from@example.com', 'to@example.com', 'subject', 'body')
        ctrl.addAttachment(
            'attach', 'text/plain', inline=True, filename='README')
        message = ctrl.makeMessage()
        attachment = message.get_payload()[1]
        self.assertEqual('attach', attachment.get_payload(decode=True))
        self.assertEqual(
            'text/plain', attachment['Content-Type'])
        self.assertEqual(
            'inline; filename="README"', attachment['Content-Disposition'])

    def test_encodeOptimally_with_ascii_text(self):
        """Mostly-ascii attachments should be encoded as quoted-printable."""
        text = 'I went to the cafe today.\n\r'
        part = Message()
        part.set_payload(text)
        MailController.encodeOptimally(part, exact=False)
        self.assertEqual(part.get_payload(), part.get_payload(decode=True))
        self.assertIs(None, part['Content-Transfer-Encoding'])

    def test_encodeOptimally_with_7_bit_binary(self):
        """Mostly-ascii attachments should be encoded as quoted-printable."""
        text = 'I went to the cafe today.\n\r'
        part = Message()
        part.set_payload(text)
        MailController.encodeOptimally(part)
        self.assertEqual(text, part.get_payload(decode=True))
        self.assertEqual('I went to the cafe today.=0A=0D',
                         part.get_payload())
        self.assertEqual('quoted-printable',
                         part['Content-Transfer-Encoding'])

    def test_encodeOptimally_with_text(self):
        """Mostly-ascii attachments should be encoded as quoted-printable."""
        text = u'I went to the caf\u00e9 today.'.encode('utf-8')
        part = Message()
        part.set_payload(text)
        MailController.encodeOptimally(part)
        self.assertEqual(text, part.get_payload(decode=True))
        self.assertEqual('quoted-printable',
                         part['Content-Transfer-Encoding'])

    def test_encodeOptimally_with_binary(self):
        """Significantly non-ascii attachments should be base64-encoded."""
        bytes = '\x00\xff\x44\x55\xaa\x99'
        part = Message()
        part.set_payload(bytes)
        MailController.encodeOptimally(part)
        self.assertEqual(bytes, part.get_payload(decode=True))
        self.assertEqual('base64', part['Content-Transfer-Encoding'])

    def test_sendUsesRealTo(self):
        """MailController.envelope_to is provided as to_addrs."""
        ctrl = MailController('from@example.com', 'to@example.com', 'subject',
                              'body', envelope_to=['to@example.org'])
        sendmail_kwargs = {}

        def fake_sendmail(message, to_addrs=None, bulk=True):
            sendmail_kwargs.update(locals())
        real_sendmail = sendmail.sendmail
        sendmail.sendmail = fake_sendmail
        try:
            ctrl.send()
        finally:
            sendmail.sendmail = real_sendmail
        self.assertEqual('to@example.com', sendmail_kwargs['message']['To'])
        self.assertEqual(['to@example.org'], sendmail_kwargs['to_addrs'])

    def test_MailController_into_timeline(self):
        """sendmail records stuff in the timeline."""
        fake_mailer = RecordingMailer()
        self.useFixture(ZopeUtilityFixture(
            fake_mailer, IMailDelivery, 'Mail'))
        to_addresses = ['to1@example.com', 'to2@example.com']
        subject = self.getUniqueString('subject')
        with CaptureTimeline() as ctl:
            ctrl = MailController(
                'from@example.com', to_addresses,
                subject, 'body', {'key': 'value'})
            ctrl.send()
        self.assertEquals(fake_mailer.from_addr, 'bounces@canonical.com')
        self.assertEquals(fake_mailer.to_addr, to_addresses)
        self.checkTimelineHasOneMailAction(ctl.timeline, subject=subject)

    def test_sendmail_with_email_header(self):
        """Check the timeline is ok even if there is an email.Header.

        See https://bugs.launchpad.net/launchpad/+bug/885972
        """
        fake_mailer = RecordingMailer()
        self.useFixture(ZopeUtilityFixture(
            fake_mailer, IMailDelivery, 'Mail'))
        subject_str = self.getUniqueString('subject')
        subject_header = email.header.Header(subject_str)
        message = Message()
        message.add_header('From', 'bounces@canonical.com')
        message['Subject'] = subject_header
        message.add_header('To', 'dest@example.com')
        with CaptureTimeline() as ctl:
            sendmail.sendmail(message)
        self.assertEquals(fake_mailer.from_addr, 'bounces@canonical.com')
        self.assertEquals(fake_mailer.to_addr, ['dest@example.com'])
        self.checkTimelineHasOneMailAction(ctl.timeline, subject=subject_str)

    def checkTimelineHasOneMailAction(self, timeline, subject):
        actions = timeline.actions
        self.assertEquals(len(actions), 1)
        a0 = actions[0]
        self.assertEquals(a0.category, 'sendmail')
        self.assertEquals(a0.detail, subject)
        self.assertIsInstance(a0.detail, basestring)


class RecordingMailer(object):

    implements(IMailDelivery)

    def send(self, from_addr, to_addr, raw_message):
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.raw_message = raw_message


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(DocTestSuite('lp.services.mail.sendmail'))
    suite.addTests(unittest.TestLoader().loadTestsFromName(__name__))
    return suite
