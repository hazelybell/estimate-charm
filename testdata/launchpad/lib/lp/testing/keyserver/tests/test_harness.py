# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from urllib import urlopen

from lp.services.config import config
from lp.testing import TestCase
from lp.testing.keyserver import KeyServerTac
from lp.testing.keyserver.web import GREETING


class TestKeyServerTac(TestCase):

    def test_url(self):
        # The url is the one that gpghandler is configured to hit.
        fixture = KeyServerTac()
        self.assertEqual(
            'http://%s:%d' % (
                config.gpghandler.host, config.gpghandler.port),
            fixture.url)

    def test_starts_properly(self):
        # Make sure the tac starts properly and that we can load the page.
        fixture = KeyServerTac()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        content = urlopen(fixture.url).readline()
        self.assertEqual(GREETING, content)
