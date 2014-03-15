# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Runs the doctests for buildmaster module."""

__metaclass__ = type


import logging
import os
import unittest

from lp.services.config import config
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setGlobs,
    setUp,
    tearDown,
    )


def buildmasterSetUp(test):
    """Setup a typical builddmaster test environment.

    Log in as ANONYMOUS and perform DB operations as the builddmaster
    dbuser.
    """
    test_dbuser = config.builddmaster.dbuser
    login(ANONYMOUS)
    setGlobs(test)
    test.globs['test_dbuser'] = test_dbuser
    switch_dbuser(test_dbuser)


def buildmasterTearDown(test):
    logout()


special = {
    'builder.txt': LayeredDocFileSuite(
        '../doc/builder.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer),
    'buildqueue.txt': LayeredDocFileSuite(
        '../doc/buildqueue.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer),
    }


def test_suite():
    """Load doctests in this directory.

    Use `LayeredDocFileSuite` with the custom `setUp` and tearDown`,
    suppressed logging messages (only warnings and errors will be posted)
    on `LaunchpadZopelessLayer`.
    """
    suite = unittest.TestSuite()
    tests_dir = os.path.dirname(os.path.realpath(__file__))
    docs_dir = tests_dir + "/../doc"

    # Add special tests that do not use the default buildmaster setup
    # and teardown.
    for key in sorted(special):
        suite.addTest(special[key])

    # Add tests using the default buildmaster setup and teardown.
    filenames = [
        filename
        for filename in os.listdir(docs_dir)
        if filename.lower().endswith('.txt') and filename not in special
        ]

    for filename in sorted(filenames):
        test = LayeredDocFileSuite(
            "../doc/" + filename, setUp=buildmasterSetUp,
            tearDown=buildmasterTearDown,
            stdout_logging_level=logging.WARNING,
            layer=LaunchpadZopelessLayer)
        suite.addTest(test)

    return suite
