#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This script updates the cached source package information in the system.
# We use this for fast source package searching (as opposed to joining
# through gazillions of publishing tables).

import _pythonpath

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.scripts.base import LaunchpadCronScript
from lp.soyuz.model.distributionsourcepackagecache import (
    DistributionSourcePackageCache,
    )
from lp.soyuz.model.distroseriespackagecache import DistroSeriesPackageCache


class PackageCacheUpdater(LaunchpadCronScript):
    """Helper class for updating package caches.

    It iterates over all distributions, distroseries and archives (including
    PPAs) updating the package caches to reflect what is currently published
    in those locations.
    """

    def updateDistributionPackageCounters(self, distribution):
        """Update package counters for a given distribution."""
        for distroseries in distribution:
            distroseries.updatePackageCount()
            self.txn.commit()
            for arch in distroseries.architectures:
                arch.updatePackageCount()
                self.txn.commit()

    def updateDistributionCache(self, distribution, archive):
        """Update package caches for the given location.

        'archive' can be one of the main archives (PRIMARY, PARTNER or
        EMBARGOED) or even a PPA.

        This method commits the transaction frequently since it deal with
        a huge amount of data.

        PPA archives caches are consolidated in a Archive row to optimize
        searches across PPAs.
        """
        for distroseries in distribution.series:
            self.updateDistroSeriesCache(distroseries, archive)

        DistributionSourcePackageCache.removeOld(
            distribution, archive, log=self.logger)

        updates = DistributionSourcePackageCache.updateAll(
            distribution, archive=archive, ztm=self.txn, log=self.logger)

        if updates > 0:
            self.txn.commit()

    def updateDistroSeriesCache(self, distroseries, archive):
        """Update package caches for the given location."""
        self.logger.info('%s %s %s starting' % (
            distroseries.distribution.name, distroseries.name,
            archive.displayname))

        DistroSeriesPackageCache.removeOld(
            distroseries, archive=archive, log=self.logger)

        updates = DistroSeriesPackageCache.updateAll(
            distroseries, archive=archive, ztm=self.txn, log=self.logger)

        if updates > 0:
            self.txn.commit()

    def main(self):
        self.logger.debug('Starting the package cache update')

        # Do the package counter and cache update for each distribution.
        distroset = getUtility(IDistributionSet)
        for distribution in distroset:
            self.logger.info(
                'Updating %s package counters' % distribution.name)
            self.updateDistributionPackageCounters(distribution)

            self.logger.info(
                'Updating %s main archives' % distribution.name)
            for archive in distribution.all_distro_archives:
                self.updateDistributionCache(distribution, archive)

            self.logger.info(
                'Updating %s PPAs' % distribution.name)
            for archive in distribution.getAllPPAs():
                self.updateDistributionCache(distribution, archive)
                archive.updateArchiveCache()

            # Commit any remaining update for a distribution.
            self.txn.commit()
            self.logger.info('%s done' % distribution.name)

        self.logger.debug('Finished the package cache update')

if __name__ == '__main__':
    script = PackageCacheUpdater(
        'update-cache', dbuser="update-pkg-cache")
    script.lock_and_run()
