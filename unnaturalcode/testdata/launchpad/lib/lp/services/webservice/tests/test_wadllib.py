# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Run the standalone wadllib tests."""

__metaclass__ = type
__all__ = ['test_suite']


import os
import unittest

import wadllib

from lp.testing.systemdocs import LayeredDocFileSuite


topdir = os.path.dirname(wadllib.__file__)

def test_suite():
    suite = unittest.TestSuite()

    # Find all the doctests in wadllib.
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
        doctest = LayeredDocFileSuite(path, package=wadllib)
        suite.addTest(doctest)

    return suite
