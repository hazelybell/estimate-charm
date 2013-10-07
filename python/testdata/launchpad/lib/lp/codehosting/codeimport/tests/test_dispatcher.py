# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the code import dispatcher."""

__metaclass__ = type


from optparse import OptionParser
import os
import shutil
import socket
import tempfile

from lp.codehosting.codeimport.dispatcher import CodeImportDispatcher
from lp.services import scripts
from lp.services.log.logger import BufferLogger
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class StubSchedulerClient:
    """A scheduler client that returns a pre-arranged answer."""

    def __init__(self, ids_to_return):
        self.ids_to_return = ids_to_return

    def getJobForMachine(self, machine, limit):
        return self.ids_to_return.pop(0)


class MockSchedulerClient:
    """A scheduler client that records calls to `getJobForMachine`."""

    def __init__(self):
        self.calls = []

    def getJobForMachine(self, machine, limit):
        self.calls.append((machine, limit))
        return 0


class TestCodeImportDispatcherUnit(TestCase):
    """Unit tests for `CodeImportDispatcher`."""

    layer = BaseLayer

    def setUp(self):
        TestCase.setUp(self)
        self.pushConfig('codeimportdispatcher', forced_hostname='none')

    def makeDispatcher(self, worker_limit=10, _sleep=lambda delay: None):
        """Make a `CodeImportDispatcher`."""
        return CodeImportDispatcher(
            BufferLogger(), worker_limit, _sleep=_sleep)

    def test_getHostname(self):
        # By default, getHostname return the same as socket.gethostname()
        dispatcher = self.makeDispatcher()
        self.assertEqual(socket.gethostname(), dispatcher.getHostname())

    def test_getHostnameOverride(self):
        # getHostname can be overridden by the config for testing, however.
        dispatcher = self.makeDispatcher()
        self.pushConfig('codeimportdispatcher', forced_hostname='test-value')
        self.assertEqual('test-value', dispatcher.getHostname())

    def writePythonScript(self, script_path, script_body):
        """Write out an executable Python script.

        This method writes a script header and `script_body` (which should be
        a list of lines of Python source) to `script_path` and makes the file
        executable.
        """
        script = open(script_path, 'w')
        for script_line in script_body:
            script.write(script_line + '\n')

    def filterOutLoggingOptions(self, arglist):
        """Remove the standard logging options from a list of arguments."""

        # Calling parser.parse_args as we do below is dangerous,
        # as if a callback invokes parser.error the test suite
        # terminates. This hack removes the dangerous argument manually.
        arglist = [
            arg for arg in arglist if not arg.startswith('--log-file=')]
        while '--log-file' in arglist:
            index = arglist.index('--log-file')
            del arglist[index] # Delete the argument
            del arglist[index] # And its parameter

        parser = OptionParser()
        scripts.logger_options(parser)
        options, args = parser.parse_args(arglist)
        return args

    def test_dispatchJob(self):
        # dispatchJob launches a process described by its
        # worker_script attribute with a given job id as an argument.

        # We create a script that writes its command line arguments to
        # some a temporary file and examine that.
        dispatcher = self.makeDispatcher()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        script_path = os.path.join(tmpdir, 'script.py')
        output_path = os.path.join(tmpdir, 'output.txt')
        self.writePythonScript(
            script_path,
            ['import sys',
             'open(%r, "w").write(str(sys.argv[1:]))' % output_path])
        dispatcher.worker_script = script_path
        proc = dispatcher.dispatchJob(10)
        proc.wait()
        arglist = self.filterOutLoggingOptions(eval(open(output_path).read()))
        self.assertEqual(['10'], arglist)

    def test_findAndDispatchJob_jobWaiting(self):
        # If there is a job to dispatch, then we call dispatchJob with its id
        # and the worker_limit supplied to the dispatcher.
        calls = []
        dispatcher = self.makeDispatcher()
        dispatcher.dispatchJob = lambda job_id: calls.append(job_id)
        found = dispatcher.findAndDispatchJob(StubSchedulerClient([10]))
        self.assertEqual(([10], True), (calls, found))

    def test_findAndDispatchJob_noJobWaiting(self):
        # If there is no job to dispatch, then we just exit quietly.
        calls = []
        dispatcher = self.makeDispatcher()
        dispatcher.dispatchJob = lambda job_id: calls.append(job_id)
        found = dispatcher.findAndDispatchJob(StubSchedulerClient([0]))
        self.assertEqual(([], False), (calls, found))

    def test_findAndDispatchJob_calls_getJobForMachine_with_limit(self):
        # findAndDispatchJob calls getJobForMachine on the scheduler client
        # with the hostname and supplied worker limit.
        worker_limit = self.factory.getUniqueInteger()
        dispatcher = self.makeDispatcher(worker_limit)
        scheduler_client = MockSchedulerClient()
        dispatcher.findAndDispatchJob(scheduler_client)
        self.assertEqual(
            [(dispatcher.getHostname(), worker_limit)],
            scheduler_client.calls)

    def test_findAndDispatchJobs(self):
        # findAndDispatchJobs calls getJobForMachine on the scheduler_client,
        # dispatching jobs, until it indicates that there are no more jobs to
        # dispatch.
        calls = []
        dispatcher = self.makeDispatcher()
        dispatcher.dispatchJob = lambda job_id: calls.append(job_id)
        dispatcher.findAndDispatchJobs(StubSchedulerClient([10, 9, 0]))
        self.assertEqual([10, 9], calls)

    def test_findAndDispatchJobs_sleeps(self):
        # After finding a job, findAndDispatchJobs sleeps for an interval as
        # returned by _getSleepInterval.
        sleep_calls = []
        interval = self.factory.getUniqueInteger()
        def _sleep(delay):
            sleep_calls.append(delay)
        dispatcher = self.makeDispatcher(_sleep=_sleep)
        dispatcher.dispatchJob = lambda job_id: None
        dispatcher._getSleepInterval = lambda : interval
        dispatcher.findAndDispatchJobs(StubSchedulerClient([10, 0]))
        self.assertEqual([interval], sleep_calls)
