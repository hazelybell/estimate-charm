#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.services.database.policy import SlaveDatabasePolicy
from lp.services.scripts.base import LaunchpadCronScript
from lp.translations.scripts.po_export_queue import process_queue


class RosettaExportQueue(LaunchpadCronScript):
    """Translation exports."""

    def main(self):
        with SlaveDatabasePolicy():
            process_queue(self.txn, self.logger)


if __name__ == '__main__':
    script = RosettaExportQueue('rosetta-export-queue', dbuser='poexport')
    script.lock_and_run()
