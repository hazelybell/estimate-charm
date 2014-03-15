# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Tools for managing long-running or difficult tasks with Twisted."""

__metaclass__ = type
__all__ = [
    'AlreadyRunningError',
    'ITaskConsumer',
    'ITaskSource',
    'NotRunningError',
    'ParallelLimitedTaskConsumer',
    'PollingTaskSource',
    ]

import logging

from twisted.internet import (
    defer,
    reactor,
    )
from twisted.internet.task import LoopingCall
from twisted.python import log
from zope.interface import (
    implements,
    Interface,
    )


class ITaskSource(Interface):
    """A source of tasks to do.

    This is passed to `ITaskConsumer.consume` as a source of tasks to do.
    Tasks are nullary callables that might return Deferreds.

    Objects that provide this interface must call `ITaskConsumer.noTasksFound`
    if there are no tasks to generate, and call `ITaskConsumer.taskStarted`
    with the nullary callable whenever it generates a task.
    """

    def start(task_consumer):
        """Start generating tasks.

        If `start` has already been called, then the given 'task_consumer'
        replaces the existing task accepter.

        :param task_consumer: A provider of `ITaskConsumer`.
        """

    def stop():
        """Stop generating tasks.

        It might not be possible to return instantly, so this method should
        return a Deferred with a boolean that indicates whether
        `ITaskSource.start` was called in the meantime.

        Any subsequent calls to `stop` are silently ignored.

        :return: A Deferred that will fire when the source is stopped.  It is
            possible that tasks may be produced until this deferred fires.
            The deferred will fire with a boolean; True if the source is still
            stopped, False if the source has been restarted since stop() was
            called.
        """


class ITaskConsumer(Interface):
    """A consumer of tasks.

    Pass this to the 'start' method of an `ITaskSource` provider.

    Note that implementations of `ITaskConsumer` need to provide their own way
    of getting references to ITaskSources.
    """

    def taskStarted(task):
        """Called when the task source generates a task.

        This is a throw-it-over-the-wall interface used by ITaskSource.
        ITaskSource expects it to finish quickly and to not raise errors. Any
        return value is completely ignored.

        :param task: The interface for this is defined by the task source.
        """

    def noTasksFound():
        """Called when no tasks were found."""

    def taskProductionFailed(reason):
        """Called when the task source fails to produce a task.

        :param reason: A `twisted.python.failure.Failure` object.
        """


class PollingTaskSource:
    """A task source that polls to generate tasks.

    This is useful for systems where we need to poll a central server in order
    to find new work to do.
    """

    implements(ITaskSource)

    def __init__(self, interval, task_producer, clock=None, logger=None):
        """Construct a `PollingTaskSource`.

        Polls 'task_producer' every 'interval' seconds. 'task_producer'
        returns either None if there's no work to do right now, or some
        representation of the task which is passed to the 'task_consumer'
        callable given to `start`. 'task_producer' can also return a
        `Deferred`.

        :param interval: The length of time between polls in seconds.
        :param task_producer: The polling mechanism. This is a nullary
            callable that can return a Deferred. See above for more details.
        :param clock: An `IReactorTime` implementation that we use to manage
            the interval-based polling. Defaults to using the reactor (i.e.
            actual time).
        """
        if logger is None:
            logger = logging.getLogger(__name__)
        self._logger = logger
        self._interval = interval
        self._task_producer = task_producer
        if clock is None:
            clock = reactor
        self._clock = clock
        self._looping_call = None
        # _polling_lock is used to prevent concurrent attempts to poll for
        # work, and to delay the firing of the deferred returned from stop()
        # until any poll in progress at the moment of the call is complete.
        self._polling_lock = defer.DeferredLock()

    def _log_state(self, method_name, extra=''):
        self._logger.debug(
            '%s.%s() %s; looping=%s; polling_lock.locked=%s'
            % (self.__class__.__name__,
               method_name,
               extra,
               self._looping_call is not None,
               bool(self._polling_lock.locked)))

    def start(self, task_consumer):
        """See `ITaskSource`."""
        self._log_state('start')
        self._clear_looping_call('called from start()')
        assert self._looping_call is None, (
            "Looping call must be None before we create a new one: %r"
            % (self._looping_call,))
        self._looping_call = LoopingCall(self._poll, task_consumer)
        self._looping_call.clock = self._clock
        self._looping_call.start(self._interval)
        self._log_state('start', 'completed')

    def _clear_looping_call(self, reason):
        """Stop the looping call, and log about it."""
        if self._looping_call is not None:
            self._log_state('_clear_looping_call', reason)
            self._looping_call.stop()
            self._looping_call = None

    def _poll(self, task_consumer):
        """Poll for tasks, passing them to 'task_consumer'."""
        def got_task(task):
            self._log_state('got_task', task)
            if task is not None:
                # Note that we deliberately throw away the return value. The
                # task and the consumer need to figure out how to get output
                # back to the end user.
                task_consumer.taskStarted(task)
            else:
                task_consumer.noTasksFound()
        def task_failed(reason):
            # If task production fails, we inform the consumer of this, but we
            # don't let any deferred it returns delay subsequent polls.
            self._log_state('task_failed', reason)
            task_consumer.taskProductionFailed(reason)
        def poll():
            # If stop() has been called before the lock was acquired, don't
            # actually poll for more work.
            self._log_state('acquired_poll')
            if self._looping_call:
                d = defer.maybeDeferred(self._task_producer)
                return d.addCallbacks(got_task, task_failed).addBoth(
                    lambda ignored: self._log_state('releasing_poll'))
        self._log_state('_poll')
        return self._polling_lock.run(poll).addBoth(
            lambda ignored: self._log_state('released_poll'))

    def stop(self):
        """See `ITaskSource`."""
        self._log_state('stop')
        self._clear_looping_call('called from stop()')
        def _return_still_stopped():
            self._log_state('_return_still_stopped')
            return self._looping_call is None
        return self._polling_lock.run(_return_still_stopped)


class AlreadyRunningError(Exception):
    """Raised when we try to start a consumer that's already running."""

    def __init__(self, consumer, source):
        Exception.__init__(
            self, "%r is already consuming tasks from %r."
            % (consumer, source))


class NotRunningError(Exception):
    """Raised when we try to run tasks on a consumer before it has started."""

    def __init__(self, consumer):
        Exception.__init__(
            self, "%r has not started, cannot run tasks." % (consumer,))


class ParallelLimitedTaskConsumer:
    """A consumer that runs tasks with limited parallelism.

    Assumes that the task source generates tasks that are nullary callables
    that might return `Deferred`s.
    """

    implements(ITaskConsumer)

    def __init__(self, worker_limit, logger=None):
        if logger is None:
            logger = logging.getLogger(__name__)
        self._logger = logger
        self._task_source = None
        self._worker_limit = worker_limit
        self._worker_count = 0
        self._terminationDeferred = None
        self._stopping_lock = None

    def _log_state(self, method, action=''):
        self._logger.debug(
            '%s.%s() %s: worker_count=%s; worker_limit=%s'
            % (self.__class__.__name__,
               method,
               action,
               self._worker_count,
               self._worker_limit))

    def _stop(self):
        def _call_stop(ignored):
            self._log_state('_stop', 'Got lock, stopping source')
            return self._task_source.stop()
        def _release_or_stop(still_stopped):
            self._log_state('_stop', 'stop() returned %s' % (still_stopped,))
            if still_stopped and self._worker_count == 0:
                self._logger.debug('Firing termination deferred')
                self._terminationDeferred.callback(None)
                # Note that in this case we don't release the lock: we don't
                # want to try to fire the _terminationDeferred twice!
            else:
                self._logger.debug('Releasing lock')
                self._stopping_lock.release()
        self._log_state('_stop', 'Acquiring lock')
        d = self._stopping_lock.acquire()
        d.addCallback(_call_stop)
        d.addCallback(_release_or_stop)
        return d

    def consume(self, task_source):
        """Start consuming tasks from 'task_source'.

        :param task_source: An `ITaskSource` provider.
        :raise AlreadyRunningError: If 'consume' has already been called on
            this consumer.
        :return: A `Deferred` that fires when the task source is exhausted
            and we are not running any tasks.
        """
        self._log_state('consume')
        if self._task_source is not None:
            self._log_state('consume', 'Already running')
            raise AlreadyRunningError(self, self._task_source)
        self._task_source = task_source
        self._terminationDeferred = defer.Deferred()
        self._stopping_lock = defer.DeferredLock()
        task_source.start(self)
        return self._terminationDeferred

    def taskStarted(self, task):
        """See `ITaskConsumer`.

        Stops the task source when we reach the maximum number of concurrent
        tasks.

        :raise NotRunningError: if 'consume' has not yet been called.
        """
        self._log_state('taskStarted', task)
        if self._task_source is None:
            raise NotRunningError(self)
        self._worker_count += 1
        self._log_state('taskStarted', 'Incremented')
        if self._worker_count >= self._worker_limit:
            self._log_state('taskStarted', 'Hit worker limit')
            self._stop()
        else:
            self._log_state(
                'taskStarted', 'Below worker limit, starting again')
            self._task_source.start(self)
        d = defer.maybeDeferred(task)
        # We don't expect these tasks to have interesting return values or
        # failure modes.
        d.addErrback(log.err)
        d.addBoth(self._taskEnded)

    def noTasksFound(self):
        """See `ITaskConsumer`.

        Called when the producer found no tasks.  If we are not currently
        running any workers, exit.
        """
        self._log_state('noTasksFound')
        if self._worker_count == 0:
            self._stop()

    def taskProductionFailed(self, reason):
        """See `ITaskConsumer`.

        Called by the task source when a failure occurs while producing a
        task. When this happens, we stop the task source. Any currently
        running tasks will finish, and each time this happens, we'll ask the
        task source to start again.

        If the source keeps failing, we'll eventually have no tasks running,
        at which point we stop the source and fire the termination deferred,
        signalling the end of this run.

        This approach allows us to handle intermittent failures gracefully (by
        retrying the next time a task finishes), and to handle persistent
        failures well (by shutting down when there are no more tasks left).

        :raise NotRunningError: if 'consume' has not yet been called.
        """
        self._log_state('taskProductionFailed', reason)
        if self._task_source is None:
            raise NotRunningError(self)
        self._stop()

    def _taskEnded(self, ignored):
        """Handle a task reaching completion.

        Reduces the number of concurrent workers. If there are no running
        workers then we fire the termination deferred, signalling the end of
        the run.

        If there are available workers, we ask the task source to start
        producing jobs.
        """
        self._log_state('_taskEnded')
        self._worker_count -= 1
        self._log_state('_taskEnded', 'Decremented')
        if self._worker_count < self._worker_limit:
            self._log_state('_taskEnded', 'Too few workers, asking for more.')
            self._task_source.start(self)
        else:
            # We're over the worker limit, nothing we can do.
            self._log_state('_taskEnded', 'Hit limit, doing nothing.')
