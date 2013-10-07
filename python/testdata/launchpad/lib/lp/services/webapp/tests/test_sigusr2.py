# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the SIGUSR2 signal handler."""

__metaclass__ = type
__all__ = []

import os.path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class SIGUSR2TestCase(unittest.TestCase):
    def setUp(self):
        self.logdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.logdir)

    def test_sigusr2(self):
        main_log = os.path.join(self.logdir, 'main')
        cycled_log = os.path.join(self.logdir, 'cycled')

        helper_cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), 'sigusr2.py'),
            main_log]
        proc = subprocess.Popen(
            helper_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            # Wait until things have started up.
            self.sync('ready')

            # Make the helper emit a log message.
            os.kill(proc.pid, signal.SIGUSR1)
            self.sync('emit_1')

            # Move the log file under the helper's feed.
            os.rename(main_log, cycled_log)

            # Emit another log message. This will go to cycled_log
            # as the helper hasn't reopened its logs yet.
            os.kill(proc.pid, signal.SIGUSR1)
            self.sync('emit_2')

            # Invoke the sigusr2 handler in the helper. This reopens
            # the logs, so the helper will start logging to main_log
            # again.
            os.kill(proc.pid, signal.SIGUSR2)
            self.sync('sigusr2')

            # Make the helper emit a log message.
            os.kill(proc.pid, signal.SIGUSR1)
            self.sync('emit_3')
        finally:
            os.kill(proc.pid, signal.SIGKILL)

        # Confirm content in the main log and the cycled log are what we
        # expect.
        self.assertEqual(
            open(cycled_log, 'r').read(), 'Message 1\nMessage 2\n')
        self.assertEqual(open(main_log, 'r').read(), 'Message 3\n')

    def sync(self, step):
        retries = 200
        event_filename = os.path.join(self.logdir, step)
        for i in range(retries):
            if os.path.exists(event_filename):
                os.unlink(event_filename)
                return
            time.sleep(0.3)
        self.fail("sync step %s didn't happen after %d retries." % (
            step, retries))
