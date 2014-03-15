# Copyright 20010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the lpstanding monekypatches"""

__metaclass__ = type
__all__ = []

from Mailman import Errors
from Mailman.Handlers import LPStanding

from lp.registry.interfaces.person import PersonalStanding
from lp.services.mailman.tests import MailmanTestCase
from lp.testing import celebrity_logged_in
from lp.testing.layers import DatabaseFunctionalLayer


class TestLPStandingTestCase(MailmanTestCase):
    """Test lpstanding.

    Mailman process() methods quietly return. They may set msg_data key-values
    or raise an error to end processing. This group of tests tests often check
    for errors, but that does not mean there is an error condition, it only
    means message processing has reached a final decision. Messages that do
    not cause a final decision pass-through and the process() methods ends
    without a return.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestLPStandingTestCase, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)
        self.lp_user_email = 'beaver@eg.dom'
        self.lp_user = self.factory.makePerson(email=self.lp_user_email)

    def tearDown(self):
        super(TestLPStandingTestCase, self).tearDown()
        self.cleanMailmanList(self.mm_list)

    def test_non_subscriber_without_good_standing_is_not_approved(self):
        # Non-subscribers without good standing are not approved to post.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = {}
        silence = LPStanding.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)
        self.assertFalse('approved' in msg_data)

    def test_non_subscriber_with_good_standing_is_approved(self):
        # Non-subscribers with good standing are approved to post.
        with celebrity_logged_in('admin'):
            self.lp_user.personal_standing = PersonalStanding.GOOD
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = {}
        silence = LPStanding.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)
        self.assertTrue(msg_data['approved'])

    def test_proxy_error_retries_message(self):
        # When the Launchpad xmlrpc proxy raises an error, the message
        # is re-enqueed.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = {}
        with self.raise_proxy_exception('inGoodStanding'):
            args = (self.mm_list, message, msg_data)
            self.assertRaises(
                Errors.DiscardMessage, LPStanding.process, *args)
            self.assertIsEnqueued(message)
