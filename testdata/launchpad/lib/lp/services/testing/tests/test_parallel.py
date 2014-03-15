# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parallel test glue."""

__metaclass__ = type

from StringIO import StringIO
import subprocess
import tempfile

from fixtures import (
    PopenFixture,
    TestWithFixtures,
    )
from testtools import (
    TestCase,
    TestResult,
    )

from lp.services.testing.parallel import (
    find_load_list,
    find_tests,
    ListTestCase,
    prepare_argv,
    )


class TestListTestCase(TestCase, TestWithFixtures):

    def test_run(self):
        # ListTestCase.run should run bin/test adding in --subunit,
        # --load-list, with a list file containing the supplied list ids.
        def check_list_file(info):
            """Callback from subprocess.Popen for testing run()."""
            # A temp file should have been made.
            args = info['args']
            load_list = find_load_list(args)
            self.assertNotEqual(None, load_list)
            with open(load_list, 'rt') as testlist:
                contents = testlist.readlines()
            self.assertEqual(['foo\n', 'bar\n'], contents)
            return {'stdout': StringIO(''), 'stdin': StringIO()}
        popen = self.useFixture(PopenFixture(check_list_file))
        case = ListTestCase(['foo', 'bar'], ['bin/test'])
        self.assertEqual([], popen.procs)
        result = TestResult()
        case.run(result)
        self.assertEqual(0, result.testsRun)
        self.assertEqual(1, len(popen.procs))
        self.assertEqual(['bin/test', '--subunit', '--load-list'],
            popen.procs[0]._args['args'][:-1])


class TestUtilities(TestCase, TestWithFixtures):

    def test_prepare_argv_removes_subunit(self):
        self.assertEqual(
            ['bin/test', 'foo'],
            prepare_argv(['bin/test', '--subunit', 'foo']))

    def test_prepare_argv_removes_parallel(self):
        self.assertEqual(
            ['bin/test', 'foo'],
            prepare_argv(['bin/test', '--parallel', 'foo']))

    def test_prepare_argv_removes_load_list_with_equals(self):
        self.assertEqual(
            ['bin/test', 'foo'],
            prepare_argv(['bin/test', '--load-list=Foo', 'foo']))

    def test_prepare_argv_removes_load_2_arg_form(self):
        self.assertEqual(
            ['bin/test', 'foo'],
            prepare_argv(['bin/test', '--load-list', 'Foo', 'foo']))

    def test_find_tests_honours_list_list_equals(self):
        with tempfile.NamedTemporaryFile() as listfile:
            listfile.write('foo\nbar\n')
            listfile.flush()
            self.assertEqual(
                ['foo', 'bar'],
                find_tests(
                    ['bin/test', '--load-list=%s' % listfile.name, 'foo']))

    def test_find_tests_honours_list_list_two_arg_form(self):
        with tempfile.NamedTemporaryFile() as listfile:
            listfile.write('foo\nbar\n')
            listfile.flush()
            self.assertEqual(
                ['foo', 'bar'],
                find_tests(
                    ['bin/test', '--load-list', listfile.name, 'foo']))

    def test_find_tests_live(self):
        # When --load-tests wasn't supplied, find_tests needs to run bin/test
        # with --list-tests and --subunit, and parse the resulting subunit
        # stream.
        def inject_testlist(args):
            self.assertEqual(subprocess.PIPE, args['stdin'])
            self.assertEqual(subprocess.PIPE, args['stdout'])
            self.assertEqual(
                ['bin/test', '-vt', 'filter', '--list-tests', '--subunit'],
                args['args'])
            return {'stdin': StringIO(), 'stdout': StringIO(u"""\
test: quux
successful: quux
test: glom
successful: glom
""")}
        self.useFixture(PopenFixture(inject_testlist))
        self.assertEqual(
            ['quux', 'glom'],
            find_tests(['bin/test', '-vt', 'filter', '--parallel']))
