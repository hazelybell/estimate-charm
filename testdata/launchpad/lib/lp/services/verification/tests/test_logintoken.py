# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the logintoken module."""

__metaclass__ = type

import doctest
from textwrap import dedent

from testtools.matchers import DocTestMatches
from zope.component import getUtility

from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import ILoginTokenSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.mail_helpers import pop_notifications


class TestLoginToken(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_sendMergeRequestEmail(self):
        # sendMergeRequestEmail() sends an email to the user informing him/her
        # of the request.

        user1 = self.factory.makePerson(name="requester")
        user2 = self.factory.makePerson(name="duplicate", displayname="Bob")

        with person_logged_in(user1):
            token = getUtility(ILoginTokenSet).new(
                user1, user1.preferredemail.email, user2.preferredemail.email,
                LoginTokenType.ACCOUNTMERGE)

        token.sendMergeRequestEmail()
        (message,) = pop_notifications()
        self.assertEqual(
            "Launchpad Account Merge <noreply@launchpad.net>",
            message['from'])
        self.assertEqual(
            "Launchpad: Merge of Accounts Requested", message['subject'])
        expected_message = dedent("""
            Hello

            Launchpad: request to merge accounts
            ------------------------------------

            Someone has asked us to merge one of your Launchpad
            accounts with another.

            If you go ahead, this will merge the account called
            'Bob (duplicate)' into the account 'requester'.

            To confirm you want to do this, please follow
            this link:

                http://launchpad.dev/token/...

            If you didn't ask to merge these accounts, please
            either ignore this email or report it to the
            Launchpad team: feedback@launchpad.net

            You can read more about merging accounts in our
            help wiki:

                https://help.launchpad.net/YourAccount/Merging

            Thank you,

            The Launchpad team
            https://launchpad.net
            """)
        expected_matcher = DocTestMatches(
            expected_message, doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
        self.assertThat(message.get_payload(decode=True), expected_matcher)
