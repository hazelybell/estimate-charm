# Copyright 20010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the LaunchpadMember monekypatches"""

__metaclass__ = type
__all__ = []

import hashlib

from Mailman import (
    Errors,
    mm_cfg,
    )
from Mailman.Handlers import LaunchpadMember

from lp.services.mailman.tests import MailmanTestCase
from lp.testing.layers import DatabaseFunctionalLayer


class TestLaunchpadMemberTestCase(MailmanTestCase):
    """Test lphandler.

    Mailman process() methods quietly return. They may set msg_data key-values
    or raise an error to end processing. This group of tests tests often check
    for errors, but that does not mean there is an error condition, it only
    means message processing has reached a final decision. Messages that do
    not cause a final decision pass-through and the process() methods ends
    without a return.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestLaunchpadMemberTestCase, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)

    def tearDown(self):
        super(TestLaunchpadMemberTestCase, self).tearDown()
        self.cleanMailmanList(self.mm_list)

    def test_messages_from_unknown_senders_are_discarded(self):
        # A massage from an unknown email address is discarded.
        message = self.makeMailmanMessage(
            self.mm_list, 'gerbil@noplace.dom', 'subject', 'any content.')
        msg_data = {}
        args = (self.mm_list, message, msg_data)
        self.assertRaises(
            Errors.DiscardMessage, LaunchpadMember.process, *args)

    def test_preapproved_messages_are_always_accepted(self):
        # An approved message is accepted even if the email address is
        # unknown.
        message = self.makeMailmanMessage(
            self.mm_list, 'gerbil@noplace.dom', 'subject', 'any content.')
        msg_data = dict(approved=True)
        silence = LaunchpadMember.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)

    def test_messages_from_launchpad_users_are_accepted(self):
        # A message from a launchpad user is accepted.
        lp_user_email = 'chinchila@eg.dom'
        lp_user = self.factory.makePerson(email=lp_user_email)
        message = self.makeMailmanMessage(
            self.mm_list, lp_user_email, 'subject', 'any content.')
        msg_data = {}
        silence = LaunchpadMember.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)

    def test_messages_from_launchpad_itself_are_accepted(self):
        # A message from launchpad itself is accepted. Launchpad will sent
        # a secret.
        message = self.makeMailmanMessage(
            self.mm_list, 'guinea-pig@noplace.dom', 'subject', 'any content.')
        message['message-id'] = 'hamster.hamster'
        hash = hashlib.sha1(mm_cfg.LAUNCHPAD_SHARED_SECRET)
        hash.update(message['message-id'])
        message['x-launchpad-hash'] = hash.hexdigest()
        msg_data = {}
        silence = LaunchpadMember.process(self.mm_list, message, msg_data)
        self.assertEqual(None, silence)
        self.assertEqual(True, msg_data['approved'])

    def test_proxy_error_retries_message(self):
        # When the Launchpad xmlrpc proxy raises an error, the message
        # is re-enqueed.
        lp_user_email = 'groundhog@eg.dom'
        lp_user = self.factory.makePerson(email=lp_user_email)
        message = self.makeMailmanMessage(
            self.mm_list, lp_user_email, 'subject', 'any content.')
        msg_data = {}
        with self.raise_proxy_exception('isRegisteredInLaunchpad'):
            args = (self.mm_list, message, msg_data)
            self.assertRaises(
                Errors.DiscardMessage, LaunchpadMember.process, *args)
            self.assertIsEnqueued(message)
