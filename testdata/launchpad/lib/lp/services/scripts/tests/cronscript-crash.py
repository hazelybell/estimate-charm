#!/usr/bin/python -S
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Cronscript that raises an unhandled exception."""

__metaclass__ = type
__all__ = []

import _pythonpath

from lp.services.scripts.base import LaunchpadCronScript
from lp.services.webapp.errorlog import globalErrorUtility


class CrashScript(LaunchpadCronScript):

    def main(self):
        self.oopses = []
        globalErrorUtility._oops_config.publishers[:] = [self.oopses.append]

        self.logger.debug("This is debug level")
        # Debug messages do not generate an OOPS.
        assert not self.oopses, "oops reported %r" % (self.oopses,)

        self.logger.warn("This is a warning")
        if len(self.oopses):
            self.logger.info("New OOPS detected")
        del self.oopses[:]

        self.logger.critical("This is critical")
        if len(self.oopses):
            self.logger.info("New OOPS detected")

        raise NotImplementedError("Whoops")


if __name__ == "__main__":
    script = CrashScript("crash")
    script.lock_and_run()
