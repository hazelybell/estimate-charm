#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Look for and dispatch code import jobs as needed."""

import _pythonpath

from xmlrpclib import ServerProxy

from lp.codehosting.codeimport.dispatcher import CodeImportDispatcher
from lp.services.config import config
from lp.services.scripts.base import LaunchpadScript
from lp.services.webapp.errorlog import globalErrorUtility


class CodeImportDispatcherScript(LaunchpadScript):

    def add_my_options(self):
        self.parser.add_option(
            "--max-jobs", dest="max_jobs", type=int,
            default=config.codeimportdispatcher.max_jobs_per_machine,
            help="The maximum number of jobs to run on this machine.")

    def run(self, use_web_security=False, isolation=None):
        """See `LaunchpadScript.run`.

        We override to avoid all of the setting up all of the component
        architecture and connecting to the database.
        """
        self.main()

    def main(self):
        globalErrorUtility.configure('codeimportdispatcher')

        dispatcher = CodeImportDispatcher(self.logger, self.options.max_jobs)
        dispatcher.findAndDispatchJobs(
            ServerProxy(config.codeimportdispatcher.codeimportscheduler_url))


if __name__ == '__main__':
    script = CodeImportDispatcherScript("codeimportdispatcher")
    script.lock_and_run()

