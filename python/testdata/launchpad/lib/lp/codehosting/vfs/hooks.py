# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementations for the `seen_new_branch_hook` of `BranchFileSystemClient`.
"""

__metaclass__ = type
__all__ = ['SetProcTitleHook']

import setproctitle


class SetProcTitleHook:
    """Use seen() as the hook to report branch access in ps(1) output."""

    def __init__(self, setproctitle_mod=None):
        if setproctitle_mod is None:
            setproctitle_mod = setproctitle
        self.setproctitle_mod = setproctitle_mod
        self.basename = setproctitle_mod.getproctitle()

    def seen(self, branch_url):
        branch_url = branch_url.strip('/')
        self.setproctitle_mod.setproctitle(
            self.basename + ' BRANCH:' + branch_url)
