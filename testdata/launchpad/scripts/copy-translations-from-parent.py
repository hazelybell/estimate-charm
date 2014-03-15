#!/usr/bin/python -S
#
# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Furnish distroseries with lacking translations that its parent does have.

This can be used either to update a distroseries' translations, or to
provide a new distroseries in a series with its initial translation data.
Only current translations are copied.
"""

import _pythonpath

import sys

from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.scripts.base import LaunchpadCronScript
from lp.translations.scripts.copy_distroseries_translations import (
    copy_distroseries_translations,
    )


class TranslationsCopier(LaunchpadCronScript):
    """Copy latest distroseries translations from parent series.

    Core job is to invoke `distroseries.copyMissingTranslationsFromParent()`.
    """

    def add_my_options(self):
        self.parser.add_option('-d', '--distribution', dest='distro',
            default='ubuntu',
            help='Name of distribution to copy translations in.')
        self.parser.add_option('-s', '--series', dest='series',
            help='Name of distroseries whose translations should be updated')
        self.parser.add_option('-f', '--force', dest='force',
            action="store_true", default=False,
            help="Don't check if target's UI and imports are blocked; "
                 "actively block them.")

    def _getTargetSeries(self):
        """Retrieve target `DistroSeries`."""
        series = self.options.series
        return getUtility(IDistributionSet)[self.options.distro][series]

    def main(self):
        series = self._getTargetSeries()

        # Both translation UI and imports for this series should be blocked
        # while the copy is in progress, to reduce the chances of deadlocks or
        # other conflicts.
        blocked = (
            series.hide_all_translations and series.defer_translation_imports)
        if not blocked and not self.options.force:
            self.txn.abort()
            self.logger.error(
                'Before this process starts, set the '
                'hide_all_translations and defer_translation_imports '
                'flags for distribution %s, series %s; or use the '
                '--force option to make it happen automatically.' % (
                    self.options.distro, self.options.series))
            sys.exit(1)

        self.logger.info('Starting...')

        # Actual work is done here.
        copy_distroseries_translations(series, self.txn, self.logger)

        # We would like to update the DistroRelase statistics, but it takes
        # too long so this should be done after.
        #
        # Finally, we changed many things related with cached statistics, so
        # we may want to update those.
        # self.logger.info('Updating DistroSeries statistics...')
        # series.updateStatistics(self.txn)

        self.txn.commit()
        self.logger.info('Done.')

    @property
    def lockfilename(self):
        """Return lock file name for this script on this distroseries.

        No global lock is needed, only one for the distroseries we operate
        on.  This does mean that our options must have been parsed before this
        property is ever accessed.  Luckily that is what the `LaunchpadScript`
        code does!
        """
        return "launchpad-%s-%s-%s.lock" % (self.name, self.options.distro,
            self.options.series)


if __name__ == '__main__':
    script = TranslationsCopier(
        'copy-missing-translations', dbuser='translations_distroseries_copy')
    script.lock_and_run()
