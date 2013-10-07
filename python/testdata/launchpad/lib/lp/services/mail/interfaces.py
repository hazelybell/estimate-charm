# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces specific to mail handling."""

__metaclass__ = type
__all__ = [
    'BugTargetNotFound',
    'EmailProcessingError',
    'IBugEditEmailCommand',
    'IBugEmailCommand',
    'IBugTaskEditEmailCommand',
    'IBugTaskEmailCommand',
    'IEmailCommand',
    'IMailHandler',
    'INotificationRecipientSet',
    'ISignedMessage',
    'IWeaklyAuthenticatedPrincipal',
    'UnknownRecipientError',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    ASCII,
    Bool,
    )

from lp import _


class IWeaklyAuthenticatedPrincipal(Interface):
    """The principal has been weakly authenticated.

    At the moment it means that the user was authenticated simply by
    looking at the From address in an email.
    """


class ISignedMessage(Interface):
    """A message that's possibly signed with an OpenPGP key.

    If the message wasn't signed, all attributes will be None.
    """

    def __getitem__(name):
        """Returns the message header with the given name."""

    signedMessage = Attribute("The part that was signed, represented "
                              "as an email.Message.")

    signedContent = ASCII(title=_("Signed Content"),
                          description=_("The text that was signed."))

    signature = ASCII(title=_("Signature"),
                      description=_("The OpenPGP signature used to sign "
                                    "the message."))

    parsed_string = Attribute(
        "The string that was parsed to create the SignedMessage.")


class IMailHandler(Interface):
    """Handles incoming mail sent to a specific email domain.

    For example, in email address '1@bugs.launchpad.ubuntu.com',
    'bugs.launchpad.ubuntu.com' is the email domain.

    The handler should be registered as a named utility, with the domain
    it handles as the name.
    """

    allow_unknown_users = Bool(
        title=u"Allow unknown users",
        description=u"The handler can handle emails from persons not"
                    " registered in Launchpad (which will result in an"
                    " anonymous interaction being set up.")

    def process(signed_msg, to_address, filealias, log=None):
        """Processes a ISignedMessage

        The 'to_address' is the address the mail was sent to.
        The 'filealias' is an ILibraryFileAlias.
        The 'log' is the logger to be used.

        Return False if to_address does not exist/is bad.
        Return True if the mesage was processed, successfully or
        unsuccessfully.  This includes user or input errors.
        Programming errors should cause exceptions to be raised.
        """


class EmailProcessingError(Exception):
    """Something went wrong while processing an email command."""

    def __init__(self, args, stop_processing=False):
        """Initialize

        :args: The standard exception extra arguments.
        "stop_processing: Should the processing of the email be stopped?
        """
        Exception.__init__(self, args)
        self.stop_processing = stop_processing


class UnknownRecipientError(KeyError):
    """Error raised when an email or person isn't part of the recipient set.
    """


class INotificationRecipientSet(Interface):
    """Represents a set of notification recipients and rationales.

    All Launchpad emails should include a footer explaining why the user
    is receiving the email. An INotificationRecipientSet encapsulates a
    list of recipients along the rationale for being on the recipients list.

    The pattern for using this are as follows: email addresses in an
    INotificationRecipientSet are being notified because of a specific
    event (for instance, because a bug changed). The rationales describe
    why that email addresses is included in the recipient list,
    detailing subscription types, membership in teams and/or other
    possible reasons.

    The set maintains the list of `IPerson` that will be contacted as well
    as the email address to use to contact them.
    """

    def getEmails():
        """Return all email addresses registered, sorted alphabetically."""

    def getRecipients():
        """Return the set of person who will be notified.

        :return: An iterator of `IPerson`, sorted by display name.
        """

    def getRecipientPersons():
        """Return the set of individual Persons who will be notified.

        :return: An iterator of (`email_address`, `IPerson`), unsorted.
        """

    def __iter__():
        """Return an iterator of the recipients."""

    def __contains__(person_or_email):
        """Is person_or_email in the notification recipients list?

        Return true if person or email is in the notification recipients list.
        """

    def __nonzero__():
        """Return False when the set is empty, True when it's not."""

    def getReason(person_or_email):
        """Return a reason tuple containing (text, header) for an address.

        The text is meant to appear in the notification footer. The header
        should be a short code that will appear in an
        X-Launchpad-Message-Rationale header for automatic filtering.

        :param person_or_email: An `IPerson` or email address that is in the
            recipients list.

        :raises UnknownRecipientError: if the person or email isn't in the
            recipients list.
        """

    def add(person, reason, header):
        """Add a person or a sequence of persons to the recipients list.

        When the added person is a team without an email address, all its
        members emails will be added. If the person is already in the
        recipients list, the reson for contacting him is not changed.

        :param person: The `IPerson` or a sequence of `IPerson`
            that will be notified.
        :param reason: The rationale message that should appear in the
            notification footer.
        :param header: The code that will appear in the
            X-Launchpad-Message-Rationale header.
        """

    def remove(person):
        """Remove a person or a list of persons from the recipients list.

        :param person: The `IPerson` or a sequence of `IPerson`
            that will removed from the recipients list.
        """

    def update(recipient_set):
        """Updates this instance's reasons with reasons from another set.

        The rationale for recipient already in this set will not be updated.

        :param recipient_set: An `INotificationRecipientSet`.
        """


class BugTargetNotFound(Exception):
    """A bug target couldn't be found."""


class IEmailCommand(Interface):
    """An email command.

    Email commands can be embedded in mails sent to Launchpad. For
    example in comments to bugs sent via email, you can include:

      private yes

    in order to make the bug private.
    """

    def execute(context):
        """Execute the command in a context."""

    def setAttributeValue(context, attr_name, attr_value):
        """Set the value of the attribute.

        Subclasses may want to override this if, for example, the
        attribute is set through a special method instead of a normal
        attribute.
        """

    def __str__():
        """Return a textual representation of the command and its arguments.
        """


class IBugEmailCommand(IEmailCommand):
    """An email command specific to getting or creating a bug."""

    RANK = Attribute(
        "The int used to determine the order of execution of many commands.")

    def execute(parsed_msg, filealias):
        """Either create or get an exiting bug.

        If a bug is created, parsed_msg and filealias will be used to
        create the initial comment of the bug.

        The bug and an event is returned as a two-tuple.
        """


class IBugTaskEmailCommand(IEmailCommand):
    """An email command specific to getting or creating a bug task."""

    RANK = Attribute(
        "The int used to determine the order of execution of many commands.")

    def execute(bug):
        """Either create or get an exiting bug task.

        The bug task and an event is returned as a two-tuple.
        """


class IBugEditEmailCommand(IEmailCommand):
    """An email command specific to editing a bug."""

    RANK = Attribute(
        "The int used to determine the order of execution of many commands.")

    def execute(bug, current_event):
        """Execute the command in the context of the bug.

        The modified bug and an event is returned.
        """


class IBugTaskEditEmailCommand(IEmailCommand):
    """An email command specific to editing a bug task."""

    RANK = Attribute(
        "The int used to determine the order of execution of many commands.")

    def execute(bugtask, current_event):
        """Execute the command in the context of the bug task.

        The modified bug task and an event is returned.
        """
