# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Module docstring goes here."""

__metaclass__ = type

from doctest import (
    DocTestSuite,
    ELLIPSIS,
    NORMALIZE_WHITESPACE,
    )
from unittest import TestSuite

from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.systemdocs import (
    setUp,
    tearDown,
    )


def test_suite():
    suite = TestSuite()
    import lp.app.validators.validation
    test = DocTestSuite(
        lp.app.validators.validation,
        setUp=setUp,
        tearDown=tearDown,
        optionflags=ELLIPSIS | NORMALIZE_WHITESPACE
        )
    # We have to invoke the LaunchpadFunctionalLayer in order to
    # initialize the ZCA machinery, which is a pre-requisite for using
    # login().
    test.layer = LaunchpadFunctionalLayer
    suite.addTest(test)
    return suite

if __name__ == '__main__':
    DEFAULT = test_suite()
    import unittest
    unittest.main('DEFAULT')
