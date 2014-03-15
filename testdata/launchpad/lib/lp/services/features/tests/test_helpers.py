# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the feature flags test helpers."""

__metaclass__ = type
__all__ = []

from lp.services.features import getFeatureFlag
from lp.services.features.testing import FeatureFixture
from lp.testing import (
    layers,
    TestCase,
    )


class TestFeaturesContextManager(TestCase):
    """Tests for the feature flags context manager test helper."""

    layer = layers.DatabaseFunctionalLayer

    def test_setting_one_flag_with_manager(self):
        flag = self.getUniqueString()
        value_outside_manager = getFeatureFlag(flag)
        value_in_manager = None

        with FeatureFixture({flag: u'on'}):
            value_in_manager = getFeatureFlag(flag)

        self.assertEqual(value_in_manager, u'on')
        self.assertEqual(value_outside_manager, getFeatureFlag(flag))
        self.assertNotEqual(value_outside_manager, value_in_manager)


class TestFeaturesFixture(TestCase):
    """Tests for the feature flags test fixture."""

    layer = layers.DatabaseFunctionalLayer

    def test_fixture_sets_one_flag_and_cleans_up_again(self):
        flag = self.getUniqueString()
        value_before_fixture_setup = getFeatureFlag(flag)
        value_after_fixture_setup = None

        fixture = FeatureFixture({flag: 'on'})
        fixture.setUp()
        value_after_fixture_setup = getFeatureFlag(flag)
        fixture.cleanUp()

        self.assertEqual(value_after_fixture_setup, 'on')
        self.assertEqual(value_before_fixture_setup, getFeatureFlag(flag))
        self.assertNotEqual(
            value_before_fixture_setup, value_after_fixture_setup)

    def test_fixture_deletes_existing_values(self):
        self.useFixture(FeatureFixture({'one': '1'}))
        self.useFixture(FeatureFixture({'two': '2'}))

        self.assertEqual(getFeatureFlag('one'), None)
        self.assertEqual(getFeatureFlag('two'), u'2')

    def test_fixture_overrides_previously_set_flags(self):
        self.useFixture(FeatureFixture({'one': '1'}))
        self.useFixture(FeatureFixture({'one': '5'}))

        self.assertEqual(getFeatureFlag('one'), u'5')

    def test_fixture_does_not_set_value_for_flags_that_are_None(self):
        self.useFixture(FeatureFixture({'nothing': None}))
        self.assertEqual(getFeatureFlag('nothing'), None)
