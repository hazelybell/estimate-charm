#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""List the stacked branches in Launchpad.

Usage: ./get-stacked-on-branches.py

Prints the stacked branches in Launchpad to standard output in the following
format:
  <id> <branch_type> <unique_name> <stacked_on_id> <stacked_on_unique_name>

<id> is the database ID of the Branch as a decimal integer.
<branch_type> is the name of the BranchType, e.g. 'HOSTED'.
<unique_name> is the unique_name property of the Branch.
<stacked_on_id> is the database ID of the Branch.stacked_on branch
<stacked_on_unique_name> is the unique_name property of the Branch.stacked_on
    branch.

This script is intended to be used in conjunction with "update-stacked-on.py".
"""

__metaclass__ = type

import _pythonpath

from optparse import OptionParser

from storm.locals import Not

from lp.services.database.interfaces import ISlaveStore
from lp.services.scripts import execute_zcml_for_scripts


def get_stacked_branches():
    """Iterate over all branches that, according to the db, are stacked."""
    # Avoiding circular import.
    from lp.code.model.branch import Branch
    return ISlaveStore(Branch).find(Branch, Not(Branch.stacked_on == None))


def main():
    """Print all stacked branches from the database.

    See the module docstring for more information.
    """
    parser = OptionParser(
        description="List the stacked branches in Launchpad.")
    parser.parse_args()

    execute_zcml_for_scripts()
    for db_branch in get_stacked_branches():
        stacked_on = db_branch.stacked_on
        print '%s %s %s %s %s' % (
            db_branch.id, db_branch.branch_type.name, db_branch.unique_name,
            stacked_on.id, stacked_on.unique_name)


if __name__ == '__main__':
    main()
