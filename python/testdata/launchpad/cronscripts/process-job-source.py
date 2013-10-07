#!/usr/bin/python -S
#
# Copyright 2009, 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Handle jobs for a specified job source class."""

__metaclass__ = type

import _pythonpath

from collections import defaultdict
import sys

from twisted.python import log
from zope.component import getUtility

from lp.services.config import config
from lp.services.job import runner
from lp.services.scripts.base import LaunchpadCronScript
from lp.services.webapp import errorlog


class ProcessJobSource(LaunchpadCronScript):
    """Run jobs for a specified job source class."""
    usage = (
        "Usage: %prog [options] JOB_SOURCE\n\n"
        "For more help, run:\n"
        "    cronscripts/process-job-source-groups.py --help")

    description = (
        "Takes pending jobs of the given type off the queue and runs them.")

    def __init__(self):
        super(ProcessJobSource, self).__init__()
        # The fromlist argument is necessary so that __import__()
        # returns the bottom submodule instead of the top one.
        module = __import__(self.config_section.module,
                            fromlist=[self.job_source_name])
        self.source_interface = getattr(module, self.job_source_name)

    @property
    def config_name(self):
        return self.job_source_name

    @property
    def config_section(self):
        return getattr(config, self.config_name)

    @property
    def dbuser(self):
        return self.config_section.dbuser

    @property
    def name(self):
        return 'process-job-source-%s' % self.job_source_name

    @property
    def runner_class(self):
        runner_class_name = getattr(
            self.config_section, 'runner_class', 'JobRunner')
        # Override attributes that are normally set in __init__().
        return getattr(runner, runner_class_name)

    def add_my_options(self):
        self.parser.add_option(
            '--log-twisted', action='store_true', default=False,
            help='Enable extra Twisted logging.')

    def handle_options(self):
        if len(self.args) != 1:
            self.parser.print_help()
            sys.exit(1)
        self.job_source_name = self.args[0]
        super(ProcessJobSource, self).handle_options()

    def job_counts(self, jobs):
        """Return a list of tuples containing the job name and counts."""
        counts = defaultdict(lambda: 0)
        for job in jobs:
            counts[job.__class__.__name__] += 1
        return sorted(counts.items())

    def main(self):
        if self.options.verbose:
            log.startLogging(sys.stdout)
        errorlog.globalErrorUtility.configure(self.config_name)
        job_source = getUtility(self.source_interface)
        kwargs = {}
        if getattr(self.options, 'log_twisted', False):
            kwargs['_log_twisted'] = True
        runner = self.runner_class.runFromSource(
            job_source, self.dbuser, self.logger, **kwargs)
        for name, count in self.job_counts(runner.completed_jobs):
            self.logger.info('Ran %d %s jobs.', count, name)
        for name, count in self.job_counts(runner.incomplete_jobs):
            self.logger.info('%d %s jobs did not complete.', count, name)


if __name__ == '__main__':
    script = ProcessJobSource()
    script.lock_and_run()
