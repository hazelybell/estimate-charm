# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Tests for our task support."""

__metaclass__ = type

from twisted.internet.defer import (
    Deferred,
    succeed,
    )
from twisted.internet.task import Clock
from zope.interface import implements

from lp.services.twistedsupport.task import (
    AlreadyRunningError,
    ITaskConsumer,
    ITaskSource,
    NotRunningError,
    ParallelLimitedTaskConsumer,
    PollingTaskSource,
    )
from lp.testing import TestCase


class NoopTaskConsumer:
    """Task consumer that does nothing."""

    implements(ITaskConsumer)

    def taskStarted(self, task):
        """Do nothing."""

    def noTasksFound(self):
        """Do nothing."""

    def taskProductionFailed(self, reason):
        """Do nothing."""


class AppendingTaskConsumer(NoopTaskConsumer):
    """Task consumer that logs calls to `taskStarted`."""

    def __init__(self, data_sink):
        self.data_sink = data_sink

    def taskStarted(self, task):
        """Log that 'task' has started."""
        self.data_sink.append(task)


class LoggingSource:
    """Task source that logs calls to `start` and `stop'`"""

    implements(ITaskSource)

    def __init__(self, log, stop_deferred=None):
        self._log = log
        if stop_deferred is None:
            self.stop_deferred = succeed(True)
        else:
            self.stop_deferred = stop_deferred

    def start(self, consumer):
        self._log.append(('start', consumer))

    def stop(self):
        self._log.append('stop')
        return self.stop_deferred


class TestPollingTaskSource(TestCase):
    """Tests for `PollingTaskSource`."""

    def setUp(self):
        TestCase.setUp(self)
        self._num_task_producer_calls = 0
        self._default_task_consumer = NoopTaskConsumer()

    def _default_task_producer(self):
        """Producer that records the number of times it has been called.

        :return: None, indicating that there are no tasks to do right now.
        """
        self._num_task_producer_calls += 1
        return None

    def makeTaskSource(self, task_producer=None, interval=None, clock=None):
        """Make a task source for testing.

        :param task_producer: The producer of tasks. Defaults to a producer
            that returns None and increments a count of the number of times
            it has been called.
        :param interval: The interval between polls. Defaults to an arbitrary
            integer.
        :param clock: The clock to use for measuring the interval. Defaults to
            an instance of `Clock`.
        :return: A `PollingTaskSource`.
        """
        if task_producer is None:
            task_producer = self._default_task_producer
        if clock is None:
            clock = Clock()
        if interval is None:
            interval = self.factory.getUniqueInteger()
        return PollingTaskSource(interval, task_producer, clock=clock)

    def test_provides_ITaskSource(self):
        # PollingTaskSource instances provide ITaskSource.
        self.assertProvides(self.makeTaskSource(), ITaskSource)

    def test_start_commences_polling(self):
        # Calling `start` on a PollingTaskSource begins polling the task
        # factory.
        task_source = self.makeTaskSource()
        task_source.start(self._default_task_consumer)
        self.assertEqual(1, self._num_task_producer_calls)

    def test_noTasksFound_called_when_no_tasks_found(self):
        # When a call to the producer indicates that no job is found, the
        # 'noTasksFound' method is called on the consumer.
        class NoTasksFoundCountingConsumer:
            def __init__(self):
                self._noTasksFound_calls = 0
            def noTasksFound(self):
                self._noTasksFound_calls += 1
        task_source = self.makeTaskSource(task_producer=lambda: None)
        consumer = NoTasksFoundCountingConsumer()
        task_source.start(consumer)
        self.assertEqual(1, consumer._noTasksFound_calls)

    def test_start_continues_polling(self):
        # Calling `start` on a PollingTaskSource begins polling the task
        # factory. This polling continues over time, once every 'interval'
        # seconds.
        clock = Clock()
        interval = self.factory.getUniqueInteger()
        task_source = self.makeTaskSource(interval=interval, clock=clock)
        task_source.start(self._default_task_consumer)
        self._num_task_producer_calls = 0
        clock.advance(interval)
        self.assertEqual(1, self._num_task_producer_calls)

    def test_stop_stops_polling(self):
        # Calling `stop` after a PollingTaskSource has started will stop the
        # polling.
        clock = Clock()
        interval = self.factory.getUniqueInteger()
        task_source = self.makeTaskSource(interval=interval, clock=clock)
        task_source.start(self._default_task_consumer)
        task_source.stop()
        self._num_task_producer_calls = 0
        clock.advance(interval)
        # No more calls were made.
        self.assertEqual(0, self._num_task_producer_calls)

    def test_stop_deferred_fires_immediately_if_no_polling(self):
        # Calling stop when the source is not polling returns a deferred that
        # fires immediately with True.
        task_source = self.makeTaskSource()
        task_source.start(NoopTaskConsumer())
        stop_deferred = task_source.stop()
        stop_calls = []
        stop_deferred.addCallback(stop_calls.append)
        self.assertEqual([True], stop_calls)

    def test_start_multiple_times_polls_immediately(self):
        # Starting a task source multiple times polls immediately.
        clock = Clock()
        interval = self.factory.getUniqueInteger()
        task_source = self.makeTaskSource(interval=interval, clock=clock)
        task_source.start(self._default_task_consumer)
        clock.advance(interval / 2.0)
        self._num_task_producer_calls = 0
        task_source.start(self._default_task_consumer)
        self.assertEqual(1, self._num_task_producer_calls)

    def test_start_multiple_times_resets_polling_loop(self):
        # Starting a task source multiple times resets the polling loop to
        # start from now.
        clock = Clock()
        interval = self.factory.getUniqueInteger()
        task_source = self.makeTaskSource(interval=interval, clock=clock)
        task_source.start(self._default_task_consumer)
        clock.advance(interval / 2.0)
        task_source.start(self._default_task_consumer)
        self._num_task_producer_calls = 0
        clock.advance(interval)
        self.assertEqual(1, self._num_task_producer_calls)

    def test_starting_again_changes_consumer(self):
        # Starting a task source again changes the task consumer.
        tasks = [
            self.factory.getUniqueString(), self.factory.getUniqueString()]
        consumer1_tasks = []
        consumer2_tasks = []
        task_source = self.makeTaskSource(task_producer=iter(tasks).next)
        task_source.start(AppendingTaskConsumer(consumer1_tasks))
        task_source.start(AppendingTaskConsumer(consumer2_tasks))
        self.assertEqual(
            ([tasks[0]], [tasks[1]]), (consumer1_tasks, consumer2_tasks))

    def test_task_consumer_not_called_when_factory_doesnt_produce(self):
        # The task_consumer passed to start is *not* called when the factory
        # returns None (implying there are no tasks to do right now).
        task_producer = lambda: None
        started_tasks = []
        task_source = self.makeTaskSource(task_producer=task_producer)
        task_source.start(AppendingTaskConsumer(started_tasks))
        self.assertEqual([], started_tasks)

    def test_stop_without_start(self):
        # Calling 'stop' before 'start' is called silently succeeds.
        task_source = self.makeTaskSource()
        # Assert that this doesn't raise an exception.
        task_source.stop()

    def test_stop_multiple_times(self):
        # Calling 'stop' multiple times has no effect.
        task_source = self.makeTaskSource()
        task_source.stop()
        # Assert that this doesn't raise an exception.
        task_source.stop()

    def test_producer_returns_deferred(self):
        # The task producer can return Deferreds. In this case, we only call
        # the consumer when the Deferred fires.
        deferred = Deferred()
        tasks_called = []
        task_source = self.makeTaskSource(task_producer=lambda: deferred)
        task_source.start(AppendingTaskConsumer(tasks_called))
        self.assertEqual([], tasks_called)
        deferred.callback('foo')
        self.assertEqual(['foo'], tasks_called)

    def test_only_one_producer_call_at_once(self):
        # If the task producer returns a Deferred, it will not be called again
        # until that deferred has fired, even if takes longer than the
        # interval we're polling at.
        tasks_called = []
        produced_deferreds = []
        def producer():
            deferred = Deferred()
            produced_deferreds.append(deferred)
            return deferred
        clock = Clock()
        interval = self.factory.getUniqueInteger()
        task_source = self.makeTaskSource(
            task_producer=producer, interval=interval, clock=clock)
        task_source.start(AppendingTaskConsumer(tasks_called))
        # The call to start calls producer.  It returns a deferred which has
        # not been fired.
        self.assertEqual(len(produced_deferreds), 1)
        # If 'interval' seconds passes and the deferred has still not fired
        # the producer is not called again.
        clock.advance(interval)
        self.assertEqual(len(produced_deferreds), 1)
        # If the task-getting deferred is fired and more time passes, we poll
        # again.
        produced_deferreds[0].callback(None)
        clock.advance(interval)
        self.assertEqual(len(produced_deferreds), 2)

    def test_stop_deferred_doesnt_fire_until_polling_finished(self):
        # If there is a call to the task producer outstanding when stop() is
        # called, stop() returns a deferred that fires when the poll finishes.
        # The value fired with is True if the source is still stopped when the
        # deferred fires.
        produced_deferred = Deferred()
        def producer():
            return produced_deferred
        task_source = self.makeTaskSource(task_producer=producer)
        task_source.start(NoopTaskConsumer())
        # The call to start calls producer.  It returns produced_deferred
        # which has not been fired, so stop returns a deferred that has not
        # been fired.
        stop_deferred = task_source.stop()
        stop_called = []
        stop_deferred.addCallback(stop_called.append)
        self.assertEqual([], stop_called)
        # When the task producing deferred fires, the stop deferred fires with
        # 'True' to indicate that the source is still stopped.
        produced_deferred.callback(None)
        self.assertEqual([True], stop_called)

    def test_stop_deferred_fires_with_false_if_source_restarted(self):
        # If there is a call to the task producer outstanding when stop() is
        # called, stop() returns a deferred that fires when the poll finishes.
        # The value fired with is False if the source is no longer stopped
        # when the deferred fires.
        produced_deferred = Deferred()
        def producer():
            return produced_deferred
        task_source = self.makeTaskSource(task_producer=producer)
        task_source.start(NoopTaskConsumer())
        # The call to start calls producer.  It returns produced_deferred
        # which has not been fired so stop returns a deferred that has not
        # been fired.
        stop_deferred = task_source.stop()
        stop_called = []
        stop_deferred.addCallback(stop_called.append)
        # Now we restart the source.
        task_source.start(NoopTaskConsumer())
        self.assertEqual([], stop_called)
        # When the task producing deferred fires, the stop deferred fires with
        # 'False' to indicate that the source has been restarted.
        produced_deferred.callback(None)
        self.assertEqual([False], stop_called)

    def test_stop_start_stop_when_polling_doesnt_poll_again(self):
        # If, while task acquisition is in progress, stop(), start() and
        # stop() again are called in sequence, we shouldn't try to acquire
        # another job when the first acquisition completes.
        produced_deferreds = []
        def producer():
            d = Deferred()
            produced_deferreds.append(d)
            return d
        task_source = self.makeTaskSource(task_producer=producer)
        # Start the source.  This calls the producer.
        task_source.start(NoopTaskConsumer())
        self.assertEqual(1, len(produced_deferreds))
        task_source.stop()
        # If we start it again, this does not call the producer because
        # the above call is still in process.
        task_source.start(NoopTaskConsumer())
        self.assertEqual(1, len(produced_deferreds))
        # If we now stop the source and the initial poll for a task completes,
        # we don't poll again.
        task_source.stop()
        produced_deferreds[0].callback(None)
        self.assertEqual(1, len(produced_deferreds))

    def test_taskStarted_deferred_doesnt_delay_polling(self):
        # If taskStarted returns a deferred, we don't wait for it to fire
        # before polling again.
        class DeferredStartingConsumer(NoopTaskConsumer):
            def taskStarted(self, task):
                started.append(task)
                return Deferred()
        interval = self.factory.getUniqueInteger()
        clock = Clock()
        produced = []
        started = []
        def producer():
            value = self.factory.getUniqueInteger()
            produced.append(value)
            return value
        task_source = self.makeTaskSource(
            task_producer=producer, interval=interval, clock=clock)
        consumer = DeferredStartingConsumer()
        task_source.start(consumer)
        # The call to start polls once and taskStarted is called.
        self.assertEqual((1, 1), (len(produced), len(started)))
        # Even though taskStarted returned a deferred which has not yet fired,
        # we poll again after 'interval' seconds.
        clock.advance(interval)
        self.assertEqual((2, 2), (len(produced), len(started)))

    def test_producer_errors_call_taskProductionFailed(self):
        # If the producer raises an error, then we call taskProductionFailed
        # on the task consumer.
        class LoggingConsumer:
            def __init__(self):
                self._task_production_failed_calls = []
            def taskStarted(self, task):
                self.fail("taskStarted should not be called.")
            def taskProductionFailed(self, reason):
                self._task_production_failed_calls.append(reason)

        task_source = self.makeTaskSource(task_producer=lambda: 1/0)
        consumer = LoggingConsumer()
        task_source.start(consumer)
        self.assertEqual(1, len(consumer._task_production_failed_calls))
        reason = consumer._task_production_failed_calls[0]
        self.assertTrue(reason.check(ZeroDivisionError))

    def test_taskProductionFailed_deferred_doesnt_delay_polling(self):
        # If taskProductionFailed returns a deferred, we don't wait for it to
        # fire before polling again.
        class DeferredFailingConsumer(NoopTaskConsumer):
            def taskProductionFailed(self, reason):
                failures.append(reason)
                return Deferred()
        interval = self.factory.getUniqueInteger()
        clock = Clock()
        produced = []
        failures = []
        def producer():
            exc = RuntimeError()
            produced.append(exc)
            raise exc
        task_source = self.makeTaskSource(
            task_producer=producer, interval=interval, clock=clock)
        consumer = DeferredFailingConsumer()
        task_source.start(consumer)
        # The call to start polls once and taskProductionFailed is called.
        self.assertEqual((1, 1), (len(produced), len(failures)))
        # Even though taskProductionFailed returned a deferred which has not
        # yet fired, we poll again after 'interval' seconds.
        clock.advance(interval)
        self.assertEqual((2, 2), (len(produced), len(failures)))


class TestParallelLimitedTaskConsumer(TestCase):
    """Tests for `ParallelLimitedTaskConsumer`."""

    def makeConsumer(self, worker_limit=None):
        """Make a consumer for testing.

        :param worker_limit: The maximum number of concurrent workers. If
            None, then default to an unreasonably large number so that it
            won't interfere with tests.
        :return: A `ParallelLimitedTaskConsumer`.
        """
        if worker_limit is None:
            # Unreasonably large number.
            worker_limit = 9999999
        return ParallelLimitedTaskConsumer(worker_limit=worker_limit)

    def _neverEndingTask(self):
        """A task that never completes.

        Just return a deferred that we will never fire.
        """
        return Deferred()

    def test_implements_ITaskConsumer(self):
        # ParallelLimitedTaskConsumer instances provide ITaskConsumer.
        self.assertProvides(self.makeConsumer(), ITaskConsumer)

    def test_consume_starts_source(self):
        # Calling `consume` with a task source starts that source.
        consumer = self.makeConsumer()
        log = []
        source = LoggingSource(log)
        consumer.consume(source)
        self.assertEqual([('start', consumer)], log)

    def test_consume_twice_raises_error(self):
        # Calling `consume` twice always raises an error.
        consumer = self.makeConsumer()
        source = LoggingSource([])
        consumer.consume(source)
        self.assertRaises(AlreadyRunningError, consumer.consume, source)

    def test_consumer_doesnt_finish_until_tasks_finish(self):
        # `consume` returns a Deferred that fires when no more tasks are
        # running, but only after we've actually done something.
        consumer = self.makeConsumer()
        log = []
        d = consumer.consume(LoggingSource([]))
        d.addCallback(log.append)
        self.assertEqual([], log)

    def test_consumer_finishes_if_no_tasks_found(self):
        # `consume` returns a Deferred that fires if no tasks are found when
        # no tasks are running.
        consumer = self.makeConsumer()
        task_log = []
        d = consumer.consume(LoggingSource([]))
        d.addCallback(task_log.append)
        consumer.noTasksFound()
        self.assertEqual([None], task_log)

    def test_consumer_doesnt_finish_until_stop_deferred_fires(self):
        # The Deferred returned by `consume` does not fire until the deferred
        # returned by the source's stop() method fires with True to indicate
        # that the source is still stopped.
        consumer = self.makeConsumer()
        consume_log = []
        stop_deferred = Deferred()
        source = LoggingSource([], stop_deferred)
        d = consumer.consume(source)
        d.addCallback(consume_log.append)
        consumer.noTasksFound()
        self.assertEqual([], consume_log)
        stop_deferred.callback(True)
        self.assertEqual([None], consume_log)

    def test_consumer_doesnt_finish_if_stop_doesnt_stop(self):
        # The Deferred returned by `consume` does not fire when the deferred
        # returned by the source's stop() method fires with False to indicate
        # that the source has been restarted.
        consumer = self.makeConsumer()
        consume_log = []
        stop_deferred = Deferred()
        source = LoggingSource([], stop_deferred)
        d = consumer.consume(source)
        d.addCallback(consume_log.append)
        consumer.noTasksFound()
        self.assertEqual([], consume_log)
        stop_deferred.callback(False)
        self.assertEqual([], consume_log)

    def test_consumer_doesnt_finish_if_no_tasks_found_and_job_running(self):
        # If no tasks are found while a job is running, the Deferred returned
        # by `consume` is not fired.
        consumer = self.makeConsumer()
        task_log = []
        d = consumer.consume(LoggingSource([]))
        d.addCallback(task_log.append)
        consumer.taskStarted(self._neverEndingTask)
        consumer.noTasksFound()
        self.assertEqual([], task_log)

    def test_source_not_stopped_if_no_tasks_found_and_job_running(self):
        # If no tasks are found while a job is running, we do not stop the
        # source.
        consumer = self.makeConsumer()
        log = []
        consumer.consume(LoggingSource(log))
        consumer.taskStarted(self._neverEndingTask)
        consumer.noTasksFound()
        self.assertEqual(0, log.count('stop'))

    def test_source_started_when_all_tasks_done(self):
        # When no more tasks are running, we start the task source so it has
        # one more chance to give us work.
        consumer = self.makeConsumer()
        log = []
        consumer.consume(LoggingSource(log))
        del log[:]
        # Finishes immediately, all tasks are done.
        consumer.taskStarted(lambda: None)
        self.assertEqual(2, log.count(('start', consumer)))
        self.assertEqual(0, log.count('stop'))

    def test_taskStarted_before_consume_raises_error(self):
        # taskStarted can only be called after we have started consuming. This
        # is because taskStarted might need to stop task production to avoid a
        # work overload.
        consumer = self.makeConsumer()
        self.assertRaises(NotRunningError, consumer.taskStarted, None)

    def test_taskProductionFailed_before_consume_raises_error(self):
        # taskProductionFailed can only be called after we have started
        # consuming. This is because taskProductionFailed might need to stop
        # task production to handle errors properly.
        consumer = self.makeConsumer()
        self.assertRaises(
            NotRunningError, consumer.taskProductionFailed, None)

    def test_taskStarted_runs_task(self):
        # Calling taskStarted with a task runs that task.
        log = []
        consumer = self.makeConsumer()
        consumer.consume(LoggingSource([]))
        consumer.taskStarted(lambda: log.append('task'))
        self.assertEqual(['task'], log)

    def test_taskStarted_restarts_source(self):
        # If, after the task passed to taskStarted has been started, the
        # consumer is not yet at its worker_limit, it starts the source again
        # in order consume as many pending jobs as we can as quickly as we
        # can.
        log = []
        consumer = self.makeConsumer()
        consumer.consume(LoggingSource(log))
        del log[:]
        consumer.taskStarted(self._neverEndingTask)
        self.assertEqual([('start', consumer)], log)

    def test_reaching_working_limit_stops_source(self):
        # Each time taskStarted is called, we start a worker. When we reach
        # the worker limit, we tell the source to stop generating work.
        worker_limit = 3
        consumer = self.makeConsumer(worker_limit=worker_limit)
        log = []
        source = LoggingSource(log)
        consumer.consume(source)
        del log[:]
        consumer.taskStarted(self._neverEndingTask)
        self.assertEqual(0, log.count('stop'))
        for i in range(worker_limit - 1):
            consumer.taskStarted(self._neverEndingTask)
        self.assertEqual(1, log.count('stop'))

    def test_passing_working_limit_stops_source(self):
        # If we have already reached the worker limit, and taskStarted is
        # called, we tell the source (again, presumably), to stop generating
        # work.
        worker_limit = 1
        consumer = self.makeConsumer(worker_limit=worker_limit)
        log = []
        source = LoggingSource(log)
        consumer.consume(source)
        del log[:]
        consumer.taskStarted(self._neverEndingTask)
        # Reached the limit.
        self.assertEqual(['stop'], log)
        del log[:]
        # Passed the limit.
        consumer.taskStarted(self._neverEndingTask)
        self.assertEqual(['stop'], log)

    def test_run_task_even_though_passed_limit(self):
        # If the source sends us work to do even though we've passed our
        # concurrency limit, we'll do the work anyway. We cannot rely on the
        # source sending us the work again.
        log = []
        def log_append(item):
            log.append(item)
            return Deferred()
        consumer = self.makeConsumer(worker_limit=1)
        consumer.consume(LoggingSource([]))
        consumer.taskStarted(lambda: log_append('task1'))
        consumer.taskStarted(lambda: log_append('task2'))
        self.assertEqual(['task1', 'task2'], log)

    def test_restart_source_when_worker_available(self):
        # When we reach the worker limit, we tell the source to stop. Once we
        # drop back down below the limit, however, we tell it to start up
        # again.
        worker_limit = 2
        consumer = self.makeConsumer(worker_limit=worker_limit)
        log = []
        source = LoggingSource(log)
        consumer.consume(source)
        consumer.taskStarted(self._neverEndingTask)
        d = Deferred()
        consumer.taskStarted(lambda: d)
        # Reached the limit.
        del log[:]
        # One of the tasks is finished
        d.callback(None)
        self.assertEqual([('start', consumer)], log)

    def test_production_failed_stops_source(self):
        # If `taskProductionFailed` is called after we've started consuming
        # then we stop the producer.
        log = []
        source = LoggingSource(log)
        consumer = self.makeConsumer()
        consumer.consume(source)
        del log[:]
        consumer.taskProductionFailed(None)
        self.assertEqual(['stop'], log)

    def test_failure_before_any_tasks_stops_consumer(self):
        # If `taskProductionFailed` is called after we've started consuming
        # but before any jobs are running then we stop the producer and fire
        # the termination deferred.
        consumer = self.makeConsumer()
        log = []
        d = consumer.consume(LoggingSource([]))
        d.addCallback(log.append)
        consumer.taskProductionFailed(None)
        self.assertEqual([None], log)

    def test_one_failure_doesnt_stop_consumer(self):
        # Even after the source has failed in producing a task, we will ask it
        # for more tasks when a worker becomes available.
        consumer = self.makeConsumer()
        task_log = []
        source_log = []
        terminator = consumer.consume(LoggingSource(source_log))
        terminator.addCallback(task_log.append)
        d = Deferred()
        consumer.taskStarted(lambda: d)
        consumer.taskStarted(self._neverEndingTask)
        consumer.taskProductionFailed(None)
        del source_log[:]
        d.callback(None)
        self.assertEqual([], task_log)
        self.assertEqual([('start', consumer)], source_log)
