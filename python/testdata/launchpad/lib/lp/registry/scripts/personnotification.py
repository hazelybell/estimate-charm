# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person notification script utilities."""

__all__ = [
    'PersonNotificationManager',
    ]


from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility

from lp.registry.interfaces.personnotification import IPersonNotificationSet
from lp.services.config import config


class PersonNotificationManager:

    def __init__(self, txn, logger):
        """Initialize the manager with a transaction manager and logger."""
        self.txn = txn
        self.logger = logger

    def sendNotifications(self):
        """Send notifications to users."""
        notifications_sent = False
        unsent_notifications = []
        notification_set = getUtility(IPersonNotificationSet)
        pending_notifications = notification_set.getNotificationsToSend()
        self.logger.info(
            '%d notification(s) to send.' % pending_notifications.count())
        for notification in pending_notifications:
            person = notification.person
            if not notification.can_send:
                unsent_notifications.append(notification)
                self.logger.info(
                    "%s has no email address." % person.name)
                continue
            self.logger.info("Notifying %s." % person.name)
            notification.send(logger=self.logger)
            notifications_sent = True
            # Commit after each email sent, so that we won't re-mail the
            # notifications in case of something going wrong in the middle.
            self.txn.commit()
        if not notifications_sent:
            self.logger.debug("No notifications were sent.")
        if len(unsent_notifications) == 0:
            unsent_notifications = None
        return unsent_notifications

    def purgeNotifications(self, extra_notifications=None):
        """Delete PersonNotifications that are older than the retention limit.

        The limit is set in the configuration:
        person_notification.retained_days

        :param extra_messages: a list of additional notifications to
            purge. These may be messages to users without email addresses.
        """
        retained_days = timedelta(
            days=int(config.person_notification.retained_days))
        time_limit = (datetime.now(pytz.timezone('UTC')) - retained_days)
        notification_set = getUtility(IPersonNotificationSet)
        to_delete = notification_set.getNotificationsOlderThan(time_limit)
        if to_delete.count():
            self.logger.info(
                "Notification retention limit is %s." % retained_days)
            self.logger.info(
                "Deleting %d old notification(s)." % to_delete.count())
            for notification in to_delete:
                notification.destroySelf()
            self.txn.commit()
        if extra_notifications is not None:
            for notification in extra_notifications:
                notification.destroySelf()
                self.txn.commit()
