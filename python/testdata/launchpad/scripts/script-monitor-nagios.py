#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Nagios plugin for script monitoring.

This script is needed as separate from script-monitor.py because Nagios
only understands one line of returned text, and interprets specific
return codes as plugin statuses. These are:

    0: OK
    1: WARNING
    2: CRITICAL
    3: UNKNOWN

As such, it was felt more appropriate to separate out the scripts,
even though there is some code duplication.
"""

__metaclass__ = type
__all__ = ['check_script']

import _pythonpath

from datetime import (
    datetime,
    timedelta,
    )
from optparse import OptionParser
import sys
from time import strftime

from lp.scripts.scriptmonitor import check_script
from lp.services.database.sqlbase import connect
from lp.services.scripts import (
    db_options,
    logger,
    logger_options,
    )


def main():
    # XXX: Tom Haddon 2007-07-12
    # There's a lot of untested stuff here: parsing options -
    # this should be moved into a testable location.
    # Also duplicated code in scripts/script-monitor.py
    parser = OptionParser(
            '%prog [options] (minutes) (host:scriptname) [host:scriptname]'
            )
    db_options(parser)
    logger_options(parser)

    (options, args) = parser.parse_args()

    if len(args) < 2:
        print "Must specify time in minutes and " \
            "at least one host and script"
        return 3

    # First argument is the number of minutes into the past
    # we want to look for the scripts on the specified hosts
    try:
        minutes_ago, args = int(args[0]), args[1:]
        start_date = datetime.now() - timedelta(minutes=minutes_ago)

        completed_from = strftime("%Y-%m-%d %H:%M:%S", start_date.timetuple())
        completed_to = strftime(
            "%Y-%m-%d %H:%M:%S", datetime.now().timetuple())

        hosts_scripts = []
        for arg in args:
            try:
                hostname, scriptname = arg.split(':')
            except TypeError:
                print "%r is not in the format 'host:scriptname'" % arg
                return 3
            hosts_scripts.append((hostname, scriptname))
    except ValueError:
        print "Must specify time in minutes and " \
            "at least one host and script"
        return 3

    log = logger(options)

    try:
        log.debug("Connecting to database")
        con = connect()
        error_found = False
        msg = []
        for hostname, scriptname in hosts_scripts:
            failure_msg = check_script(con, log, hostname,
                scriptname, completed_from, completed_to)
            if failure_msg is not None:
                msg.append("%s:%s" % (hostname, scriptname))
                error_found = True
        if error_found:
            # Construct our return message
            print "Scripts failed to run: %s" % ', '.join(msg)
            return 2
        else:
            # Construct our return message
            print "All scripts ran as expected"
            return 0
    except Exception as e:
        # Squeeze the exception type and stringification of the exception
        # value on to one line.
        print "Unhandled exception: %s %r" % (e.__class__.__name__, str(e))
        return 3

if __name__ == '__main__':
    sys.exit(main())
