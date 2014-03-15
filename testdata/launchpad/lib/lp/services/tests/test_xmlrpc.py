# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the generic and/or shared xmlrpc code that Launchpad provides."""

__metaclass__ = type

import httplib

from lp.services.xmlrpc import Transport
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class TestTransport(TestCase):
    """Test code that allows xmlrpclib.ServerProxy to have a socket timeout"""

    layer = BaseLayer

    def test_default_initialization(self):
        transport = Transport()
        conn = httplib.HTTPConnection('localhost')
        self.assertEqual(conn.timeout, transport.timeout)

    def test_custom_initialization(self):
        transport = Transport(timeout=25)
        self.assertEqual(25, transport.timeout)

    def test_timeout_passed_to_connection(self):
        transport = Transport(timeout=25)
        http = transport.make_connection('localhost')
        # See logic in lp.services.xmlrpc.Transport.make_connection
        http = getattr(http, "_conn", http)
        self.assertEqual(25, http.timeout)
