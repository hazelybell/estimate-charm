# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite

from zope.component import getUtility

from lp.testing import (
    ANONYMOUS,
    login,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


def setUp(test):
    test.globs['getUtility'] = getUtility
    login(ANONYMOUS)

def test_suite():
    suite = DocTestSuite('lp.registry.model.projectgroup', setUp=setUp)
    suite.layer = LaunchpadFunctionalLayer
    return suite
