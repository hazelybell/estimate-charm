#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database garbage collector.

Remove or archive unwanted data. Detect, warn and possibly repair data
corruption.
"""

__metaclass__ = type
__all__ = []

import _pythonpath

from lp.scripts.garbo import DailyDatabaseGarbageCollector


if __name__ == '__main__':
    script = DailyDatabaseGarbageCollector()
    script.continue_on_failure = True
    script.lock_and_run()
