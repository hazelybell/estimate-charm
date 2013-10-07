# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the validators."""

__metaclass__ = type

import unittest

from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


def test_suite():
    suite = unittest.TestSuite()
    test = LayeredDocFileSuite(
        'validation.txt', setUp=setUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer)
    suite.addTest(test)
    return suite


if __name__ == '__main__':
    unittest.main()
