# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the script that does a smoke-test of the librarian."""

__metaclass__ = type

from contextlib import contextmanager
from cStringIO import StringIO

from lp.services.librarian import smoketest
from lp.services.librarian.smoketest import (
    do_smoketest,
    FILE_DATA,
    store_file,
    )
from lp.services.librarianserver.testing.fake import FakeLibrarian
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer


class GoodUrllib:
    """A urllib replacement for testing that returns good results."""

    def urlopen(self, url):
        return StringIO(FILE_DATA)


class BadUrllib:
    """A urllib replacement for testing that returns bad results."""

    def urlopen(self, url):
        return StringIO('bad data')


class ErrorUrllib:
    """A urllib replacement for testing that raises an exception."""

    def urlopen(self, url):
        raise IOError('network error')


class ExplosiveUrllib:
    """A urllib replacement that raises an "explosive" exception."""

    def __init__(self, exception):
        self.exception = exception

    def urlopen(self, url):
        raise self.exception


@contextmanager
def fake_urllib(fake):
    original_urllib = smoketest.urllib
    smoketest.urllib = fake
    yield
    smoketest.urllib = original_urllib


class SmokeTestTestCase(TestCaseWithFactory):
    """Class test for translation importer creation."""
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(SmokeTestTestCase, self).setUp()
        self.fake_librarian = self.useFixture(FakeLibrarian())

    def test_store_file(self):
        # Make sure that the function meant to store a file in the librarian
        # and return the file's HTTP URL works.
        self.assertEquals(
            store_file(self.fake_librarian),
            (93, 'http://localhost:58000/93/smoke-test-file'))

    def test_good_data(self):
        # If storing and retrieving both the public and private files work,
        # the main function will return 0 (which will be used as the processes
        # exit code to signal success).
        with fake_urllib(GoodUrllib()):
            self.assertEquals(
                do_smoketest(self.fake_librarian, self.fake_librarian,
                             output=StringIO()),
                0)

    def test_bad_data(self):
        # If incorrect data is retrieved, the main function will return 1
        # (which will be used as the processes exit code to signal an error).
        with fake_urllib(BadUrllib()):
            self.assertEquals(
                do_smoketest(self.fake_librarian, self.fake_librarian,
                             output=StringIO()),
                1)

    def test_exception(self):
        # If an exception is raised when retrieving the data, the main
        # function will return 1 (which will be used as the processes exit
        # code to signal an error).
        with fake_urllib(ErrorUrllib()):
            self.assertEquals(
                do_smoketest(self.fake_librarian, self.fake_librarian,
                             output=StringIO()),
                1)

    def test_explosive_errors(self):
        # If an "explosive" exception (an exception that should not be caught)
        # is raised when retrieving the data it is re-raised.
        for exception in MemoryError, SystemExit, KeyboardInterrupt:
            with fake_urllib(ExplosiveUrllib(exception)):
                self.assertRaises(
                    exception,
                    do_smoketest, self.fake_librarian, self.fake_librarian,
                    output=StringIO())
