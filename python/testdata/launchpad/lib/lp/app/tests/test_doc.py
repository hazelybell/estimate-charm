# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

import os

from lp.services.testing import build_test_suite
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))

special = {
    'tales.txt': LayeredDocFileSuite(
        '../doc/tales.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'menus.txt': LayeredDocFileSuite(
        '../doc/menus.txt', layer=None,
        ),
    }


def test_suite():
    return build_test_suite(here, special)
