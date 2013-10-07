# Copyright 20010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the lpmoderate monekypatches"""

__metaclass__ = type
__all__ = []

from Mailman import Errors
from Mailman.Handlers import LPModerate
from zope.security.proxy import removeSecurityProxy

from lp.services.mailman.tests import MailmanTestCase
from lp.testing.layers import LaunchpadFunctionalLayer


class TestLPModerateTestCase(MailmanTestCase):
    """Test lpmoderate.

    Mailman process() methods quietly return. They may set msg_data key-values
    or raise an error to end processing. These tests often check for errors,
    but that does not mean there is an error condition, it only means message
    processing has reached a final decision. Messages that do not cause a
    final decision pass through, and the process() methods ends without a
    return.
    """

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestLPModerateTestCase, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)
        self.lp_user_email = 'capybara@eg.dom'
        self.lp_user = self.factory.makePerson(email=self.lp_user_email)

    def tearDown(self):
        super(TestLPModerateTestCase, self).tearDown()
        self.cleanMailmanList(self.mm_list)

    def test_process_message_from_preapproved(self):
        # Any message mark with approval will silently complete the process.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = dict(approved=True)
        silence = LPModerate.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)

    def test_process_message_from_subscriber(self):
        # Messages from subscribers silently complete the process.
        subscriber_email = removeSecurityProxy(
            self.team.teamowner).preferredemail.email
        message = self.makeMailmanMessage(
            self.mm_list, subscriber_email, 'subject', 'any content.')
        msg_data = {}
        silence = LPModerate.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)

    def test_process_message_from_lp_user_held_for_moderation(self):
        # Messages from Launchpad users are held for moderation.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'content')
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.HoldMessage, LPModerate.process, *args)
        self.assertEqual(1, self.mailing_list.getReviewableMessages().count())

    def test_process_message_with_non_ascii_from_lp_user_held(self):
        # Non-ascii messages can be held for moderation.
        non_ascii_email = 'I \xa9 M <%s>' % self.lp_user_email.encode('ascii')
        message = self.makeMailmanMessage(
            self.mm_list, non_ascii_email, 'subject \xa9', 'content \xa9')
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.HoldMessage, LPModerate.process, *args)
        self.assertEqual(1, self.mailing_list.getReviewableMessages().count())

    def test_process_duplicate_message_discarded(self):
        # Messages are discarded is they are already held for moderation.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'content')
        self.mm_list.held_message_ids = {message['message-id']: message}
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.DiscardMessage, LPModerate.process, *args)
        self.assertEqual(0, self.mailing_list.getReviewableMessages().count())

    def test_process_empty_mesage_from_nonsubcriber_discarded(self):
        # Messages from Launchpad users without text content are discarded.
        spam_message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email,
            'get drugs', '<a><img /></a>.', mime_type='html')
        msg_data = dict(approved=False)
        args = (self.mm_list, spam_message, msg_data)
        self.assertRaises(
            Errors.DiscardMessage, LPModerate.process, *args)
        self.assertEqual(0, self.mailing_list.getReviewableMessages().count())

    def test_process_message_from_list_discarded(self):
        # Messages that claim to be from the list itself (not a subcriber) are
        # discarded because Mailman's internal handlers did not set 'approve'
        # in msg_data.
        list_email = 'spammer <%s>' % self.mailing_list.address
        message = self.makeMailmanMessage(
            self.mm_list, list_email, 'subject', 'any content.')
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.DiscardMessage, LPModerate.process, *args)
        self.assertEqual(0, self.mailing_list.getReviewableMessages().count())
