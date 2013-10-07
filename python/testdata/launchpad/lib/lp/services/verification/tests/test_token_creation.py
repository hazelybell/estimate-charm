# Copyright 2009, 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import random

import testtools

from lp.services.database.constants import UTC_NOW
from lp.services.tokens import (
    create_token,
    create_unique_token_for_table,
    )
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.model.logintoken import LoginToken
from lp.testing.layers import DatabaseFunctionalLayer


class Test_create_token(testtools.TestCase):

    def test_length(self):
        token = create_token(99)
        self.assertEquals(len(token), 99)


class Test_create_unique_token_for_table(testtools.TestCase):
    layer = DatabaseFunctionalLayer

    def test_token_uniqueness(self):
        orig_state = random.getstate()
        self.addCleanup(lambda: random.setstate(orig_state))
        # Calling create_unique_token_for_table() twice with the same
        # random.seed() will generate two identical tokens, as the token was
        # never inserted in the table.
        random.seed(0)
        token1 = create_unique_token_for_table(99, LoginToken.token)
        random.seed(0)
        token2 = create_unique_token_for_table(99, LoginToken.token)
        self.assertEquals(token1, token2)

        # Now insert the token in the table so that the next time we call
        # create_unique_token_for_table() we get a different token.
        LoginToken(
            requester=None, token=token2, email='email@example.com',
            tokentype=LoginTokenType.ACCOUNTMERGE, created=UTC_NOW)
        random.seed(0)
        token3 = create_unique_token_for_table(99, LoginToken.token)
        self.assertNotEquals(token1, token3)
