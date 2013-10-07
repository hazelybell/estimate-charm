# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for ProcessMonitorProtocol and ProcessMonitorProtocolWithTimeout."""

__metaclass__ = type

from testtools.deferredruntest import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    flush_logged_errors,
    )
from twisted.internet import (
    defer,
    error,
    task,
    )
from twisted.python import failure

from lp.services.twistedsupport import suppress_stderr
from lp.services.twistedsupport.processmonitor import (
    ProcessMonitorProtocol,
    ProcessMonitorProtocolWithTimeout,
    ProcessProtocolWithTwoStageKill,
    ProcessWithTimeout,
    run_process_with_timeout,
    )
from lp.testing import TestCase


def makeFailure(exception_factory, *args, **kwargs):
    """Make a Failure object from the given exception factory.

    Any other arguments are passed straight on to the factory.
    """
    try:
        raise exception_factory(*args, **kwargs)
    except:
        return failure.Failure()


class ProcessTestsMixin:
    """Helpers to allow direct testing of ProcessProtocol subclasses.
    """

    class StubTransport:
        """Stub process transport that implements the minimum we need.

        We're manually manipulating the protocol, so we don't need a real
        transport and associated process.

        A little complexity is required to only call
        self.protocol.processEnded() once.
        """

        only_sigkill_kills = False

        def __init__(self, protocol, clock):
            self.protocol = protocol
            self.clock = clock
            self.calls = []
            self.exited = False

        def loseConnection(self):
            self.calls.append('loseConnection')

        def signalProcess(self, signal_name):
            self.calls.append(('signalProcess', signal_name))
            if self.exited:
                raise error.ProcessExitedAlready
            if not self.only_sigkill_kills or signal_name == 'KILL':
                self.exited = True
                reason = failure.Failure(error.ProcessTerminated())
                self.protocol.processEnded(reason)

    def makeProtocol(self):
        """Construct an `ProcessProtocol` instance to be tested.

        Override this in subclasses.
        """
        raise NotImplementedError

    def simulateProcessExit(self, clean=True):
        """Pretend the child process we're monitoring has exited."""
        self.protocol.transport.exited = True
        if clean:
            exc = error.ProcessDone(None)
        else:
            exc = error.ProcessTerminated(exitCode=1)
        self.protocol.processEnded(failure.Failure(exc))

    def setUp(self):
        super(ProcessTestsMixin, self).setUp()
        self.termination_deferred = defer.Deferred()
        self.clock = task.Clock()
        self.protocol = self.makeProtocol()
        self.protocol.transport = self.StubTransport(
            self.protocol, self.clock)
        self.protocol.connectionMade()


class TestProcessWithTimeout(ProcessTestsMixin, TestCase):
    """Tests for `ProcessWithTimeout`."""

    run_tests_with = AsynchronousDeferredRunTest
    TIMEOUT = 100

    def makeProtocol(self):
        """See `ProcessMonitorProtocolTestsMixin.makeProtocol`."""
        self._deferred = defer.Deferred()
        return ProcessWithTimeout(
            self._deferred, self.TIMEOUT, clock=self.clock)

    def test_end_versus_timeout_race_condition(self):
        # If the timeout fires around the same time as the process ends,
        # then there is a race condition.  The timeoutConnection()
        # method can try and kill the process which has already exited
        # which normally throws a
        # twisted.internet.error.ProcessExitedAlready - the code should
        # catch this and ignore it.

        # Simulate process exit without "killing" it:
        self.protocol._process_transport = self.protocol.transport
        self.protocol.transport.exited = True

        # Without catching the ProcessExitedAlready this will blow up.
        self.clock.advance(self.TIMEOUT+1)

        # At this point, processEnded is yet to be called so the
        # Deferred has not fired.  Ideally it would be nice to test for
        # something more concrete here but the stub transport doesn't
        # work exactly like the real one.
        self.assertFalse(self._deferred.called)


class TestProcessProtocolWithTwoStageKill(ProcessTestsMixin, TestCase):

    """Tests for `ProcessProtocolWithTwoStageKill`."""

    run_tests_with = AsynchronousDeferredRunTest

    def makeProtocol(self):
        """See `ProcessMonitorProtocolTestsMixin.makeProtocol`."""
        return ProcessProtocolWithTwoStageKill(self.clock)

    def test_interrupt(self):
        # When we call terminateProcess, we send SIGINT to the child
        # process.
        self.protocol.terminateProcess()
        self.assertEqual(
            [('signalProcess', 'INT')],
            self.protocol.transport.calls)

    def test_interruptThenKill(self):
        # If SIGINT doesn't kill the process, we send SIGKILL after a delay.
        self.protocol.transport.only_sigkill_kills = True

        self.protocol.terminateProcess()

        # When the error happens, we SIGINT the process.
        self.assertEqual(
            [('signalProcess', 'INT')],
            self.protocol.transport.calls)

        # After the expected time elapsed, we send SIGKILL.
        self.clock.advance(self.protocol.default_wait_before_kill + 1)
        self.assertEqual(
            [('signalProcess', 'INT'), ('signalProcess', 'KILL')],
            self.protocol.transport.calls)

    def test_processExitClearsTimer(self):
        # If SIGINT doesn't kill the process, we schedule a SIGKILL after a
        # delay.  If the process exits before this delay elapses, we cancel
        # the SIGKILL.
        self.protocol.transport.only_sigkill_kills = True
        self.protocol.terminateProcess()
        saved_delayed_call = self.protocol._sigkill_delayed_call
        self.failUnless(self.protocol._sigkill_delayed_call.active())
        self.simulateProcessExit(clean=False)
        self.failUnless(self.protocol._sigkill_delayed_call is None)
        self.failIf(saved_delayed_call.active())


class TestProcessMonitorProtocol(ProcessTestsMixin, TestCase):
    """Tests for `ProcessMonitorProtocol`."""

    run_tests_with = AsynchronousDeferredRunTest

    def makeProtocol(self):
        """See `ProcessMonitorProtocolTestsMixin.makeProtocol`."""
        return ProcessMonitorProtocol(
            self.termination_deferred, self.clock)

    def test_processTermination(self):
        # The protocol fires a Deferred when the child process terminates.
        self.simulateProcessExit()
        # The only way this test can realistically fail is by hanging.
        return self.termination_deferred

    def test_terminatesWithError(self):
        # When the child process terminates with a non-zero exit code, pass on
        # the error.
        self.simulateProcessExit(clean=False)
        return assert_fails_with(
            self.termination_deferred, error.ProcessTerminated)

    def test_unexpectedError(self):
        # unexpectedError() sends SIGINT to the child process but the
        # termination deferred is fired with originally passed-in failure.
        self.protocol.unexpectedError(
            makeFailure(RuntimeError, 'error message'))
        self.assertEqual(
            [('signalProcess', 'INT')],
            self.protocol.transport.calls)
        return assert_fails_with(
            self.termination_deferred, RuntimeError)

    def test_runNotification(self):
        # The first call to runNotification just runs the passed function.
        calls = []
        self.protocol.runNotification(calls.append, 'called')
        self.assertEqual(calls, ['called'])

    def test_runNotificationFailure(self):
        # If a notification function fails, the child process is killed and
        # the manner of failure reported.
        def fail():
            raise RuntimeError
        self.protocol.runNotification(fail)
        self.assertEqual(
            [('signalProcess', 'INT')],
            self.protocol.transport.calls)
        return assert_fails_with(
            self.termination_deferred, RuntimeError)

    def test_runNotificationSerialization(self):
        # If two calls are made to runNotification, the second function passed
        # is not called until any deferred returned by the first one fires.
        deferred = defer.Deferred()
        calls = []
        self.protocol.runNotification(lambda : deferred)
        self.protocol.runNotification(calls.append, 'called')
        self.assertEqual(calls, [])
        deferred.callback(None)
        self.assertEqual(calls, ['called'])

    def test_failingNotificationCancelsPendingNotifications(self):
        # A failed notification prevents any further notifications from being
        # run.  Specifically, if a notification returns a deferred which
        # subsequently errbacks, any notifications which have been requested
        # in the mean time are not run.
        deferred = defer.Deferred()
        calls = []
        self.protocol.runNotification(lambda : deferred)
        self.protocol.runNotification(calls.append, 'called')
        self.assertEqual(calls, [])
        deferred.errback(makeFailure(RuntimeError))
        self.assertEqual(calls, [])
        return assert_fails_with(
            self.termination_deferred, RuntimeError)

    def test_waitForPendingNotification(self):
        # Don't fire the termination deferred until all notifications are
        # complete, even if the process has died.
        deferred = defer.Deferred()
        self.protocol.runNotification(lambda : deferred)
        self.simulateProcessExit()
        notificaion_pending = True
        self.termination_deferred.addCallback(
            lambda ignored: self.failIf(notificaion_pending))
        notificaion_pending = False
        deferred.callback(None)
        return self.termination_deferred

    def test_pendingNotificationFails(self):
        # If the process exits cleanly while a notification is pending and the
        # notification subsequently fails, the notification's failure is
        # passed on to the termination deferred.
        deferred = defer.Deferred()
        self.protocol.runNotification(lambda : deferred)
        self.simulateProcessExit()
        deferred.errback(makeFailure(RuntimeError))
        return assert_fails_with(
            self.termination_deferred, RuntimeError)

    @suppress_stderr
    def test_uncleanExitAndPendingNotificationFails(self):
        # If the process exits with a non-zero exit code while a
        # notification is pending and the notification subsequently
        # fails, the ProcessTerminated is still passed on to the
        # termination deferred.
        deferred = defer.Deferred()
        self.protocol.runNotification(lambda : deferred)
        self.simulateProcessExit(clean=False)
        runtime_error_failure = makeFailure(RuntimeError)
        deferred.errback(runtime_error_failure)
        self.assertEqual(
            flush_logged_errors(RuntimeError), [runtime_error_failure])
        return assert_fails_with(
            self.termination_deferred, error.ProcessTerminated)

    @suppress_stderr
    def test_unexpectedErrorAndNotificationFailure(self):
        # If unexpectedError is called while a notification is pending and the
        # notification subsequently fails, the first failure "wins" and is
        # passed on to the termination deferred.
        deferred = defer.Deferred()
        self.protocol.runNotification(lambda : deferred)
        self.protocol.unexpectedError(makeFailure(TypeError))
        runtime_error_failure = makeFailure(RuntimeError)
        deferred.errback(runtime_error_failure)
        self.assertEqual(
            flush_logged_errors(RuntimeError), [runtime_error_failure])
        return assert_fails_with(
            self.termination_deferred, TypeError)


class TestProcessMonitorProtocolWithTimeout(ProcessTestsMixin, TestCase):
    """Tests for `ProcessMonitorProtocolWithTimeout`."""

    run_tests_with = AsynchronousDeferredRunTest

    timeout = 5

    def makeProtocol(self):
        """See `ProcessMonitorProtocolTestsMixin.makeProtocol`."""
        return ProcessMonitorProtocolWithTimeout(
            self.termination_deferred, self.timeout, self.clock)

    def test_timeoutWithoutProgress(self):
        # If we don't receive any messages after the configured timeout
        # period, then we kill the child process.
        self.clock.advance(self.timeout + 1)
        return assert_fails_with(
            self.termination_deferred, error.TimeoutError)

    def test_resetTimeout(self):
        # Calling resetTimeout resets the timeout.
        self.clock.advance(self.timeout - 1)
        self.protocol.resetTimeout()
        self.clock.advance(2)
        self.simulateProcessExit()
        return self.termination_deferred

    def test_processExitingResetsTimeout(self):
        # When the process exits, the timeout is reset.
        deferred = defer.Deferred()
        self.protocol.runNotification(lambda : deferred)
        self.clock.advance(self.timeout - 1)
        self.simulateProcessExit()
        self.clock.advance(2)
        deferred.callback(None)
        return self.termination_deferred


class TestRunProcessWithTimeout(TestCase):
    """Tests for `run_process_with_timeout`."""

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=10)

    def test_run_process_with_timeout_invalid_args(self):
        # `run_process_with_timeout` expects the process 'args' to be a
        # tuple.
        self.assertRaises(
            AssertionError, run_process_with_timeout, 'true')

    def test_run_proces_with_timeout_success(self):
        # On success, i.e process succeeded before the specified timeout,
        # callback is fired with 'None'.
        d = run_process_with_timeout(('true',))
        def check_success_result(result):
            self.assertEquals(result, None, "Success result is not None.")
        d.addCallback(check_success_result)
        return d

    def test_run_process_with_timeout_failure(self):
        # On failed process, the errback is fired with a `ProcessTerminated`
        # failure.
        d = run_process_with_timeout(('false',))
        return assert_fails_with(d, error.ProcessTerminated)

    def test_run_process_with_timeout_broken(self):
        # On broken process, the errback is fired with a `ProcessTerminated`
        # failure.
        d = run_process_with_timeout(('does-not-exist',))
        return assert_fails_with(d, error.ProcessTerminated)

    def test_run_process_with_timeout_timeout(self):
        # On process timeout, the errback is fired with `TimeoutError`
        # failure.
        clock = task.Clock()
        d = run_process_with_timeout(
            ('sleep', '2'), timeout=1, clock=clock)
        clock.advance(2)
        return assert_fails_with(d, error.TimeoutError)
