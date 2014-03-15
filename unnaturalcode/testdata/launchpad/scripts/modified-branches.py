#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script to print disk locations of modified branches.

This script will be used by IS for the rsync backups.
"""

import _pythonpath

from lp.codehosting.scripts.modifiedbranches import ModifiedBranchesScript


if __name__ == '__main__':
    script = ModifiedBranchesScript(
        'modified-branches', dbuser='modified-branches')
    script.run()
