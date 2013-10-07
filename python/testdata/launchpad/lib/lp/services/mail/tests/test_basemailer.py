# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Tests for the BaseMailer class."""


__metaclass__ = type

from smtplib import SMTPException

from lp.services.mail.basemailer import BaseMailer
from lp.services.mail.sendmail import MailController
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.mail_helpers import pop_notifications


class FakeSubscription:
    """Stub for use with these tests."""

    mail_header = 'pete'

    def getReason(self):
        return "Because"


class BaseMailerSubclass(BaseMailer):
    """Subclass of BaseMailer to avoid getting the body template."""

    def _getBody(self, email, recipient):
        return 'body'


class ToAddressesUpper(BaseMailerSubclass):
    """Subclass of BaseMailer providing an example getToAddresses."""

    def _getToAddresses(self, recipient, email):
        return email.upper()


class AttachmentMailer(BaseMailerSubclass):
    """Subclass the test mailer to add an attachment."""

    def _addAttachments(self, ctrl, email):
        ctrl.addAttachment('attachment1')
        ctrl.addAttachment('attachment2')


class RaisingMailController(MailController):
    """A mail controller that can raise errors."""

    def raiseOnSend(self):
        """Make send fail for the specified email address."""
        self.raise_on_send = True

    def send(self, bulk=True):
        if getattr(self, 'raise_on_send', False):
            raise SMTPException('boom')
        else:
            super(RaisingMailController, self).send(bulk)


class RaisingMailControllerFactory:
    """Pretends to be a class to make raising mail controllers."""

    def __init__(self, bad_email_addr, raise_count):
        self.bad_email_addr = bad_email_addr
        self.raise_count = raise_count

    def __call__(self, *args, **kwargs):
        ctrl = RaisingMailController(*args, **kwargs)
        if ((self.bad_email_addr in kwargs['envelope_to'])
            and self.raise_count):
            self.raise_count -= 1
            ctrl.raiseOnSend()
        return ctrl


class TestBaseMailer(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_generateEmail_sets_envelope_to(self):
        """BaseMailer.generateEmail sets MailController.envelope_to.

        The only item in the list is the supplied email address.
        """
        fake_to = self.factory.makePerson(email='to@example.com',
            displayname='Example To')
        recipients = {fake_to: FakeSubscription()}
        mailer = BaseMailerSubclass(
            'subject', None, recipients, 'from@example.com')
        ctrl = mailer.generateEmail('to@example.com', fake_to)
        self.assertEqual(['to@example.com'], ctrl.envelope_to)
        self.assertEqual(['Example To <to@example.com>'], ctrl.to_addrs)

    def test_generateEmail_uses_getToAddresses(self):
        """BaseMailer.generateEmail uses getToAddresses.

        We verify this by using a subclass that provides getToAddresses
        as a single-item list with the uppercased email address.
        """
        fake_to = self.factory.makePerson(email='to@example.com')
        recipients = {fake_to: FakeSubscription()}
        mailer = ToAddressesUpper(
            'subject', None, recipients, 'from@example.com')
        ctrl = mailer.generateEmail('to@example.com', fake_to)
        self.assertEqual(['TO@EXAMPLE.COM'], ctrl.to_addrs)

    def test_generateEmail_adds_attachments(self):
        # BaseMailer.generateEmail calls _addAttachments.
        fake_to = self.factory.makePerson(email='to@example.com')
        recipients = {fake_to: FakeSubscription()}
        mailer = AttachmentMailer(
            'subject', None, recipients, 'from@example.com')
        ctrl = mailer.generateEmail('to@example.com', fake_to)
        self.assertEqual(2, len(ctrl.attachments))

    def test_generateEmail_force_no_attachments(self):
        # If BaseMailer.generateEmail is called with
        # force_no_attachments=True then attachments are not added.
        fake_to = self.factory.makePerson(email='to@example.com')
        recipients = {fake_to: FakeSubscription()}
        mailer = AttachmentMailer(
            'subject', None, recipients, 'from@example.com')
        ctrl = mailer.generateEmail(
            'to@example.com', fake_to, force_no_attachments=True)
        self.assertEqual(1, len(ctrl.attachments))
        attachment = ctrl.attachments[0]
        self.assertEqual(
            'Excessively large attachments removed.',
            attachment.get_payload())
        self.assertEqual('text/plain', attachment['Content-Type'])
        self.assertEqual('inline', attachment['Content-Disposition'])

    def test_sendall_single_failure_doesnt_kill_all(self):
        # A failure to send to a particular email address doesn't stop sending
        # to others.
        recipients = {
            self.factory.makePerson(name='good', email='good@example.com'):
                FakeSubscription(),
            self.factory.makePerson(name='bad', email='bad@example.com'):
                FakeSubscription()}
        controller_factory = RaisingMailControllerFactory(
            'bad@example.com', 2)
        mailer = BaseMailerSubclass(
            'subject', None, recipients, 'from@example.com',
            mail_controller_class=controller_factory)
        mailer.sendAll()
        # One email is still sent.
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        self.assertEqual('Good <good@example.com>', notifications[0]['To'])

    def test_sendall_first_failure_strips_attachments(self):
        # If sending an email fails, we try again without the (almost
        # certainly) large attachment.
        recipients = {
            self.factory.makePerson(name='good', email='good@example.com'):
                FakeSubscription(),
            self.factory.makePerson(name='bad', email='bad@example.com'):
                FakeSubscription()}
        # Only raise the first time for bob.
        controller_factory = RaisingMailControllerFactory(
            'bad@example.com', 1)
        mailer = AttachmentMailer(
            'subject', None, recipients, 'from@example.com',
            mail_controller_class=controller_factory)
        mailer.sendAll()
        # Both emails are sent.
        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        bad, good = notifications
        # The good email as the expected attachments.
        good_parts = good.get_payload()
        self.assertEqual(3, len(good_parts))
        self.assertEqual(
            'attachment1', good_parts[1].get_payload(decode=True))
        self.assertEqual(
            'attachment2', good_parts[2].get_payload(decode=True))
        # The bad email has the normal attachments stripped off and replaced
        # with the text.
        bad_parts = bad.get_payload()
        self.assertEqual(2, len(bad_parts))
        self.assertEqual(
            'Excessively large attachments removed.',
            bad_parts[1].get_payload(decode=True))
