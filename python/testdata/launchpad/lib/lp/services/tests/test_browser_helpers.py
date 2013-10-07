# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for browser helper functions."""

__metaclass__ = type
__all__ = ['TestGetUserAgentDistroSeries', 'test_suite']

import unittest

from lp.services.browser_helpers import get_user_agent_distroseries


class TestGetUserAgentDistroSeries(unittest.TestCase):
    """Test that the user_agent string is correctly parsed for os version."""

    def test_get_user_agent_distroseries_when_present(self):
        """The version number is returned when present."""
        user_agent = ('Mozilla/5.0 '
                      '(X11; U; Linux i686; en-US; rv:1.9.0.10) '
                      'Gecko/2009042523 Ubuntu/10.09 (whatever) '
                      'Firefox/3.0.10')

        version = get_user_agent_distroseries(user_agent)
        self.failUnlessEqual('10.09', version,
                             "Incorrect version string returned.")

    def test_get_user_agent_distroseries_when_invalid(self):
        """None should be returned when the version is not matched."""
        user_agent = ('Mozilla/5.0 '
                      '(X11; U; Linux i686; en-US; rv:1.9.0.10) '
                      'Gecko/2009042523 Ubuntu/10a.09 (whatever) '
                      'Firefox/3.0.10')

        version = get_user_agent_distroseries(user_agent)
        self.failUnless(version is None,
                        "None should be returned when the match fails.")

def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
