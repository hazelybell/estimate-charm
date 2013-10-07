#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Refresh and verify cached POFile translation statistics."""

import _pythonpath

from lp.services.scripts.base import LaunchpadCronScript
from lp.translations.scripts.verify_pofile_stats import (
    VerifyPOFileStatsProcess,
    )


class VerifyPOFileStats(LaunchpadCronScript):
    """Trawl `POFile` table, verifying and updating cached statistics."""

    def add_my_options(self):
        self.parser.add_option('-i', '--start-id', dest='start_id',
            type='int',
            help="Verify from this POFile id upward.")

    def main(self):
        if self.options.start_id is not None:
            start_id = int(self.options.start_id)
        else:
            start_id = 0

        verifier = VerifyPOFileStatsProcess(
            self.txn, self.logger, start_at_id=start_id)
        verifier.run()


if __name__ == '__main__':
    script = VerifyPOFileStats(name="pofile-stats", dbuser='pofilestats')
    script.lock_and_run()
