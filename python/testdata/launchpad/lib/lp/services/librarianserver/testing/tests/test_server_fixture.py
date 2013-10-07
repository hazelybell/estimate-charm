# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from __future__ import with_statement

"""Test the LibrarianServerFixture."""

__metaclass__ = type

import os
import socket
from textwrap import dedent
from urllib import urlopen

from lp.services.config import config
from lp.services.config.fixture import ConfigFixture
from lp.services.librarianserver.testing.server import LibrarianServerFixture
from lp.testing import TestCase
from lp.testing.layers import (
    BaseLayer,
    DatabaseLayer,
    )


class TestLibrarianServerFixture(TestCase):

    layer = DatabaseLayer

    def skip_if_persistent(self, fixture):
        if fixture._persistent_servers():
            self.skip('persistent server running.')

    def test_on_init_no_pid(self):
        fixture = LibrarianServerFixture(BaseLayer.config_fixture)
        self.skip_if_persistent(fixture)
        self.assertEqual(None, fixture.pid)

    def test_setUp_allocates_resources(self):
        # We need a new ConfigFixture, and create a
        # LibrarianServerFixture using it. We can then confirm that new
        # resources have been allocated by comparing with the currently
        # in use ConfigFixture and config.
        config_fixture = ConfigFixture(
            'foo', BaseLayer.config_fixture.instance_name)
        self.addCleanup(config_fixture.cleanUp)
        config_fixture.setUp()
        fixture = LibrarianServerFixture(config_fixture)
        self.skip_if_persistent(fixture)
        with fixture:
            try:
                self.assertNotEqual(config.librarian_server.root, fixture.root)
                self.assertNotEqual(
                    config.librarian.download_port,
                    fixture.download_port)
                self.assertNotEqual(
                    config.librarian.upload_port,
                    fixture.upload_port)
                self.assertNotEqual(
                    config.librarian.restricted_download_port,
                    fixture.restricted_download_port)
                self.assertNotEqual(
                    config.librarian.restricted_upload_port,
                    fixture.restricted_upload_port)
                # And it exposes a config fragment (but it is not activated).
                expected_config = dedent("""\
                    [librarian_server]
                    root: %s
                    [librarian]
                    download_port: %s
                    upload_port: %s
                    download_url: http://%s:%s/
                    restricted_download_port: %s
                    restricted_upload_port: %s
                    restricted_download_url: http://%s:%s/
                    """) % (
                        fixture.root,
                        fixture.download_port,
                        fixture.upload_port,
                        config.librarian.download_host,
                        fixture.download_port,
                        fixture.restricted_download_port,
                        fixture.restricted_upload_port,
                        config.librarian.restricted_download_host,
                        fixture.restricted_download_port,
                        )
                self.assertEqual(expected_config, fixture.service_config)
            except:
                self.attachLibrarianLog(fixture)
                raise

    def test_getLogChunks(self):
        fixture = LibrarianServerFixture(BaseLayer.config_fixture)
        with fixture:
            chunks = fixture.getLogChunks()
            self.assertIsInstance(chunks, list)
        found_started = False
        for chunk in chunks:
            if 'daemon ready' in chunk:
                found_started = True
        self.assertTrue(found_started)

    def test_smoke_test(self):
        # Avoid indefinite hangs:
        self.addCleanup(socket.setdefaulttimeout, socket.getdefaulttimeout())
        socket.setdefaulttimeout(1)
        fixture = LibrarianServerFixture(BaseLayer.config_fixture)
        with fixture:
            librarian_url = "http://%s:%d" % (
                config.librarian.download_host,
                fixture.download_port)
            restricted_librarian_url = "http://%s:%d" % (
                config.librarian.restricted_download_host,
                fixture.restricted_download_port)
            # Both download ports work:
            self.assertIn('Copyright', urlopen(librarian_url).read())
            self.assertIn(
                'Copyright', urlopen(restricted_librarian_url).read())
            os.path.isdir(fixture.root)
        # Ports are closed on cleanUp.
        self.assertRaises(IOError, urlopen, librarian_url)
        self.assertRaises(IOError, urlopen, restricted_librarian_url)
        self.assertFalse(os.path.exists(fixture.root))
        # We can use the fixture again (gets a new URL):
        with fixture:
            librarian_url = "http://%s:%d" % (
                config.librarian.download_host,
                fixture.download_port)
            self.assertIn('Copyright', urlopen(librarian_url).read())
