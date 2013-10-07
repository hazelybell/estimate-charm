# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

import os
import unittest

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.projectgroup import IProjectGroupSet
from lp.services.mail.tests.test_doc import ProcessMailLayer
from lp.services.testing import build_test_suite
from lp.testing import (
    ANONYMOUS,
    login,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))


def productSetUp(test):
    """Test environment for product."""
    setUp(test)
    thunderbird = getUtility(IProductSet).getByName('thunderbird')
    test.globs['target'] = thunderbird
    test.globs['collection'] = thunderbird
    login('foo.bar@canonical.com')
    test.globs['newFAQ'] = thunderbird.newFAQ
    login(ANONYMOUS)


def distributionSetUp(test):
    """Test environment for distribution."""
    setUp(test)
    kubuntu = getUtility(IDistributionSet).getByName('kubuntu')
    test.globs['target'] = kubuntu
    test.globs['collection'] = kubuntu
    login('foo.bar@canonical.com')
    test.globs['newFAQ'] = kubuntu.newFAQ
    login(ANONYMOUS)


def projectSetUp(test):
    """Test environment for project."""
    setUp(test)
    gnome_project = getUtility(IProjectGroupSet).getByName('gnome')
    products_queue = list(gnome_project.products)

    def newFAQ(owner, title, content, keywords=None, date_created=None):
        """Create a new FAQ on each project's product in turn."""
        product = products_queue.pop(0)
        products_queue.append(product)
        return product.newFAQ(
            owner, title, content, keywords=keywords,
            date_created=date_created)

    test.globs['collection'] = gnome_project
    test.globs['newFAQ'] = newFAQ


def sourcepackageSetUp(test):
    setUp(test)
    ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['target'] = ubuntu.currentseries.getSourcePackage('evolution')


def distributionsourcepackageSetUp(test):
    setUp(test)
    ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['target'] = ubuntu.getSourcePackage('evolution')


def create_interface_test_suite(test_file, targets):
    """Create a test suite for an interface test using several fixtures."""

    suite = unittest.TestSuite()
    for name, setup_func in targets:
        test_path = os.path.join(os.path.pardir, 'doc', test_file)
        id_ext = "%s-%s" % (test_file, name)
        test = LayeredDocFileSuite(
            test_path,
            id_extensions=[id_ext],
            setUp=setup_func, tearDown=tearDown,
            layer=DatabaseFunctionalLayer)
        suite.addTest(test)
    return suite


special = {
    'questiontarget.txt': create_interface_test_suite(
        'questiontarget.txt',
        [('product', productSetUp),
         ('distribution', distributionSetUp),
         ('distributionsourcepackage', distributionsourcepackageSetUp),
         ]),

    'faqtarget.txt': create_interface_test_suite(
        'faqtarget.txt',
        [('product', productSetUp),
         ('distribution', distributionSetUp),
         ]),

    'faqcollection.txt': create_interface_test_suite(
        'faqcollection.txt',
        [('product', productSetUp),
         ('distribution', distributionSetUp),
         ('project', projectSetUp),
         ]),
    'emailinterface.txt': LayeredDocFileSuite(
        'emailinterface.txt',
        setUp=setUp, tearDown=tearDown,
        layer=ProcessMailLayer,
        stdout_logging=False)
    }


def test_suite():
    return build_test_suite(here, special)
