#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""When passed a CodeImportJob id on the command line, process that job.

The actual work of processing a job is done by the code-import-worker.py
script which this process runs as a child process and updates the database on
its progress and result.

This script is usually run by the code-import-dispatcher cronscript.
"""

__metaclass__ = type


import _pythonpath

import os

from twisted.internet import (
    defer,
    reactor,
    )
from twisted.python import log
from twisted.web import xmlrpc

from lp.codehosting.codeimport.workermonitor import CodeImportWorkerMonitor
from lp.services.config import config
from lp.services.scripts.base import LaunchpadScript
from lp.services.twistedsupport.loggingsupport import set_up_oops_reporting


class CodeImportWorker(LaunchpadScript):

    def __init__(self, name, dbuser=None, test_args=None):
        LaunchpadScript.__init__(self, name, dbuser, test_args)
        # The logfile changes its name according to the code in
        # CodeImportDispatcher, so we pull it from the command line
        # options.
        set_up_oops_reporting(
            self.name, 'codeimportworker', logfile=self.options.log_file)

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            "--access-policy", type="choice", metavar="ACCESS_POLICY",
            choices=["anything", "default"], default=None)

    def _init_db(self, isolation):
        # This script doesn't access the database.
        pass

    def main(self):
        arg, = self.args
        job_id = int(arg)
        # XXX: MichaelHudson 2008-05-07 bug=227586: Setting up the component
        # architecture overrides $GNUPGHOME to something stupid.
        os.environ['GNUPGHOME'] = ''
        reactor.callWhenRunning(self._do_import, job_id)
        reactor.run()

    def _do_import(self, job_id):
        defer.maybeDeferred(self._main, job_id).addErrback(
            log.err).addCallback(
            lambda ignored: reactor.stop())

    def _main(self, job_id):
        worker = CodeImportWorkerMonitor(
            job_id, self.logger,
            xmlrpc.Proxy(config.codeimportdispatcher.codeimportscheduler_url),
            self.options.access_policy)
        return worker.run()

if __name__ == '__main__':
    script = CodeImportWorker('codeimportworker')
    script.run()
