# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test harness for running decoratedresultset.txt."""

__metaclass__ = type

__all__ = []

import unittest

from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


def test_suite():
    suite = unittest.TestSuite()

    test = LayeredDocFileSuite(
        'decoratedresultset.txt',
        setUp=setUp, tearDown=tearDown,
        layer=DatabaseFunctionalLayer)
    suite.addTest(test)
    return suite


if __name__ == '__main__':
    unittest.main()
