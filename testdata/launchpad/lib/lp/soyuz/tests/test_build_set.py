# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.binarypackagebuild import (
    BuildSetStatus,
    IBinaryPackageBuildSet,
    )
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL


class TestBuildSet(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuildSet, self).setUp()
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)
        self.processor_one = self.factory.makeProcessor()
        self.processor_two = self.factory.makeProcessor()
        self.distroseries = self.factory.makeDistroSeries()
        self.distribution = self.distroseries.distribution
        self.das_one = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries, processor=self.processor_one,
            supports_virtualized=True)
        self.das_two = self.factory.makeDistroArchSeries(
            distroseries=self.distroseries, processor=self.processor_two,
            supports_virtualized=True)
        self.archive = self.factory.makeArchive(
            distribution=self.distroseries.distribution,
            purpose=ArchivePurpose.PRIMARY)
        with person_logged_in(self.admin):
            self.publisher = SoyuzTestPublisher()
            self.publisher.prepareBreezyAutotest()
            self.distroseries.nominatedarchindep = self.das_one
            self.publisher.addFakeChroots(distroseries=self.distroseries)
            self.builder_one = self.factory.makeBuilder(
                processor=self.processor_one)
            self.builder_two = self.factory.makeBuilder(
                processor=self.processor_two)
        self.builds = []
        self.spphs = []

    def setUpBuilds(self):
        for i in range(5):
            # Create some test builds
            spph = self.publisher.getPubSource(
                sourcename=self.factory.getUniqueString(),
                version="%s.%s" % (self.factory.getUniqueInteger(), i),
                distroseries=self.distroseries, architecturehintlist='any')
            self.spphs.append(spph)
            builds = spph.createMissingBuilds()
            with person_logged_in(self.admin):
                for b in builds:
                    b.updateStatus(BuildStatus.BUILDING)
                    if i == 4:
                        b.updateStatus(BuildStatus.FAILEDTOBUILD)
                    else:
                        b.updateStatus(BuildStatus.FULLYBUILT)
                    b.buildqueue_record.destroySelf()
            self.builds += builds

    def test_get_for_distro_distribution(self):
        # Test fetching builds for a distro's main archives
        self.setUpBuilds()
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distribution)
        self.assertEquals(set.count(), 10)

    def test_get_for_distro_distroseries(self):
        # Test fetching builds for a distroseries' main archives
        self.setUpBuilds()
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distroseries)
        self.assertEquals(set.count(), 10)

    def test_get_for_distro_distroarchseries(self):
        # Test fetching builds for a distroarchseries' main archives
        self.setUpBuilds()
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.das_one)
        self.assertEquals(set.count(), 5)

    def test_get_for_distro_filter_build_status(self):
        # The result can be filtered based on the build status
        self.setUpBuilds()
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distribution, status=BuildStatus.FULLYBUILT)
        self.assertEquals(set.count(), 8)

    def test_get_for_distro_filter_name(self):
        # The result can be filtered based on the name
        self.setUpBuilds()
        spn = self.builds[2].source_package_release.sourcepackagename.name
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distribution, name=spn)
        self.assertEquals(set.count(), 2)

    def test_get_for_distro_filter_pocket(self):
        # The result can be filtered based on the pocket of the build
        self.setUpBuilds()
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distribution, pocket=PackagePublishingPocket.RELEASE)
        self.assertEquals(set.count(), 10)
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distribution, pocket=PackagePublishingPocket.UPDATES)
        self.assertEquals(set.count(), 0)

    def test_get_for_distro_filter_arch_tag(self):
        # The result can be filtered based on the archtag of the build
        self.setUpBuilds()
        set = getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self.distribution, arch_tag=self.das_one.architecturetag)
        self.assertEquals(set.count(), 5)

    def test_get_status_summary_for_builds(self):
        # We can query for the status summary of a number of builds
        self.setUpBuilds()
        relevant_builds = [self.builds[0], self.builds[2], self.builds[-2]]
        summary = getUtility(
            IBinaryPackageBuildSet).getStatusSummaryForBuilds(
                relevant_builds)
        self.assertEquals(summary['status'], BuildSetStatus.FAILEDTOBUILD)
        self.assertEquals(summary['builds'], [self.builds[-2]])

    def test_preload_data(self):
        # The BuildSet class allows data to be preloaded
        # Note, it is an internal method, so we have to push past the security
        # proxy
        self.setUpBuilds()
        build_ids = [self.builds[i] for i in (0, 1, 2, 3)]
        rset = removeSecurityProxy(
            getUtility(IBinaryPackageBuildSet))._prefetchBuildData(build_ids)
        self.assertEquals(len(rset), 4)

    def test_get_builds_by_source_package_release(self):
        # We are able to return all of the builds for the source package
        # release ids passed in.
        self.setUpBuilds()
        spphs = self.spphs[:2]
        ids = [spph.sourcepackagerelease.id for spph in spphs]
        builds = getUtility(
            IBinaryPackageBuildSet).getBuildsBySourcePackageRelease(ids)
        expected_titles = []
        for spph in spphs:
            for das in (self.das_one, self.das_two):
                expected_titles.append(
                    '%s build of %s %s in %s %s RELEASE' % (
                        das.architecturetag, spph.source_package_name,
                        spph.source_package_version,
                        self.distroseries.distribution.name,
                        self.distroseries.name))
        build_titles = [build.title for build in builds]
        self.assertEquals(sorted(expected_titles), sorted(build_titles))

    def test_get_builds_by_source_package_release_filtering(self):
        self.setUpBuilds()
        ids = [self.spphs[-1].sourcepackagerelease.id]
        builds = getUtility(
            IBinaryPackageBuildSet).getBuildsBySourcePackageRelease(
                ids, buildstate=BuildStatus.FAILEDTOBUILD)
        expected_titles = []
        for das in (self.das_one, self.das_two):
            expected_titles.append(
                '%s build of %s %s in %s %s RELEASE' % (
                    das.architecturetag, self.spphs[-1].source_package_name,
                    self.spphs[-1].source_package_version,
                    self.distroseries.distribution.name,
                    self.distroseries.name))
        build_titles = [build.title for build in builds]
        self.assertEquals(sorted(expected_titles), sorted(build_titles))
        builds = getUtility(
            IBinaryPackageBuildSet).getBuildsBySourcePackageRelease(
                ids, buildstate=BuildStatus.CHROOTWAIT)
        self.assertEquals([], list(builds))

    def test_no_get_builds_by_source_package_release(self):
        # If no ids or None are passed into .getBuildsBySourcePackageRelease,
        # an empty list is returned.
        builds = getUtility(
            IBinaryPackageBuildSet).getBuildsBySourcePackageRelease(None)
        self.assertEquals([], builds)
        builds = getUtility(
            IBinaryPackageBuildSet).getBuildsBySourcePackageRelease([])
        self.assertEquals([], builds)
