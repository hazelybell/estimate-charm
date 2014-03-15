# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for running a child process and communicating things about it."""

__metaclass__ = type
__all__ = [
    'ProcessMonitorProtocol',
    'ProcessMonitorProtocolWithTimeout',
    'ProcessWithTimeout',
    'run_process_with_timeout',
    ]


import os
import StringIO

from twisted.internet import (
    defer,
    error,
    reactor,
    )
from twisted.internet.protocol import ProcessProtocol
from twisted.protocols.policies import TimeoutMixin
from twisted.python import (
    failure,
    log,
    )


class ProcessProtocolWithTwoStageKill(ProcessProtocol):
    """Support for interrupting, then killing if necessary, processes.

    :ivar _clock: A provider of Twisted's IReactorTime, to allow testing that
        does not depend on an external clock.  If a clock is not explicitly
        supplied the reactor is used.
    :ivar _sigkill_delayed_call: When we are terminating a process, we send
        SIGINT, wait a while and then send SIGKILL if required.  We stash the
        DelayedCall here so that it can be cancelled if the SIGINT causes the
        process to exit.
    """

    default_wait_before_kill = 5

    def __init__(self, clock=None):
        """Construct an instance.

        :param clock: A provider of Twisted's IReactorTime.  This parameter
            exists to allow testing that does not depend on an external clock.
            If a clock is not passed in explicitly the reactor is used.
        """
        if clock is None:
            clock = reactor
        self._clock = clock
        self._sigkill_delayed_call = None

    def terminateProcess(self, timeout=None):
        """Terminate the process by SIGINT initially, but SIGKILL if needed.

        :param timeout: How many seconds to wait after the SIGINT before
            sending the SIGKILL.  If None, use self.default_wait_before_kill
            instead.
        """
        if timeout is None:
            timeout = self.default_wait_before_kill
        try:
            self.transport.signalProcess('INT')
        except error.ProcessExitedAlready:
            # The process has already died. Fine.
            pass
        else:
            self._sigkill_delayed_call = self._clock.callLater(
                timeout, self._sigkill)

    def _sigkill(self):
        """Forcefully kill the process."""
        self._sigkill_delayed_call = None
        try:
            self.transport.signalProcess('KILL')
        except error.ProcessExitedAlready:
            # The process has already died. Fine.
            pass

    def processEnded(self, reason):
        """See `ProcessProtocol.processEnded`.

        If the process dies and we're waiting to SIGKILL it, we can stop
        waiting.
        """
        ProcessProtocol.processEnded(self, reason)
        if self._sigkill_delayed_call is not None:
            self._sigkill_delayed_call.cancel()
            self._sigkill_delayed_call = None


class ProcessMonitorProtocol(ProcessProtocolWithTwoStageKill):
    """Support for running a process and reporting on its progress.

    The idea is this: you want to run a child process.  Occasionally, you want
    to report on what it is doing to some other entity: maybe it's a multistep
    task and you want to update a row in a database to reflect which step it
    is currently on.  This class provides a runNotification() method that
    helps with this, taking a callable that performs this notfication, maybe
    returning a deferred.

    Design decisions:

     - The notifications are serialized.  If you call runNotification() with
       two callables, the deferred returned by the first must fire before the
       second callable will be called.

     - A notification failing is treated as a fatal error: the child process
       is killed and the 'termination deferred' fired.

     - Because there are multiple things that can go wrong more-or-less at
       once (the process can exit with an error condition at the same time as
       unexpectedError is called for some reason), we take the policy of
       reporting the first thing that we notice going wrong to the termination
       deferred and log.err()ing the others.

     - The deferred passed into the constructor will not be fired until the
       child process has exited and all pending notifications have completed.
       Note that Twisted does not tell us the process has exited until all of
       it's output has been processed.

    :ivar _deferred: The deferred that will be fired when the child process
        exits.
    :ivar _notification_lock: A DeferredLock, used to serialize the
        notifications.
    :ivar _termination_failure: When we kill the child process in response to
        some unexpected error, we report the reason we killed it to
        self._deferred, not that it exited because we killed it.
    """

    def __init__(self, deferred, clock=None):
        """Construct an instance of the protocol, for listening to a worker.

        :param deferred: A Deferred that will be fired when the subprocess has
            finished (either successfully or unsuccesfully).
        """
        ProcessProtocolWithTwoStageKill.__init__(self, clock)
        self._deferred = deferred
        self._notification_lock = defer.DeferredLock()
        self._termination_failure = None

    def runNotification(self, func, *args):
        """Run a given function in series with other notifications.

        "func(*args)" will be called when any other running or queued
        notifications have completed.  func() may return a Deferred.  Note
        that if func() errors out, this is considered a fatal error and the
        subprocess will be killed.
        """
        def wrapper():
            if self._termination_failure is not None:
                return
            else:
                return defer.maybeDeferred(func, *args).addErrback(
                    self.unexpectedError)
        return self._notification_lock.run(wrapper)

    def unexpectedError(self, failure):
        """Something's gone wrong: kill the subprocess and report failure.

        Note that we depend on terminateProcess() killing the process: we
        depend on the fact that processEnded will be called after calling it.
        """
        if self._termination_failure is not None:
            log.msg(
                "unexpectedError called for second time, dropping error:",
                isError=True)
            log.err(failure)
            return
        self._termination_failure = failure
        self.terminateProcess()

    def processEnded(self, reason):
        """See `ProcessProtocol.processEnded`.

        We fire the termination deferred, after waiting for any in-progress
        notifications to complete.
        """
        ProcessProtocolWithTwoStageKill.processEnded(self, reason)

        if not reason.check(error.ProcessDone):
            if self._termination_failure is None:
                self._termination_failure = reason
            # else:
            #     We _could_ log.err(reason) here, but the process is almost
            #     certainly dying because of the zap we gave it in
            #     unexpectedError, so we don't.

        def fire_final_deferred():
            # We defer reading _termination_failure off self until we have the
            # lock in case there is a pending notification that fails and so
            # sets _termination_failure to something interesting.
            self._deferred.callback(self._termination_failure)

        self._notification_lock.run(fire_final_deferred)


class ProcessMonitorProtocolWithTimeout(ProcessMonitorProtocol, TimeoutMixin):
    """Support for killing a monitored process after a period of inactivity.

    Note that this class does not define activity in any way: your subclass
    should call the `resetTimeout()` from `TimeoutMixin` when it deems the
    subprocess has made progress.

    :ivar _timeout: The subprocess will be killed after this many seconds of
        inactivity.
    """

    def __init__(self, deferred, timeout, clock=None):
        """Construct an instance of the protocol, for listening to a worker.

        :param deferred: Passed to `ProcessMonitorProtocol.__init__`.
        :param timeout: The subprocess will be killed after this many seconds of
            inactivity.
        :param clock: Passed to `ProcessMonitorProtocol.__init__`.
        """
        ProcessMonitorProtocol.__init__(self, deferred, clock)
        self._timeout = timeout

    def callLater(self, period, func):
        """Override TimeoutMixin.callLater so we use self._clock.

        This allows us to write unit tests that don't depend on actual wall
        clock time.
        """
        return self._clock.callLater(period, func)

    def connectionMade(self):
        """Start the timeout counter when connection is made."""
        self.setTimeout(self._timeout)

    def timeoutConnection(self):
        """When a timeout occurs, kill the process and record a TimeoutError.
        """
        self.unexpectedError(failure.Failure(error.TimeoutError()))

    def processEnded(self, reason):
        """See `ProcessMonitorProtocol.processEnded`.

        Cancel the timeout, as the process no longer exists.
        """
        self.setTimeout(None)
        ProcessMonitorProtocol.processEnded(self, reason)


def run_process_with_timeout(args, timeout=5, clock=None):
    """Run the given process with the specificed timeout.

    :param args: tuple with the command-line arguments.
    :param timeout: command timeout in seconds, defaults to 5.
    :param clock: Passed to `ProcessMonitorProtocolWithTimeout.__init__`.

    :return: a `Deferred` of the spawed process using
        `ProcessMonitorProtocolWithTimeout`
    """
    assert isinstance(args, tuple), "'args' must be a tuple."
    d = defer.Deferred()
    p = ProcessMonitorProtocolWithTimeout(d, timeout, clock)
    executable = args[0]
    reactor.spawnProcess(p, executable, args)
    return d


class ProcessWithTimeout(ProcessProtocol, TimeoutMixin):
    """Run a process and capture its output while applying a timeout."""

    # XXX Julian 2010-04-21
    # This class doesn't have enough unit tests yet, it's used by
    # lib/lp/buildmaster/manager.py which tests its features indirectly.
    # See lib/lp/services/twistedsupport/tests/test_processmonitor.py -
    # TestProcessWithTimeout for the beginnings of tests.

    def __init__(self, deferred, timeout, clock=None):
        self._deferred = deferred
        self._clock = clock
        self._timeout = timeout
        self._out_buf = StringIO.StringIO()
        self._err_buf = StringIO.StringIO()
        self._process_transport = None

        # outReceived and errReceived are callback methods on
        # ProcessProtocol.
        # All we want to do when we receive stuff from stdout
        # or stderr is store it for later.
        self.outReceived = self._out_buf.write
        self.errReceived = self._err_buf.write

    def callLater(self, period, func):
        """Override TimeoutMixin.callLater so we use self._clock.

        This allows us to write unit tests that don't depend on actual wall
        clock time.
        """
        if self._clock is None:
            return TimeoutMixin.callLater(self, period, func)

        return self._clock.callLater(period, func)

    def spawnProcess(self, *args, **kwargs):
        """Start a process.

        See reactor.spawnProcess.
        """
        self._process_transport = reactor.spawnProcess(
            self, *args, **kwargs)

    def connectionMade(self):
        """Start the timeout counter when connection is made."""
        self.setTimeout(self._timeout)

    def timeoutConnection(self):
        """When a timeout occurs, kill the process with a SIGKILL."""
        try:
            self._process_transport.signalProcess("KILL")
        except error.ProcessExitedAlready:
            # The process has already died. Fine.
            pass
        # processEnded will get called.

    def processEnded(self, reason):
        self.setTimeout(None)
        out = self._out_buf.getvalue()
        err = self._err_buf.getvalue()
        e = reason.value
        code = e.exitCode
        if e.signal:
            self._deferred.errback((out, err, e.signal))
        elif code != os.EX_OK:
            self._deferred.errback((out, err, code))
        else:
            self._deferred.callback((out, err, code))

