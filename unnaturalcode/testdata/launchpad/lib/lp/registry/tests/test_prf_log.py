# -*- coding: utf-8 -*-
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for productreleasefinder.log."""

__author__ = "Scott James Remnant <scott@canonical.com>"

import unittest


class GetLogger(unittest.TestCase):
    def testLogger(self):
        """get_logger returns a Logger instance."""
        from lp.registry.scripts.productreleasefinder.log import get_logger
        from logging import Logger
        self.failUnless(isinstance(get_logger("test"), Logger))

    def testNoParent(self):
        """get_logger works if no parent is given."""
        from lp.registry.scripts.productreleasefinder.log import get_logger
        self.assertEquals(get_logger("test").name, "test")

    def testRootParent(self):
        """get_logger works if root logger is given."""
        from lp.registry.scripts.productreleasefinder.log import get_logger
        from logging import root
        self.assertEquals(get_logger("test", root).name, "test")

    def testNormalParent(self):
        """get_logger works if non-root logger is given."""
        from lp.registry.scripts.productreleasefinder.log import get_logger
        from logging import getLogger
        parent = getLogger("foo")
        self.assertEquals(get_logger("test", parent).name, "foo.test")

    def testDeepParent(self):
        """get_logger works if deep-level logger is given."""
        from lp.registry.scripts.productreleasefinder.log import get_logger
        from logging import getLogger
        getLogger("foo")
        parent2 = getLogger("foo.bar")
        self.assertEquals(get_logger("test", parent2).name, "foo.bar.test")
