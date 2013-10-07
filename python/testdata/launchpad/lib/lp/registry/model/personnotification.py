# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person notifications."""

__metaclass__ = type
__all__ = [
    'PersonNotification',
    'PersonNotificationSet',
    ]

from datetime import datetime

import pytz
from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.registry.interfaces.personnotification import (
    IPersonNotification,
    IPersonNotificationSet,
    )
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.mail.sendmail import (
    format_address,
    simple_sendmail,
    )
from lp.services.propertycache import cachedproperty


class PersonNotification(SQLBase):
    """See `IPersonNotification`."""
    implements(IPersonNotification)

    person = ForeignKey(dbName='person', notNull=True, foreignKey='Person')
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_emailed = UtcDateTimeCol(notNull=False)
    body = StringCol(notNull=True)
    subject = StringCol(notNull=True)

    @cachedproperty
    def to_addresses(self):
        """See `IPersonNotification`."""
        if self.person.is_team:
            return self.person.getTeamAdminsEmailAddresses()
        elif self.person.preferredemail is None:
            return []
        else:
            return [format_address(
                self.person.displayname, self.person.preferredemail.email)]

    @property
    def can_send(self):
        """See `IPersonNotification`."""
        return len(self.to_addresses) > 0

    def send(self, logger=None):
        """See `IPersonNotification`."""
        if not self.can_send:
            raise AssertionError(
                "Can't send a notification to a person without an email.")
        to_addresses = self.to_addresses
        if logger:
            logger.info("Sending notification to %r." % to_addresses)
        from_addr = config.canonical.bounce_address
        simple_sendmail(from_addr, to_addresses, self.subject, self.body)
        self.date_emailed = datetime.now(pytz.timezone('UTC'))


class PersonNotificationSet:
    """See `IPersonNotificationSet`."""
    implements(IPersonNotificationSet)

    def getNotificationsToSend(self):
        """See `IPersonNotificationSet`."""
        return PersonNotification.selectBy(
            date_emailed=None, orderBy=['date_created,id'])

    def addNotification(self, person, subject, body):
        """See `IPersonNotificationSet`."""
        return PersonNotification(person=person, subject=subject, body=body)

    def getNotificationsOlderThan(self, time_limit):
        """See `IPersonNotificationSet`."""
        return PersonNotification.select(
            'date_created < %s' % sqlvalues(time_limit))
