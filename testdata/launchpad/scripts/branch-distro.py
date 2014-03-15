#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.codehosting.branchdistro import DistroBrancher
from lp.codehosting.vfs import get_rw_server
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )


class BranchDistroScript(LaunchpadScript):

    usage = "%prog distro old-series new-series"

    def add_my_options(self):
        self.parser.add_option(
            '--check', dest="check", action="store_true", default=False,
            help=("Check that the new distro series has its official "
                  "branches set up correctly."))

    def main(self):
        if len(self.args) != 3:
            self.parser.error("Wrong number of arguments.")
        brancher = DistroBrancher.fromNames(self.logger, *self.args)
        server = get_rw_server(direct_database=True)
        server.start_server()
        try:
            if self.options.check:
                if not brancher.checkNewBranches():
                    raise LaunchpadScriptFailure("Check failed")
            else:
                brancher.makeNewBranches()
        finally:
            server.stop_server()

if __name__ == '__main__':
    BranchDistroScript("branch-distro", dbuser='branch-distro').run()
