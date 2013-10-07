# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for debversion."""

__metaclass__ = type

# These tests came from sourcerer.

import unittest

from lp.archivepublisher.debversion import (
    BadInputError,
    BadUpstreamError,
    Version,
    VersionError,
    )


class VersionTests(unittest.TestCase):
    # Known values that should work
    VALUES = (
        "1",
        "1.0",
        "1:1.0",
        "1.0-1",
        "1:1.0-1",
        "3.4-2.1",
        "1.5.4-1.woody.0",
        "1.6-0+1.5a-4",
        "1.3~rc1-4",
        )

    # Known less-than comparisons
    COMPARISONS = (
        ("1.0", "1.1"),
        ("1.1", "2.0"),
        ("2.1", "2.10"),
        ("2.2", "2.10"),
        ("1.0", "1:1.0"),
        ("1:9.0", "2:1.0"),
        ("1.0-1", "1.0-2"),
        ("1.0", "1.0-1"),
        ("1a", "1b"),
        ("1a", "2"),
        ("1a", "1."),
        ("1a", "1+"),
        ("1:1a", "1:1:"),
        ("1a-1", "1--1"),
        ("1+-1", "1--1"),
        ("1--1", "1.-1"),
        ("1:1.", "1:1:"),
        ("1A", "1a"),
        ("1~", "1"),
        ("1~", "1~a"),
        ("1~a", "1~b"),
        )

    def testAcceptsString(self):
        """Version should accept a string input."""
        Version("1.0")

    def testReturnString(self):
        """Version should convert to a string."""
        self.assertEquals(str(Version("1.0")), "1.0")

    def testAcceptsInteger(self):
        """Version should accept an integer."""
        self.assertEquals(str(Version(1)), "1")

    def testAcceptsNumber(self):
        """Version should accept a number."""
        self.assertEquals(str(Version(1.2)), "1.2")

    def testNotEmpty(self):
        """Version should fail with empty input."""
        self.assertRaises(BadInputError, Version, "")

    def testEpochNotEmpty(self):
        """Version should fail with empty epoch."""
        self.assertRaises(VersionError, Version, ":1")

    def testEpochNonNumeric(self):
        """Version should fail with non-numeric epoch."""
        self.assertRaises(VersionError, Version, "a:1")

    def testEpochNonInteger(self):
        """Version should fail with non-integral epoch."""
        self.assertRaises(VersionError, Version, "1.0:1")

    def testEpochNonNegative(self):
        """Version should fail with a negative epoch."""
        self.assertRaises(VersionError, Version, "-1:1")

    def testUpstreamNotEmpty(self):
        """Version should fail with empty upstream."""
        self.assertRaises(BadUpstreamError, Version, "1:-1")

    def testUpstreamNonDigitStart(self):
        """Version should fail when upstream doesn't start with a digit."""
        self.assertRaises(BadUpstreamError, Version, "a1")

    def testUpstreamInvalid(self):
        """Version should fail when upstream contains a bad character."""
        self.assertRaises(VersionError, Version, "1!0")

    def testRevisionNotEmpty(self):
        """Version should not allow an empty revision."""
        v = Version("1-")
        self.assertEquals("1-", v.upstream_version)
        self.assertEquals(None, v.debian_version)

    def testRevisionInvalid(self):
        """Version should fail when revision contains a bad character."""
        self.assertRaises(VersionError, Version, "1-!")

    def testValues(self):
        """Version should give same input as output."""
        for value in self.VALUES:
            result = str(Version(value))
            self.assertEquals(value, result)

    def testComparisons(self):
        """Sample Version comparisons should pass."""
        for x, y in self.COMPARISONS:
            self.failUnless(Version(x) < Version(y))

    def testNullEpochIsZero(self):
        """Version should treat an omitted epoch as a zero one."""
        self.assertEquals(Version("1.0"), Version("0:1.0"))

    def notestNullRevisionIsZero(self):
        """Version should treat an omitted revision as being equal to zero.
        """
        self.assertEquals(Version("1.0"), Version("1.0-0"))
        self.failUnless(Version("1.0") == Version("1.0-0"))
