# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of DistributionSourcePackageRelease."""

from testtools.matchers import LessThan
from zope.component import getUtility

from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.model.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease,
    )
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount


class TestDistributionSourcePackageRelease(TestCaseWithFactory):
    """Tests for DistributionSourcePackageRelease."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistributionSourcePackageRelease, self).setUp()
        self.sourcepackagerelease = self.factory.makeSourcePackageRelease()
        self.distroarchseries = self.factory.makeDistroArchSeries(
            distroseries=self.sourcepackagerelease.sourcepackage.distroseries)
        distribution = self.distroarchseries.distroseries.distribution
        self.dsp_release = DistributionSourcePackageRelease(
            distribution, self.sourcepackagerelease)

    def makeBinaryPackageRelease(self, name=None):
        if name is None:
            name = self.factory.makeBinaryPackageName()
        bp_build = self.factory.makeBinaryPackageBuild(
            source_package_release=self.sourcepackagerelease,
            distroarchseries=self.distroarchseries)
        bp_release = self.factory.makeBinaryPackageRelease(
            build=bp_build, binarypackagename=name, architecturespecific=True,
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

    def test_sample_binary_packages__no_releases(self):
        # If no binary releases exist,
        # DistributionSourcePackageRelease.sample_binary_packages is empty.
        self.assertEqual(0, self.dsp_release.sample_binary_packages.count())

    def test_sample_binary_packages__one_release(self):
        # If a binary release exists,
        # DistributionSourcePackageRelease.sample_binary_packages
        # returns it.
        self.makeBinaryPackageRelease(
            self.factory.makeBinaryPackageName(name='binary-package'))
        self.assertEqual(
            ['binary-package'],
            [release.name
             for release in self.dsp_release.sample_binary_packages])

    def test_sample_binary_packages__two_releases_one_binary_package(self):
        # If two binary releases with the same name exist,
        # DistributionSourcePackageRelease.sample_binary_packages
        # returns only one.
        name = self.factory.makeBinaryPackageName(name='binary-package')
        self.makeBinaryPackageRelease(name)
        self.makeBinaryPackageRelease(name)
        self.assertEqual(
            ['binary-package'],
            [release.name
             for release in self.dsp_release.sample_binary_packages])

    def test_sample_binary_packages__two_release_two_binary_packages(self):
        # If a two binary releases with different names exist,
        # DistributionSourcePackageRelease.sample_binary_packages
        # returns both.
        self.makeBinaryPackageRelease(
            self.factory.makeBinaryPackageName(name='binary-package'))
        self.makeBinaryPackageRelease(
            self.factory.makeBinaryPackageName(name='binary-package-2'))
        self.assertEqual(
            ['binary-package', 'binary-package-2'],
            [release.name
             for release in self.dsp_release.sample_binary_packages])

    def updateDistroSeriesPackageCache(self):
        # Create DistroSeriesPackageCache records for new binary
        # packages.
        #
        # SoyuzTestPublisher.updateDistroSeriesPackageCache() creates
        # a DistroSeriesPackageCache record for the new binary package.
        # The method closes the current DB connection, making references
        # to DB objects in other DB objects unusable. Starting with
        # the distroarchseries, we can create new, valid, instances of
        # objects required later in the test again.
        # of the objects we need later.
        sourcepackagename = self.sourcepackagerelease.sourcepackagename
        publisher = SoyuzTestPublisher()
        publisher.updateDistroSeriesPackageCache(
            self.distroarchseries.distroseries)
        self.distroarchseries = DistroArchSeries.get(self.distroarchseries.id)
        distribution = self.distroarchseries.distroseries.distribution
        releases = distribution.getCurrentSourceReleases([sourcepackagename])
        [(distribution_sourcepackage, dsp_release)] = releases.items()
        self.dsp_release = dsp_release
        self.sourcepackagerelease = dsp_release.sourcepackagerelease

    def test_sample_binary_packages__constant_number_sql_queries(self):
        # Retrieving
        # DistributionSourcePackageRelease.sample_binary_packages and
        # accessing the property "summary" of its items requires a
        # constant number of SQL queries, regardless of the number
        # of existing binary package releases.
        self.makeBinaryPackageRelease()
        self.updateDistroSeriesPackageCache()
        with StormStatementRecorder() as recorder:
            for ds_package in self.dsp_release.sample_binary_packages:
                ds_package.summary
        self.assertThat(recorder, HasQueryCount(LessThan(5)))
        self.assertEqual(1, self.dsp_release.sample_binary_packages.count())

        for iteration in range(5):
            self.makeBinaryPackageRelease()
        self.updateDistroSeriesPackageCache()
        with StormStatementRecorder() as recorder:
            for ds_package in self.dsp_release.sample_binary_packages:
                ds_package.summary
        self.assertThat(recorder, HasQueryCount(LessThan(5)))
        self.assertEqual(6, self.dsp_release.sample_binary_packages.count())

        # Even if the cache is not updated for binary packages,
        # DistributionSourcePackageRelease objects do not try to
        # retrieve DistroSeriesPackageCache records if they know
        # that such records do not exist.
        for iteration in range(5):
            self.makeBinaryPackageRelease()
        with StormStatementRecorder() as recorder:
            for ds_package in self.dsp_release.sample_binary_packages:
                ds_package.summary
        self.assertThat(recorder, HasQueryCount(LessThan(5)))
        self.assertEqual(11, self.dsp_release.sample_binary_packages.count())
