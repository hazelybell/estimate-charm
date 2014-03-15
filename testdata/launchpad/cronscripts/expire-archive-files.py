#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This script expires PPA binaries that are superseded or deleted, and
# are older than 30 days.  It's done with pure SQL rather than Python
# for speed reasons.

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.expire_archive_files import ArchiveExpirer


if __name__ == '__main__':
    script = ArchiveExpirer(
        'expire-archive-files', dbuser=config.binaryfile_expire.dbuser)
    script.lock_and_run()

