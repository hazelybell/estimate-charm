# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Run the standalone tests in an opensource package.

XXX BarryWarsaw 14-May-2008: This shim is here so that the tests within the
launchpadlib and wadllib packages (living in the opensource directory) will
run as part of Launchpad's standard test suite.  Those tests cannot yet be run
on their own, since they require a running Launchpad appserver, but not the
real Launchpad!.  Eventually, there will be mock objects in the packages' test
suites so that they can be run on their own outside the Launchpad development
environment.
"""

__metaclass__ = type
__all__ = ['test_suite']


import logging
import os
import unittest

import launchpadlib
import wadllib

from lp.testing.layers import AppServerLayer
from lp.testing.systemdocs import LayeredDocFileSuite


def add_testable_opensource_package(suite, package):
    """Sniff out all the doctests in `package` and add them to `suite`."""
    topdir = os.path.dirname(package.__file__)

    packages = []
    for dirpath, dirnames, filenames in os.walk(topdir):
        if 'docs' in dirnames:
            docsdir = os.path.join(dirpath, 'docs')[len(topdir)+1:]
            packages.append(docsdir)
    doctest_files = {}
    for docsdir in packages:
        for filename in os.listdir(os.path.join(topdir, docsdir)):
            if os.path.splitext(filename)[1] == '.txt':
                doctest_files[filename] = os.path.join(docsdir, filename)
    # Sort the tests.
    for filename in sorted(doctest_files):
        path = doctest_files[filename]
        doctest = LayeredDocFileSuite(
            path, package=package, layer=AppServerLayer,
            stdout_logging_level=logging.WARNING)
        suite.addTest(doctest)


def test_suite():
    suite = unittest.TestSuite()
    add_testable_opensource_package(suite, launchpadlib)
    add_testable_opensource_package(suite, wadllib)
    return suite
