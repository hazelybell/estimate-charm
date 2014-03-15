# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing the mock Swift test fixture."""

__metaclass__ = type
__all__ = []

import httplib

from swiftclient import client as swiftclient

from lp.testing import TestCase
from lp.testing.layers import BaseLayer
from lp.testing.swift.fixture import SwiftFixture


class TestSwiftFixture(TestCase):
    layer = BaseLayer

    def setUp(self):
        super(TestSwiftFixture, self).setUp()
        self.swift_fixture = SwiftFixture()
        self.useFixture(self.swift_fixture)

    def test_basic(self):
        client = self.swift_fixture.connect()
        size = 30
        headers, body = client.get_object("size", str(size))
        self.assertEquals(body, "0" * size)
        self.assertEqual(str(size), headers["content-length"])
        self.assertEqual("text/plain", headers["content-type"])

    def test_shutdown_and_startup(self):
        # This test demonstrates how the Swift client deals with a
        # flapping Swift server. In particular, that once a connection
        # has started failing it will continue failing so we need to
        # ensure that once we encounter a fail we open a fresh
        # connection. This is probably a property of our mock Swift
        # server rather than reality but the mock is a required target.
        size = 30

        # With no Swift server, a fresh connection fails with
        # a swiftclient.ClientException when it fails to
        # authenticate.
        self.swift_fixture.shutdown()
        client = self.swift_fixture.connect()
        self.assertRaises(
            swiftclient.ClientException,
            client.get_object, "size", str(size))

        # Things work fine when the Swift server is up.
        self.swift_fixture.startup()
        headers, body = client.get_object("size", str(size))
        self.assertEquals(body, "0" * size)

        # But if the Swift server goes away again, we end up with
        # different failures since the connection has already
        # authenticated.
        self.swift_fixture.shutdown()
        self.assertRaises(
            httplib.HTTPException,
            client.get_object, "size", str(size))

        # And even if we bring it back up, existing connections
        # continue to fail
        self.swift_fixture.startup()
        self.assertRaises(
            httplib.HTTPException,
            client.get_object, "size", str(size))

        # But fresh connections are fine.
        client = self.swift_fixture.connect()
        headers, body = client.get_object("size", str(size))
        self.assertEquals(body, "0" * size)
