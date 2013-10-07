# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'UploadPackageTranslations',
    ]

import os

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


class UploadPackageTranslations(LaunchpadScript):
    """Upload translations for given distribution package."""
    description = "Upload translation files for a package."

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option('-d', '--distribution', dest='distro',
            help="Distribution to upload for.", default='ubuntu')
        self.parser.add_option('-s', '--series', dest='distroseries',
            help="Distribution release series to upload for.")
        self.parser.add_option('-p', '--package', dest='package',
            help="Name of source package to upload to.")
        self.parser.add_option('-l', '--dry-run', dest='dryrun',
            action='store_true', default=False,
            help="Pretend to upload, but make no actual changes.")

    def main(self):
        """See `LaunchpadScript`."""
        self._setDistroDetails()
        self._setPackage()

        if self.options.dryrun:
            self.logger.info("Dry run.  Not really uploading anything.")

        queue = getUtility(ITranslationImportQueue)
        rosetta_team = getUtility(ILaunchpadCelebrities).rosetta_experts

        for filename in self.args:
            if not os.access(filename, os.R_OK):
                raise LaunchpadScriptFailure(
                    "File not readable: %s" % filename)
            self.logger.info("Uploading: %s." % filename)
            content = open(filename).read()
            queue.addOrUpdateEntry(
                filename, content, True, rosetta_team,
                sourcepackagename = self.sourcepackagename,
                distroseries = self.distroseries)
            self._commit()

        self.logger.info("Done.")

    def _commit(self):
        """Commit transaction (or abort if dry run)."""
        if self.txn:
            if self.options.dryrun:
                self.txn.abort()
            else:
                self.txn.commit()

    def _setDistroDetails(self):
        """Figure out the `Distribution`/`DistroSeries` to act upon."""
        distroset = getUtility(IDistributionSet)
        self.distro = distroset.getByName(self.options.distro)

        if not self.options.distroseries:
            raise LaunchpadScriptFailure(
                "Specify a distribution release series.")

        self.distroseries = self.distro.getSeries(self.options.distroseries)

    def _setPackage(self):
        """Find `SourcePackage` of given name."""
        if not self.options.package:
            raise LaunchpadScriptFailure("No package specified.")

        nameset = getUtility(ISourcePackageNameSet)

        self.sourcepackagename = nameset.queryByName(self.options.package)
