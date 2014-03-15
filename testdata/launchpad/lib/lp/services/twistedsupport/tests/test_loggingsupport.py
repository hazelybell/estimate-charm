# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the integration between Twisted's logging and Launchpad's."""

__metaclass__ = type

import os

from fixtures import TempDir
import pytz

from lp.services.twistedsupport.loggingsupport import LaunchpadLogFile
from lp.testing import TestCase


UTC = pytz.utc


class TestLaunchpadLogFile(TestCase):

    def setUp(self):
        super(TestLaunchpadLogFile, self).setUp()
        self.temp_dir = self.useFixture(TempDir()).path

    def testInitialization(self):
        """`LaunchpadLogFile` initialization.

        It has proper default values for 'maxRotatedFiles' (5) and
        'compressLast' (3), although allows call sites to specify their own
        values.

        The initialization fails if the given 'compressLast' value is
        incoherent with 'maxRotatedFiles', like requesting the compression
        of more files that we have rotated.
        """
        # Default behavior.
        log_file = LaunchpadLogFile('test.log', self.temp_dir)
        self.assertEqual(5, log_file.maxRotatedFiles)
        self.assertEqual(3, log_file.compressLast)

        # Keeping only compressed rotated logs.
        log_file = LaunchpadLogFile(
            'test.log', self.temp_dir, maxRotatedFiles=1, compressLast=1)
        self.assertEqual(1, log_file.maxRotatedFiles)
        self.assertEqual(1, log_file.compressLast)

        # Inconsistent parameters, compression more than kept rotated files.
        self.assertRaises(
            AssertionError, LaunchpadLogFile, 'test.log', self.temp_dir,
            maxRotatedFiles=1, compressLast=2)

    def createTestFile(self, name, content='nothing'):
        """Create a new file in the test directory."""
        file_path = os.path.join(self.temp_dir, name)
        fd = open(file_path, 'w')
        fd.write(content)
        fd.close()
        return file_path

    def listTestFiles(self):
        """Return a ordered list of files in the test directory."""
        return sorted(os.listdir(self.temp_dir))

    def testListLogs(self):
        """Check `LaunchpadLogFile.listLogs`

        This lookup method return the rotated logfiles present in the
        logging directory. It ignores the current log file and extraneous.

        Only corresponding log files (plain and compressed) are returned,
        the newest first.
        """
        log_file = LaunchpadLogFile('test.log', self.temp_dir)
        self.assertEqual(['test.log'], self.listTestFiles())
        self.assertEqual([], log_file.listLogs())

        self.createTestFile('boing')
        self.assertEqual([], log_file.listLogs())

        self.createTestFile('test.log.2000-12-31')
        self.createTestFile('test.log.2000-12-30.bz2')
        self.assertEqual(
            ['test.log.2000-12-31', 'test.log.2000-12-30.bz2'],
            [os.path.basename(log_path) for log_path in log_file.listLogs()])

    def testRotate(self):
        """Check `LaunchpadLogFile.rotate`.

        Check if the log file is rotated as expected and only the specified
        number to rotated files are kept, also that the specified number of
        compressed files are created.
        """
        log_file = LaunchpadLogFile(
            'test.log', self.temp_dir, maxRotatedFiles=2, compressLast=1)

        # Monkey-patch DailyLogFile.suffix to be time independent.
        self.local_index = 0

        def testSuffix(tupledate):
            self.local_index += 1
            return str(self.local_index)

        log_file.suffix = testSuffix

        log_file.rotate()
        self.assertEqual(
            ['test.log', 'test.log.1'],
            self.listTestFiles())

        log_file.rotate()
        self.assertEqual(
            ['test.log', 'test.log.1.bz2', 'test.log.2'],
            self.listTestFiles())

        log_file.rotate()
        self.assertEqual(
            ['test.log', 'test.log.2.bz2', 'test.log.3'],
            self.listTestFiles())
