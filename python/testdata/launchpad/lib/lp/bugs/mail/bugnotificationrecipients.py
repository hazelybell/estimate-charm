# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code for handling bug notification recipients in bug mail."""

__metaclass__ = type
__all__ = [
    'BugNotificationRecipients',
    ]

from zope.interface import implements

from lp.services.mail.interfaces import INotificationRecipientSet
from lp.services.mail.notificationrecipientset import NotificationRecipientSet


class BugNotificationRecipients(NotificationRecipientSet):
    """A set of emails and rationales notified for a bug change.

    Each email address registered in a BugNotificationRecipients is
    associated to a string and a header that explain why the address is
    being emailed. For instance, if the email address is that of a
    distribution bug supervisor for a bug, the string and header will make
    that fact clear.

    The string is meant to be rendered in the email footer. The header
    is meant to be used in an X-Launchpad-Message-Rationale header.

    The first rationale registered for an email address is the one
    which will be used, regardless of other rationales being added
    for it later. This gives us a predictable policy of preserving
    the first reason added to the registry; the callsite should
    ensure that the manipulation of the BugNotificationRecipients
    instance is done in preferential order.

    Instances of this class are meant to be returned by
    IBug.getBugNotificationRecipients().
    """
    implements(INotificationRecipientSet)

    def __init__(self, duplicateof=None):
        """Constructs a new BugNotificationRecipients instance.

        If this bug is a duplicate, duplicateof should be used to
        specify which bug ID it is a duplicate of.

        Note that there are two duplicate situations that are
        important:
          - One is when this bug is a duplicate of another bug:
            the subscribers to the main bug get notified of our
            changes.
          - Another is when the bug we are changing has
            duplicates; in that case, direct subscribers of
            duplicate bugs get notified of our changes.
        These two situations are catered respectively by the
        duplicateof parameter above and the addDupeSubscriber method.
        Don't confuse them!
        """
        super(BugNotificationRecipients, self).__init__()
        self.duplicateof = duplicateof
        self.subscription_filters = set()

    def _addReason(self, person, reason, header):
        """Adds a reason (text and header) for a person.

        It takes care of modifying the message when the person is notified
        via a duplicate.
        """
        if self.duplicateof is not None:
            reason = reason + " (via bug %s)" % self.duplicateof.id
            header = header + " via Bug %s" % self.duplicateof.id
        reason = "You received this bug notification because you %s." % reason
        self.add(person, reason, header)

    def addDupeSubscriber(self, person, duplicate_bug=None):
        """Registers a subscriber of a duplicate of this bug."""
        reason = "Subscriber of Duplicate"
        if person.is_team:
            text = ("are a member of %s, which is subscribed "
                    "to a duplicate bug report" % person.displayname)
            reason += " @%s" % person.name
        else:
            text = "are subscribed to a\nduplicate bug report"
        if duplicate_bug is not None:
            text += " (%s)" % duplicate_bug.id
        self._addReason(person, text, reason)

    def addDirectSubscriber(self, person):
        """Registers a direct subscriber of this bug."""
        reason = "Subscriber"
        if person.is_team:
            text = ("are a member of %s, which is subscribed "
                    "to the bug report" % person.displayname)
            reason += " @%s" % person.name
        else:
            text = "are subscribed to the bug report"
        self._addReason(person, text, reason)

    def addAssignee(self, person):
        """Registers an assignee of a bugtask of this bug."""
        reason = "Assignee"
        if person.is_team:
            text = ("are a member of %s, which is a bug assignee"
                    % person.displayname)
            reason += " @%s" % person.name
        else:
            text = "are a bug assignee"
        self._addReason(person, text, reason)

    def addStructuralSubscriber(self, person, target):
        """Registers a structural subscriber to this bug's target."""
        reason = "Subscriber (%s)" % target.displayname
        if person.is_team:
            text = ("are a member of %s, which is subscribed to %s" %
                (person.displayname, target.displayname))
            reason += " @%s" % person.name
        else:
            text = "are subscribed to %s" % target.displayname
        self._addReason(person, text, reason)

    def update(self, recipient_set):
        """See `INotificationRecipientSet`."""
        super(BugNotificationRecipients, self).update(recipient_set)
        self.subscription_filters.update(
            recipient_set.subscription_filters)

    def addFilter(self, subscription_filter):
        if subscription_filter is not None:
            self.subscription_filters.add(subscription_filter)
