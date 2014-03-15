#!/usr/bin/python -S
#
# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Request jobs to update products and send emails."""

__metaclass__ = type

import _pythonpath

import transaction

from lp.registry.model.productjob import ProductJobManager
from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript
from lp.services.webapp.errorlog import globalErrorUtility


class RequestProductJobs(LaunchpadCronScript):
    """Create `ProductJobs` for products that need updating."""

    def __init__(self):
        name = 'daily_product_jobs'
        dbuser = config.ICommercialExpiredJobSource.dbuser
        LaunchpadCronScript.__init__(self, name, dbuser)

    def main(self):
        globalErrorUtility.configure(self.name)
        manager = ProductJobManager(self.logger)
        job_count = manager.createAllDailyJobs()
        self.logger.info('Requested %d total product jobs.' % job_count)
        transaction.commit()


if __name__ == '__main__':
    script = RequestProductJobs()
    script.lock_and_run()
