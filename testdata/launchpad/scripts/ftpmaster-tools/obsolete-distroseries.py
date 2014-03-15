#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Obsolete all packages in an obsolete distroseries.

This script will obsolete (schedule for removal) all published packages
in an obsolete distroseries.
"""

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.obsolete_distroseries import ObsoleteDistroseries


if __name__ == '__main__':
    script = ObsoleteDistroseries(
        'obsolete-distroseries', dbuser=config.archivepublisher.dbuser)
    script.lock_and_run()
