#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Create a copy archive and populate it with packages.

    Please note: the destination copy archive must not exist yet. Otherwise
    the script will abort with an error.
"""

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.populate_archive import ArchivePopulator


if __name__ == '__main__':
    script = ArchivePopulator(
        'populate-archive', dbuser=config.archivepublisher.dbuser)
    script.lock_and_run()
