# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Run YUI.test tests."""

__metaclass__ = type
__all__ = []

from lp.testing import (
    build_yui_unittest_suite,
    YUIUnitTestCase,
    )
from lp.testing.layers import YUITestLayer


class BugsYUIUnitTestCase(YUIUnitTestCase):

    layer = YUITestLayer
    suite_name = 'BugsYUIUnitTests'


def test_suite():
    app_testing_path = 'lp/bugs'
    return build_yui_unittest_suite(app_testing_path, BugsYUIUnitTestCase)
