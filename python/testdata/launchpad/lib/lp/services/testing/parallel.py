# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parallel test glue."""

__metaclass__ = type
__all__ = ["main"]

import itertools
import subprocess
import sys
import tempfile

from bzrlib.osutils import local_concurrency
from subunit import ProtocolTestCase
from subunit.run import SubunitTestRunner
from testtools import (
    ConcurrentTestSuite,
    TestResult,
    TextTestResult,
    )
from testtools.compat import unicode_output_stream


def prepare_argv(argv):
    """Remove options from argv that would be added by ListTestCase."""
    result = []
    skipn = 0
    for pos, arg in enumerate(argv):
        if skipn:
            skipn -= 1
            continue
        if arg in ('--subunit', '--parallel'):
            continue
        if arg.startswith('--load-list='):
            continue
        if arg == '--load-list':
            skipn = 1
            continue
        result.append(arg)
    return result


def find_load_list(args):
    """Get the value passed in to --load-list=FOO."""
    load_list = None
    for pos, arg in enumerate(args):
        if arg.startswith('--load-list='):
            load_list = arg[len('--load-list='):]
        if arg == '--load-list':
            load_list = args[pos+1]
    return load_list


class GatherIDs(TestResult):
    """Gather test ids from a test run."""

    def __init__(self):
        super(GatherIDs, self).__init__()
        self.ids = []

    def startTest(self, test):
        super(GatherIDs, self).startTest(test)
        self.ids.append(test.id())


def find_tests(argv):
    """Find tests to parallel run.

    :param argv: The argv given to the test runner, used to get the tests to
        run.
    :return: A list of test IDs.
    """
    load_list = find_load_list(argv)
    if load_list:
        # just use the load_list
        with open(load_list, 'rt') as list_file:
            return [id for id in list_file.read().split('\n') if id]
    # run in --list-tests mode
    argv = prepare_argv(argv) + ['--list-tests', '--subunit']
    process = subprocess.Popen(argv, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE)
    process.stdin.close()
    test = ProtocolTestCase(process.stdout)
    result = GatherIDs()
    test.run(result)
    process.wait()
    if process.returncode:
        raise Exception('error listing tests: %s' % err)
    return result.ids


class ListTestCase(ProtocolTestCase):

    def __init__(self, test_ids, args):
        """Create a ListTestCase.

        :param test_ids: The ids of the tests to run.
        :param args: The args to use to run the test runner (without
            --load-list - that is added automatically).
        """
        self._test_ids = test_ids
        self._args = args

    def run(self, result):
        with tempfile.NamedTemporaryFile() as test_list_file:
            for test_id in self._test_ids:
                test_list_file.write(test_id + '\n')
            test_list_file.flush()
            argv = self._args + ['--subunit', '--load-list', test_list_file.name]
            process = subprocess.Popen(argv, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, bufsize=1)
            try:
                # If it tries to read, give it EOF.
                process.stdin.close()
                ProtocolTestCase.__init__(self, process.stdout)
                ProtocolTestCase.run(self, result)
            finally:
                process.wait()


def concurrency():
    """Return the number of current tests we should run on this machine.
    
    Each test is run in its own process, and we assume that the optimal number
    is one per core.
    """
    # TODO: limit by memory as well.
    procs = local_concurrency()
    return procs


def partition_tests(test_ids, count):
    """Partition suite into count lists of tests."""
    # This just assigns tests in a round-robin fashion.  On one hand this
    # splits up blocks of related tests that might run faster if they shared
    # resources, but on the other it avoids assigning blocks of slow tests to
    # just one partition.  So the slowest partition shouldn't be much slower
    # than the fastest.
    partitions = [list() for i in range(count)]
    for partition, test_id in itertools.izip(itertools.cycle(partitions), test_ids):
        partition.append(test_id)
    return partitions


def main(argv, prepare_args=prepare_argv, find_tests=find_tests):
    """CLI entry point to adapt a test run to parallel testing."""
    child_args = prepare_argv(argv)
    test_ids = find_tests(argv)
    # We could create a proxy object per test id if desired in future)
    def parallelise_tests(suite):
        test_ids = list(suite)[0]._test_ids
        count = concurrency()
        partitions = partition_tests(test_ids, count)
        return [ListTestCase(partition, child_args) for partition in partitions]
    suite = ConcurrentTestSuite(ListTestCase(test_ids, None), parallelise_tests)
    if '--subunit' in argv:
        runner = SubunitTestRunner(sys.stdout)
        result = runner.run(suite)
    else:
        stream = unicode_output_stream(sys.stdout)
        result = TextTestResult(stream)
        result.startTestRun()
        try:
            suite.run(result)
        finally:
            result.stopTestRun()
    if result.wasSuccessful():
        return 0
    return -1

