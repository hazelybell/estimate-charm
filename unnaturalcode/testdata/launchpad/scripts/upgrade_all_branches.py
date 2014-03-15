#!/usr/bin/python -S

__metaclass__ = type

import _pythonpath

from lp.codehosting.bzrutils import server
from lp.codehosting.upgrade import Upgrader
from lp.codehosting.vfs.branchfs import get_rw_server
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )


class UpgradeAllBranches(LaunchpadScript):

    def add_my_options(self):
        self.parser.add_option(
            '--finish', action="store_true",
            help=("Finish the upgrade and move the new branches into place."))

    def main(self):
        if len(self.args) < 1:
            raise LaunchpadScriptFailure('Please specify a target directory.')
        if len(self.args) > 1:
            raise LaunchpadScriptFailure('Too many arguments.')
        target_dir = self.args[0]
        with server(get_rw_server()):
            if self.options.finish:
                Upgrader.finish_all_upgrades(target_dir, self.logger)
            else:
                Upgrader.start_all_upgrades(target_dir, self.logger)


if __name__ == "__main__":
    script = UpgradeAllBranches(
        "upgrade-all-branches", dbuser='upgrade-branches')
    script.lock_and_run()
