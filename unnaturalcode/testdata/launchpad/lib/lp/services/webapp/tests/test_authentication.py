# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests authentication.py"""

__metaclass__ = type


import unittest

from contrib.oauth import OAuthRequest

from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


class TestOAuthParsing(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_split_oauth(self):
        # OAuth headers are parsed correctly: see bug 314507.
        # This was really a bug in the underlying contrib/oauth.py module, but
        # it has no standalone test case.
        #
        # Note that the 'realm' parameter is not returned, because it's not
        # included in the OAuth calculations.
        headers = OAuthRequest._split_header(
            'OAuth realm="foo", oauth_consumer_key="justtesting"')
        self.assertEquals(headers,
            {'oauth_consumer_key': 'justtesting'})
        headers = OAuthRequest._split_header(
            'OAuth oauth_consumer_key="justtesting"')
        self.assertEquals(headers,
            {'oauth_consumer_key': 'justtesting'})
        headers = OAuthRequest._split_header(
            'OAuth oauth_consumer_key="justtesting", realm="realm"')
        self.assertEquals(headers,
            {'oauth_consumer_key': 'justtesting'})


def test_suite():
    suite = unittest.TestLoader().loadTestsFromName(__name__)
    suite.addTest(LayeredDocFileSuite(
        'test_launchpad_login_source.txt',
        layer=LaunchpadFunctionalLayer, setUp=setUp, tearDown=tearDown))
    return suite
