# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for emails sent after bug task deletion."""

import transaction
from zope.component import getUtility

from lp.bugs.model.bugnotification import BugNotification
from lp.bugs.scripts.bugnotification import construct_email_notifications
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestDeletionNotification(TestCaseWithFactory):
    """Test email notifications when a bug task is deleted."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Run the tests as a logged-in user.
        super(TestDeletionNotification, self).setUp(
            user='test@canonical.com')
        self.user = getUtility(ILaunchBag).user
        product = self.factory.makeProduct(owner=self.user)
        self.bug_task = self.factory.makeBugTask(target=product)

    def test_for_bug_modifier_header(self):
        """Test X-Launchpad-Bug-Modifier appears when a bugtask is deleted."""
        self.bug_task.delete(self.user)
        transaction.commit()
        latest_notification = BugNotification.selectFirst(orderBy='-id')
        notifications, omitted, messages = construct_email_notifications(
            [latest_notification])
        self.assertEqual(len(notifications), 1,
                         'email notification not created')
        headers = [msg['X-Launchpad-Bug-Modifier'] for msg in messages]
        self.assertEqual(len(headers), len(messages))
