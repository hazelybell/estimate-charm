# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DBLoopTuner',
    'ITunableLoop',
    'LoopTuner',
    'TunableLoop',
    ]


from datetime import timedelta
import sys
import time

import transaction
from zope.interface import (
    implements,
    Interface,
    )

from lp.services.database.interfaces import IMasterStore
import lp.services.scripts


class ITunableLoop(Interface):
    """Interface for self-tuning loop bodies to be driven by LoopTuner.

    To construct a self-tuning batched loop, define your loop body as a class
    implementing TunableLoop, and pass an instance to your LoopTuner.
    """
    def isDone():
        """Is this loop finished?

        Once this returns True, the LoopTuner will no longer touch this
        object.
        """

    def __call__(chunk_size):
        """Perform an iteration of the loop.

        The chunk_size parameter says (in some way you define) how much work
        the LoopTuner believes you should try to do in this iteration in order
        to get as close as possible to your time goal.

        Note that chunk_size is a float, so, for example, if you use it to
        slice a list, be careful to round it to an int first.
        """

    def cleanUp(self):
        """Clean up any open resources.

        Optional.

        This method is needed because loops may be aborted before
        completion, so clean up code in the isDone() method may
        never be invoked.
        """


class LoopTuner:
    """A loop that tunes itself to approximate an ideal time per iteration.

    Use this for large processing jobs that need to be broken down into chunks
    of such size that processing a single chunk takes approximately a given
    ideal time.  For example, large database operations may have to be
    performed and committed in a large number of small steps in order to avoid
    locking out other clients that need to access the same data.  Regular
    commits allow other clients to get their work done.

    In such a situation, committing for every step is often far too costly.
    Imagine inserting a million rows and committing after every row!  You
    could hand-pick a static number of steps per commit, but that takes a lot
    of experimental guesswork and it will still waste time when things go
    well, and on the other hand, it will still end up taking too much time per
    batch when the system slows down for whatever reason.

    Instead, define your loop body in an ITunableLoop; parameterize it on the
    number of steps per batch; say how much time you'd like to spend per
    batch; and pass it to a LoopTuner.  The LoopTuner will execute your loop,
    dynamically tuning its batch-size parameter to stay close to your time
    goal.  If things go faster than expected, it will ask your loop body to do
    more work for the next batch.  If a batch takes too much time, the next
    batch will be smaller.  There is also some cushioning for one-off spikes
    and troughs in processing speed.
    """

    def __init__(
        self, operation, goal_seconds,
        minimum_chunk_size=1, maximum_chunk_size=1000000000,
        abort_time=None, cooldown_time=None, log=None):
        """Initialize a loop, to be run to completion at most once.

        Parameters:

        operation: an object implementing the loop body.  It must support the
            ITunableLoop interface.

        goal_seconds: the ideal number of seconds for any one iteration to
            take.  The algorithm will vary chunk size in order to stick close
            to this ideal.

        minimum_chunk_size: the smallest chunk size that is reasonable.  The
            tuning algorithm will never let chunk size sink below this value.

        maximum_chunk_size: the largest allowable chunk size.  A maximum is
            needed even if the ITunableLoop ignores chunk size for whatever
            reason, since reaching floating-point infinity would seriously
            break the algorithm's arithmetic.

        cooldown_time: time (in seconds, float) to sleep between consecutive
            operation runs.  Defaults to None for no sleep.

        abort_time: abort the loop, logging a WARNING message, if the runtime
            takes longer than this many seconds.

        log: The log object to use. DEBUG level messages are logged
            giving iteration statistics.
        """
        assert(ITunableLoop.providedBy(operation))
        self.operation = operation
        self.goal_seconds = float(goal_seconds)
        self.minimum_chunk_size = minimum_chunk_size
        self.maximum_chunk_size = maximum_chunk_size
        self.cooldown_time = cooldown_time
        self.abort_time = abort_time
        if log is None:
            self.log = lp.services.scripts.log
        else:
            self.log = log

    # True if this task has timed out. Set by _isTimedOut().
    _has_timed_out = False

    def _isTimedOut(self, extra_seconds=0):
        """Return True if the task will be timed out in extra_seconds.

        If this method returns True, all future calls will also return
        True.
        """
        if self.abort_time is None:
            return False
        if self._has_timed_out:
            return True
        if self._time() + extra_seconds >= self.start_time + self.abort_time:
            self._has_timed_out = True
            return True
        return False

    def run(self):
        """Run the loop to completion."""
        # Cleanup function, if we have one.
        cleanup = getattr(self.operation, 'cleanUp', lambda: None)
        try:
            chunk_size = self.minimum_chunk_size
            iteration = 0
            total_size = 0
            self.start_time = self._time()
            last_clock = self.start_time
            while not self.operation.isDone():

                if self._isTimedOut():
                    self.log.info(
                        "Task aborted after %d seconds.", self.abort_time)
                    break

                self.operation(chunk_size)

                new_clock = self._time()
                time_taken = new_clock - last_clock
                last_clock = new_clock

                self.log.debug2(
                    "Iteration %d (size %.1f): %.3f seconds",
                    iteration, chunk_size, time_taken)

                last_clock = self._coolDown(last_clock)

                total_size += chunk_size

                # Adjust parameter value to approximate goal_seconds.
                # The new value is the average of two numbers: the
                # previous value, and an estimate of how many rows would
                # take us to exactly goal_seconds seconds. The weight in
                # this estimate of any given historic measurement decays
                # exponentially with an exponent of 1/2. This softens
                # the blows from spikes and dips in processing time. Set
                # a reasonable minimum for time_taken, just in case we
                # get weird values for whatever reason and destabilize
                # the algorithm.
                time_taken = max(self.goal_seconds / 10, time_taken)
                chunk_size *= (1 + self.goal_seconds / time_taken) / 2
                chunk_size = max(chunk_size, self.minimum_chunk_size)
                chunk_size = min(chunk_size, self.maximum_chunk_size)
                iteration += 1

            total_time = last_clock - self.start_time
            average_size = total_size / max(1, iteration)
            average_speed = total_size / max(1, total_time)
            self.log.debug2(
                "Done. %d items in %d iterations, %3f seconds, "
                "average size %f (%s/s)",
                total_size, iteration, total_time, average_size,
                average_speed)
        except Exception:
            exc_info = sys.exc_info()
            try:
                cleanup()
            except Exception:
                # We need to raise the original exception, but we don't
                # want to lose the information about the cleanup
                # failure, so log it.
                self.log.exception("Unhandled exception in cleanUp")
            # Reraise the original exception.
            raise exc_info[0], exc_info[1], exc_info[2]
        else:
            cleanup()

    def _coolDown(self, bedtime):
        """Sleep for `self.cooldown_time` seconds, if set.

        Assumes that anything the main LoopTuner loop does apart from
        doing a chunk of work or sleeping takes zero time.

        :param bedtime: Time the cooldown started, i.e. the time the
        chunk of real work was completed.
        :return: Time when cooldown completed, i.e. the starting time
        for a next chunk of work.
        """
        if self.cooldown_time is None or self.cooldown_time <= 0.0:
            return bedtime
        else:
            self._sleep(self.cooldown_time)
            return self._time()

    def _time(self):
        """Monotonic system timer with unit of 1 second.

        Overridable so tests can fake processing speeds accurately and without
        actually waiting.
        """
        return time.time()

    def _sleep(self, seconds):
        """Sleep.

        If the sleep interval would put us over the tasks timeout,
        do nothing.
        """
        if not self._isTimedOut(seconds):
            time.sleep(seconds)


class DBLoopTuner(LoopTuner):
    """A LoopTuner that plays well with PostgreSQL and replication.

    This LoopTuner blocks when database replication is lagging.
    Making updates faster than replication can deal with them is
    counter productive and in extreme cases can put the database
    into a death spiral. So we don't do that.

    This LoopTuner also blocks when there are long running
    transactions. Vacuuming is ineffective when there are long
    running transactions. We block when long running transactions
    have been detected, as it means we have already been bloating
    the database for some time and we shouldn't make it worse. Once
    the long running transactions have completed, we know the dead
    space we have already caused can be cleaned up so we can keep
    going.

    INFO level messages are logged when the DBLoopTuner blocks in addition
    to the DEBUG level messages emitted by the standard LoopTuner.
    """

    # We block until replication lag is under this threshold.
    acceptable_replication_lag = timedelta(seconds=30)  # In seconds.

    # We block if there are transactions running longer than this threshold.
    long_running_transaction = 30 * 60  # In seconds.

    def _blockWhenLagged(self):
        """When database replication lag is high, block until it drops."""
        # Lag is most meaningful on the master.
        from lp.services.librarian.model import LibraryFileAlias
        store = IMasterStore(LibraryFileAlias)
        msg_counter = 0
        while not self._isTimedOut():
            lag = store.execute("SELECT replication_lag()").get_one()[0]
            if lag is None or lag <= self.acceptable_replication_lag:
                return

            # Report just once every 10 minutes to avoid log spam.
            msg_counter += 1
            if msg_counter % 60 == 1:
                self.log.info(
                    "Database replication lagged %s. "
                    "Sleeping up to 10 minutes.", lag)

            # Don't become a long running transaction!
            transaction.abort()
            self._sleep(10)

    def _blockForLongRunningTransactions(self):
        """If there are long running transactions, block to avoid making
        bloat worse."""
        if self.long_running_transaction is None:
            return
        from lp.services.librarian.model import LibraryFileAlias
        store = IMasterStore(LibraryFileAlias)
        msg_counter = 0
        while not self._isTimedOut():
            results = list(store.execute("""
                SELECT
                    CURRENT_TIMESTAMP - xact_start,
                    procpid,
                    usename,
                    datname,
                    current_query
                FROM activity()
                WHERE xact_start < CURRENT_TIMESTAMP - interval '%f seconds'
                    AND datname = current_database()
                ORDER BY xact_start LIMIT 4
                """ % self.long_running_transaction).get_all())
            if not results:
                break

            # Check for long running transactions every 10 seconds, but
            # only report every 10 minutes to avoid log spam.
            msg_counter += 1
            if msg_counter % 60 == 1:
                for runtime, procpid, usename, datname, query in results:
                    self.log.info(
                        "Blocked on %s old xact %s@%s/%d - %s.",
                        runtime, usename, datname, procpid, query)
                self.log.info("Sleeping for up to 10 minutes.")
            # Don't become a long running transaction!
            transaction.abort()
            self._sleep(10)

    def _coolDown(self, bedtime):
        """As per LoopTuner._coolDown, except we always wait until there
        is no replication lag.
        """
        self._blockForLongRunningTransactions()
        self._blockWhenLagged()
        if self.cooldown_time is not None and self.cooldown_time > 0.0:
            remaining_nap = self._time() - bedtime + self.cooldown_time
            if remaining_nap > 0.0:
                self._sleep(remaining_nap)
        return self._time()


class TunableLoop:
    """A base implementation of `ITunableLoop`."""
    implements(ITunableLoop)

    # DBLoopTuner blocks on replication lag and long transactions. If a
    # subclass wants to ignore them, it can override this to be a normal
    # LoopTuner.
    tuner_class = DBLoopTuner

    goal_seconds = 2
    minimum_chunk_size = 1
    maximum_chunk_size = None  # Override.
    cooldown_time = 0

    def __init__(self, log, abort_time=None):
        self.log = log
        self.abort_time = abort_time

    def isDone(self):
        """Return True when the TunableLoop is complete."""
        raise NotImplementedError(self.isDone)

    def run(self):
        assert self.maximum_chunk_size is not None, (
            "Did not override maximum_chunk_size.")
        self.tuner_class(
            self, self.goal_seconds,
            minimum_chunk_size=self.minimum_chunk_size,
            maximum_chunk_size=self.maximum_chunk_size,
            cooldown_time=self.cooldown_time,
            abort_time=self.abort_time,
            log=self.log).run()
