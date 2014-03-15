# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Check the integrity of the /scripts and /cronscripts."""

__metaclass__ = type

import doctest
import os
import unittest

from testtools import clone_test_with_new_id
from testtools.matchers import DocTestMatches

from lp.services.scripts.tests import find_lp_scripts
from lp.testing import (
    run_script,
    TestCase,
    )


class ScriptsTestCase(TestCase):
    """Check the integrity of all scripts shipped in the tree."""

    def test_script(self):
        # Run self.script_path with '-h' to make sure it runs cleanly.
        cmd_line = self.script_path + " -h"
        out, err, returncode = run_script(cmd_line)
        self.assertThat(err, DocTestMatches('', doctest.REPORT_NDIFF))
        self.assertEqual('', err)
        self.assertEqual(os.EX_OK, returncode)


def make_new_id(old_id, script_path):
    base, name = old_id.rsplit('.', 1)
    script_name = os.path.splitext(os.path.basename(script_path))[0]
    return '.'.join([base, 'script_' + script_name])


def test_suite():
    test = ScriptsTestCase('test_script')
    test_id = test.id()
    suite = unittest.TestSuite()
    for script_path in find_lp_scripts():
        new_test = clone_test_with_new_id(
            test, make_new_id(test_id, script_path))
        new_test.script_path = script_path
        suite.addTest(new_test)
    return suite
