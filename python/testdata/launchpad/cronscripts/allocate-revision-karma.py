#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.code.scripts.revisionkarma import RevisionKarmaAllocator
from lp.services.config import config


if __name__ == '__main__':
    script = RevisionKarmaAllocator('allocate-revision-karma',
        dbuser=config.revisionkarma.dbuser)
    script.lock_and_run()
