# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.testing.systemdocs module."""

__metaclass__ = type

import doctest
import logging
import os
import shutil
import tempfile
import unittest

from lp.services.config import config
from lp.testing import reset_logging
from lp.testing.systemdocs import (
    default_optionflags,
    LayeredDocFileSuite,
    )


class LayeredDocFileSuiteTests(unittest.TestCase):
    """Tests for LayeredDocFileSuite()."""

    def setUp(self):
        self.orig_root = config.root
        # we need an empty story to test with, and it has to be in the
        # testing namespace
        self.tempdir = tempfile.mkdtemp(dir=os.path.dirname(__file__))

    def tearDown(self):
        shutil.rmtree(self.tempdir)
        config.root = self.orig_root
        reset_logging()

    def makeTestFile(self, filename, content=''):
        """Make a doctest file in the temporary directory."""
        test_filename = os.path.join(self.tempdir, filename)
        test_file = open(test_filename, 'w')
        test_file.write(content)
        test_file.close()

    def runSuite(self, suite, num_tests=1):
        """Run a test suite, checking that all tests passed."""
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(num_tests, result.testsRun,)
        self.assertEqual([], result.failures)
        self.assertEqual([], result.errors)

    def test_creates_test_suites(self):
        """LayeredDocFileSuite creates test suites."""
        self.makeTestFile('foo.txt')
        self.makeTestFile('bar.txt')
        base = os.path.basename(self.tempdir)
        suite = LayeredDocFileSuite(
            [os.path.join(base, 'foo.txt'),
             os.path.join(base, 'bar.txt')])
        self.assertTrue(isinstance(suite, unittest.TestSuite))

        [foo_test, bar_test] = list(suite)
        self.assertTrue(isinstance(foo_test, unittest.TestCase))
        self.assertEqual(os.path.basename(foo_test.id()), 'foo.txt')
        self.assertTrue(isinstance(bar_test, unittest.TestCase))
        self.assertEqual(os.path.basename(bar_test.id()), 'bar.txt')
        self.runSuite(suite, num_tests=2)

    def test_set_layer(self):
        """A layer can be applied to the created tests."""
        self.makeTestFile('foo.txt')
        base = os.path.basename(self.tempdir)
        # By default, no layer is applied to the suite.
        suite = LayeredDocFileSuite(os.path.join(base, 'foo.txt'))
        self.assertFalse(hasattr(suite, 'layer'))
        # But if one is passed as a keyword argument, it is applied:
        suite = LayeredDocFileSuite(
            os.path.join(base, 'foo.txt'), layer='some layer')
        self.assertEqual(suite.layer, 'some layer')

    def test_stdout_logging(self):
        """LayeredDocFileSuite handles logging."""
        base = os.path.basename(self.tempdir)
        self.makeTestFile('foo.txt', """
            >>> import logging
            >>> logging.info("An info message (not printed)")
            >>> logging.warning("A warning message")
            WARNING:root:A warning message
        """)
        # Create a suite with logging turned on.
        suite = LayeredDocFileSuite(
            os.path.join(base, 'foo.txt'),
            stdout_logging=True, stdout_logging_level=logging.WARNING)
        self.runSuite(suite)
        # And one with it turned off.
        self.makeTestFile('foo.txt', """
            >>> import logging
            >>> logging.info("An info message (not printed)")
            >>> logging.warning("A warning message")
        """)
        suite = LayeredDocFileSuite(
            os.path.join(base, 'foo.txt'),
            stdout_logging=False, stdout_logging_level=logging.WARNING)
        self.runSuite(suite)

    def test_optionflags(self):
        """A default set of option flags are applied to doc tests."""
        self.makeTestFile('foo.txt')
        base = os.path.basename(self.tempdir)
        suite = LayeredDocFileSuite(os.path.join(base, 'foo.txt'))
        [foo_test] = list(suite)
        self.assertEqual(foo_test._dt_optionflags, default_optionflags)
        # If the optionflags argument is passed, it takes precedence:
        suite = LayeredDocFileSuite(
            os.path.join(base, 'foo.txt'), optionflags=doctest.ELLIPSIS)
        [foo_test] = list(suite)
        self.assertEqual(foo_test._dt_optionflags, doctest.ELLIPSIS)

    def test_strip_prefix(self):
        """The Launchpad tree root is stripped from test names."""
        self.makeTestFile('foo.txt')
        base = os.path.basename(self.tempdir)
        # Set the Launchpad tree root to our temporary directory and
        # create a test suite.
        config.root = self.tempdir
        suite = LayeredDocFileSuite(os.path.join(base, 'foo.txt'))
        [foo_test] = list(suite)
        # The test ID and string representation have the prefix
        # stripped off.
        self.assertEqual(foo_test.id(), 'foo.txt')
        self.assertEqual(str(foo_test), 'foo.txt')
        # Tests outside of the Launchpad tree root are left as is:
        config.root = '/nonexistent'
        suite = LayeredDocFileSuite(os.path.join(base, 'foo.txt'))
        [foo_test] = list(suite)
        self.assertTrue(str(foo_test).startswith(self.orig_root))


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
