#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This module uses relative imports.
"""
Gina launcher script. Handles commandline options and makes the proper
calls to the other classes and instances.

The callstack is essentially:
    main -> run_gina
                -> import_sourcepackages -> do_one_sourcepackage
                -> import_binarypackages -> do_one_binarypackage
"""

__metaclass__ = type

import _pythonpath

import sys

from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript
from lp.soyuz.scripts.gina.runner import run_gina


class Gina(LaunchpadCronScript):

    def __init__(self):
        super(Gina, self).__init__(name='gina', dbuser=config.gina.dbuser)

    @property
    def usage(self):
        return "%s [options] (targets|--all)" % sys.argv[0]

    def add_my_options(self):
        self.parser.add_option("-a", "--all", action="store_true",
            help="Run all sections defined in launchpad.conf (in order)",
            dest="all", default=False)
        self.parser.add_option("-l", "--list-targets", action="store_true",
            help="List configured import targets", dest="list_targets",
            default=False)

    def getConfiguredTargets(self):
        """Get the configured import targets.

        Gina's targets are configured as "[gina_target.*]" sections in the
        LAZR config.
        """
        sections = config.getByCategory('gina_target', [])
        targets = [
            target.category_and_section_names[1] for target in sections]
        if len(targets) == 0:
            self.logger.warn("No gina_target entries configured.")
        return targets

    def listTargets(self, targets):
        """Print out the given targets list."""
        for target in targets:
            self.logger.info("Target: %s", target)

    def getTargets(self, possible_targets):
        """Get targets to process."""
        targets = self.args
        if self.options.all:
            return list(possible_targets)
        else:
            if not targets:
                self.parser.error(
                    "Must specify at least one target to run, or --all")
            for target in targets:
                if target not in possible_targets:
                    self.parser.error(
                        "No Gina target %s in config file" % target)
            return targets

    def main(self):
        possible_targets = self.getConfiguredTargets()

        if self.options.list_targets:
            self.listTargets(possible_targets)
            return

        for target in self.getTargets(possible_targets):
            target_section = config['gina_target.%s' % target]
            run_gina(self.options, self.txn, target_section)


if __name__ == "__main__":
    gina = Gina()
    gina.lock_and_run()
