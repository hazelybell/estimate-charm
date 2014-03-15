# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

import logging
import os

import transaction

from lp.registry.tests import mailinglists_helper
from lp.services.testing import (
    build_doctest_suite,
    build_test_suite,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    DatabaseLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))


def peopleKarmaTearDown(test):
    """Restore the database after testing karma."""
    # We can't detect db changes made by the subprocess (yet).
    DatabaseLayer.force_dirty_database()
    tearDown(test)

special = {
    'distribution-mirror.txt': LayeredDocFileSuite(
        '../doc/distribution-mirror.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'person-karma.txt': LayeredDocFileSuite(
        '../doc/person-karma.txt',
        setUp=setUp, tearDown=peopleKarmaTearDown,
        layer=LaunchpadFunctionalLayer,
        stdout_logging_level=logging.WARNING
        ),
    'product.txt': LayeredDocFileSuite(
        '../doc/product.txt',
        setUp=setUp,
        tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'private-team-roles.txt': LayeredDocFileSuite(
        '../doc/private-team-roles.txt',
        setUp=setUp,
        tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'productrelease.txt': LayeredDocFileSuite(
        '../doc/productrelease.txt',
        setUp=setUp,
        tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'productrelease-file-download.txt': LayeredDocFileSuite(
        '../doc/productrelease-file-download.txt',
        setUp=setUp,
        tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'standing.txt': LayeredDocFileSuite(
        '../doc/standing.txt',
        layer=LaunchpadZopelessLayer,
        setUp=setUp, tearDown=tearDown,
        ),
    'karmacache.txt': LayeredDocFileSuite(
        '../doc/karmacache.txt',
        layer=LaunchpadZopelessLayer,
        setUp=setUp, tearDown=tearDown),
    'sourcepackage.txt': LayeredDocFileSuite(
        '../doc/sourcepackage.txt',
        layer=LaunchpadFunctionalLayer,
        setUp=setUp, tearDown=tearDown),
    'distribution-sourcepackage.txt': LayeredDocFileSuite(
        '../doc/distribution-sourcepackage.txt',
        layer=LaunchpadZopelessLayer,
        setUp=setUp, tearDown=tearDown),
    }


def test_suite():
    suite = build_test_suite(here, special, layer=DatabaseFunctionalLayer)
    launchpadlib_path = os.path.join(os.path.pardir, 'doc', 'launchpadlib')
    lplib_suite = build_doctest_suite(here, launchpadlib_path,
                                      layer=DatabaseFunctionalLayer)
    suite.addTest(lplib_suite)
    return suite
