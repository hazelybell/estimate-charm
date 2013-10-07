# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Runn test_logger.txt."""

__metaclass__ = type
__all__ = []

import doctest
from sys import exc_info
import unittest

from testtools.matchers import DocTestMatches

from lp.services.scripts.logger import LaunchpadFormatter
from lp.services.utils import traceback_info
from lp.testing import TestCase
from lp.testing.layers import BaseLayer
from lp.testing.systemdocs import LayeredDocFileSuite


DOCTEST_FLAGS = (
    doctest.ELLIPSIS |
    doctest.NORMALIZE_WHITESPACE |
    doctest.REPORT_NDIFF)


class TestLaunchpadFormatter(TestCase):
    """Tests of `LaunchpadFormatter`."""

    def test_traceback_info(self):
        # LaunchpadFormatter inherits from zope.exceptions.log.Formatter, so
        # __traceback_info__ annotations are included in formatted exceptions.

        traceback_info("Captain Kirk")

        try:
            0/0
        except ZeroDivisionError:
            info = exc_info()

        self.assertThat(
            LaunchpadFormatter().formatException(info),
            DocTestMatches(
                flags=DOCTEST_FLAGS, example="""
                    Traceback (most recent call last):
                    ...
                    __traceback_info__: Captain Kirk
                    ZeroDivisionError: ...
                    """))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(
        LayeredDocFileSuite(
            'test_logger.txt', layer=BaseLayer))
    suite.addTest(
        unittest.TestLoader().loadTestsFromName(__name__))
    return suite
