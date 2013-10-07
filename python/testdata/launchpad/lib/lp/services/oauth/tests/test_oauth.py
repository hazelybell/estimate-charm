# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the OAuth database classes."""

__metaclass__ = type
__all__ = []

import unittest

from storm.zope.interfaces import IZStorm
from zope.component import getUtility

from lp.services.database.interfaces import (
    MAIN_STORE,
    MASTER_FLAVOR,
    )
from lp.services.oauth.model import (
    OAuthAccessToken,
    OAuthConsumer,
    OAuthNonce,
    OAuthRequestToken,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class BaseOAuthTestCase(unittest.TestCase):
    """Base tests for the OAuth database classes."""
    layer = DatabaseFunctionalLayer

    def test__get_store_should_return_the_main_master_store(self):
        """We want all OAuth classes to use the master store.
        Otherwise, the OAuth exchanges will fail because the authorize
        screen won't probably find the new request token on the slave store.
        """
        zstorm = getUtility(IZStorm)
        self.assertEquals(
            '%s-%s' % (MAIN_STORE, MASTER_FLAVOR),
            zstorm.get_name(self.class_._get_store()))


class OAuthAccessTokenTestCase(BaseOAuthTestCase):
    class_ = OAuthAccessToken


class OAuthRequestTokenTestCase(BaseOAuthTestCase):
    class_ = OAuthRequestToken


class OAuthConsumerTestCase(BaseOAuthTestCase):
    class_ = OAuthConsumer


class OAuthNonceTestCase(BaseOAuthTestCase):
    class_ = OAuthNonce


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(OAuthAccessTokenTestCase),
        unittest.makeSuite(OAuthRequestTokenTestCase),
        unittest.makeSuite(OAuthNonceTestCase),
        unittest.makeSuite(OAuthConsumerTestCase),
            ))
