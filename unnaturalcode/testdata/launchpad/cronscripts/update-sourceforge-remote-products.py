#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Cron job to update remote_products using SourceForge project data."""

import _pythonpath

import time

from lp.bugs.scripts.sfremoteproductfinder import (
    SourceForgeRemoteProductFinder,
    )
from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript


class UpdateRemoteProductsFromSourceForge(LaunchpadCronScript):

    def main(self):
        start_time = time.time()

        finder = SourceForgeRemoteProductFinder(self.txn, self.logger)
        finder.setRemoteProductsFromSourceForge()

        run_time = time.time() - start_time
        self.logger.info("Time for this run: %.3f seconds." % run_time)


if __name__ == '__main__':
    script = UpdateRemoteProductsFromSourceForge(
        "updateremoteproduct",
        dbuser=config.updatesourceforgeremoteproduct.dbuser)
    script.lock_and_run()
