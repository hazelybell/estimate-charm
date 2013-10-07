# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from zope.component import getUtility

from lp.services.config import config
from lp.services.scripts.interfaces.scriptactivity import IScriptActivitySet
from lp.testing.layers import LaunchpadZopelessLayer


class TestProcessUpload(unittest.TestCase):
    """Test the process-upload.py script."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        self.queue_location = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.queue_location)

    def runProcessUpload(self, extra_args=None):
        """Run process-upload.py, returning the result and output."""
        if extra_args is None:
            extra_args = []
        script = os.path.join(config.root, "scripts", "process-upload.py")
        args = [sys.executable, script, "-vvv", self.queue_location]
        args.extend(extra_args)
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        return (process.returncode, stdout, stderr)

    def assertQueuePath(self, path):
        """Check if given path exists within the current queue_location."""
        probe_path = os.path.join(self.queue_location, path)
        self.assertTrue(
            os.path.exists(probe_path), "'%s' does not exist." % path)

    def testSimpleRun(self):
        """Try a simple process-upload run.

        Observe it creating the required directory tree for a given
        empty queue_location.

        It should also generate some scriptactivity.
        """
        # No scriptactivity should exist before it's run.
        activity = getUtility(
            IScriptActivitySet).getLastActivity('process-upload')
        self.assertTrue(activity is None, "'activity' should be None")

        returncode, out, err = self.runProcessUpload()
        self.assertEqual(0, returncode)

        # There should now be some scriptactivity.
        activity = getUtility(
            IScriptActivitySet).getLastActivity('process-upload')
        self.assertFalse(activity is None, "'activity' should not be None")

        # directory tree in place.
        for directory in ['incoming', 'accepted', 'rejected', 'failed']:
            self.assertQueuePath(directory)

        # just to check if local assertion is working as expect.
        self.assertRaises(AssertionError, self.assertQueuePath, 'foobar')

        # Explicitly mark the database dirty.
        self.layer.force_dirty_database()

    def testTopLevelLockFile(self):
        """Try a simple process-upload run.

        Expect it to exit earlier due the occupied lockfile
        """
        # acquire the process-upload lockfile locally
        from contrib.glock import GlobalLock
        locker = GlobalLock('/var/lock/process-upload-insecure.lock')
        locker.acquire()

        returncode, out, err = self.runProcessUpload(
            extra_args=['-C', 'insecure'])

        # the process-upload call terminated with ERROR and
        # proper log message
        self.assertEqual(1, returncode)
        self.assert_(
            'INFO    Creating lockfile: '
            '/var/lock/process-upload-insecure.lock' in err.splitlines())
        self.assert_(
            'INFO    Lockfile /var/lock/process-upload-insecure.lock in use'
            in err.splitlines())

        # release the locally acquired lockfile
        locker.release()
