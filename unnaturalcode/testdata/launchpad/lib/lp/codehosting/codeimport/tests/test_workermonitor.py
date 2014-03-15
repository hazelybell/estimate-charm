# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the CodeImportWorkerMonitor and related classes."""

__metaclass__ = type
__all__ = [
    'nuke_codeimport_sample_data',
    ]

import os
import shutil
import StringIO
import tempfile
import urllib

from bzrlib.branch import Branch
from bzrlib.tests import TestCase as BzrTestCase
import oops_twisted
from testtools.deferredruntest import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    flush_logged_errors,
    )
import transaction
from twisted.internet import (
    defer,
    error,
    protocol,
    reactor,
    )
from twisted.python import log
from twisted.web import xmlrpc
from zope.component import getUtility

from lp.code.enums import (
    CodeImportResultStatus,
    CodeImportReviewStatus,
    RevisionControlSystems,
    )
from lp.code.interfaces.codeimport import ICodeImportSet
from lp.code.interfaces.codeimportjob import ICodeImportJobSet
from lp.code.model.codeimport import CodeImport
from lp.code.model.codeimportjob import CodeImportJob
from lp.codehosting.codeimport.tests.servers import (
    BzrServer,
    CVSServer,
    GitServer,
    SubversionServer,
    )
from lp.codehosting.codeimport.tests.test_worker import (
    clean_up_default_stores_for_import,
    )
from lp.codehosting.codeimport.worker import (
    CodeImportSourceDetails,
    CodeImportWorkerExitCode,
    get_default_bazaar_branch_store,
    )
from lp.codehosting.codeimport.workermonitor import (
    CodeImportWorkerMonitor,
    CodeImportWorkerMonitorProtocol,
    ExitQuietly,
    )
from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.services.twistedsupport import suppress_stderr
from lp.services.twistedsupport.tests.test_processmonitor import (
    makeFailure,
    ProcessTestsMixin,
    )
from lp.services.webapp import errorlog
from lp.testing import (
    login,
    logout,
    TestCase,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessAppServerLayer,
    )
from lp.xmlrpc.faults import NoSuchCodeImportJob


class TestWorkerMonitorProtocol(ProcessTestsMixin, TestCase):

    class StubWorkerMonitor:

        def __init__(self):
            self.calls = []

        def updateHeartbeat(self, tail):
            self.calls.append(('updateHeartbeat', tail))

    def setUp(self):
        self.worker_monitor = self.StubWorkerMonitor()
        self.log_file = StringIO.StringIO()
        super(TestWorkerMonitorProtocol, self).setUp()

    def makeProtocol(self):
        """See `ProcessTestsMixin.makeProtocol`."""
        return CodeImportWorkerMonitorProtocol(
            self.termination_deferred, self.worker_monitor, self.log_file,
            self.clock)

    def test_callsUpdateHeartbeatInConnectionMade(self):
        # The protocol calls updateHeartbeat() as it is connected to the
        # process.
        # connectionMade() is called during setUp().
        self.assertEqual(
            self.worker_monitor.calls,
            [('updateHeartbeat', '')])

    def test_callsUpdateHeartbeatRegularly(self):
        # The protocol calls 'updateHeartbeat' on the worker_monitor every
        # config.codeimportworker.heartbeat_update_interval seconds.
        # Forget the call in connectionMade()
        self.worker_monitor.calls = []
        # Advance the simulated time a little to avoid fencepost errors.
        self.clock.advance(0.1)
        # And check that updateHeartbeat is called at the frequency we expect:
        for i in range(4):
            self.protocol.resetTimeout()
            self.assertEqual(
                self.worker_monitor.calls,
                [('updateHeartbeat', '')] * i)
            self.clock.advance(
                config.codeimportworker.heartbeat_update_interval)

    def test_updateHeartbeatStopsOnProcessExit(self):
        # updateHeartbeat is not called after the process has exited.
        # Forget the call in connectionMade()
        self.worker_monitor.calls = []
        self.simulateProcessExit()
        # Advance the simulated time past the time the next update is due.
        self.clock.advance(
            config.codeimportworker.heartbeat_update_interval + 1)
        # Check that updateHeartbeat was not called.
        self.assertEqual(self.worker_monitor.calls, [])

    def test_outReceivedWritesToLogFile(self):
        # outReceived writes the data it is passed into the log file.
        output = ['some data\n', 'some more data\n']
        self.protocol.outReceived(output[0])
        self.assertEqual(self.log_file.getvalue(), output[0])
        self.protocol.outReceived(output[1])
        self.assertEqual(self.log_file.getvalue(), output[0] + output[1])

    def test_outReceivedUpdatesTail(self):
        # outReceived updates the tail of the log, currently and arbitrarily
        # defined to be the last 5 lines of the log.
        lines = ['line %d' % number for number in range(1, 7)]
        self.protocol.outReceived('\n'.join(lines[:3]) + '\n')
        self.assertEqual(
            self.protocol._tail, 'line 1\nline 2\nline 3\n')
        self.protocol.outReceived('\n'.join(lines[3:]) + '\n')
        self.assertEqual(
            self.protocol._tail, 'line 3\nline 4\nline 5\nline 6\n')


class FakeCodeImportScheduleEndpointProxy:
    """A fake implementation of a proxy to `ICodeImportScheduler`.

    The constructor takes a dictionary mapping job ids to information that
    should be returned by getImportDataForJobID and the exception to raise if
    getImportDataForJobID is called with a job id not in the passed-in
    dictionary, defaulting to a fault with the same code as
    NoSuchCodeImportJob (because the class of the exception is lost when you
    go through XML-RPC serialization).
    """

    def __init__(self, jobs_dict, no_such_job_exception=None):
        self.calls = []
        self.jobs_dict = jobs_dict
        if no_such_job_exception is None:
            no_such_job_exception = xmlrpc.Fault(
                faultCode=NoSuchCodeImportJob.error_code, faultString='')
        self.no_such_job_exception = no_such_job_exception

    def callRemote(self, method_name, *args):
        method = getattr(self, '_remote_%s' % method_name, self._default)
        deferred = defer.maybeDeferred(method, *args)

        def append_to_log(pass_through):
            self.calls.append((method_name,) + tuple(args))
            return pass_through

        deferred.addCallback(append_to_log)
        return deferred

    def _default(self, *args):
        return None

    def _remote_getImportDataForJobID(self, job_id):
        if job_id in self.jobs_dict:
            return self.jobs_dict[job_id]
        else:
            raise self.no_such_job_exception


class TestWorkerMonitorUnit(TestCase):
    """Unit tests for most of the `CodeImportWorkerMonitor` class.

    We have to pay attention to the fact that several of the methods of the
    `CodeImportWorkerMonitor` class are wrapped in decorators that create and
    commit a transaction, and have to start our own transactions to check what
    they did.
    """

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=20)

    class WorkerMonitor(CodeImportWorkerMonitor):
        """A subclass of CodeImportWorkerMonitor that stubs logging OOPSes."""

        def _logOopsFromFailure(self, failure):
            log.err(failure)

    def makeWorkerMonitorWithJob(self, job_id=1, job_data=()):
        return self.WorkerMonitor(
            job_id, BufferLogger(),
            FakeCodeImportScheduleEndpointProxy({job_id: job_data}),
            "anything")

    def makeWorkerMonitorWithoutJob(self, exception=None):
        return self.WorkerMonitor(
            1, BufferLogger(),
            FakeCodeImportScheduleEndpointProxy({}, exception),
            None)

    def test_getWorkerArguments(self):
        # getWorkerArguments returns a deferred that fires with the
        # 'arguments' part of what getImportDataForJobID returns.
        args = [self.factory.getUniqueString(),
                self.factory.getUniqueString()]
        worker_monitor = self.makeWorkerMonitorWithJob(1, (args, 1, 2))
        return worker_monitor.getWorkerArguments().addCallback(
            self.assertEqual, args)

    def test_getWorkerArguments_sets_branch_url_and_logfilename(self):
        # getWorkerArguments sets the _branch_url (for use in oops reports)
        # and _log_file_name (for upload to the librarian) attributes on the
        # WorkerMonitor from the data returned by getImportDataForJobID.
        branch_url = self.factory.getUniqueString()
        log_file_name = self.factory.getUniqueString()
        worker_monitor = self.makeWorkerMonitorWithJob(
            1, (['a'], branch_url, log_file_name))

        def check_branch_log(ignored):
            # Looking at the _ attributes here is in slightly poor taste, but
            # much much easier than them by logging and parsing an oops, etc.
            self.assertEqual(
                (branch_url, log_file_name),
                (worker_monitor._branch_url, worker_monitor._log_file_name))

        return worker_monitor.getWorkerArguments().addCallback(
            check_branch_log)

    def test_getWorkerArguments_job_not_found_raises_exit_quietly(self):
        # When getImportDataForJobID signals a fault indicating that
        # getWorkerArguments didn't find the supplied job, getWorkerArguments
        # translates this to an 'ExitQuietly' exception.
        worker_monitor = self.makeWorkerMonitorWithoutJob()
        return assert_fails_with(
            worker_monitor.getWorkerArguments(), ExitQuietly)

    def test_getWorkerArguments_endpoint_failure_raises(self):
        # When getImportDataForJobID raises an arbitrary exception, it is not
        # handled in any special way by getWorkerArguments.
        worker_monitor = self.makeWorkerMonitorWithoutJob(
            exception=ZeroDivisionError())
        return assert_fails_with(
            worker_monitor.getWorkerArguments(), ZeroDivisionError)

    def test_getWorkerArguments_arbitrary_fault_raises(self):
        # When getImportDataForJobID signals an arbitrary fault, it is not
        # handled in any special way by getWorkerArguments.
        worker_monitor = self.makeWorkerMonitorWithoutJob(
            exception=xmlrpc.Fault(1, ''))
        return assert_fails_with(
            worker_monitor.getWorkerArguments(), xmlrpc.Fault)

    def test_updateHeartbeat(self):
        # updateHeartbeat calls the updateHeartbeat XML-RPC method.
        log_tail = self.factory.getUniqueString()
        job_id = self.factory.getUniqueInteger()
        worker_monitor = self.makeWorkerMonitorWithJob(job_id)

        def check_updated_details(result):
            self.assertEqual(
                [('updateHeartbeat', job_id, log_tail)],
                worker_monitor.codeimport_endpoint.calls)

        return worker_monitor.updateHeartbeat(log_tail).addCallback(
            check_updated_details)

    def test_finishJob_calls_finishJobID_empty_log_file(self):
        # When the log file is empty, finishJob calls finishJobID with the
        # name of the status enum and an empty string to indicate that no log
        # file was uplaoded to the librarian.
        job_id = self.factory.getUniqueInteger()
        worker_monitor = self.makeWorkerMonitorWithJob(job_id)
        self.assertEqual(worker_monitor._log_file.tell(), 0)

        def check_finishJob_called(result):
            self.assertEqual(
                [('finishJobID', job_id, 'SUCCESS', '')],
                worker_monitor.codeimport_endpoint.calls)

        return worker_monitor.finishJob(
            CodeImportResultStatus.SUCCESS).addCallback(
            check_finishJob_called)

    def test_finishJob_uploads_nonempty_file_to_librarian(self):
        # finishJob method uploads the log file to the librarian and calls the
        # finishJobID XML-RPC method with the url of that file.
        self.layer.force_dirty_database()
        log_text = self.factory.getUniqueString()
        worker_monitor = self.makeWorkerMonitorWithJob()
        worker_monitor._log_file.write(log_text)

        def check_file_uploaded(result):
            transaction.abort()
            url = worker_monitor.codeimport_endpoint.calls[0][3]
            text = urllib.urlopen(url).read()
            self.assertEqual(log_text, text)

        return worker_monitor.finishJob(
            CodeImportResultStatus.SUCCESS).addCallback(
            check_file_uploaded)

    @suppress_stderr
    def test_finishJob_still_calls_finishJobID_if_upload_fails(self):
        # If the upload to the librarian fails for any reason, the worker
        # monitor still calls the finishJobID XML-RPC method, but logs an
        # error to indicate there was a problem.
        class Fail(Exception):
            """Some arbitrary failure."""

        # Write some text so that we try to upload the log.
        job_id = self.factory.getUniqueInteger()
        worker_monitor = self.makeWorkerMonitorWithJob(job_id)
        worker_monitor._log_file.write('some text')

        # Make _createLibrarianFileAlias fail in a distinctive way.
        worker_monitor._createLibrarianFileAlias = FakeMethod(failure=Fail())

        def check_finishJob_called(result):
            self.assertEqual(
                [('finishJobID', job_id, 'SUCCESS', '')],
                worker_monitor.codeimport_endpoint.calls)
            errors = flush_logged_errors(Fail)
            self.assertEqual(1, len(errors))

        return worker_monitor.finishJob(
            CodeImportResultStatus.SUCCESS).addCallback(
            check_finishJob_called)

    def patchOutFinishJob(self, worker_monitor):
        """Replace `worker_monitor.finishJob` with a `FakeMethod`-alike stub.

        :param worker_monitor: CodeImportWorkerMonitor to patch up.
        :return: A list of statuses that `finishJob` has been called with.
            Future calls will be appended to this list.
        """
        calls = []

        def finishJob(status):
            calls.append(status)
            return defer.succeed(None)

        worker_monitor.finishJob = finishJob
        return calls

    def test_callFinishJobCallsFinishJobSuccess(self):
        # callFinishJob calls finishJob with CodeImportResultStatus.SUCCESS if
        # its argument is not a Failure.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        worker_monitor.callFinishJob(None)
        self.assertEqual(calls, [CodeImportResultStatus.SUCCESS])

    @suppress_stderr
    def test_callFinishJobCallsFinishJobFailure(self):
        # callFinishJob calls finishJob with CodeImportResultStatus.FAILURE
        # and swallows the failure if its argument indicates that the
        # subprocess exited with an exit code of
        # CodeImportWorkerExitCode.FAILURE.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(
            makeFailure(
                error.ProcessTerminated,
                exitCode=CodeImportWorkerExitCode.FAILURE))
        self.assertEqual(calls, [CodeImportResultStatus.FAILURE])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    def test_callFinishJobCallsFinishJobSuccessNoChange(self):
        # If the argument to callFinishJob indicates that the subprocess
        # exited with a code of CodeImportWorkerExitCode.SUCCESS_NOCHANGE, it
        # calls finishJob with a status of SUCCESS_NOCHANGE.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(
            makeFailure(
                error.ProcessTerminated,
                exitCode=CodeImportWorkerExitCode.SUCCESS_NOCHANGE))
        self.assertEqual(calls, [CodeImportResultStatus.SUCCESS_NOCHANGE])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    @suppress_stderr
    def test_callFinishJobCallsFinishJobArbitraryFailure(self):
        # If the argument to callFinishJob indicates that there was some other
        # failure that had nothing to do with the subprocess, it records
        # failure.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(makeFailure(RuntimeError))
        self.assertEqual(calls, [CodeImportResultStatus.FAILURE])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    def test_callFinishJobCallsFinishJobPartial(self):
        # If the argument to callFinishJob indicates that the subprocess
        # exited with a code of CodeImportWorkerExitCode.SUCCESS_PARTIAL, it
        # calls finishJob with a status of SUCCESS_PARTIAL.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(
            makeFailure(
                error.ProcessTerminated,
                exitCode=CodeImportWorkerExitCode.SUCCESS_PARTIAL))
        self.assertEqual(calls, [CodeImportResultStatus.SUCCESS_PARTIAL])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    def test_callFinishJobCallsFinishJobInvalid(self):
        # If the argument to callFinishJob indicates that the subprocess
        # exited with a code of CodeImportWorkerExitCode.FAILURE_INVALID, it
        # calls finishJob with a status of FAILURE_INVALID.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(
            makeFailure(
                error.ProcessTerminated,
                exitCode=CodeImportWorkerExitCode.FAILURE_INVALID))
        self.assertEqual(calls, [CodeImportResultStatus.FAILURE_INVALID])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    def test_callFinishJobCallsFinishJobUnsupportedFeature(self):
        # If the argument to callFinishJob indicates that the subprocess
        # exited with a code of FAILURE_UNSUPPORTED_FEATURE, it
        # calls finishJob with a status of FAILURE_UNSUPPORTED_FEATURE.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(makeFailure(
            error.ProcessTerminated,
            exitCode=CodeImportWorkerExitCode.FAILURE_UNSUPPORTED_FEATURE))
        self.assertEqual(
            calls, [CodeImportResultStatus.FAILURE_UNSUPPORTED_FEATURE])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    def test_callFinishJobCallsFinishJobRemoteBroken(self):
        # If the argument to callFinishJob indicates that the subprocess
        # exited with a code of FAILURE_REMOTE_BROKEN, it
        # calls finishJob with a status of FAILURE_REMOTE_BROKEN.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        ret = worker_monitor.callFinishJob(
            makeFailure(
                error.ProcessTerminated,
                exitCode=CodeImportWorkerExitCode.FAILURE_REMOTE_BROKEN))
        self.assertEqual(
            calls, [CodeImportResultStatus.FAILURE_REMOTE_BROKEN])
        # We return the deferred that callFinishJob returns -- if
        # callFinishJob did not swallow the error, this will fail the test.
        return ret

    @suppress_stderr
    def test_callFinishJobLogsTracebackOnFailure(self):
        # When callFinishJob is called with a failure, it dumps the traceback
        # of the failure into the log file.
        self.layer.force_dirty_database()
        worker_monitor = self.makeWorkerMonitorWithJob()
        ret = worker_monitor.callFinishJob(makeFailure(RuntimeError))

        def check_log_file(ignored):
            worker_monitor._log_file.seek(0)
            log_text = worker_monitor._log_file.read()
            self.assertIn('Traceback (most recent call last)', log_text)
            self.assertIn('RuntimeError', log_text)
        return ret.addCallback(check_log_file)

    def test_callFinishJobRespects_call_finish_job(self):
        # callFinishJob does not call finishJob if _call_finish_job is False.
        # This is to support exiting without fuss when the job we are working
        # on is deleted in the web UI.
        worker_monitor = self.makeWorkerMonitorWithJob()
        calls = self.patchOutFinishJob(worker_monitor)
        worker_monitor._call_finish_job = False
        worker_monitor.callFinishJob(None)
        self.assertEqual(calls, [])


class TestWorkerMonitorRunNoProcess(BzrTestCase):
    """Tests for `CodeImportWorkerMonitor.run` that don't launch a subprocess.
    """

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=20)

    class WorkerMonitor(CodeImportWorkerMonitor):
        """See `CodeImportWorkerMonitor`.

        Override _launchProcess to return a deferred that we can
        callback/errback as we choose.  Passing ``has_job=False`` to the
        constructor will cause getWorkerArguments() to raise ExitQuietly (this
        bit is tested above).
        """

        def __init__(self, process_deferred, has_job=True):
            if has_job:
                job_data = {1: ([], '', '')}
            else:
                job_data = {}
            CodeImportWorkerMonitor.__init__(
                self, 1, BufferLogger(),
                FakeCodeImportScheduleEndpointProxy(job_data),
                "anything")
            self.result_status = None
            self.process_deferred = process_deferred

        def _launchProcess(self, worker_arguments):
            return self.process_deferred

        def finishJob(self, status):
            assert self.result_status is None, "finishJob called twice!"
            self.result_status = status
            return defer.succeed(None)

    def assertFinishJobCalledWithStatus(self, ignored, worker_monitor,
                                        status):
        """Assert that finishJob was called with the given status."""
        self.assertEqual(worker_monitor.result_status, status)

    def assertFinishJobNotCalled(self, ignored, worker_monitor):
        """Assert that finishJob was called with the given status."""
        self.assertFinishJobCalledWithStatus(ignored, worker_monitor, None)

    def test_success(self):
        # In the successful case, finishJob is called with
        # CodeImportResultStatus.SUCCESS.
        worker_monitor = self.WorkerMonitor(defer.succeed(None))
        return worker_monitor.run().addCallback(
            self.assertFinishJobCalledWithStatus, worker_monitor,
            CodeImportResultStatus.SUCCESS)

    def test_failure(self):
        # If the process deferred is fired with a failure, finishJob is called
        # with CodeImportResultStatus.FAILURE, but the call to run() still
        # succeeds.
        # Need a twisted error reporting stack (normally set up by
        # loggingsuppoer.set_up_oops_reporting).
        errorlog.globalErrorUtility.configure(
            config_factory=oops_twisted.Config,
            publisher_adapter=oops_twisted.defer_publisher)
        self.addCleanup(errorlog.globalErrorUtility.configure)
        worker_monitor = self.WorkerMonitor(defer.fail(RuntimeError()))
        return worker_monitor.run().addCallback(
            self.assertFinishJobCalledWithStatus, worker_monitor,
            CodeImportResultStatus.FAILURE)

    def test_quiet_exit(self):
        # If the process deferred fails with ExitQuietly, the call to run()
        # succeeds, and finishJob is not called at all.
        worker_monitor = self.WorkerMonitor(
            defer.succeed(None), has_job=False)
        return worker_monitor.run().addCallback(
            self.assertFinishJobNotCalled, worker_monitor)

    def test_quiet_exit_from_finishJob(self):
        # If finishJob fails with ExitQuietly, the call to run() still
        # succeeds.
        worker_monitor = self.WorkerMonitor(defer.succeed(None))

        def finishJob(reason):
            raise ExitQuietly
        worker_monitor.finishJob = finishJob
        return worker_monitor.run()

    def test_log_oops(self):
        # Ensure an OOPS is logged if published.
        errorlog.globalErrorUtility.configure(
            config_factory=oops_twisted.Config,
            publisher_adapter=oops_twisted.defer_publisher)
        self.addCleanup(errorlog.globalErrorUtility.configure)
        failure_msg = "test_log_oops expected failure"
        worker_monitor = self.WorkerMonitor(
            defer.fail(RuntimeError(failure_msg)))

        def finishJob(reason):
            from twisted.python import failure
            return worker_monitor._logOopsFromFailure(
                failure.Failure())

        worker_monitor.finishJob = finishJob
        d = worker_monitor.run()

        def check_log_file(ignored):
            worker_monitor._log_file.seek(0)
            log_text = worker_monitor._log_file.read()
            self.assertIn(
                "Failure: exceptions.RuntimeError: " + failure_msg,
                log_text)

        d.addCallback(check_log_file)
        return d


def nuke_codeimport_sample_data():
    """Delete all the sample data that might interfere with tests."""
    for job in CodeImportJob.select():
        job.destroySelf()
    for code_import in CodeImport.select():
        code_import.destroySelf()


class CIWorkerMonitorProtocolForTesting(CodeImportWorkerMonitorProtocol):
    """A `CodeImportWorkerMonitorProtocol` that counts `resetTimeout` calls.
    """

    def __init__(self, deferred, worker_monitor, log_file, clock=None):
        """See `CodeImportWorkerMonitorProtocol.__init__`."""
        CodeImportWorkerMonitorProtocol.__init__(
            self, deferred, worker_monitor, log_file, clock)
        self.reset_calls = 0

    def resetTimeout(self):
        """See `ProcessMonitorProtocolWithTimeout.resetTimeout`."""
        CodeImportWorkerMonitorProtocol.resetTimeout(self)
        self.reset_calls += 1


class CIWorkerMonitorForTesting(CodeImportWorkerMonitor):
    """A `CodeImportWorkerMonitor` that hangs on to the process protocol."""

    def _makeProcessProtocol(self, deferred):
        """See `CodeImportWorkerMonitor._makeProcessProtocol`.

        We hang on to the constructed object for later inspection -- see
        `TestWorkerMonitorIntegration.assertImported`.
        """
        protocol = CIWorkerMonitorProtocolForTesting(
            deferred, self, self._log_file)
        self._protocol = protocol
        return protocol


class TestWorkerMonitorIntegration(BzrTestCase):

    layer = ZopelessAppServerLayer
    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=60)

    def setUp(self):
        BzrTestCase.setUp(self)
        login('no-priv@canonical.com')
        self.factory = LaunchpadObjectFactory()
        nuke_codeimport_sample_data()
        self.repo_path = tempfile.mkdtemp()
        self.disable_directory_isolation()
        self.addCleanup(shutil.rmtree, self.repo_path)
        self.foreign_commit_count = 0

    def tearDown(self):
        BzrTestCase.tearDown(self)
        logout()

    def makeCVSCodeImport(self):
        """Make a `CodeImport` that points to a real CVS repository."""
        cvs_server = CVSServer(self.repo_path)
        cvs_server.start_server()
        self.addCleanup(cvs_server.stop_server)

        cvs_server.makeModule('trunk', [('README', 'original\n')])
        self.foreign_commit_count = 2

        return self.factory.makeCodeImport(
            cvs_root=cvs_server.getRoot(), cvs_module='trunk')

    def makeSVNCodeImport(self):
        """Make a `CodeImport` that points to a real Subversion repository."""
        self.subversion_server = SubversionServer(self.repo_path)
        self.subversion_server.start_server()
        self.addCleanup(self.subversion_server.stop_server)
        url = self.subversion_server.makeBranch(
            'trunk', [('README', 'contents')])
        self.foreign_commit_count = 2

        return self.factory.makeCodeImport(svn_branch_url=url)

    def makeBzrSvnCodeImport(self):
        """Make a `CodeImport` that points to a real Subversion repository."""
        self.subversion_server = SubversionServer(
            self.repo_path, use_svn_serve=True)
        self.subversion_server.start_server()
        self.addCleanup(self.subversion_server.stop_server)
        url = self.subversion_server.makeBranch(
            'trunk', [('README', 'contents')])
        self.foreign_commit_count = 2

        return self.factory.makeCodeImport(
            svn_branch_url=url, rcs_type=RevisionControlSystems.BZR_SVN)

    def makeGitCodeImport(self):
        """Make a `CodeImport` that points to a real Git repository."""
        self.git_server = GitServer(self.repo_path, use_server=False)
        self.git_server.start_server()
        self.addCleanup(self.git_server.stop_server)

        self.git_server.makeRepo([('README', 'contents')])
        self.foreign_commit_count = 1

        return self.factory.makeCodeImport(
            git_repo_url=self.git_server.get_url())

    def makeBzrCodeImport(self):
        """Make a `CodeImport` that points to a real Bazaar branch."""
        self.bzr_server = BzrServer(self.repo_path)
        self.bzr_server.start_server()
        self.addCleanup(self.bzr_server.stop_server)

        self.bzr_server.makeRepo([('README', 'contents')])
        self.foreign_commit_count = 1
        return self.factory.makeCodeImport(
            bzr_branch_url=self.bzr_server.get_url())

    def getStartedJobForImport(self, code_import):
        """Get a started `CodeImportJob` for `code_import`.

        This method approves the import, creates a job, marks it started and
        returns the job.  It also makes sure there are no branches or foreign
        trees in the default stores to interfere with processing this job.
        """
        source_details = CodeImportSourceDetails.fromCodeImport(code_import)
        clean_up_default_stores_for_import(source_details)
        self.addCleanup(clean_up_default_stores_for_import, source_details)
        if code_import.review_status != CodeImportReviewStatus.REVIEWED:
            code_import.updateFromData(
                {'review_status': CodeImportReviewStatus.REVIEWED},
                self.factory.makePerson())
        job = getUtility(ICodeImportJobSet).getJobForMachine('machine', 10)
        self.assertEqual(code_import, job.code_import)
        return job

    def assertCodeImportResultCreated(self, code_import):
        """Assert that a `CodeImportResult` was created for `code_import`."""
        self.assertEqual(len(list(code_import.results)), 1)
        result = list(code_import.results)[0]
        self.assertEqual(result.status, CodeImportResultStatus.SUCCESS)

    def assertBranchImportedOKForCodeImport(self, code_import):
        """Assert that a branch was pushed into the default branch store."""
        url = get_default_bazaar_branch_store()._getMirrorURL(
            code_import.branch.id)
        branch = Branch.open(url)
        self.assertEqual(self.foreign_commit_count, branch.revno())

    def assertImported(self, ignored, code_import_id):
        """Assert that the `CodeImport` of the given id was imported."""
        # In the in-memory tests, check that resetTimeout on the
        # CodeImportWorkerMonitorProtocol was called at least once.
        if self._protocol is not None:
            self.assertPositive(self._protocol.reset_calls)
        code_import = getUtility(ICodeImportSet).get(code_import_id)
        self.assertCodeImportResultCreated(code_import)
        self.assertBranchImportedOKForCodeImport(code_import)

    def performImport(self, job_id):
        """Perform the import job with ID job_id.

        Return a Deferred that fires when it the job is done.

        This implementation does it in-process.
        """
        logger = BufferLogger()
        monitor = CIWorkerMonitorForTesting(
            job_id, logger,
            xmlrpc.Proxy(config.codeimportdispatcher.codeimportscheduler_url),
            "anything")
        deferred = monitor.run()

        def save_protocol_object(result):
            """Save the process protocol object.

            We do this in an addBoth so that it's called after the process
            protocol is actually constructed but before we drop the last
            reference to the monitor object.
            """
            self._protocol = monitor._protocol
            return result

        return deferred.addBoth(save_protocol_object)

    def test_import_cvs(self):
        # Create a CVS CodeImport and import it.
        job = self.getStartedJobForImport(self.makeCVSCodeImport())
        code_import_id = job.code_import.id
        job_id = job.id
        self.layer.txn.commit()
        result = self.performImport(job_id)
        return result.addCallback(self.assertImported, code_import_id)

    def test_import_subversion(self):
        # Create a Subversion CodeImport and import it.
        job = self.getStartedJobForImport(self.makeSVNCodeImport())
        code_import_id = job.code_import.id
        job_id = job.id
        self.layer.txn.commit()
        result = self.performImport(job_id)
        return result.addCallback(self.assertImported, code_import_id)

    def test_import_git(self):
        # Create a Git CodeImport and import it.
        job = self.getStartedJobForImport(self.makeGitCodeImport())
        code_import_id = job.code_import.id
        job_id = job.id
        self.layer.txn.commit()
        result = self.performImport(job_id)
        return result.addCallback(self.assertImported, code_import_id)

    def test_import_bzr(self):
        # Create a Bazaar CodeImport and import it.
        job = self.getStartedJobForImport(self.makeBzrCodeImport())
        code_import_id = job.code_import.id
        job_id = job.id
        self.layer.txn.commit()
        result = self.performImport(job_id)
        return result.addCallback(self.assertImported, code_import_id)

    def test_import_bzrsvn(self):
        # Create a Subversion-via-bzr-svn CodeImport and import it.
        job = self.getStartedJobForImport(self.makeBzrSvnCodeImport())
        code_import_id = job.code_import.id
        job_id = job.id
        self.layer.txn.commit()
        result = self.performImport(job_id)
        return result.addCallback(self.assertImported, code_import_id)


class DeferredOnExit(protocol.ProcessProtocol):

    def __init__(self, deferred):
        self._deferred = deferred

    def processEnded(self, reason):
        if reason.check(error.ProcessDone):
            self._deferred.callback(None)
        else:
            self._deferred.errback(reason)


class TestWorkerMonitorIntegrationScript(TestWorkerMonitorIntegration):
    """Tests for CodeImportWorkerMonitor that execute a child process."""

    def setUp(self):
        TestWorkerMonitorIntegration.setUp(self)
        self._protocol = None

    def performImport(self, job_id):
        """Perform the import job with ID job_id.

        Return a Deferred that fires when it the job is done.

        This implementation does it in a child process.
        """
        script_path = os.path.join(
            config.root, 'scripts', 'code-import-worker-monitor.py')
        process_end_deferred = defer.Deferred()
        # The "childFDs={0:0, 1:1, 2:2}" means that any output from the script
        # goes to the test runner's console rather than to pipes that noone is
        # listening too.
        interpreter = '%s/bin/py' % config.root
        reactor.spawnProcess(
            DeferredOnExit(process_end_deferred), interpreter, [
                interpreter,
                script_path,
                '--access-policy=anything',
                str(job_id),
                '-q',
                ], childFDs={0: 0, 1: 1, 2: 2}, env=os.environ)
        return process_end_deferred
