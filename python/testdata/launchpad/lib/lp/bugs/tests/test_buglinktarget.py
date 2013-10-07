# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test harness for running the buglinktarget.txt interface test

This module will run the interface test against the CVE, Specification and
Question implementations of that interface.
"""

__metaclass__ = type

__all__ = []

import unittest

from zope.component import getUtility

from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.blueprints.interfaces.specification import ISpecificationSet
from lp.bugs.interfaces.cve import ICveSet
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


def questionSetUp(test):
    setUp(test)
    test.globs['target'] = getUtility(IQuestionSet).get(1)


def cveSetUp(test):
    setUp(test)
    test.globs['target'] = getUtility(ICveSet)['2005-2730']


def specificationSetUp(test):
    setUp(test)
    test.globs['target'] = getUtility(ISpecificationSet).getByURL(
        'http://wiki.mozilla.org/Firefox:1.1_Product_Team')


def test_suite():
    suite = unittest.TestSuite()

    targets = [('cve', cveSetUp),
               ('question', questionSetUp),
               ('specification', specificationSetUp),
               ]

    for name, setUpMethod in targets:
        test = LayeredDocFileSuite(
            'buglinktarget.txt',
            id_extensions=[name],
            setUp=setUpMethod, tearDown=tearDown,
            layer=LaunchpadFunctionalLayer)
        suite.addTest(test)
    return suite


if __name__ == '__main__':
    unittest.main()
