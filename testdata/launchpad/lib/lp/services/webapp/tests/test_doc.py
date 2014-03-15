# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

__metaclass__ = type

import os

from lp.services.testing import build_test_suite
from lp.services.webapp.tests import test_notifications
from lp.testing.layers import (
    FunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))


special = {
    'canonical_url.txt': LayeredDocFileSuite(
        '../doc/canonical_url.txt',
        setUp=setUp, tearDown=tearDown,
        layer=FunctionalLayer,),
    'notification-text-escape.txt': LayeredDocFileSuite(
        '../doc/notification-text-escape.txt',
        setUp=test_notifications.setUp,
        tearDown=test_notifications.tearDown,
        stdout_logging=False, layer=None),
    'test_adapter.txt': LayeredDocFileSuite(
        '../doc/test_adapter.txt',
        layer=LaunchpadFunctionalLayer),
# XXX Julian 2009-05-13, bug=376171
# Temporarily disabled because of intermittent failures.
#    'test_adapter_timeout.txt': LayeredDocFileSuite(
#        '../doc/test_adapter_timeout.txt',
#        setUp=setUp,
#        tearDown=tearDown,
#        layer=LaunchpadFunctionalLayer),
    'test_adapter_permissions.txt': LayeredDocFileSuite(
        '../doc/test_adapter_permissions.txt',
        layer=LaunchpadFunctionalLayer),
    'uri.txt': LayeredDocFileSuite(
        '../doc/uri.txt',
        setUp=setUp, tearDown=tearDown,
        layer=FunctionalLayer),
    }


def test_suite():
    return build_test_suite(here, special, layer=LaunchpadFunctionalLayer)
