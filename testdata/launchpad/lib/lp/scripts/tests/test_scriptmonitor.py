# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test scriptmonitor.py."""

__metaclass__ = type

from unittest import TestCase

from lp.scripts.scriptmonitor import check_script
from lp.services.database.sqlbase import connect
from lp.services.scripts import logger
from lp.testing.layers import DatabaseLayer


class CheckScriptTestCase(TestCase):
    """Test script activity."""
    layer = DatabaseLayer

    def setUp(self):
        # We need some fake options so that this test doesn't try to parse
        # sys.args.  We don't care about the log messages, so just throw them
        # away.
        class FakeOptions:
            log_file = None
            loglevel = 1000
            verbose = False
            milliseconds = False
        self.con = connect()
        self.log = logger(FakeOptions())

    def tearDown(self):
        self.con.close()

    def test_scriptfound(self):
        self.assertEqual(
            check_script(self.con, self.log, 'localhost',
                         'script-monitor-test',
                         '2007-05-23 00:30:00', '2007-05-23 01:30:00'), None)

    def test_scriptnotfound_timing(self):
        output = ("The script 'script-monitor-test' didn't run on "
            "'localhost' between 2007-05-23 01:30:00 and "
            "2007-05-23 02:30:00 (last seen 2007-05-23 01:00:00)")
        self.assertEqual(
            check_script(self.con, self.log, 'localhost',
                         'script-monitor-test',
                         '2007-05-23 01:30:00', '2007-05-23 02:30:00'),
            output)

    def test_scriptnotfound_hostname(self):
        output = ("The script 'script-monitor-test' didn't run on "
            "'notlocalhost' between 2007-05-23 00:30:00 and "
            "2007-05-23 01:30:00")
        self.assertEqual(
            check_script(self.con, self.log, 'notlocalhost',
                         'script-monitor-test',
                         '2007-05-23 00:30:00', '2007-05-23 01:30:00'),
            output)
