#!/usr/bin/python -S
#
# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.services.scripts.base import LaunchpadCronScript
from lp.soyuz.scripts.retrydepwait import RetryDepwaitTunableLoop


class RetryDepwait(LaunchpadCronScript):

    def add_my_options(self):
        self.parser.add_option(
            "-n", "--dry-run", action="store_true",
            dest="dry_run", default=False,
            help="Don't commit changes to the DB.")

    def main(self):
        updater = RetryDepwaitTunableLoop(self.logger, self.options.dry_run)
        updater.run()

if __name__ == '__main__':
    script = RetryDepwait('retry-depwait', dbuser='retry_depwait')
    script.lock_and_run()
