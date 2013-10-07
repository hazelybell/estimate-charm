# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test message documentation."""

__metaclass__ = type

import os

from lp.services.testing import build_test_suite
from lp.testing.layers import LaunchpadFunctionalLayer


here = os.path.dirname(os.path.realpath(__file__))


def test_suite():
    suite = build_test_suite(here, {}, layer=LaunchpadFunctionalLayer)
    return suite
