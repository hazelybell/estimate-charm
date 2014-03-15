# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the haproxy integration view."""

__metaclass__ = type
__all__ = []

from textwrap import dedent

from zope.app.testing.functional import HTTPCaller

from lp.services.config import config
from lp.services.database.policy import (
    DatabaseBlockedPolicy,
    LaunchpadDatabasePolicyFactory,
    )
from lp.services.webapp import haproxy
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer


class HAProxyIntegrationTest(TestCase):
    layer = FunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        self.http = HTTPCaller()
        self.original_flag = haproxy.going_down_flag
        self.addCleanup(haproxy.set_going_down_flag, self.original_flag)

    def test_HAProxyStatusView_all_good_returns_200(self):
        result = self.http(u'GET /+haproxy HTTP/1.0', handle_errors=False)
        self.assertEquals(200, result.getStatus())

    def test_authenticated_HAProxyStatusView_works(self):
        # We don't use authenticated requests, but this keeps us from
        # generating oopses.
        result = self.http(
            u'GET /+haproxy HTTP/1.0\n'
            u'Authorization: Basic Zm9vLmJhckBjYW5vbmljYWwuY29tOnRlc3Q=\n',
            handle_errors=False)
        self.assertEquals(200, result.getStatus())

    def test_HAProxyStatusView_going_down_returns_500(self):
        haproxy.set_going_down_flag(True)
        result = self.http(u'GET /+haproxy HTTP/1.0', handle_errors=False)
        self.assertEquals(500, result.getStatus())

    def test_haproxy_url_uses_DatabaseBlocked_policy(self):
        request = LaunchpadTestRequest(environ={'PATH_INFO': '/+haproxy'})
        policy = LaunchpadDatabasePolicyFactory(request)
        self.assertIsInstance(policy, DatabaseBlockedPolicy)

    def test_switch_going_down_flag(self):
        haproxy.set_going_down_flag(True)
        haproxy.switch_going_down_flag()
        self.assertEquals(False, haproxy.going_down_flag)
        haproxy.switch_going_down_flag()
        self.assertEquals(True, haproxy.going_down_flag)

    def test_HAProxyStatusView_status_code_is_configurable(self):
        config.push('change_haproxy_status_code', dedent('''
            [haproxy_status_view]
            going_down_status: 499
            '''))
        self.addCleanup(config.pop, 'change_haproxy_status_code')
        haproxy.set_going_down_flag(True)
        result = self.http(u'GET /+haproxy HTTP/1.0', handle_errors=False)
        self.assertEquals(499, result.getStatus())
