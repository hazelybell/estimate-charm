# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug notifications."""

__metaclass__ = type
__all__ = [
    'IBugNotification',
    'IBugNotificationFilter',
    'IBugNotificationRecipient',
    'IBugNotificationSet',
    ]

from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    TextLine,
    )

from lp import _
from lp.bugs.enums import BugNotificationStatus
from lp.bugs.interfaces.bugsubscriptionfilter import IBugSubscriptionFilter
from lp.registry.interfaces.role import IHasOwner
from lp.services.fields import BugField


class IBugNotification(IHasOwner):
    """A textual representation of bug changes."""

    id = Attribute('id')
    message = Attribute(
        "The message containing the text representation of the changes"
        " to the bug.")
    activity = Attribute(
        "The bug activity object corresponding to this notification.  Will "
        "be None for older notification objects, and will be None if the "
        "bugchange object that provides the data for the change returns None "
        "for getBugActivity.")
    bug = BugField(title=u"The bug this notification is for.",
                   required=True)
    is_comment = Bool(
        title=u"Comment", description=u"Is the message a comment?",
        required=True)
    date_emailed = Datetime(
        title=u"Date emailed",
        description=u"When was the notification sent? None, if it hasn't"
                     " been sent yet.",
        required=False)
    recipients = Attribute(
        "The people to which this notification should be sent.")
    status = Choice(
            title=_("Status"), required=True,
            vocabulary=BugNotificationStatus,
            default=BugNotificationStatus.PENDING,
            description=_(
                "The status of this bug notification."),
            )
    bug_filters = Attribute(
        "List of bug filters that caused this notification.")


class IBugNotificationSet(Interface):
    """The set of bug notifications."""

    def getNotificationsToSend():
        """Returns the notifications pending to be sent."""

    def getDeferredNotifications():
        """Returns the deferred notifications.

        A deferred noticiation is one that is pending but has no recipients.
        """

    def addNotification(self, bug, is_comment, message, recipients, activity):
        """Create a new `BugNotification`.

        Create a new `BugNotification` object and the corresponding
        `BugNotificationRecipient` objects.
        """

    def getRecipientFilterData(bug, recipient_to_sources, notifications):
        """Get non-muted recipients mapped to sources & filter descriptions.

        :param bug:
            A bug we are collecting filter data for.
        :param recipient_to_sources:
            A dict of people who are to receive the email to the sources
            (BugNotificationRecipients) that represent the subscriptions that
            caused the notifications to be sent.
        :param notifications: the notifications that are being communicated.

        The dict of recipients may have fewer recipients than were
        provided if those users muted all of the subscription filters
        that caused them to be sent.
        """


class IBugNotificationRecipient(Interface):
    """A recipient of a bug notification."""

    bug_notification = Attribute(
        "The bug notification this recipient should receive.")
    person = Attribute(
        "The person to send the bug notification to.")
    reason_header = TextLine(
        title=_('Reason header'),
        description=_("The value for the "
                      "`X-Launchpad-Message-Rationale` header."))
    reason_body = TextLine(
        title=_('Reason body'),
        description=_("The reason for this notification."))


class IBugNotificationFilter(Interface):
    """`BugSubscriptionFilter` that generated a bug notification."""

    bug_notification = Reference(
        IBugNotification,
        title=_("Bug notification"),
        required=True, readonly=True)

    bug_subscription_filter = Reference(
        IBugSubscriptionFilter,
        title=_("Bug subscription filter"),
        required=True, readonly=True)
