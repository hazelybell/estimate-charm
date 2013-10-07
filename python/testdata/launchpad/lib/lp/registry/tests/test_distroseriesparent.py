# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for DistroSeriesParent model class."""

__metaclass__ = type

from testtools.matchers import MatchesStructure
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.interfaces import Unauthorized

from lp.registry.interfaces.distroseriesparent import (
    IDistroSeriesParent,
    IDistroSeriesParentSet,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.interfaces.component import IComponentSet
from lp.testing import (
    login,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.sampledata import LAUNCHPAD_ADMIN


class TestDistroSeriesParent(TestCaseWithFactory):
    """Test the `DistroSeriesParent` model."""
    layer = ZopelessDatabaseLayer

    def test_verify_interface(self):
        # Test the interface for the model.
        dsp = self.factory.makeDistroSeriesParent()
        verified = verifyObject(IDistroSeriesParent, dsp)
        self.assertTrue(verified)

    def test_properties(self):
        # Test the model properties.
        parent_series = self.factory.makeDistroSeries()
        derived_series = self.factory.makeDistroSeries()
        dsp = self.factory.makeDistroSeriesParent(
            derived_series=derived_series,
            parent_series=parent_series,
            initialized=True)

        self.assertThat(
            dsp,
            MatchesStructure.byEquality(
                derived_series=derived_series,
                parent_series=parent_series,
                initialized=True,
                is_overlay=False,
                component=None,
                pocket=None,
                ))

    def test_properties_overlay(self):
        # Test the model properties if the DSP represents an overlay.
        parent_series = self.factory.makeDistroSeries()
        derived_series = self.factory.makeDistroSeries()
        universe_component = getUtility(IComponentSet).ensure('universe')
        dsp = self.factory.makeDistroSeriesParent(
            derived_series=derived_series,
            parent_series=parent_series,
            initialized=True,
            is_overlay=True,
            component=universe_component,
            pocket=PackagePublishingPocket.SECURITY,
            )

        self.assertThat(
            dsp,
            MatchesStructure.byEquality(
                derived_series=derived_series,
                parent_series=parent_series,
                initialized=True,
                is_overlay=True,
                component=universe_component,
                pocket=PackagePublishingPocket.SECURITY,
                ))

    def test_getByDerivedSeries(self):
        parent_series = self.factory.makeDistroSeries()
        derived_series = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesParent(
            derived_series, parent_series)
        results = getUtility(IDistroSeriesParentSet).getByDerivedSeries(
            derived_series)
        self.assertEqual(1, results.count())
        self.assertEqual(parent_series, results[0].parent_series)

        # Making a second parent should add it to the results.
        self.factory.makeDistroSeriesParent(
            derived_series, self.factory.makeDistroSeries())
        results = getUtility(IDistroSeriesParentSet).getByDerivedSeries(
            derived_series)
        self.assertEqual(2, results.count())

    def test_getByParentSeries(self):
        parent_series = self.factory.makeDistroSeries()
        derived_series = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesParent(
            derived_series, parent_series)
        results = getUtility(IDistroSeriesParentSet).getByParentSeries(
            parent_series)
        self.assertEqual(1, results.count())
        self.assertEqual(derived_series, results[0].derived_series)

        # Making a second child should add it to the results.
        self.factory.makeDistroSeriesParent(
            self.factory.makeDistroSeries(), parent_series)
        results = getUtility(IDistroSeriesParentSet).getByParentSeries(
            parent_series)
        self.assertEqual(2, results.count())


class TestDistroSeriesParentSecurity(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_random_person_is_unauthorized(self):
        dsp = self.factory.makeDistroSeriesParent()
        person = self.factory.makePerson()
        with person_logged_in(person):
            self.assertRaises(
                Unauthorized,
                setattr, dsp, "derived_series", dsp.parent_series)

    def assertCanEdit(self, dsp):
        dsp.initialized = False
        self.assertEquals(False, dsp.initialized)

    def test_distroseries_drivers_can_edit(self):
        # Test that distroseries drivers can edit the data.
        dsp = self.factory.makeDistroSeriesParent()
        person = self.factory.makePerson()
        login(LAUNCHPAD_ADMIN)
        dsp.derived_series.driver = person
        with person_logged_in(person):
            self.assertCanEdit(dsp)

    def test_admins_can_edit(self):
        dsp = self.factory.makeDistroSeriesParent()
        login(LAUNCHPAD_ADMIN)
        self.assertCanEdit(dsp)

    def test_distro_owners_can_edit(self):
        dsp = self.factory.makeDistroSeriesParent()
        person = self.factory.makePerson()
        login(LAUNCHPAD_ADMIN)
        dsp.derived_series.distribution.owner = person
        with person_logged_in(person):
            self.assertCanEdit(dsp)


class TestOverlayTree(TestCaseWithFactory):
    """Test the overlay tree."""

    layer = DatabaseFunctionalLayer

    def test_getFlattenedOverlayTree(self):
        #
        #             series
        #               |
        #    ----------------------------------
        #    |          |          |          |
        #    o          o          |          o
        #    |          |          |          |
        # parent11   parent21   parent31   parent41
        #    |          |
        #    o          o
        #    |          |             type of relation:
        # parent12   parent22          |           |
        #    |                         |           o
        #    |                         |           |
        #    |                       no overlay  overlay
        # parent13
        #
        distroseries = self.factory.makeDistroSeries()
        parent11 = self.factory.makeDistroSeries()
        parent12 = self.factory.makeDistroSeries()
        parent21 = self.factory.makeDistroSeries()
        universe_component = getUtility(IComponentSet).ensure('universe')
        # series -> parent11
        dsp_series_parent11 = self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent11,
            initialized=True, is_overlay=True,
            pocket=PackagePublishingPocket.RELEASE,
            component=universe_component)
        # parent11 -> parent12
        dsp_parent11_parent12 = self.factory.makeDistroSeriesParent(
            derived_series=parent11, parent_series=parent12,
            initialized=True, is_overlay=True,
            pocket=PackagePublishingPocket.RELEASE,
            component=universe_component)
        # parent12 -> parent13
        self.factory.makeDistroSeriesParent(derived_series=parent12,
            initialized=True, is_overlay=False)
        # series -> parent21
        dsp_series_parent21 = self.factory.makeDistroSeriesParent(
            derived_series=distroseries, parent_series=parent21,
            initialized=True, is_overlay=True,
            pocket=PackagePublishingPocket.RELEASE,
            component=universe_component)
        # parent21 -> parent22
        dsp_parent21_parent22 = self.factory.makeDistroSeriesParent(
            derived_series=parent21, initialized=True, is_overlay=True,
            pocket=PackagePublishingPocket.RELEASE,
            component=universe_component)
        # series -> parent31
        self.factory.makeDistroSeriesParent(derived_series=distroseries,
            initialized=True, is_overlay=False)
        # series -> parent41
        dsp_series_parent41 = self.factory.makeDistroSeriesParent(
            derived_series=distroseries, initialized=True, is_overlay=True,
            pocket=PackagePublishingPocket.RELEASE,
            component=universe_component)
        overlays = getUtility(
            IDistroSeriesParentSet).getFlattenedOverlayTree(distroseries)

        self.assertContentEqual(
            [dsp_series_parent11, dsp_parent11_parent12, dsp_series_parent21,
             dsp_parent21_parent22, dsp_series_parent41],
            overlays)

    def test_getFlattenedOverlayTree_empty(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeDistroSeriesParent(derived_series=distroseries,
            initialized=True, is_overlay=False)
        overlays = getUtility(
            IDistroSeriesParentSet).getFlattenedOverlayTree(distroseries)

        self.assertTrue(overlays.is_empty())
