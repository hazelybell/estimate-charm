#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script to export a tarball of translations for a distro series."""

__metaclass__ = type

import _pythonpath

from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )
from lp.translations.scripts.language_pack import export_language_pack


class RosettaLangPackExporter(LaunchpadCronScript):
    """Export language packs for a distribution series."""
    usage = '%prog [options] distribution series'

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            '--output',
            dest='output',
            default=None,
            action='store',
            help='A file to send the generated tarball to, rather than the'
                 ' Libraran.'
            )
        self.parser.add_option(
            '--component',
            dest='component',
            default=None,
            action='store',
            help='Select a concrete archive component to export.'
            )
        self.parser.add_option(
            '--force-utf8-encoding',
            dest='force_utf8',
            default=False,
            action='store_true',
            help='Whether the exported files should be exported using UTF-8'
                 ' encoding.'
            )

    def args(self):
        """Return the list of command-line arguments."""
        return self._args

    def _setargs(self, args):
        """Set distribution_name and series_name from the args."""
        if len(args) != 2:
            raise LaunchpadScriptFailure(
                'Wrong number of arguments: should include distribution '
                'and series name.')

        self._args = args
        self.distribution_name, self.series_name = self._args

    args = property(args, _setargs, doc=args.__doc__)

    @property
    def lockfilename(self):
        """Return lockfilename.

        The lockfile name is unique to the script, distribution, and series.
        The script can run concurrently for different distroseries.
        """
        lockfile_name = "launchpad-%s__%s__%s.lock" % (
            self.name, self.distribution_name, self.series_name)
        self.logger.info('Setting lockfile name to %s.' % lockfile_name)
        return lockfile_name

    def main(self):
        """See `LaunchpadScript`."""
        self.logger.info(
            'Exporting translations for series %s of distribution %s.',
            self.series_name, self.distribution_name)
        success = export_language_pack(
            distribution_name=self.distribution_name,
            series_name=self.series_name,
            component=self.options.component,
            force_utf8=self.options.force_utf8,
            output_file=self.options.output,
            logger=self.logger)

        if not success:
            raise LaunchpadScriptFailure('Language pack generation failed')
        else:
            self.txn.commit()


if __name__ == '__main__':
    script = RosettaLangPackExporter(
        'language-pack-exporter', dbuser='langpack')
    script.lock_and_run()

