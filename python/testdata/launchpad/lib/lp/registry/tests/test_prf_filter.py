# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.registry.scripts.productreleasefinder.filter."""

import unittest


class Filter_Logging(unittest.TestCase):
    def testCreatesDefaultLogger(self):
        """Filter creates a default logger."""
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter)
        from logging import Logger
        f = Filter()
        self.failUnless(isinstance(f.log, Logger))

    def testCreatesChildLogger(self):
        """Filter creates a child logger if given a parent."""
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter)
        from logging import getLogger
        parent = getLogger("foo")
        f = Filter(log_parent=parent)
        self.assertEquals(f.log.parent, parent)


class Filter_Init(unittest.TestCase):
    def testDefaultFiltersProperty(self):
        """Filter constructor initializes filters property to empty dict."""
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter)
        f = Filter()
        self.assertEquals(f.filters, [])

    def testFiltersPropertyGiven(self):
        """Filter constructor accepts argument to set filters property."""
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter)
        f = Filter(["wibble"])
        self.assertEquals(len(f.filters), 1)
        self.assertEquals(f.filters[0], "wibble")


class Filter_CheckUrl(unittest.TestCase):
    def testNoFilters(self):
        """Filter.check returns None if there are no filters."""
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter)
        f = Filter()
        self.assertEquals(f.check("file:///subdir/file"), None)

    def makeFilter(self, key, urlglob):
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter, FilterPattern)
        pattern = FilterPattern(key, urlglob)
        return Filter([pattern])

    def testNotMatching(self):
        """Filter.check returns None if doesn't match a filter."""
        f = self.makeFilter("foo", "file:///subdir/w*")
        self.assertEquals(f.check("file:///subdir/file"), None)

    def testNoMatchingSlashes(self):
        """Filter.check that the glob does not match slashes."""
        f = self.makeFilter("foo", "file:///*l*")
        self.assertEquals(f.check("file:///subdir/file"), None)

    def testReturnsMatching(self):
        """Filter.check returns the matching keyword."""
        f = self.makeFilter("foo", "file:///subdir/f*e")
        self.assertEquals(f.check("file:///subdir/file"), "foo")

    def testGlobSubdir(self):
        # Filter.glob can contain slashes to match subdirs
        f = self.makeFilter("foo", "file:///sub*/f*e")
        self.assertEquals(f.check("file:///subdir/file"), "foo")

    def testReturnsNonMatchingBase(self):
        """Filter.check returns None if the base does not match."""
        f = self.makeFilter("foo", "http:f*e")
        self.assertEquals(f.check("file:///subdir/file"), None)


class Filter_IsPossibleParentUrl(unittest.TestCase):

    def makeFilter(self, key, urlglob):
        from lp.registry.scripts.productreleasefinder.filter import (
            Filter, FilterPattern)
        pattern = FilterPattern(key, urlglob)
        return Filter([pattern])

    def testNotContainedByMatch(self):
        # if the URL matches the pattern, then it can't contain matches.
        f = self.makeFilter("foo", "file:///subdir/foo-1.*.tar.gz")
        self.assertFalse(f.isPossibleParent("file:///subdir/foo-1.42.tar.gz"))

    def testContainedByParent(self):
        # parent directories of the match can contain the match
        f = self.makeFilter("foo", "file:///subdir/foo/bar")
        self.assertTrue(f.isPossibleParent("file:///subdir/foo/"))
        self.assertTrue(f.isPossibleParent("file:///subdir/foo"))
        self.assertTrue(f.isPossibleParent("file:///subdir"))
        self.assertTrue(f.isPossibleParent("file:///"))

    def testContainedByGlobbedParent(self):
        # test that glob matched parents can contain matches
        f = self.makeFilter("foo", "file:///subdir/1.*/foo-1.*.tar.gz")
        self.assertTrue(f.isPossibleParent("file:///subdir/1.0/"))
        self.assertTrue(f.isPossibleParent("file:///subdir/1.42"))
        self.assertTrue(f.isPossibleParent("file:///subdir/1.abc/"))
        self.assertFalse(f.isPossibleParent("file:///subdir/2.0"))
