# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Code for the BugWatch scheduler."""

__metaclass__ = type
__all__ = [
    'BugWatchScheduler',
    'MAX_SAMPLE_SIZE',
    ]

import transaction

from lp.bugs.interfaces.bugwatch import BUG_WATCH_ACTIVITY_SUCCESS_STATUSES
from lp.bugs.model.bugwatch import BugWatch
from lp.services.database.interfaces import IMasterStore
from lp.services.database.sqlbase import sqlvalues
from lp.services.looptuner import TunableLoop

# The maximum additional delay in days that a watch may have placed upon
# it.
MAX_DELAY_DAYS = 6
# The maximum number of BugWatchActivity entries we want to examine.
MAX_SAMPLE_SIZE = 5


def get_delay_coefficient(max_delay_days, max_sample_size):
    return float(max_delay_days) / float(max_sample_size)


class BugWatchScheduler(TunableLoop):
    """An `ITunableLoop` for scheduling BugWatches."""

    maximum_chunk_size = 1000

    def __init__(self, log, abort_time=None, max_delay_days=None,
                 max_sample_size=None):
        super(BugWatchScheduler, self).__init__(log, abort_time)
        self.transaction = transaction
        self.store = IMasterStore(BugWatch)

        if max_delay_days is None:
            max_delay_days = MAX_DELAY_DAYS
        if max_sample_size is None:
            max_sample_size = MAX_SAMPLE_SIZE
        self.max_sample_size = max_sample_size

        self.delay_coefficient = get_delay_coefficient(
            max_delay_days, max_sample_size)

    def __call__(self, chunk_size):
        """Run the loop."""
        # XXX 2010-03-25 gmb bug=198767:
        #     We cast chunk_size to an integer to ensure that we're not
        #     trying to slice using floats or anything similarly
        #     foolish. We shouldn't have to do this.
        chunk_size = int(chunk_size)
        query = """
        UPDATE BugWatch
            SET next_check =
                COALESCE(
                    lastchecked + interval '1 day',
                    now() AT TIME ZONE 'UTC') +
                (interval '1 day' * (%s * recent_failure_count))
            FROM (
                SELECT bug_watch.id,
                    (SELECT COUNT(*)
                        FROM (SELECT 1
                            FROM bugwatchactivity
                           WHERE bugwatchactivity.bug_watch = bug_watch.id
                             AND bugwatchactivity.result NOT IN (%s)
                           ORDER BY bugwatchactivity.id DESC
                           LIMIT %s) AS recent_failures
                    ) AS recent_failure_count
                FROM BugWatch AS bug_watch
                WHERE bug_watch.next_check IS NULL
                LIMIT %s
            ) AS counts
        WHERE BugWatch.id = counts.id
        """ % sqlvalues(
            self.delay_coefficient, BUG_WATCH_ACTIVITY_SUCCESS_STATUSES,
            self.max_sample_size, chunk_size)
        self.transaction.begin()
        result = self.store.execute(query)
        self.log.debug("Scheduled %s watches" % result.rowcount)
        self.transaction.commit()

    def isDone(self):
        """Return True when there are no more watches to schedule."""
        return self.store.find(
            BugWatch, BugWatch.next_check == None).is_empty()
