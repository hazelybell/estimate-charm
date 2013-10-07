# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person notifications."""

__metaclass__ = type
__all__ = [
    'IPersonNotification',
    'IPersonNotificationSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Datetime,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.person import IPerson


class IPersonNotification(Interface):
    """A textual message about a change in our records about a person."""

    person = Object(
        title=_("The person who will receive this notification."),
        schema=IPerson)
    date_emailed = Datetime(
        title=_("Date emailed"),
        description=_("When was the notification sent? None, if it hasn't"
                      " been sent yet."),
        required=False)
    date_created = Datetime(title=_("Date created"))
    body = Text(title=_("Notification body."))
    subject = TextLine(title=_("Notification subject."))

    can_send = Attribute("Can the notification be sent?")

    to_addresses = Attribute(
        "The list of addresses to send the notification to.")

    def destroySelf():
        """Delete this notification."""

    def send():
        """Send the notification by email."""


class IPersonNotificationSet(Interface):
    """The set of person notifications."""

    def getNotificationsToSend():
        """Return the notifications that haven't been sent yet."""

    def addNotification(person, subject, body):
        """Create a new `IPersonNotification`."""

    def getNotificationsOlderThan(time_limit):
        """Return notifications that are older than the time_limit."""
