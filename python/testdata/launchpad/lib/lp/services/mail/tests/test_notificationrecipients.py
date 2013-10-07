# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.registry.interfaces.person import PersonVisibility
from lp.services.mail.notificationrecipientset import NotificationRecipientSet
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestNotificationRecipientSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_add_doesnt_break_on_private_teams(self):
        # Since notifications are not exposed to UI, they should handle
        # protected preferred emails fine.
        email = self.factory.getUniqueEmailAddress()
        notified_team = self.factory.makeTeam(
            email=email, visibility=PersonVisibility.PRIVATE)
        recipients = NotificationRecipientSet()
        notifier = self.factory.makePerson()
        with person_logged_in(notifier):
            recipients.add([notified_team], 'some reason', 'some header')
        with celebrity_logged_in("admin"):
            self.assertEqual([notified_team], recipients.getRecipients())
