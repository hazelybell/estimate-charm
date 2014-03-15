#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Import Debian bugs into Launchpad, linking them to Ubuntu.

New bugs will be filed against the Debian source package in
Launchpad, with the real Debian bug linked as a bug watch.

An Ubuntu task will be created for each imported bug.
"""

import _pythonpath

from lp.bugs.scripts.importdebianbugs import import_debian_bugs
from lp.services.config import config
from lp.services.scripts.base import LaunchpadScript


class DebianBugImportScript(LaunchpadScript):
    """Import Debian bugs into Launchpad, linking them to Ubuntu.

    New bugs will be filed against the Debian source package in
    Launchpad, with the real Debian bug linked as a bug watch.

    An Ubuntu task will be created for each imported bug.
    """

    usage = "%(prog)s [options] <debian-bug-1> ... <debian-bug-n>"
    description = __doc__

    def add_my_options(self):
        self.parser.add_option(
            '-n', '--dry-run', action='store_true',
           help="Don't commit the DB transaction.",
           dest='dry_run', default=False)

    def main(self):
        if len(self.args) < 1:
            self.parser.print_help()
            return

        import_debian_bugs(self.args)

        if self.options.dry_run:
            self.logger.info("Dry run - rolling back the transaction.")
            self.txn.abort()
        else:
            self.logger.info("Committing the transaction.")
            self.txn.commit()


if __name__ == '__main__':
    script = DebianBugImportScript(
        'lp.services.scripts.importdebianbugs',
        dbuser=config.checkwatches.dbuser)
    script.run()
