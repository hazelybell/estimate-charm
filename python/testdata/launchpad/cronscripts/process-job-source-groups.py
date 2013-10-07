#!/usr/bin/python -S
#
# Copyright 2009, 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Handle jobs for multiple job source classes."""

__metaclass__ = type

import _pythonpath

from optparse import IndentedHelpFormatter
import os
import subprocess
import sys
import textwrap

from lp.services.config import config
from lp.services.helpers import english_list
from lp.services.propertycache import cachedproperty
from lp.services.scripts.base import LaunchpadCronScript


class LongEpilogHelpFormatter(IndentedHelpFormatter):
    """Preserve newlines in epilog."""

    def format_epilog(self, epilog):
        if epilog:
            return '\n%s\n' % epilog
        else:
            return ""


class ProcessJobSourceGroups(LaunchpadCronScript):
    """Handle each job source in a separate process with ProcessJobSource."""

    def add_my_options(self):
        self.parser.usage = "%prog [ -e JOB_SOURCE ] GROUP [GROUP]..."
        self.parser.epilog = (
            textwrap.fill(
            "At least one group must be specified. Excluding job sources "
            "is useful when you want to run all the other job sources in "
            "a group.")
            + "\n\n" + self.group_help)

        self.parser.formatter = LongEpilogHelpFormatter()
        self.parser.add_option(
            '-e', '--exclude', dest='excluded_job_sources',
            metavar="JOB_SOURCE", default=[], action='append',
            help="Exclude specific job sources.")
        self.parser.add_option(
            '--wait', dest='do_wait', default=False, action='store_true',
            help="Wait for the child processes to finish. This is useful "
                 "for testing, but it shouldn't be used in a cronjob, since "
                 "it would prevent the cronjob from processing new jobs "
                 "if just one of the child processes is still processing, "
                 "and each process only handles a single job source class.")

    def main(self):
        selected_groups = self.args
        if len(selected_groups) == 0:
            self.parser.print_help()
            sys.exit(1)

        selected_job_sources = set()
        # Include job sources from selected groups.
        for group in selected_groups:
            selected_job_sources.update(self.grouped_sources[group])
        # Then, exclude job sources.
        for source in self.options.excluded_job_sources:
            if source not in selected_job_sources:
                self.logger.info(
                    '%r is not in %s' % (
                        source, english_list(selected_groups, "or")))
            else:
                selected_job_sources.remove(source)
        # Process job sources.
        command = os.path.join(
            os.path.dirname(sys.argv[0]), 'process-job-source.py')
        child_args = [command]
        if self.options.verbose:
            child_args.append('-v')
        children = []
        for job_source in selected_job_sources:
            child = subprocess.Popen(child_args + [job_source])
            children.append(child)
        if self.options.do_wait:
            for child in children:
                child.wait()

    @cachedproperty
    def all_job_sources(self):
        job_sources = config['process-job-source-groups'].job_sources
        return [job_source.strip() for job_source in job_sources.split(',')]

    @cachedproperty
    def grouped_sources(self):
        groups = {}
        for source in self.all_job_sources:
            if source not in config:
                continue
            section = config[source]
            group = groups.setdefault(section.crontab_group, [])
            group.append(source)
        return groups

    @cachedproperty
    def group_help(self):
        return '\n\n'.join(
            'Group: %s\n    %s' % (group, '\n    '.join(sources))
            for group, sources in sorted(self.grouped_sources.items()))


if __name__ == '__main__':
    script = ProcessJobSourceGroups()
    # We do not need to take a lock here; all the interesting work is done
    # by process-job-source.py, which takes its own per-job-source locks.
    script.run()
