# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parse logging command line arguments and output some log messages.

Used by test_logger.txt.
"""

__metaclass__ = type
__all__ = []

# Monkey patch time.gmtime to make our tests easier to read.
import time


def fake_gmtime(ignored_seconds):
    # 1985-12-21 13:45:55
    return (1985, 12, 21, 13, 45, 55, 5, 355, 0)
time.gmtime = fake_gmtime

from optparse import OptionParser

from lp.services.scripts.logger import (
    logger,
    logger_options,
    )

parser = OptionParser()
logger_options(parser)

options, args = parser.parse_args()

if len(args) > 0:
    print "Args: %s" % repr(args)

log = logger(options, 'loglevels')

log.error("This is an error")
log.warn("This is a warning")
log.info("This is info")
log.debug("This is debug")
log.debug2("This is debug2")
log.debug3("This is debug3")
log.debug4("This is debug4")
log.debug5("This is debug5")
log.debug6("This is debug6")
log.debug7("This is debug7")
log.debug8("This is debug8")
log.debug9("This is debug9")
