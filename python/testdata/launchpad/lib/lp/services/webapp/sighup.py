# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Signal handler for SIGHUP."""

__metaclass__ = type
__all__ = []

import logging
import signal

from lp.services.webapp import haproxy


def sighup_handler(signum, frame):
    """Switch the state of the HAProxy going_down flag."""
    haproxy.switch_going_down_flag()
    logging.getLogger('sighup').info(
        'Received SIGHUP, swiched going_down flag to %s' %
        haproxy.going_down_flag)


def setup_sighup(event):
    """Configure the SIGHUP handler.  Called at startup."""
    signal.signal(signal.SIGHUP, sighup_handler)

