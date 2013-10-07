# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test generic override policy classes."""

from operator import attrgetter

from testtools.matchers import Equals
from zope.component import getUtility

from lp.services.database import bulk
from lp.services.database.sqlbase import flush_database_caches
from lp.soyuz.adapters.overrides import (
    BinaryOverride,
    FromExistingOverridePolicy,
    SourceOverride,
    UbuntuOverridePolicy,
    UnknownOverridePolicy,
    )
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.component import IComponentSet
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.matchers import HasQueryCount


class TestOverrides(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_no_source_overrides(self):
        # If the spn is not published in the given archive/distroseries, an
        # empty list is returned.
        spn = self.factory.makeSourcePackageName()
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        policy = FromExistingOverridePolicy()
        overrides = policy.calculateSourceOverrides(
            distroseries.main_archive, distroseries, pocket, (spn,))
        self.assertEqual([], overrides)

    def test_source_overrides(self):
        # When the spn is published in the given archive/distroseries, the
        # overrides for that archive/distroseries are returned.
        spph = self.factory.makeSourcePackagePublishingHistory()
        policy = FromExistingOverridePolicy()
        overrides = policy.calculateSourceOverrides(
            spph.distroseries.main_archive, spph.distroseries, spph.pocket,
            (spph.sourcepackagerelease.sourcepackagename,))
        expected = [SourceOverride(
            spph.sourcepackagerelease.sourcepackagename,
            spph.component, spph.section)]
        self.assertEqual(expected, overrides)

    def test_source_overrides_latest_only_is_returned(self):
        # When the spn is published multiple times in the given
        # archive/distroseries, the latest publication's overrides are
        # returned.
        spn = self.factory.makeSourcePackageName()
        distroseries = self.factory.makeDistroSeries()
        published_spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=spn)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=published_spr, distroseries=distroseries,
            status=PackagePublishingStatus.PUBLISHED)
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=spn)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, distroseries=distroseries)
        policy = FromExistingOverridePolicy()
        overrides = policy.calculateSourceOverrides(
            distroseries.main_archive, distroseries, spph.pocket, (spn,))
        self.assertEqual(
            [SourceOverride(spn, spph.component, spph.section)], overrides)

    def test_source_overrides_constant_query_count(self):
        # The query count is constant, no matter how many sources are
        # checked.
        spns = []
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        for i in xrange(10):
            spph = self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries, archive=distroseries.main_archive,
                pocket=pocket)
            spns.append(spph.sourcepackagerelease.sourcepackagename)
        flush_database_caches()
        distroseries.main_archive
        bulk.reload(spns)
        policy = FromExistingOverridePolicy()
        with StormStatementRecorder() as recorder:
            policy.calculateSourceOverrides(
                spph.distroseries.main_archive, spph.distroseries,
                spph.pocket, spns)
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_no_binary_overrides(self):
        # if the given binary is not published in the given distroarchseries,
        # an empty list is returned.
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(distroseries=distroseries)
        distroseries.nominatedarchindep = das
        bpn = self.factory.makeBinaryPackageName()
        pocket = self.factory.getAnyPocket()
        policy = FromExistingOverridePolicy()
        overrides = policy.calculateBinaryOverrides(
            distroseries.main_archive, distroseries, pocket, ((bpn, None),))
        self.assertEqual([], overrides)

    def test_binary_overrides(self):
        # When a binary is published in the given distroarchseries, the
        # overrides are returned.
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        distroseries = bpph.distroarchseries.distroseries
        distroseries.nominatedarchindep = bpph.distroarchseries
        policy = FromExistingOverridePolicy()
        overrides = policy.calculateBinaryOverrides(
            distroseries.main_archive, distroseries, bpph.pocket,
            ((bpph.binarypackagerelease.binarypackagename, None),))
        expected = [
            BinaryOverride(
                bpph.binarypackagerelease.binarypackagename,
                bpph.distroarchseries, bpph.component, bpph.section,
                bpph.priority, None)]
        self.assertEqual(expected, overrides)

    def test_binary_overrides_constant_query_count(self):
        # The query count is constant, no matter how many bpn-das pairs are
        # checked.
        bpns = []
        distroarchseries = self.factory.makeDistroArchSeries()
        distroseries = distroarchseries.distroseries
        distroseries.nominatedarchindep = distroarchseries
        pocket = self.factory.getAnyPocket()
        for i in xrange(10):
            bpph = self.factory.makeBinaryPackagePublishingHistory(
                distroarchseries=distroarchseries,
                archive=distroseries.main_archive, pocket=pocket)
            bpns.append((bpph.binarypackagerelease.binarypackagename, None))
        flush_database_caches()
        distroseries.main_archive
        bulk.reload(bpn[0] for bpn in bpns)
        policy = FromExistingOverridePolicy()
        with StormStatementRecorder() as recorder:
            policy.calculateBinaryOverrides(
                distroseries.main_archive, distroseries, pocket, bpns)
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_getComponentOverride_default_name(self):
        # getComponentOverride returns the default component name when an
        # unknown component name is passed.
        component_name = UnknownOverridePolicy.getComponentOverride('no-name')

        self.assertEqual('universe', component_name)

    def test_getComponentOverride_default_component(self):
        # getComponentOverride also accepts a component object (as
        # opposed to a component's name).
        component = getUtility(IComponentSet)['universe']
        component_name = UnknownOverridePolicy.getComponentOverride(component)

        self.assertEqual('universe', component_name)

    def test_getComponentOverride_return_component(self):
        # Passing return_component=True to getComponentOverride makes it
        # return the Component object (as opposed to the component's
        # name).
        universe_component = getUtility(IComponentSet)['universe']
        component = UnknownOverridePolicy.getComponentOverride(
            universe_component, return_component=True)

        self.assertEqual(universe_component, component)

    def test_unknown_sources(self):
        # If the unknown policy is used, it does no checks, just returns the
        # defaults.
        spph = self.factory.makeSourcePackagePublishingHistory()
        policy = UnknownOverridePolicy()
        overrides = policy.calculateSourceOverrides(
            spph.distroseries.main_archive, spph.distroseries, spph.pocket,
            (spph.sourcepackagerelease.sourcepackagename,))
        universe = getUtility(IComponentSet)['universe']
        expected = [
            SourceOverride(
                spph.sourcepackagerelease.sourcepackagename, universe,
                None)]
        self.assertEqual(expected, overrides)

    def test_unknown_binaries(self):
        # If the unknown policy is used, it does no checks, just returns the
        # defaults.
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        distroseries = bpph.distroarchseries.distroseries
        distroseries.nominatedarchindep = bpph.distroarchseries
        policy = UnknownOverridePolicy()
        overrides = policy.calculateBinaryOverrides(
            distroseries.main_archive, distroseries, bpph.pocket,
            ((bpph.binarypackagerelease.binarypackagename, None),))
        universe = getUtility(IComponentSet)['universe']
        expected = [
            BinaryOverride(
                bpph.binarypackagerelease.binarypackagename,
                bpph.distroarchseries, universe, None, None, None)]
        self.assertEqual(expected, overrides)

    def test_ubuntu_override_policy_sources(self):
        # The Ubuntu policy incorporates both the existing and the unknown
        # policy.
        universe = getUtility(IComponentSet)['universe']
        spns = [self.factory.makeSourcePackageName()]
        expected = [SourceOverride(spns[0], universe, None)]
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        for i in xrange(8):
            spph = self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries, archive=distroseries.main_archive,
                pocket=pocket)
            spns.append(spph.sourcepackagerelease.sourcepackagename)
            expected.append(
                SourceOverride(
                    spph.sourcepackagerelease.sourcepackagename,
                    spph.component, spph.section))
        spns.append(self.factory.makeSourcePackageName())
        expected.append(SourceOverride(spns[-1], universe, None))
        policy = UbuntuOverridePolicy()
        overrides = policy.calculateSourceOverrides(
            distroseries.main_archive, distroseries, pocket, spns)
        self.assertEqual(10, len(overrides))
        sorted_expected = sorted(
            expected, key=attrgetter("source_package_name.name"))
        sorted_overrides = sorted(
            overrides, key=attrgetter("source_package_name.name"))
        self.assertEqual(sorted_expected, sorted_overrides)

    def test_ubuntu_override_policy_binaries(self):
        # The Ubuntu policy incorporates both the existing and the unknown
        # policy.
        universe = getUtility(IComponentSet)['universe']
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        bpn = self.factory.makeBinaryPackageName()
        bpns = []
        expected = []
        for i in xrange(3):
            distroarchseries = self.factory.makeDistroArchSeries(
                distroseries=distroseries)
            bpb = self.factory.makeBinaryPackageBuild(
                distroarchseries=distroarchseries)
            bpr = self.factory.makeBinaryPackageRelease(
                build=bpb, binarypackagename=bpn,
                architecturespecific=True)
            bpph = self.factory.makeBinaryPackagePublishingHistory(
                binarypackagerelease=bpr, distroarchseries=distroarchseries,
                archive=distroseries.main_archive, pocket=pocket)
            bpns.append((bpn, distroarchseries.architecturetag))
            expected.append(
                BinaryOverride(
                    bpn, distroarchseries, bpph.component, bpph.section,
                    bpph.priority, None))
        for i in xrange(2):
            distroarchseries = self.factory.makeDistroArchSeries(
                distroseries=distroseries)
            bpns.append((bpn, distroarchseries.architecturetag))
            expected.append(
                BinaryOverride(
                    bpn, distroarchseries, universe, None, None, None))
        distroseries.nominatedarchindep = distroarchseries
        policy = UbuntuOverridePolicy()
        overrides = policy.calculateBinaryOverrides(
            distroseries.main_archive, distroseries, pocket, bpns)
        self.assertEqual(5, len(overrides))
        key = attrgetter("binary_package_name.name",
            "distro_arch_series.architecturetag",
            "component.name")
        sorted_expected = sorted(expected, key=key)
        sorted_overrides = sorted(overrides, key=key)
        self.assertEqual(sorted_expected, sorted_overrides)

    def test_calculateBinaryOverrides_skips_unknown_arch(self):
        # If calculateBinaryOverrides is passed with an archtag that
        # does not correspond to an ArchSeries of the distroseries,
        # an empty list is returned.
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(
            architecturetag='amd64',
            distroseries=distroseries)
        distroseries.nominatedarchindep = das
        bpn = self.factory.makeBinaryPackageName()
        pocket = self.factory.getAnyPocket()
        policy = FromExistingOverridePolicy()
        overrides = policy.calculateBinaryOverrides(
            distroseries.main_archive, distroseries, pocket, ((bpn, 'i386'),))

        self.assertEqual([], overrides)

    def test_phased_update_percentage(self):
        # A policy with a phased_update_percentage applies it to new binary
        # overrides.
        universe = getUtility(IComponentSet)['universe']
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        bpn = self.factory.makeBinaryPackageName()
        bpns = []
        expected = []
        distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=distroseries)
        bpb = self.factory.makeBinaryPackageBuild(
            distroarchseries=distroarchseries)
        bpr = self.factory.makeBinaryPackageRelease(
            build=bpb, binarypackagename=bpn, architecturespecific=True)
        bpph = self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr, distroarchseries=distroarchseries,
            archive=distroseries.main_archive, pocket=pocket)
        bpns.append((bpn, distroarchseries.architecturetag))
        expected.append(
            BinaryOverride(
                bpn, distroarchseries, bpph.component, bpph.section,
                bpph.priority, 50))
        distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=distroseries)
        bpns.append((bpn, distroarchseries.architecturetag))
        expected.append(
            BinaryOverride(bpn, distroarchseries, universe, None, None, 50))
        distroseries.nominatedarchindep = distroarchseries
        policy = UbuntuOverridePolicy(phased_update_percentage=50)
        overrides = policy.calculateBinaryOverrides(
            distroseries.main_archive, distroseries, pocket, bpns)
        self.assertEqual(2, len(overrides))
        key = attrgetter("binary_package_name.name",
            "distro_arch_series.architecturetag",
            "component.name")
        sorted_expected = sorted(expected, key=key)
        sorted_overrides = sorted(overrides, key=key)
        self.assertEqual(sorted_expected, sorted_overrides)
