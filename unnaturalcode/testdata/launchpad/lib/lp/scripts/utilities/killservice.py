#!../bin/py

# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This module uses relative imports.
__metaclass__ = type

import logging
from optparse import OptionParser
import os
from signal import (
    SIGKILL,
    SIGTERM,
    )
import time

from lp.services.config import config
from lp.services.mailman.runmailman import stop_mailman
from lp.services.pidfile import (
    get_pid,
    pidfile_path,
    remove_pidfile,
    )
from lp.services.scripts import (
    logger,
    logger_options,
    )


def main():
    parser = OptionParser('Usage: %prog [options] [SERVICE ...]')
    parser.add_option("-w", "--wait", metavar="SECS",
        default=20, type="int",
        help="Wait up to SECS seconds for processes "
            "to die before retrying with SIGKILL")
    logger_options(parser, logging.INFO)
    (options, args) = parser.parse_args()
    log = logger(options)
    if len(args) < 1:
        parser.error('No service name provided')

    pids = [] # List of pids we tried to kill.
    services = args[:]

    # Mailman is special, but only stop it if it was launched.
    if 'mailman' in services:
        if config.mailman.launch:
            stop_mailman()
        services.remove('mailman')

    for service in services:
        log.debug("PID file is %s", pidfile_path(service))
        try:
            pid = get_pid(service)
        except ValueError as error:
            log.error(error)
            continue
        if pid is not None:
            log.info("Killing %s (%d)", service, pid)
            try:
                os.kill(pid, SIGTERM)
                pids.append((service, pid))
            except OSError as x:
                log.error(
                    "Unable to SIGTERM %s (%d) - %s",
                    service, pid, x.strerror)
        else:
            log.debug("No PID file for %s", service)

    wait_for_pids(pids, options.wait, log)

    # Anything that didn't die, kill harder with SIGKILL.
    for service, pid in pids:
        if not process_exists(pid):
            continue
        log.warn(
            "SIGTERM failed to kill %s (%d). Trying SIGKILL", service, pid)
        try:
            os.kill(pid, SIGKILL)
        except OSError as x:
            log.error(
                "Unable to SIGKILL %s (%d) - %s", service, pid, x.strerror)

    wait_for_pids(pids, options.wait, log)

    # Report anything still left running after a SIGKILL.
    for service, pid in pids:
        if process_exists(pid):
            log.error("SIGKILL didn't terminate %s (%d)", service, pid)

    # Remove any pidfiles that didn't get cleaned up if there is no
    # corresponding process (from an unkillable process, or maybe some
    # other job has relaunched it while we were not looking).
    for service in services:
        pid = get_pid(service)
        if pid is not None and not process_exists(pid):
            try:
                remove_pidfile(service)
            except OSError:
                pass


def process_exists(pid):
    """True if the given process exists."""
    try:
        os.getpgid(pid)
    except OSError as x:
        if x.errno == 3:
            return False
        logging.error("Unknown exception from getpgid - %s", str(x))
    return True


def wait_for_pids(pids, wait, log):
    """
    Wait until all signalled processes are dead, or until we hit the
    timeout.

    Processes discovered to be dead are removed from the list.

    :param pids: A list of (service, pid).

    :param wait: How many seconds to wait.
    """
    wait_start = time.time()
    while len(pids) > 0 and time.time() < wait_start + wait:
        for service, pid in pids[:]: # Copy pids because we mutate it.
            if not process_exists(pid):
                pids.remove((service, pid))
        time.sleep(0.1)
