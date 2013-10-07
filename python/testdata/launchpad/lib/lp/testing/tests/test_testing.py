# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the testing module."""

__metaclass__ = type

import os
import tempfile

from lp.services.config import config
from lp.services.features import (
    getFeatureFlag,
    uninstall_feature_controller,
    )
from lp.testing import (
    feature_flags,
    NestedTempfile,
    set_feature_flag,
    TestCase,
    YUIUnitTestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestFeatureFlags(TestCase):

    layer = DatabaseFunctionalLayer

    def test_set_feature_flags_raises_if_not_available(self):
        """set_feature_flags raises an error if there is no feature
        controller available for the current thread.
        """
        # Remove any existing feature controller for the sake of this
        # test (other tests will re-add it). This prevents weird
        # interactions in a parallel test environment.
        uninstall_feature_controller()
        self.assertRaises(AssertionError, set_feature_flag, u'name', u'value')

    def test_flags_set_within_feature_flags_context(self):
        """In the feature_flags context, set/get works."""
        self.useContext(feature_flags())
        set_feature_flag(u'name', u'value')
        self.assertEqual('value', getFeatureFlag('name'))

    def test_flags_unset_outside_feature_flags_context(self):
        """get fails when used outside the feature_flags context."""
        with feature_flags():
            set_feature_flag(u'name', u'value')
        self.assertIs(None, getFeatureFlag('name'))


class TestYUIUnitTestCase(TestCase):

    def test_id(self):
        test = YUIUnitTestCase()
        test.initialize("foo/bar/baz.html")
        self.assertEqual(test.test_path, test.id())

    def test_id_is_normalized_and_relative_to_root(self):
        test = YUIUnitTestCase()
        test_path = os.path.join(config.root, "../bar/baz/../bob.html")
        test.initialize(test_path)
        self.assertEqual("../bar/bob.html", test.id())


class NestedTempfileTest(TestCase):
    """Tests for `NestedTempfile`."""

    def test_normal(self):
        # The temp directory is removed when the context is exited.
        starting_tempdir = tempfile.gettempdir()
        with NestedTempfile():
            self.assertEqual(tempfile.tempdir, tempfile.gettempdir())
            self.assertNotEqual(tempfile.tempdir, starting_tempdir)
            self.assertTrue(os.path.isdir(tempfile.tempdir))
            nested_tempdir = tempfile.tempdir
        self.assertEqual(tempfile.tempdir, tempfile.gettempdir())
        self.assertEqual(starting_tempdir, tempfile.tempdir)
        self.assertFalse(os.path.isdir(nested_tempdir))

    def test_exception(self):
        # The temp directory is removed when the context is exited, even if
        # the code running in context raises an exception.
        class ContrivedException(Exception):
            pass
        try:
            with NestedTempfile():
                nested_tempdir = tempfile.tempdir
                raise ContrivedException
        except ContrivedException:
            self.assertFalse(os.path.isdir(nested_tempdir))
