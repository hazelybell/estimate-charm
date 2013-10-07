# Copyright 2009 Canonical Ltd.  This software is licensed under the
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

    # Include the doctests in __init__.py.
    from lp.app import validators
    suite.addTest(
        DocTestSuite(validators, optionflags=ELLIPSIS | NORMALIZE_WHITESPACE))

    from lp.app.validators import email, name, url, version
    suite.addTest(suitefor(email))
    suite.addTest(suitefor(name))
    suite.addTest(suitefor(url))
    suite.addTest(suitefor(version))

    return suite


def suitefor(module):
    """Make a doctest suite with common setUp and tearDown functions."""
    suite = DocTestSuite(
        module, setUp=setUp, tearDown=tearDown,
        optionflags=ELLIPSIS | NORMALIZE_WHITESPACE)
    # We have to invoke the LaunchpadFunctionalLayer in order to
    # initialize the ZCA machinery, which is a pre-requisite for using
    # login().
    suite.layer = LaunchpadFunctionalLayer
    return suite


if __name__ == '__main__':
    DEFAULT = test_suite()
    import unittest
    unittest.main('DEFAULT')
