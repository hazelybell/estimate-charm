# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BadMessage',
    'JobScheduler',
    'LockError',
    'PullerMaster',
    'PullerMonitorProtocol',
    ]

import os
import socket
from StringIO import StringIO

from contrib.glock import (
    GlobalLock,
    LockAlreadyAcquired,
    )
from twisted.internet import (
    defer,
    error,
    reactor,
    )
from twisted.protocols.basic import (
    NetstringParseError,
    NetstringReceiver,
    )
from twisted.python import (
    failure,
    log,
    )

from lp.code.interfaces.codehosting import LAUNCHPAD_SERVICES
from lp.codehosting.puller import get_lock_id_for_branch_id
from lp.codehosting.puller.worker import get_canonical_url_for_branch_name
from lp.services.config import config
from lp.services.twistedsupport.processmonitor import (
    ProcessMonitorProtocolWithTimeout,
    )
from lp.services.twistedsupport.task import (
    ParallelLimitedTaskConsumer,
    PollingTaskSource,
    )
from lp.services.webapp import errorlog


class BadMessage(Exception):
    """Raised when the protocol receives a message that we don't recognize."""

    def __init__(self, bad_netstring):
        Exception.__init__(
            self, 'Received unrecognized message: %r' % bad_netstring)


class UnexpectedStderr(Exception):
    """Raised when the worker prints to stderr."""

    def __init__(self, stderr):
        if stderr:
            last_line = stderr.splitlines()[-1]
        else:
            last_line = stderr
        Exception.__init__(
            self, "Unexpected standard error from subprocess: %s" % last_line)
        self.error = stderr


class PullerWireProtocol(NetstringReceiver):
    """The wire protocol for receiving events from the puller worker.

    The wire-level protocol is a series of netstrings.

    At the next level up, the protocol consists of messages which each look
    like this::

            [method-name] [number-of-arguments] [arguments]+

    Thus the instance is always in one of three states::

        [0] Waiting for command name.
        [1] Waiting for argument count.
        [2] Waiting for an argument.

    In state [0], we are waiting for a command name.  When we get one, we
    store it in self._current_command and move into state [1].

    In state [1], we are waiting for an argument count.  When we receive a
    message, we try to convert it to an integer.  If we fail in this, we call
    unexpectedError().  Otherwise, if it's greater than zero, we store the
    number in self._expected_args and go into state [2] or if it's zero
    execute the command (see below).

    In state [2], we are waiting for an argument.  When we receive one, we
    append it to self._current_args.  If len(self._current_args) ==
    self._expected_args, execute the command.

    "Executing the command" means looking for a method called
    do_<command name> on self.puller_protocol and calling it with
    *self._current_args.  If this raises, call
    self.puller_protocol.unexpectedError().

    The method _resetState() forces us back into state [0].
    """

    def __init__(self, puller_protocol):
        self.puller_protocol = puller_protocol
        self._resetState()

    def dataReceived(self, data):
        """See `NetstringReceiver.dataReceived`."""
        NetstringReceiver.dataReceived(self, data)
        # XXX: JonathanLange 2007-10-16
        # bug=http://twistedmatrix.com/trac/ticket/2851: There are no hooks in
        # NetstringReceiver to catch a NetstringParseError. The best we can do
        # is check the value of brokenPeer.
        if self.brokenPeer:
            self.puller_protocol.unexpectedError(
                failure.Failure(NetstringParseError(data)))

    def stringReceived(self, line):
        """See `NetstringReceiver.stringReceived`."""
        if (self._current_command is not None
            and self._expected_args is not None):
            # state [2]
            self._current_args.append(line)
        elif self._current_command is not None:
            # state [1]
            try:
                self._expected_args = int(line)
            except ValueError:
                self.puller_protocol.unexpectedError(failure.Failure())
        else:
            # state [0]
            if getattr(self.puller_protocol, 'do_%s' % line, None) is None:
                self.puller_protocol.unexpectedError(
                    failure.Failure(BadMessage(line)))
            else:
                self._current_command = line

        if len(self._current_args) == self._expected_args:
            # Execute the command.
            method = getattr(
                self.puller_protocol, 'do_%s' % self._current_command)
            try:
                try:
                    method(*self._current_args)
                except:
                    self.puller_protocol.unexpectedError(failure.Failure())
            finally:
                self._resetState()

    def _resetState(self):
        """Force into the 'waiting for command' state."""
        self._current_command = None
        self._expected_args = None
        self._current_args = []


class PullerMonitorProtocol(ProcessMonitorProtocolWithTimeout,
                            NetstringReceiver):
    """The protocol for receiving events from the puller worker."""

    def __init__(self, deferred, listener, clock=None):
        """Construct an instance of the protocol, for listening to a worker.

        :param deferred: A Deferred that will be fired when the worker has
            finished (either successfully or unsuccesfully).
        :param listener: A PullerMaster object that is notified when the
            protocol receives events from the worker.
        :param clock: A provider of Twisted's IReactorTime.  This parameter
            exists to allow testing that does not depend on an external clock.
            If a clock is not passed in explicitly the reactor is used.
        """
        ProcessMonitorProtocolWithTimeout.__init__(
            self, deferred, config.supermirror.worker_timeout, clock)
        self.reported_mirror_finished = False
        self.listener = listener
        self.wire_protocol = PullerWireProtocol(self)
        self._stderr = StringIO()
        self._deferred.addCallbacks(
            self.checkReportingFinishedAndNoStderr,
            self.ensureReportingFinished)

    def reportMirrorFinished(self, ignored):
        self.reported_mirror_finished = True

    def checkReportingFinishedAndNoStderr(self, result):
        """Check that the worker process behaved properly on clean exit.

        When the process exits cleanly, we expect it to have not printed
        anything to stderr and to have reported success or failure.  If it has
        failed to do either of these things, we should fail noisily."""
        stderr = self._stderr.getvalue()
        if stderr:
            fail = failure.Failure(UnexpectedStderr(stderr))
            fail.error = stderr
            return fail
        if not self.reported_mirror_finished:
            raise AssertionError('Process exited successfully without '
                                 'reporting success or failure?')
        return result

    def ensureReportingFinished(self, reason):
        """Clean up after the worker process exits uncleanly.

        If the worker process exited uncleanly, it probably didn't report
        success or failure, so we should report failure.  If there was output
        on stderr, it's probably a traceback, so we use the last line of that
        as a failure reason.
        """
        if not self.reported_mirror_finished:
            stderr = self._stderr.getvalue()
            reason.error = stderr
            if stderr:
                errorline = stderr.splitlines()[-1]
            else:
                errorline = str(reason.value)
            # The general policy when multiple errors occur is to report the
            # one that happens first and as an error has already happened here
            # (the process exiting uncleanly) we can only log.err() any
            # failure that comes from mirrorFailed failing.  In any case, we
            # just pass along the failure.
            report_failed_deferred = defer.maybeDeferred(
                self.listener.mirrorFailed, errorline, None)
            report_failed_deferred.addErrback(log.err)
            return report_failed_deferred.addCallback(
                lambda result: reason)
        else:
            return reason

    def makeConnection(self, process):
        """Called when the process has been created."""
        ProcessMonitorProtocolWithTimeout.makeConnection(self, process)
        NetstringReceiver.makeConnection(self, process)
        self.wire_protocol.makeConnection(process)

    def outReceived(self, data):
        self.wire_protocol.dataReceived(data)

    def errReceived(self, data):
        self._stderr.write(data)

    def do_startMirroring(self):
        self.resetTimeout()
        self.runNotification(self.listener.startMirroring)

    def do_branchChanged(self, stacked_on_url, revid_before, revid_after,
                         control_string, branch_string, repository_string):
        def branchChanged():
            d = defer.maybeDeferred(
                self.listener.branchChanged, stacked_on_url, revid_before,
                revid_after, control_string, branch_string, repository_string)
            d.addCallback(self.reportMirrorFinished)
            return d
        self.runNotification(branchChanged)

    def do_mirrorFailed(self, reason, oops):
        def mirrorFailed():
            d = defer.maybeDeferred(
                self.listener.mirrorFailed, reason, oops)
            d.addCallback(self.reportMirrorFinished)
            return d
        self.runNotification(mirrorFailed)

    def do_progressMade(self):
        """Any progress resets the timout counter."""
        self.resetTimeout()

    def do_log(self, message):
        self.listener.log(message)


class PullerMaster:
    """Controller for a single puller worker.

    The `PullerMaster` kicks off a child worker process and handles the events
    generated by that process.
    """

    path_to_script = os.path.join(config.root, 'scripts/mirror-branch.py')
    protocol_class = PullerMonitorProtocol

    def __init__(self, branch_id, source_url, unique_name, branch_type_name,
                 default_stacked_on_url, logger, client):
        """Construct a PullerMaster object.

        :param branch_id: The database ID of the branch to be mirrored.
        :param source_url: The location from which the branch is to be
            mirrored.
        :param unique_name: The unique name of the branch to be mirrored.
        :param branch_type_name: The name of the BranchType of the branch to
            be mirrored (e.g. 'MIRRORED').
        :param default_stacked_on_url: The default stacked-on URL for the
            product that the branch is in. '' implies that there is no such
            default.
        :param logger: A Python logging object.
        :param client: An asynchronous client for the branch status XML-RPC
            service.
        """
        self.branch_id = branch_id
        self.source_url = source_url.strip()
        self.destination_url = 'lp-internal:///%s' % (unique_name,)
        self.unique_name = unique_name
        self.branch_type_name = branch_type_name
        self.default_stacked_on_url = default_stacked_on_url
        self.logger = logger
        self.codehosting_endpoint = client

    def mirror(self):
        """Spawn a worker process to mirror a branch."""
        deferred = defer.Deferred()
        protocol = self.protocol_class(deferred, self)
        interpreter = '%s/bin/py' % config.root
        command = [
            interpreter, self.path_to_script, self.source_url,
            self.destination_url, str(self.branch_id), str(self.unique_name),
            self.branch_type_name,
            self.default_stacked_on_url]
        self.logger.debug("executing %s", command)
        env = os.environ.copy()
        env['BZR_EMAIL'] = get_lock_id_for_branch_id(self.branch_id)
        reactor.spawnProcess(protocol, interpreter, command, env=env)
        return deferred

    def run(self):
        """Launch a child worker and mirror a branch, handling errors.

        This is the main method to call to mirror a branch.

        :return: A Deferred that fires when the mirroring job is completed,
            one way or the other. It will never fire with a failure. The value
            of the Deferred itself is uninteresting (probably None).
        """
        deferred = self.mirror()
        deferred.addErrback(self.unexpectedError)
        return deferred

    def startMirroring(self):
        self.logger.info(
            'Worker started on branch %d: %s to %s', self.branch_id,
            self.source_url, self.destination_url)

    def mirrorFailed(self, reason, oops):
        self.logger.info('Recorded %s', oops)
        self.logger.info('Recorded failure: %s', str(reason))
        return self.codehosting_endpoint.callRemote(
            'mirrorFailed', self.branch_id, reason)

    def branchChanged(self, stacked_on_url, revid_before, revid_after,
                      control_string, branch_string, repository_string):
        if revid_before == revid_after:
            was_noop = 'noop'
        else:
            was_noop = 'non-trivial'
        self.logger.info(
            'Successfully mirrored %s branch %d %s to %s to from rev %s to %s'
            ' (%s)', self.branch_type_name, self.branch_id, self.source_url,
            self.destination_url, revid_before, revid_after, was_noop)
        return self.codehosting_endpoint.callRemote(
            'branchChanged', LAUNCHPAD_SERVICES, self.branch_id,
            stacked_on_url, revid_after, control_string, branch_string,
            repository_string)

    def log(self, message):
        self.logger.info('From worker: %s', message)

    def unexpectedError(self, failure):
        request = errorlog.ScriptRequest([
            ('branch_id', self.branch_id),
            ('source', self.source_url),
            ('dest', self.destination_url),
            ('error-explanation', failure.getErrorMessage())])
        request.URL = get_canonical_url_for_branch_name(self.unique_name)
        # If the sub-process exited abnormally, the stderr it produced is
        # probably a much more interesting traceback than the one attached to
        # the Failure we've been passed.
        tb = None
        if failure.check(error.ProcessTerminated, UnexpectedStderr):
            tb = getattr(failure, 'error', None)
        if tb is None:
            tb = failure.getTraceback()
        errorlog.globalErrorUtility.raising(
            (failure.type, failure.value, tb), request)
        self.logger.info('Recorded %s', request.oopsid)


class JobScheduler:
    """Schedule and manage the mirroring of branches.

    The jobmanager is responsible for organizing the mirroring of all
    branches.
    """

    def __init__(self, codehosting_endpoint, logger, branch_type_names):
        self.codehosting_endpoint = codehosting_endpoint
        self.logger = logger
        self.branch_type_names = branch_type_names
        self.actualLock = None
        self.name = 'branch-puller'
        self.lockfilename = '/var/lock/launchpad-%s.lock' % self.name

    def _turnJobTupleIntoTask(self, job_tuple):
        """Turn the return value of `acquireBranchToPull` into a job.

        `IBranchPuller.acquireBranchToPull` returns either an empty tuple
        (indicating there are no branches to pull currently) or a tuple of 6
        arguments, which are more or less those needed to construct a
        `PullerMaster` object.
        """
        if len(job_tuple) == 0:
            return None
        (branch_id, pull_url, unique_name,
         default_stacked_on_url, branch_type_name) = job_tuple
        master = PullerMaster(
            branch_id, pull_url, unique_name, branch_type_name,
            default_stacked_on_url, self.logger,
            self.codehosting_endpoint)
        return master.run

    def _poll(self):
        deferred = self.codehosting_endpoint.callRemote(
            'acquireBranchToPull', self.branch_type_names)
        deferred.addCallback(self._turnJobTupleIntoTask)
        return deferred

    def run(self):
        consumer = ParallelLimitedTaskConsumer(
            config.supermirror.maximum_workers, logger=self.logger)
        self.consumer = consumer
        source = PollingTaskSource(
            config.supermirror.polling_interval, self._poll,
            logger=self.logger)
        deferred = consumer.consume(source)
        deferred.addCallback(self._finishedRunning)
        return deferred

    def _finishedRunning(self, ignored):
        self.logger.info('Mirroring complete')
        return ignored

    def lock(self):
        self.actualLock = GlobalLock(self.lockfilename)
        try:
            self.actualLock.acquire()
        except LockAlreadyAcquired:
            raise LockError(self.lockfilename)

    def unlock(self):
        self.actualLock.release()

    def recordActivity(self, date_started, date_completed):
        """Record successful completion of the script."""
        started_tuple = tuple(date_started.utctimetuple())
        completed_tuple = tuple(date_completed.utctimetuple())
        return self.codehosting_endpoint.callRemote(
            'recordSuccess', self.name, socket.gethostname(), started_tuple,
            completed_tuple)


class LockError(StandardError):

    def __init__(self, lockfilename):
        StandardError.__init__(self)
        self.lockfilename = lockfilename

    def __str__(self):
        return 'Jobmanager unable to get master lock: %s' % self.lockfilename
