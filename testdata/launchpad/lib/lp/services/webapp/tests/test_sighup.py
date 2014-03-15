# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the SIGHUP signal handler."""

__metaclass__ = type

import os
import signal

from lp.services.webapp import (
    haproxy,
    sighup,
    )
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer


class SIGHUPTestCase(TestCase):
    layer = FunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        self.original_handler = signal.getsignal(signal.SIGHUP)
        self.addCleanup(signal.signal, signal.SIGHUP, self.original_handler)
        sighup.setup_sighup(None)

        self.original_flag = haproxy.going_down_flag
        self.addCleanup(haproxy.set_going_down_flag, self.original_flag)

    def test_sighup(self):
        # Sending SIGHUP should switch the PID
        os.kill(os.getpid(), signal.SIGHUP)
        self.assertEquals(not self.original_flag, haproxy.going_down_flag)

        # Sending again should switch again.
        os.kill(os.getpid(), signal.SIGHUP)
        self.assertEquals(self.original_flag, haproxy.going_down_flag)
