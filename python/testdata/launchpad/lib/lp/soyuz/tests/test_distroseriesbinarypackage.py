# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `DistroSeriesBinaryPackage`."""

__metaclass__ = type
__all__ = [
    'TestDistroSeriesBinaryPackage',
    ]

from testtools.matchers import (
    Equals,
    NotEquals,
    )

from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.soyuz.model.distroseriesbinarypackage import DistroSeriesBinaryPackage
from lp.soyuz.model.distroseriespackagecache import DistroSeriesPackageCache
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.matchers import HasQueryCount


class TestDistroSeriesBinaryPackage(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Create a distroseriesbinarypackage to play with."""
        super(TestDistroSeriesBinaryPackage, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()
        self.distroseries = self.publisher.distroseries
        self.distribution = self.distroseries.distribution
        binaries = self.publisher.getPubBinaries(
            binaryname='foo-bin', summary='Foo is the best')
        binary_pub = binaries[0]
        self.binary_package_name = (
            binary_pub.binarypackagerelease.binarypackagename)
        self.distroseries_binary_package = DistroSeriesBinaryPackage(
            self.distroseries, self.binary_package_name)

    def test_cache_attribute_when_two_cache_objects(self):
        # We have situations where there are cache objects for each
        # distro archive - we need to handle this situation without
        # OOPSing - see bug 580181.
        distro_archive_1 = self.distribution.main_archive
        distro_archive_2 = self.distribution.all_distro_archives[1]

        # Publish the same binary in another distro archive.
        self.publisher.getPubBinaries(
            binaryname='foo-bin', summary='Foo is the best',
            archive=distro_archive_2)

        logger = BufferLogger()
        with dbuser(config.statistician.dbuser):
            DistroSeriesPackageCache._update(
                self.distroseries, self.binary_package_name, distro_archive_1,
                logger)

            DistroSeriesPackageCache._update(
                self.distroseries, self.binary_package_name, distro_archive_2,
                logger)

        self.failUnlessEqual(
            'Foo is the best', self.distroseries_binary_package.summary)

    def test_none_cache_passed_at_init_counts_as_cached(self):
        # If the value None is passed as the constructor parameter
        # "cache", it is considered as a valid value.
        # Accesing the property DistroSeriesBinaryPackage.cache
        # later does not lead to the execution of an SQL query to
        # retrieve a DistroSeriesPackageCache record.
        binary_package = DistroSeriesBinaryPackage(
            self.distroseries, self.binary_package_name, cache=None)
        with StormStatementRecorder() as recorder:
            binary_package.cache
        self.assertThat(recorder, HasQueryCount(Equals(0)))

        # If the parameter "cache" was not passed, accessing
        # DistroSeriesBinaryPackage.cache for the first time requires
        # at least one SQL query.
        with StormStatementRecorder() as recorder:
            self.distroseries_binary_package.cache
        self.assertThat(recorder, HasQueryCount(NotEquals(0)))
