# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the cronscript_enabled function in scripts/base.py."""

__metaclass__ = type

import os.path
import subprocess
import sys
from tempfile import NamedTemporaryFile
from textwrap import dedent

from lp.services.log.logger import BufferLogger
from lp.services.scripts.base import cronscript_enabled
from lp.testing import TestCase


class TestCronscriptEnabled(TestCase):

    def setUp(self):
        super(TestCronscriptEnabled, self).setUp()
        self.log = BufferLogger()

    def makeConfig(self, body):
        tempfile = NamedTemporaryFile(suffix='.ini')
        tempfile.write(body)
        tempfile.flush()
        # Ensure a reference is kept until the test is over.
        # tempfile will then clean itself up.
        self.addCleanup(lambda x: None, tempfile)
        return 'file:' + os.path.abspath(tempfile.name)

    def test_noconfig(self):
        enabled = cronscript_enabled('file:/idontexist.ini', 'foo', self.log)
        self.assertIs(True, enabled)

    def test_emptyconfig(self):
        config = self.makeConfig('')
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(True, enabled)

    def test_default_true(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            enabled: True
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(True, enabled)

    def test_default_false(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            enabled: False
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(False, enabled)

    def test_specific_true(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            enabled: False
            [foo]
            enabled: True
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(True, enabled)

    def test_specific_false(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            enabled: True
            [foo]
            enabled: False
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(False, enabled)

    def test_broken_true(self):
        config = self.makeConfig(dedent("""\
            # This file is unparsable
            [DEFAULT
            enabled: False
            [foo
            enabled: False
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(True, enabled)

    def test_invalid_boolean_true(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            enabled: whoops
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(True, enabled)

    def test_specific_missing_fallsback(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            enabled: False
            [foo]
            # There is a typo in the next line.
            enobled: True
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(False, enabled)

    def test_default_missing_fallsback(self):
        config = self.makeConfig(dedent("""\
            [DEFAULT]
            # There is a typo in the next line. Fallsback to hardcoded
            # default.
            enobled: False
            [foo]
            # There is a typo in the next line.
            enobled: False
            """))
        enabled = cronscript_enabled(config, 'foo', self.log)
        self.assertIs(True, enabled)

    def test_enabled_cronscript(self):
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), 'example-cronscript.py'),
            '-qqqqq', 'enabled',
            ]
        self.assertEqual(42, subprocess.call(cmd))

    def test_disabled_cronscript(self):
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), 'example-cronscript.py'),
            '-qqqqq', 'disabled',
            ]
        self.assertEqual(0, subprocess.call(cmd))
