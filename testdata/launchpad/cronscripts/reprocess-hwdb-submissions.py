#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Cron job that parses pending HWDB submissions.


Options:
    -m, --max-submissions: (optional) The maximum number of submissions
        which will be processed.

This script iterates over the HWDB submissions with the status
INVALID. It processes only submissions with an ID greater or equal
than the number specified by the file given a option -s.

When the script terminates, it writes the ID of the last processed
submission into this file.

Properly processed submissions are set to the status PROCESSED;
submissions that cannot be processed retain the status INVALID.
"""

import _pythonpath

from lp.hardwaredb.scripts.hwdbsubmissions import (
    reprocess_invalid_submissions,
    )
from lp.services.scripts.base import LaunchpadCronScript


class HWDBSubmissionProcessor(LaunchpadCronScript):

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            '-m', '--max-submissions',
            help='Limit the number of submissions which will be processed.')
        self.parser.add_option(
            '-w', '--warnings', action="store_true", default=False,
            help='Include warnings.')
        self.parser.add_option(
            '-s', '--start-file', default=None,
            help=('The name of a file storing the smallest ID of a\n'
                  'hardware database submission that should be processed.\n'
                  'This script must have read and write access to the file.'))

    def main(self):
        max_submissions = self.options.max_submissions
        if max_submissions is not None:
            try:
                max_submissions = int(self.options.max_submissions)
            except ValueError:
                self.logger.error(
                    'Invalid value for --max_submissions specified: %r.'
                    % max_submissions)
                return
            if max_submissions <= 0:
                self.logger.error(
                    '--max_submissions must be a positive integer.')
                return

        if self.options.start_file is None:
            self.logger.error('Option --start-file not specified.')
            return
        try:
            start_file = open(self.options.start_file, 'r+')
            start_id = start_file.read().strip()
        except IOError as error:
            self.logger.error(
                'Cannot access file %s: %s' % (
                    self.options.start_file, error))
            return
        try:
            start_id = int(start_id)
        except ValueError:
            self.logger.error(
                '%s must contain only an integer' % self.options.start_file)
            return
        if start_id < 0:
            self.logger.error(
                '%s must contain a positive integer'
                % self.options.start_file)
            return

        next_start = reprocess_invalid_submissions(
            start_id, self.txn, self.logger,
            max_submissions, self.options.warnings)

        start_file.seek(0)
        start_file.write('%i' % next_start)
        start_file.close()

if __name__ == '__main__':
    script = HWDBSubmissionProcessor(
        'hwdbsubmissions', dbuser='hwdb-submission-processor')
    script.lock_and_run()
