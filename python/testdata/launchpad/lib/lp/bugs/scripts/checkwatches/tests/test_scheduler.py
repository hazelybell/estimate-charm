# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XXX: Module docstring goes here."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from pytz import utc
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.bugs.interfaces.bugwatch import (
    BugWatchActivityStatus,
    IBugWatchSet,
    )
from lp.bugs.scripts.checkwatches.scheduler import BugWatchScheduler
from lp.services.log.logger import BufferLogger
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugWatchScheduler(TestCaseWithFactory):
    """Tests for the BugWatchScheduler, which runs as part of garbo."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugWatchScheduler, self).setUp('foo.bar@canonical.com')
        # We'll make sure that all the other bug watches look like
        # they've been scheduled so that only our watch gets scheduled.
        for watch in getUtility(IBugWatchSet).search():
            removeSecurityProxy(watch).next_check = datetime.now(utc)
        self.bug_watch = removeSecurityProxy(self.factory.makeBugWatch())
        self.scheduler = BugWatchScheduler(BufferLogger())
        transaction.commit()

    def test_scheduler_schedules_unchecked_watches(self):
        # The BugWatchScheduler will schedule a BugWatch that has never
        # been checked to be checked immediately.
        self.bug_watch.next_check = None
        self.scheduler(1)

        self.assertNotEqual(None, self.bug_watch.next_check)
        self.assertTrue(
            self.bug_watch.next_check <= datetime.now(utc))

    def test_scheduler_schedules_working_watches(self):
        # If a watch has been checked and has never failed its next
        # check will be scheduled for 24 hours after its last check.
        now = datetime.now(utc)
        # Add some succesful activity to ensure that successful activity
        # is handled correctly.
        self.bug_watch.addActivity()
        self.bug_watch.lastchecked = now
        self.bug_watch.next_check = None
        transaction.commit()
        self.scheduler(1)

        self.assertEqual(
            now + timedelta(hours=24), self.bug_watch.next_check)

    def test_scheduler_schedules_failing_watches(self):
        # If a watch has failed once, it will be scheduled more than 24
        # hours after its last check.
        now = datetime.now(utc)
        self.bug_watch.lastchecked = now

        # The delay depends on the number of failures that the watch has
        # had.
        for failure_count in range(1, 6):
            self.bug_watch.next_check = None
            self.bug_watch.addActivity(
                result=BugWatchActivityStatus.BUG_NOT_FOUND)
            transaction.commit()
            self.scheduler(1)

            coefficient = self.scheduler.delay_coefficient * failure_count
            self.assertEqual(
                now + timedelta(days=1 + coefficient),
                self.bug_watch.next_check)

        # The scheduler only looks at the last 5 activity items, so even
        # if there have been more failures the maximum delay will be 7
        # days.
        for count in range(10):
            self.bug_watch.addActivity(
                result=BugWatchActivityStatus.BUG_NOT_FOUND)
        self.bug_watch.next_check = None
        transaction.commit()
        self.scheduler(1)
        self.assertEqual(
            now + timedelta(days=7), self.bug_watch.next_check)

    def test_scheduler_doesnt_schedule_scheduled_watches(self):
        # The scheduler will ignore watches whose next_check has been
        # set.
        next_check_date = datetime.now(utc) + timedelta(days=1)
        self.bug_watch.next_check = next_check_date
        transaction.commit()
        self.scheduler(1)

        self.assertEqual(next_check_date, self.bug_watch.next_check)
