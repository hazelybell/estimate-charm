#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Send bug notifications.

This script sends out all the pending bug notifications, and sets
date_emailed to the current date.
"""

__metaclass__ = type

import _pythonpath

from zope.component import getUtility

from lp.bugs.enums import BugNotificationStatus
from lp.bugs.interfaces.bugnotification import IBugNotificationSet
from lp.bugs.scripts.bugnotification import (
    get_email_notifications,
    process_deferred_notifications,
    )
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.mail.sendmail import sendmail
from lp.services.scripts.base import LaunchpadCronScript


class SendBugNotifications(LaunchpadCronScript):
    def main(self):
        notifications_sent = False
        bug_notification_set = getUtility(IBugNotificationSet)
        deferred_notifications = \
            bug_notification_set.getDeferredNotifications()
        process_deferred_notifications(deferred_notifications)
        pending_notifications = get_email_notifications(
            bug_notification_set.getNotificationsToSend())
        for (bug_notifications,
             omitted_notifications,
             messages) in pending_notifications:
            for message in messages:
                self.logger.info("Notifying %s about bug %d." % (
                    message['To'], bug_notifications[0].bug.id))
                sendmail(message)
                self.logger.debug(message.as_string())
            for notification in bug_notifications:
                notification.date_emailed = UTC_NOW
                notification.status = BugNotificationStatus.SENT
            for notification in omitted_notifications:
                notification.date_emailed = UTC_NOW
                notification.status = BugNotificationStatus.OMITTED
            notifications_sent = True
            # Commit after each batch of email sent, so that we won't
            # re-mail the notifications in case of something going wrong
            # in the middle.
            self.txn.commit()

        if not notifications_sent:
            self.logger.debug("No notifications are pending to be sent.")


if __name__ == '__main__':
    script = SendBugNotifications('send-bug-notifications',
        dbuser=config.malone.bugnotification_dbuser)
    script.lock_and_run()
