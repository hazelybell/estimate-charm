# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the view tests.
"""

import logging
import os
import unittest

from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))

# The default layer of view tests is the DatabaseFunctionalLayer. Tests
# that require something special like the librarian, memcaches, or mailman
# must run on a layer that sets those services up.
special_test_layer = {
    'distribution-views.txt': LaunchpadFunctionalLayer,
    'distributionsourcepackage-views.txt': LaunchpadFunctionalLayer,
    'gpg-views.txt': LaunchpadFunctionalLayer,
    'karmacontext-views.txt': LaunchpadFunctionalLayer,
    'mailinglist-message-views.txt': LaunchpadFunctionalLayer,
    'milestone-views.txt': LaunchpadFunctionalLayer,
    'person-views.txt': LaunchpadFunctionalLayer,
    'product-edit-people-view.txt': LaunchpadFunctionalLayer,
    'product-files-views.txt': LaunchpadFunctionalLayer,
    'product-views.txt': LaunchpadFunctionalLayer,
    'productseries-views.txt': LaunchpadFunctionalLayer,
    'projectgroup-views.txt': LaunchpadFunctionalLayer,
    'user-to-user-views.txt': LaunchpadFunctionalLayer,
}


def test_suite():
    suite = unittest.TestSuite()
    testsdir = os.path.abspath(here)

    # Add tests using default setup/teardown
    filenames = [filename
                 for filename in os.listdir(testsdir)
                 if filename.endswith('.txt')]
    # Sort the list to give a predictable order.
    filenames.sort()
    for filename in filenames:
        path = filename
        layer = special_test_layer.get(path, DatabaseFunctionalLayer)
        one_test = LayeredDocFileSuite(
            path, setUp=setUp, tearDown=tearDown, layer=layer,
            stdout_logging_level=logging.WARNING)
        suite.addTest(one_test)

    return suite
