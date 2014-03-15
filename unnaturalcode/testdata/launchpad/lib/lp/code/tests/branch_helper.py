# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper methods for branch tests and pagetest."""

__metaclass__ = type
__all__ = [
    'reset_all_branch_last_modified',
    ]

from datetime import datetime

import pytz
from zope.component import getUtility

from lp.code.interfaces.branchcollection import IAllBranches
from lp.testing import celebrity_logged_in


def reset_all_branch_last_modified(last_modified=datetime.now(pytz.UTC)):
    """Reset the date_last_modifed value on all the branches.

    DO NOT use this in a non-pagetest.
    """
    with celebrity_logged_in('admin'):
        branches = getUtility(IAllBranches).getBranches()
        for branch in branches:
            branch.date_last_modified = last_modified
