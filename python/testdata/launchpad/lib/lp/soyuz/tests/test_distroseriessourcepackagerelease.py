# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for DistroSeriesSourcePackageRelease."""

from storm.store import Store
from testtools.matchers import Equals

from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.model.distroseriessourcepackagerelease import (
    DistroSeriesSourcePackageRelease,
    )
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount


class TestDistroSeriesSourcePackageRelease(TestCaseWithFactory):
    """Tests for DistroSeriesSourcePackageRelease."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroSeriesSourcePackageRelease, self).setUp()
        self.sourcepackagerelease = self.factory.makeSourcePackageRelease()
        self.distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=self.sourcepackagerelease.sourcepackage.distroseries)
        self.dssp_release = DistroSeriesSourcePackageRelease(
            self.distroarchseries.distroseries, self.sourcepackagerelease)

    def makeBinaryPackageRelease(self, name=None):
        if name is None:
            name = self.factory.makeBinaryPackageName()
        bp_build = self.factory.makeBinaryPackageBuild(
            source_package_release=self.sourcepackagerelease,
            distroarchseries=self.distroarchseries)
        bp_release = self.factory.makeBinaryPackageRelease(
            build=bp_build, binarypackagename=name,
            version=self.factory.getUniqueString())
        sourcepackagename = self.sourcepackagerelease.sourcepackagename
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackagename,
            sourcepackagerelease=self.sourcepackagerelease,
            distroseries=self.sourcepackagerelease.sourcepackage.distroseries,
            status=PackagePublishingStatus.PUBLISHED)
        self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bp_release,
            distroarchseries=self.distroarchseries)
        return bp_release

    def test_binaries__no_releases(self):
        # If no binary releases exist,
        # DistroSeriesSourcePackageRelease.binaries returns an empty
        # sequence.
        self.assertEqual(0, self.dssp_release.binaries.count())

    def test_binaries__one_release_for_source_package(self):
        # If a binary release exists, it is returned by
        # DistroSeriesSourcePackageRelease.binaries.
        bp_release = self.makeBinaryPackageRelease()
        self.assertEqual(
            [bp_release], list(self.dssp_release.binaries))

    def test_binaries__two_releases_for_source_package(self):
        # If two binary releases with the sam name exist, both
        # are returned. The more recent one is returned first.
        name = self.factory.makeBinaryPackageName()
        bp_release_one = self.makeBinaryPackageRelease(name)
        bp_release_two = self.makeBinaryPackageRelease(name)
        self.assertEqual(
            [bp_release_two, bp_release_one],
            list(self.dssp_release.binaries))

    def test_prejoins(self):
        # The properties BinaryPackageRelease.build and
        # and BinaryPackageRelease.binarypackagename of the
        # the result objects are preloaded in the query
        # issued in DistroSeriesSourcePackageRelease.binaries.
        self.makeBinaryPackageRelease()
        # Both properties we want to check have been created
        # in makeBinaryPackageRelease() and are thus already
        # in Storm's cache. We must empty the cache, otherwise
        # accessing bp_release.build and
        # bp_release.binarypackagename will never cause an
        # SQL query to be issued.
        Store.of(self.distroarchseries).invalidate()
        [bp_release] = list(self.dssp_release.binaries)
        with StormStatementRecorder() as recorder:
            bp_release.build
            bp_release.binarypackagename
        self.assertThat(recorder, HasQueryCount(Equals(0)))
