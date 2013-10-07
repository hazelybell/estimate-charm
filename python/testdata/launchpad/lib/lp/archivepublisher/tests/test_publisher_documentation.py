# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Runs the archivepublisher doctests."""

__metaclass__ = type

import logging
import os
import unittest

from lp.services.config import config
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


def archivePublisherSetUp(test):
    setUp(test)
    switch_dbuser(config.archivepublisher.dbuser)


def test_suite():
    suite = unittest.TestSuite()
    tests_dir = os.path.dirname(os.path.realpath(__file__))

    filenames = [
        filename
        for filename in os.listdir(tests_dir)
        if filename.lower().endswith('.txt')
        ]

    for filename in sorted(filenames):
        test = LayeredDocFileSuite(
            filename, setUp=archivePublisherSetUp, tearDown=tearDown,
            layer=LaunchpadZopelessLayer,
            stdout_logging_level=logging.WARNING)
        suite.addTest(test)

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
