# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import os

from lp.testing.systemdocs import LayeredDocFileSuite

# The setUp() and tearDown() functions ensure that this doctest is not umask
# dependent.
def setUp(testobj):
    testobj._old_umask = os.umask(022)


def tearDown(testobj):
    os.umask(testobj._old_umask)


def test_suite():
    return LayeredDocFileSuite(
        "filesystem.txt",
        setUp=setUp, tearDown=tearDown, stdout_logging=False)
