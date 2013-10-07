#!/usr/bin/python -S
#
# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.bugs.scripts.bugsummaryrebuild import BugSummaryRebuildTunableLoop
from lp.services.scripts.base import LaunchpadScript


class BugSummaryRebuild(LaunchpadScript):

    def add_my_options(self):
        self.parser.add_option(
            "-n", "--dry-run", action="store_true",
            dest="dry_run", default=False,
            help="Don't commit changes to the DB.")

    def main(self):
        updater = BugSummaryRebuildTunableLoop(
            self.logger, self.options.dry_run)
        updater.run()

if __name__ == '__main__':
    script = BugSummaryRebuild(
        'bugsummary-rebuild', dbuser='bugsummaryrebuild')
    script.lock_and_run()
