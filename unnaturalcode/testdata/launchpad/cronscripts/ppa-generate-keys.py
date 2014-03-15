#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A cron script that generate missing PPA signing keys."""

__metaclass__ = type

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.ppakeygenerator import PPAKeyGenerator


if __name__ == '__main__':
    script = PPAKeyGenerator(
        "ppa-generate-keys", config.archivepublisher.dbuser)
    script.lock_and_run()

