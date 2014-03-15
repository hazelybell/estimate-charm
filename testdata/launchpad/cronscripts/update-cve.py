#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A cron script that fetches the latest database of CVE details and ensures
that all of the known CVE's are fully registered in Launchpad."""

__metaclass__ = type

import _pythonpath

from lp.bugs.scripts.cveimport import CVEUpdater
from lp.services.config import config


if __name__ == '__main__':
    script = CVEUpdater("updatecve", config.cveupdater.dbuser)
    script.lock_and_run()

