# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test behavior of the Librarian during a database outage.

Database outages happen by accident and during fastdowntime deployments."""

__metaclass__ = type

from cStringIO import StringIO
import urllib2

from fixtures import Fixture

from lp.services.librarian.client import LibrarianClient
from lp.services.librarianserver.testing.server import LibrarianServerFixture
from lp.testing import TestCase
from lp.testing.fixture import PGBouncerFixture
from lp.testing.layers import (
    BaseLayer,
    DatabaseFunctionalLayer,
    )


class PGBouncerLibrarianLayer(DatabaseFunctionalLayer):
    """Custom layer for TestLibrarianDBOutage.

    We are using a custom layer instead of standard setUp/tearDown to
    avoid the lengthy Librarian startup time, and to cope with undoing
    changes made to BaseLayer.config_fixture to allow access to the
    Librarian we just started up.
    """
    pgbouncer_fixture = None
    librarian_fixture = None

    @classmethod
    def setUp(cls):
        # Fixture to hold other fixtures.
        cls._fixture = Fixture()
        cls._fixture.setUp()

        cls.pgbouncer_fixture = PGBouncerFixture()
        # Install the PGBouncer fixture so we shut it down to
        # create database outages.
        cls._fixture.useFixture(cls.pgbouncer_fixture)

        # Bring up the Librarian, which will be connecting via
        # pgbouncer.
        cls.librarian_fixture = LibrarianServerFixture(
            BaseLayer.config_fixture)
        cls._fixture.useFixture(cls.librarian_fixture)

    @classmethod
    def tearDown(cls):
        cls.pgbouncer_fixture = None
        cls.librarian_fixture = None
        cls._fixture.cleanUp()

    @classmethod
    def testSetUp(cls):
        cls.pgbouncer_fixture.start()


class TestLibrarianDBOutage(TestCase):
    layer = PGBouncerLibrarianLayer

    def setUp(self):
        super(TestLibrarianDBOutage, self).setUp()
        self.pgbouncer = PGBouncerLibrarianLayer.pgbouncer_fixture
        self.client = LibrarianClient()

        # Add a file to the Librarian so we can download it.
        self.url = self._makeLibraryFileUrl()

    def _makeLibraryFileUrl(self):
        data = 'whatever'
        return self.client.remoteAddFile(
            'foo.txt', len(data), StringIO(data), 'text/plain')

    def getErrorCode(self):
        # We need to talk to every Librarian thread to ensure all the
        # Librarian database connections are in a known state.
        # XXX StuartBishop 2011-09-01 bug=840046: 20 might be overkill
        # for the test run, but we have no real way of knowing how many
        # connections are in use.
        num_librarian_threads = 20
        codes = set()
        for count in range(num_librarian_threads):
            try:
                urllib2.urlopen(self.url).read()
                codes.add(200)
            except urllib2.HTTPError as error:
                codes.add(error.code)
        self.assertTrue(len(codes) == 1, 'Mixed responses: %s' % str(codes))
        return codes.pop()

    def test_outage(self):
        # Everything should be working fine to start with.
        self.assertEqual(self.getErrorCode(), 200)

        # When the outage kicks in, we start getting 503 responses
        # instead of 200 and 404s.
        self.pgbouncer.stop()
        self.assertEqual(self.getErrorCode(), 503)

        # When the outage is over, things are back to normal.
        self.pgbouncer.start()
        self.assertEqual(self.getErrorCode(), 200)
