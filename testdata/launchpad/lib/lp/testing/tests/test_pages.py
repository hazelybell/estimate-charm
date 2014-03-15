# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test that creating page test stories from files and directories work."""
__metaclass__ = type

from operator import methodcaller
import os
import shutil
import tempfile
import unittest

from bzrlib.tests import iter_suite_tests

from lp.testing.layers import PageTestLayer
from lp.testing.pages import PageTestSuite


class TestMakeStoryTest(unittest.TestCase):
    layer = PageTestLayer

    def setUp(self):
        # we need an empty story to test with, and it has to be in the
        # testing namespace
        self.tempdir = tempfile.mkdtemp(dir=os.path.dirname(__file__))
        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)
        shutil.rmtree(self.tempdir)

    def test_dir_construction_and_trivial_running(self):
        test_filename = os.path.join(self.tempdir, 'xx-foo.txt')
        test_file = open(test_filename, 'wt')
        test_file.close()
        test_filename = os.path.join(self.tempdir, 'xx-bar.txt')
        test_file = open(test_filename, 'wt')
        test_file.close()
        # The test directory is looked up relative to the calling
        # module's path.
        suite = PageTestSuite(os.path.basename(self.tempdir))
        self.failUnless(isinstance(suite, unittest.TestSuite))
        tests = list(iter_suite_tests(suite))

        # Each unnumbered file appears as an independent test.
        ids = set(map(os.path.basename, map(methodcaller('id'), tests)))
        self.assertEqual(set(['xx-bar.txt', 'xx-foo.txt']), ids)
