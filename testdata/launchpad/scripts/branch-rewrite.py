#!/usr/bin/python -uS
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script intended to run as a :prg: RewriteMap.

See http://httpd.apache.org/docs/2.2/mod/mod_rewrite.html#rewritemap for the
documentation of the very simple 'protocol' Apache uses to talk to us, and
lp.codehosting.rewrite.BranchRewriter for the logic of the rewritemap.
"""

import _pythonpath

import os
import sys

import transaction

from lp.codehosting.rewrite import BranchRewriter
from lp.services.config import config
from lp.services.log.loglevels import (
    INFO,
    WARNING,
    )
from lp.services.scripts.base import LaunchpadScript


class BranchRewriteScript(LaunchpadScript):

    # By default, only emit WARNING and above messages to stderr, which
    # will end up in the Apache error log.
    loglevel = WARNING

    def add_my_options(self):
        """Make the logging go to a file by default.

        Because this script is run by Apache, logging to stderr results in our
        log output ending up in Apache's error.log, which is not so useful.
        We hack the OptionParser to set the default (which will be applied;
        Apache doesn't pass any arguments to the script it starts up) to a
        value from the config.
        """
        log_file_location = config.codehosting.rewrite_script_log_file
        log_file_directory = os.path.dirname(log_file_location)
        if not os.path.isdir(log_file_directory):
            os.makedirs(log_file_directory)
        self.parser.defaults['log_file'] = log_file_location
        self.parser.defaults['log_file_level'] = INFO

    def main(self):
        rewriter = BranchRewriter(self.logger)
        self.logger.debug("Starting up...")
        while True:
            try:
                line = sys.stdin.readline()
                transaction.abort()
                # Mod-rewrite always gives us a newline terminated string.
                if line:
                    print rewriter.rewriteLine(line.strip())
                else:
                    # Standard input has been closed, so die.
                    return
            except KeyboardInterrupt:
                sys.exit()
            except Exception:
                self.logger.exception('Exception occurred:')
                print "NULL"
                # The exception might have been a DisconnectionError or
                # similar. Cleanup such as database reconnection will
                # not happen until the transaction is rolled back.
                try:
                    transaction.abort()
                except Exception:
                    self.logger.exception('Exception occurred in abort:')


if __name__ == '__main__':
    BranchRewriteScript("branch-rewrite", dbuser='branch-rewrite').run(
        isolation='autocommit')
