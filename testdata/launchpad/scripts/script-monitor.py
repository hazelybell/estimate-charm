#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Monitor scripts."""

__metaclass__ = type
__all__ = ['check_script']

import _pythonpath

from datetime import (
    datetime,
    timedelta,
    )
from email.MIMEText import MIMEText
from optparse import OptionParser
import smtplib
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
    # There's a lot of untested stuff here: parsing options and sending
    # emails - this should be moved into a testable location.
    # Also duplicated code in scripts/script-monitor-nagios.py
    parser = OptionParser(
            '%prog [options] (minutes) (host:scriptname) [host:scriptname]'
            )
    db_options(parser)
    logger_options(parser)

    (options, args) = parser.parse_args()

    if len(args) < 2:
        parser.error("Must specify at time in minutes and "
            "at least one host and script")

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
                parser.error(
                    "%r is not in the format 'host:scriptname'" % (arg,))
            hosts_scripts.append((hostname, scriptname))
    except ValueError:
        parser.error("Must specify time in minutes and "
            "at least one host and script")

    log = logger(options)

    try:
        log.debug("Connecting to database")
        con = connect()
        error_found = False
        msg, subj = [], []
        for hostname, scriptname in hosts_scripts:
            failure_msg = check_script(con, log, hostname,
                scriptname, completed_from, completed_to)
            if failure_msg is not None:
                msg.append(failure_msg)
                subj.append("%s:%s" % (hostname, scriptname))
                error_found = 2
        if error_found:
            # Construct our email.
            msg = MIMEText('\n'.join(msg))
            msg['Subject'] = "Scripts failed to run: %s" % ", ".join(subj)
            msg['From'] = 'script-failures@launchpad.net'
            msg['Reply-To'] = 'launchpad@lists.canonical.com'
            msg['To'] = 'launchpad@lists.canonical.com'

            # Send out the email.
            smtp = smtplib.SMTP()
            smtp.connect()
            smtp.sendmail(
                'script-failures@launchpad.net',
                ['launchpad@lists.canonical.com'], msg.as_string())
            smtp.close()
            return 2
    except:
        log.exception("Unhandled exception")
        return 1

if __name__ == '__main__':
    sys.exit(main())
