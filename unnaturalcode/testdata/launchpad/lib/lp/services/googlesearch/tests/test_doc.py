# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests.
"""

import os

from lp.services.testing import build_test_suite
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    GoogleLaunchpadFunctionalLayer,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))


special = {
    'google-searchservice.txt': LayeredDocFileSuite(
        '../doc/google-searchservice.txt',
        setUp=setUp, tearDown=tearDown,
        layer=GoogleLaunchpadFunctionalLayer,),
    # XXX gary 2008-12-08 bug=306246 bug=305858: Disabled test because of
    # multiple spurious problems with layer and test.
    # 'google-service-stub.txt': LayeredDocFileSuite(
    #     '../doc/google-service-stub.txt',
    #     layer=GoogleServiceLayer,),
    }


def test_suite():
    suite = build_test_suite(here, special, layer=DatabaseFunctionalLayer)
    return suite
