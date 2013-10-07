# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test notification classes and functions."""

__metaclass__ = type

from lp.registry.mail.notification import send_direct_contact_email
from lp.services.mail.notificationrecipientset import NotificationRecipientSet
from lp.services.messages.interfaces.message import (
    IDirectEmailAuthorization,
    QuotaReachedError,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.mail_helpers import pop_notifications


class SendDirectContactEmailTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_send_message(self):
        self.factory.makePerson(email='me@eg.dom', name='me')
        user = self.factory.makePerson(email='him@eg.dom', name='him')
        subject = 'test subject'
        body = 'test body'
        recipients_set = NotificationRecipientSet()
        recipients_set.add(user, 'test reason', 'test rationale')
        pop_notifications()
        send_direct_contact_email('me@eg.dom', recipients_set, subject, body)
        notifications = pop_notifications()
        notification = notifications[0]
        self.assertEqual(1, len(notifications))
        self.assertEqual('Me <me@eg.dom>', notification['From'])
        self.assertEqual('Him <him@eg.dom>', notification['To'])
        self.assertEqual(subject, notification['Subject'])
        self.assertEqual(
            'test rationale', notification['X-Launchpad-Message-Rationale'])
        self.assertIs(None, notification['Precedence'])
        self.assertTrue('launchpad' in notification['Message-ID'])
        self.assertEqual(
            '\n'.join([
                '%s' % body,
                '-- ',
                'This message was sent from Launchpad by',
                'Me (http://launchpad.dev/~me)',
                'test reason.',
                'For more information see',
                'https://help.launchpad.net/YourAccount/ContactingPeople']),
            notification.get_payload())

    def test_quota_reached_error(self):
        # An error is raised if the user has reached the daily quota.
        self.factory.makePerson(email='me@eg.dom', name='me')
        user = self.factory.makePerson(email='him@eg.dom', name='him')
        recipients_set = NotificationRecipientSet()
        old_message = self.factory.makeSignedMessage(email_address='me@eg.dom')
        authorization = IDirectEmailAuthorization(user)
        for action in xrange(authorization.message_quota):
            authorization.record(old_message)
        self.assertRaises(
            QuotaReachedError, send_direct_contact_email,
            'me@eg.dom', recipients_set, 'subject', 'body')

    def test_empty_recipient_set(self):
        # The recipient set can be empty. No messages are sent and the
        # action does not count toward the daily quota.
        self.factory.makePerson(email='me@eg.dom', name='me')
        user = self.factory.makePerson(email='him@eg.dom', name='him')
        recipients_set = NotificationRecipientSet()
        old_message = self.factory.makeSignedMessage(email_address='me@eg.dom')
        authorization = IDirectEmailAuthorization(user)
        for action in xrange(authorization.message_quota - 1):
            authorization.record(old_message)
        pop_notifications()
        send_direct_contact_email(
            'me@eg.dom', recipients_set, 'subject', 'body')
        notifications = pop_notifications()
        self.assertEqual(0, len(notifications))
        self.assertTrue(authorization.is_allowed)

    def test_wrapping(self):
        self.factory.makePerson(email='me@eg.dom')
        user = self.factory.makePerson()
        recipients_set = NotificationRecipientSet()
        recipients_set.add(user, 'test reason', 'test rationale')
        pop_notifications()
        body = 'Can you help me? ' * 8
        send_direct_contact_email('me@eg.dom', recipients_set, 'subject', body)
        notifications = pop_notifications()
        body, footer = notifications[0].get_payload().split('-- ')
        self.assertEqual(
            'Can you help me? Can you help me? Can you help me? '
            'Can you help me? Can\n'
            'you help me? Can you help me? Can you help me? '
            'Can you help me?\n',
            body)

    def test_name_utf8_encoding(self):
        # Names are encoded in the From and To headers.
        self.factory.makePerson(email='me@eg.dom', displayname=u'sn\xefrf')
        user = self.factory.makePerson(
            email='him@eg.dom', displayname=u'pti\xedng')
        recipients_set = NotificationRecipientSet()
        recipients_set.add(user, 'test reason', 'test rationale')
        pop_notifications()
        send_direct_contact_email('me@eg.dom', recipients_set, 'test', 'test')
        notifications = pop_notifications()
        notification = notifications[0]
        self.assertEqual(
            '=?utf-8?b?c27Dr3Jm?= <me@eg.dom>', notification['From'])
        self.assertEqual(
            '=?utf-8?q?pti=C3=ADng?= <him@eg.dom>', notification['To'])
