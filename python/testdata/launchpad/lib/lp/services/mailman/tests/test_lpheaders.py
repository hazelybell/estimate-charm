# Copyright 20010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the lpheaders monekypatches"""

__metaclass__ = type
__all__ = []

from Mailman.Handlers import (
    Decorate,
    LaunchpadHeaders,
    )

from lp.services.mailman.tests import MailmanTestCase
from lp.testing.layers import DatabaseFunctionalLayer


class TestLaunchpadHeadersTestCase(MailmanTestCase):
    """Test lpheaders.

    Mailman process() methods quietly return. They may set msg_data key-values
    or raise an error to end processing. This group of tests tests often check
    for errors, but that does not mean there is an error condition, it only
    means message processing has reached a final decision. Messages that do
    not cause a final decision pass-through and the process() methods ends
    without a return.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestLaunchpadHeadersTestCase, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)
        self.lp_user_email = 'albatros@eg.dom'
        self.lp_user = self.factory.makePerson(
            name='albatros', email=self.lp_user_email)

    def tearDown(self):
        super(TestLaunchpadHeadersTestCase, self).tearDown()
        self.cleanMailmanList(self.mm_list)

    def test_message_launchpad_headers(self):
        # All messages get updated headers.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = {}
        silence = LaunchpadHeaders.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)
        self.assertEqual(
            '<team-1.lists.launchpad.dev>', message['List-Id'])
        self.assertEqual(
            '<http://help.launchpad.dev/ListHelp>', message['List-Help'])
        self.assertEqual(
            '<http://launchpad.dev/~team-1>', message['List-Subscribe'])
        self.assertEqual(
            '<http://launchpad.dev/~team-1>', message['List-Unsubscribe'])
        self.assertEqual(
            '<mailto:team-1@lists.launchpad.dev>', message['List-Post'])
        self.assertEqual(
            '<http://lists.launchpad.dev/team-1>', message['List-Archive'])
        self.assertEqual(
            '<http://launchpad.dev/~team-1>', message['List-Owner'])

    def test_message_decoration_data(self):
        # The lpheaders process method provides decoration-data.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = {}
        silence = LaunchpadHeaders.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)
        self.assertTrue('decoration-data' in msg_data)
        decoration_data = msg_data['decoration-data']
        self.assertEqual(
            'http://launchpad.dev/~team-1',
            decoration_data['list_owner'])
        self.assertEqual(
            'team-1@lists.launchpad.dev',
            decoration_data['list_post'])
        self.assertEqual(
            'http://launchpad.dev/~team-1',
            decoration_data['list_unsubscribe'])
        self.assertEqual(
            'http://help.launchpad.dev/ListHelp',
            decoration_data['list_help'])

    def test_message_decorate_footer(self):
        # The Decorate handler uses the lpheaders decoration-data.
        message = self.makeMailmanMessage(
            self.mm_list, self.lp_user_email, 'subject', 'any content.')
        msg_data = {}
        LaunchpadHeaders.process(self.mm_list, message, msg_data)
        self.assertTrue('decoration-data' in msg_data)
        silence = Decorate.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)
        body, footer = message.get_payload()[1].get_payload().rsplit('-- ', 1)
        expected = (
            "\n"
            "Mailing list: http://launchpad.dev/~team-1\n"
            "Post to     : team-1@lists.launchpad.dev\n"
            "Unsubscribe : http://launchpad.dev/~team-1\n"
            "More help   : http://help.launchpad.dev/ListHelp\n")
        self.assertEqual(expected, footer)
