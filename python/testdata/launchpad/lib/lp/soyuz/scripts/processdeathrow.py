# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Death row processor base script class

This script removes obsolete files from the selected archive(s) pool.
"""
# Disable warning on catching bare 'Exception', it's needed as a
# production artifact for continuing processing data that doesn't
# have problems.
__metaclass__ = type

__all__ = [
    'DeathRowProcessor',
    ]


from zope.component import getUtility

from lp.archivepublisher.deathrow import getDeathRow
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.scripts.base import LaunchpadCronScript


class DeathRowProcessor(LaunchpadCronScript):

    def add_my_options(self):
        self.parser.add_option(
            "-n", "--dry-run", action="store_true", default=False,
            help="Dry run: goes through the motions but commits to nothing.")

        self.parser.add_option(
            "-d", "--distribution", metavar="DISTRO", default='ubuntu',
            help="Specified the distribution name.")

        self.parser.add_option(
            "-p", "--pool-root", metavar="PATH",
            help="Override the path to the pool folder")

        self.parser.add_option(
            "--ppa", action="store_true", default=False,
            help="Run only over PPA archives.")

    def main(self):
        distribution = getUtility(IDistributionSet).getByName(
            self.options.distribution)

        if self.options.ppa:
            archives = distribution.getAllPPAs()
        else:
            archives = distribution.all_distro_archives

        for archive in archives:
            self.logger.info("Processing %s" % archive.archive_url)
            self.processDeathRow(archive)

    def processDeathRow(self, archive):
        """Process death-row for the given archive.

        It handles the current DB transaction according to the results of
        the operation just executed, i.e, commits successful runs and aborts
        runs with errors. It also respects 'dry-run' command-line option.
        """
        death_row = getDeathRow(
            archive, self.logger, self.options.pool_root)
        self.logger.debug(
            "Unpublishing death row for %s." % archive.displayname)
        try:
            death_row.reap(self.options.dry_run)
        except Exception:
            self.logger.exception(
                "Unexpected exception while doing death-row unpublish")
            self.txn.abort()
        else:
            if self.options.dry_run:
                self.logger.info("Dry run mode; rolling back.")
                self.txn.abort()
            else:
                self.logger.debug("Committing")
                self.txn.commit()

