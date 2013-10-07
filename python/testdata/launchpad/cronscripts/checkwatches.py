#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Cron job to run daily to check all of the BugWatches
"""

import _pythonpath

from lp.bugs.scripts.checkwatches import CheckWatchesCronScript
from lp.services.config import config


if __name__ == '__main__':
    script = CheckWatchesCronScript(
        "checkwatches", dbuser=config.checkwatches.dbuser)
    script.lock_and_run()
