#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Update stacked_on_location for all Bazaar branches.

Expects standard input of:
    '<id> <branch_type> <unique_name> <stacked_on_id> <stacked_on_unique_name>\n'.

Such input can be provided using "get-stacked-on-branches.py".

This script makes the stacked_on_location variables in all Bazaar branches
match the stacked_on column in the Launchpad database. This is useful for
updating stacked branches when their stacked-on branch has been moved or
renamed.
"""

__metaclass__ = type

import _pythonpath

from collections import namedtuple
import sys

from bzrlib import errors
from bzrlib.bzrdir import BzrDir
from bzrlib.config import TransportConfig

from lp.code.interfaces.codehosting import branch_id_alias
from lp.codehosting.bzrutils import get_branch_stacked_on_url
from lp.codehosting.vfs import (
    get_ro_server,
    get_rw_server,
    )
from lp.services.scripts.base import LaunchpadScript


FakeBranch = namedtuple('FakeBranch', 'id')


def set_branch_stacked_on_url(bzrdir, stacked_on_url):
    """Set the stacked_on_location for the branch at 'bzrdir'.

    We cannot use Branch.set_stacked_on, since that requires us to first open
    the branch. Opening the branch requires a working stacked_on_url:
    something we don't yet have.
    """
    branch_transport = bzrdir.get_branch_transport(None)
    branch_config = TransportConfig(branch_transport, 'branch.conf')
    stacked_on_url = branch_config.set_option(
        stacked_on_url, 'stacked_on_location')


class UpdateStackedBranches(LaunchpadScript):
    """Update stacked branches so their stacked_on_location matches the db."""

    def __init__(self):
        super(UpdateStackedBranches, self).__init__('update-stacked-on')

    def add_my_options(self):
        self.parser.add_option(
            '-n', '--dry-run', default=False, action="store_true",
            dest="dry_run",
            help=("Don't change anything on disk, just go through the "
                  "motions."))
        self.parser.add_option(
            '-i', '--id', default=False, action="store_true",
            dest="stack_on_id",
            help=("Stack on the +branch-id alias."))

    def main(self):
        if self.options.dry_run:
            server = get_ro_server()
        else:
            server = get_rw_server()
        server.start_server()
        if self.options.dry_run:
            self.logger.debug('Running read-only')
        self.logger.debug('Beginning processing')
        try:
            self.updateBranches(self.parseFromStream(sys.stdin))
        finally:
            server.stop_server()
        self.logger.info('Done')

    def updateStackedOn(self, branch_id, bzr_branch_url, stacked_on_location):
        """Stack the Bazaar branch at 'bzr_branch_url' on the given URL.

        :param branch_id: The database ID of the branch. This is only used for
            logging.
        :param bzr_branch_url: The lp-internal:/// URL of the Bazaar branch.
        :param stacked_on_location: The location to store in the branch's
            stacked_on_location configuration variable.
        """
        try:
            bzrdir = BzrDir.open(bzr_branch_url)
        except errors.NotBranchError:
            self.logger.warn(
                "No bzrdir for %r at %r" % (branch_id, bzr_branch_url))
            return

        try:
            current_stacked_on_location = get_branch_stacked_on_url(bzrdir)
        except errors.NotBranchError:
            self.logger.warn(
                "No branch for %r at %r" % (branch_id, bzr_branch_url))
        except errors.NotStacked:
            self.logger.warn(
                "Branch for %r at %r is not stacked at all. Giving up."
                % (branch_id, bzr_branch_url))
        except errors.UnstackableBranchFormat:
            self.logger.error(
                "Branch for %r at %r is unstackable. Giving up."
                % (branch_id, bzr_branch_url))
        else:
            if current_stacked_on_location != stacked_on_location:
                self.logger.info(
                    'Branch for %r at %r stacked on %r, should be on %r.'
                    % (branch_id, bzr_branch_url, current_stacked_on_location,
                       stacked_on_location))
                if not self.options.dry_run:
                    set_branch_stacked_on_url(bzrdir, stacked_on_location)

    def parseFromStream(self, stream):
        """Parse branch input from the given stream.

        Expects the stream to be populated only by blank lines or by lines
        with whitespace-separated fields. Such lines are yielded as tuples.
        Blank lines are ignored.
        """
        for line in stream.readlines():
            if not line.strip():
                continue
            yield line.split()

    def updateBranches(self, branches):
        """Update the stacked_on_location for all branches in 'branches'.

        :param branches: An iterator yielding (branch_id, branch_type,
            unique_name, stacked_on_unique_name).
        """
        for branch_info in branches:
            (branch_id, branch_type, unique_name,
             stacked_on_id, stacked_on_name) = branch_info
            if self.options.stack_on_id:
                branch = FakeBranch(stacked_on_id)
                stacked_on_location = branch_id_alias(branch)
            else:
                stacked_on_location = '/' + stacked_on_name
            self.updateStackedOn(
                branch_id, 'lp-internal:///' + unique_name,
                stacked_on_location)


if __name__ == '__main__':
    UpdateStackedBranches().lock_and_run()
