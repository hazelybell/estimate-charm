#!/usr/bin/python -S
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.add_missing_builds import AddMissingBuilds


if __name__ == "__main__":
    script = AddMissingBuilds(
        "add-missing-builds", dbuser=config.uploader.dbuser)
    script.lock_and_run()
