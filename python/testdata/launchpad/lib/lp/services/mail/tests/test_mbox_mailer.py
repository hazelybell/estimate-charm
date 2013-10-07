# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test harness for running the mbox_mailer.txt tests."""

import doctest
import os
import tempfile

from zope.testing.cleanup import cleanUp

from lp.testing.systemdocs import LayeredDocFileSuite


def setup(testobj):
    """Set up for doc test"""
    fd, mbox_filename = tempfile.mkstemp()
    os.close(fd)
    testobj.globs['mbox_filename'] = mbox_filename
    fd, chained_filename = tempfile.mkstemp()
    os.close(fd)
    testobj.globs['chained_filename'] = chained_filename


def teardown(testobj):
    os.remove(testobj.globs['mbox_filename'])
    os.remove(testobj.globs['chained_filename'])
    cleanUp()


def test_suite():
    return LayeredDocFileSuite(
        'mbox_mailer.txt',
        setUp=setup, tearDown=teardown,
        optionflags=doctest.ELLIPSIS, stdout_logging=False)
