# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

import logging
import os
import unittest

from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.pages import PageTestSuite
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))


special = {
    'poexport-queue.txt': LayeredDocFileSuite(
        '../doc/poexport-queue.txt',
        setUp=setUp, tearDown=tearDown, layer=LaunchpadFunctionalLayer
        ),
    'translationimportqueue.txt': LayeredDocFileSuite(
        '../doc/translationimportqueue.txt',
        setUp=setUp, tearDown=tearDown, layer=LaunchpadFunctionalLayer
        ),
    'rosetta-karma.txt': LayeredDocFileSuite(
        '../doc/rosetta-karma.txt',
        setUp=setUp, tearDown=tearDown, layer=LaunchpadFunctionalLayer
        ),
    'translationmessage-destroy.txt': LayeredDocFileSuite(
        '../doc/translationmessage-destroy.txt',
        layer=LaunchpadZopelessLayer
        ),
    'translationsoverview.txt': LayeredDocFileSuite(
        '../doc/translationsoverview.txt',
        layer=LaunchpadZopelessLayer
        ),
    }


def test_suite():
    suite = unittest.TestSuite()

    stories_dir = os.path.join(os.path.pardir, 'stories')
    suite.addTest(PageTestSuite(stories_dir))
    stories_path = os.path.join(here, stories_dir)
    for story_dir in os.listdir(stories_path):
        full_story_dir = os.path.join(stories_path, story_dir)
        if not os.path.isdir(full_story_dir):
            continue
        story_path = os.path.join(stories_dir, story_dir)
        suite.addTest(PageTestSuite(story_path))

    testsdir = os.path.abspath(
        os.path.normpath(os.path.join(here, os.path.pardir, 'doc')))

    # Add special needs tests
    for key in sorted(special):
        special_suite = special[key]
        suite.addTest(special_suite)

    # Add tests using default setup/teardown
    filenames = [filename
                 for filename in os.listdir(testsdir)
                 if filename.endswith('.txt') and filename not in special]
    # Sort the list to give a predictable order.
    filenames.sort()
    for filename in filenames:
        path = os.path.join('../doc/', filename)
        one_test = LayeredDocFileSuite(
            path, setUp=setUp, tearDown=tearDown,
            layer=LaunchpadFunctionalLayer,
            stdout_logging_level=logging.WARNING)
        suite.addTest(one_test)

    return suite
