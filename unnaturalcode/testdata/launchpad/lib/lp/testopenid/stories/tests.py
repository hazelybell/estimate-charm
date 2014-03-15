# Copyright 2004-2008 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import os
import unittest

from lp.testing.pages import PageTestSuite


here = os.path.dirname(os.path.realpath(__file__))


def test_suite():
    stories = sorted(
        dir for dir in os.listdir(here)
        if not dir.startswith('.') and os.path.isdir(os.path.join(here, dir)))

    suite = unittest.TestSuite()
    suite.addTest(PageTestSuite('.'))
    for storydir in stories:
        suite.addTest(PageTestSuite(storydir))

    return suite
