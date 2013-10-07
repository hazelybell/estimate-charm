#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Cron job to update Product.remote_product using bug watch information.

This script sets the remote_product string value on Launchpad Products
by looking it up from one of the product's bug watches.
"""

import _pythonpath

import time

from lp.bugs.scripts.updateremoteproduct import RemoteProductUpdater
from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript


class UpdateRemoteProduct(LaunchpadCronScript):

    def main(self):
        start_time = time.time()

        updater = RemoteProductUpdater(self.txn, self.logger)
        updater.update()

        run_time = time.time() - start_time
        self.logger.info("Time for this run: %.3f seconds." % run_time)


if __name__ == '__main__':
    script = UpdateRemoteProduct(
        "updateremoteproduct", dbuser=config.updateremoteproduct.dbuser)
    script.lock_and_run()
