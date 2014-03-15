# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for notification strings of duplicate Bugs."""

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
import transaction
from zope.component import getUtility
from zope.event import notify
from zope.interface import providedBy

from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.services.mail import stub
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestAssignmentNotification(TestCaseWithFactory):
    """Test emails sent when a bug is a duplicate of another."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Run the tests as a logged-in user.
        super(TestAssignmentNotification, self).setUp(
            user='test@canonical.com')
        self.user = getUtility(ILaunchBag).user
        self.product = self.factory.makeProduct(owner=self.user,
                                                name='project')
        self.master_bug = self.factory.makeBug(target=self.product)
        self.dup_bug = self.factory.makeBug(target=self.product)
        self.master_bug_task = self.master_bug.getBugTask(self.product)
        self.master_bug_task_before_modification = Snapshot(
            self.master_bug_task,
            providing=providedBy(self.master_bug_task))
        self.person_subscribed_email = 'person@example.com'
        self.person_subscribed = self.factory.makePerson(
            name='subscribed', displayname='Person',
            email=self.person_subscribed_email)
        self.dup_bug.subscribe(
            self.person_subscribed, subscribed_by=self.user)
        self.dup_bug.markAsDuplicate(self.master_bug)

    def test_dup_subscriber_change_notification_message(self):
        """Duplicate bug number in the reason (email footer) for
           duplicate subscribers when a master bug is modified."""
        self.assertEqual(len(stub.test_emails), 0, 'emails in queue')
        self.master_bug_task.transitionToStatus(
            BugTaskStatus.CONFIRMED, self.user)
        notify(ObjectModifiedEvent(
            self.master_bug_task, self.master_bug_task_before_modification,
            ['status'], user=self.user))
        transaction.commit()
        self.assertEqual(len(stub.test_emails), 2, 'email not sent')
        rationale = 'duplicate bug report (%i)' % self.dup_bug.id
        msg = stub.test_emails[-1][2]
        self.assertIn(rationale, msg)
