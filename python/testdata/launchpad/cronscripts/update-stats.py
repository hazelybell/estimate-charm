#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This script updates the cached stats in the system

import _pythonpath

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript
from lp.services.statistics.interfaces.statistic import ILaunchpadStatisticSet


class StatUpdater(LaunchpadCronScript):

    def main(self):
        self.logger.debug('Starting the stats update')

        # Note that we do not issue commits here in the script; content
        # objects are responsible for committing.
        distroset = getUtility(IDistributionSet)
        for distro in distroset:
            for distroseries in distro.series:
                distroseries.updateStatistics(self.txn)

        launchpad_stats = getUtility(ILaunchpadStatisticSet)
        launchpad_stats.updateStatistics(self.txn)

        getUtility(IPersonSet).updateStatistics()

        self.logger.debug('Finished the stats update')


if __name__ == '__main__':
    script = StatUpdater('launchpad-stats', dbuser=config.statistician.dbuser)
    script.lock_and_run()
