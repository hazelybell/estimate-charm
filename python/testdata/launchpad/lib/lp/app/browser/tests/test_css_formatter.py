# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the CSS TALES formatter."""

__metaclass__ = type

from testtools.matchers import Equals

from lp.testing import (
    test_tales,
    TestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestCSSFormatter(TestCase):

    layer = DatabaseFunctionalLayer

    def test_select(self):
        value = test_tales('value/css:select/visible/hidden', value=None)
        self.assertThat(value, Equals('hidden'))
        value = test_tales('value/css:select/visible/hidden', value=False)
        self.assertThat(value, Equals('hidden'))
        value = test_tales('value/css:select/visible/hidden', value='')
        self.assertThat(value, Equals('hidden'))
        value = test_tales('value/css:select/visible/hidden', value=True)
        self.assertThat(value, Equals('visible'))
        value = test_tales('value/css:select/visible/hidden', value='Hello')
        self.assertThat(value, Equals('visible'))
        value = test_tales('value/css:select/visible/hidden', value=object())
        self.assertThat(value, Equals('visible'))

    def test_select_chaining(self):
        value = test_tales(
            'value/css:select/VISIBLE/hidden/fmt:lower', value=None)
        self.assertThat(value, Equals('hidden'))
