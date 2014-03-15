# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for emails sent after bug task modification."""

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
import transaction
from zope.component import getUtility
from zope.event import notify
from zope.interface import providedBy

from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.model.bugnotification import BugNotification
from lp.bugs.scripts.bugnotification import construct_email_notifications
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestModificationNotification(TestCaseWithFactory):
    """Test email notifications when a bug task is modified."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Run the tests as a logged-in user.
        super(TestModificationNotification, self).setUp(
            user='test@canonical.com')
        self.user = getUtility(ILaunchBag).user
        self.product = self.factory.makeProduct(owner=self.user)
        self.bug = self.factory.makeBug(target=self.product)
        self.bug_task = self.bug.getBugTask(self.product)
        self.bug_task_before_modification = Snapshot(self.bug_task,
            providing=providedBy(self.bug_task))

    def test_for_bug_modifier_header(self):
        """Test X-Launchpad-Bug-Modifier appears when a bug is modified."""
        self.bug_task.transitionToStatus(BugTaskStatus.CONFIRMED, self.user)
        notify(ObjectModifiedEvent(
            self.bug_task, self.bug_task_before_modification,
            ['status'], user=self.user))
        transaction.commit()
        latest_notification = BugNotification.selectFirst(orderBy='-id')
        notifications, omitted, messages = construct_email_notifications(
            [latest_notification])
        self.assertEqual(len(notifications), 1,
                         'email notification not created')
        headers = [msg['X-Launchpad-Bug-Modifier'] for msg in messages]
        self.assertEqual(len(headers), len(messages))
