# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DuplicateMessageId',
    'IDirectEmailAuthorization',
    'IIndexedMessage',
    'IMessage',
    'IMessageChunk',
    'IMessageSet',
    'IUserToUserEmail',
    'IndexedMessage',
    'InvalidEmailMessage',
    'MissingSubject',
    'QuotaReachedError',
    'UnknownSender',
    ]


from lazr.delegates import delegates
from lazr.restful.declarations import (
    accessor_for,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_for_version,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import (
    Attribute,
    implements,
    Interface,
    )
from zope.schema import (
    Bool,
    Datetime,
    Int,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.app.errors import NotFoundError
from lp.services.librarian.interfaces import ILibraryFileAlias


class IMessage(Interface):
    """A message.

    This is like an email (RFC822) message, though it could be created through
    the web as well.
    """
    export_as_webservice_entry('message')

    id = Int(title=_('ID'), required=True, readonly=True)
    datecreated = exported(
        Datetime(title=_('Date Created'), required=True, readonly=True),
        exported_as='date_created')
    subject = exported(
        TextLine(title=_('Subject'), required=True, readonly=True))

    # XXX flacoste 2006-09-08: This attribute is only used for the
    # add form used by MessageAddView.
    content = Text(title=_("Message"), required=True, readonly=True)
    owner = exported(
        Reference(title=_('Person'), schema=Interface,
                  required=False, readonly=True))

    # Schema is really IMessage, but this cannot be declared here. It's
    # fixed below after the IMessage definition is complete.
    parent = exported(
        Reference(title=_('Parent'), schema=Interface,
                  required=False, readonly=True))

    rfc822msgid = TextLine(
        title=_('RFC822 Msg ID'), required=True, readonly=True)
    raw = Reference(title=_('Original unmodified email'),
                    schema=ILibraryFileAlias, required=False, readonly=True)
    bugs = CollectionField(
        title=_('Bug List'),
        value_type=Reference(schema=Interface))  # Redefined in bug.py

    chunks = Attribute(_('Message pieces'))

    text_contents = exported(
        Text(title=_('All the text/plain chunks joined together as a '
                     'unicode string.')),
        exported_as='content')

    title = TextLine(
        title=_('The message title, usually just the subject.'),
        readonly=True)
    visible = Bool(title=u"This message is visible or not.", required=False,
        default=True)

    bugattachments = exported(
        CollectionField(
            title=_("A list of BugAttachments connected to this "
                    "message."),
            value_type=Reference(Interface)),
        exported_as='bug_attachments')

    def __iter__():
        """Iterate over all the message chunks."""

    @accessor_for(parent)
    @export_read_operation()
    @operation_for_version('beta')
    def getAPIParent():
        """Return None because messages are not threaded over the API."""


# Fix for self-referential schema.
IMessage['parent'].schema = IMessage


class IMessageSet(Interface):
    """Set of IMessage"""

    def get(rfc822msgid):
        """Return a list of IMessage's with the given rfc822msgid.

        If no such messages exist, raise NotFoundError.
        """

    def fromText(subject, content, owner=None, datecreated=None,
        rfc822msgid=None):
        """Construct a Message from a text string and return it."""

    def fromEmail(email_message, owner=None, filealias=None,
                  parsed_message=None, fallback_parent=None, date_created=None,
                  restricted=False):
        """Construct a Message from an email message and return it.

        :param email_message: The original email as a string.
        :param owner: Specifies the owner of the new Message. The default
            is calculated using the From: or Reply-To: headers, and will raise
            a UnknownSender error if they cannot be found.
        :param filealias: The `LibraryFileAlias` of the raw email if it has
            already been uploaded to the Librarian.
        :param parsed_message: An email.Message.Message instance. If given,
            it is used internally instead of building one from the raw
            email_message. This is purely an optimization step, significant
            in many places because the emails we are handling may contain huge
            attachments and we should avoid reparsing them if possible.
        :param fallback_parent: The parent message if it could not be
            identified.
        :param date_created: Force a created date for the message. If
            specified, the value in the Date field in the passed message will
            be ignored.
        :param restricted: If set, the `LibraryFileAlias` will be uploaded to
            the restricted librarian.

        Callers may want to explicitly handle the following exceptions:
            * UnknownSender
            * MissingSubject
            * DuplicateMessageId
            * InvalidEmailMessage
        """

    def threadMessages(messages):
        """Return a threaded version of supplied message list.

        Return value is a recursive list structure.
        Each parent entry in the top-level list is a tuple of
        (parent, children), where children is a list of parents.  (Parents
        may be childless.)

        Example:
        [(parent, [(child1, [(grandchild1, [])]), (child2, [])])]
        """

    def flattenThreads(threaded_messages):
        """Convert threaded messages into a flat, indented form.

        Take a thread (in the form produced by threadMessages) and
        iterate through a series of (depth, message) tuples.  The ordering
        will match that implied by the input structure, with all replies
        to a message appearing after that message.
        """


class IIndexedMessage(Interface):
    """An `IMessage` decorated with its index and context."""
    inside = Reference(title=_('Inside'), schema=Interface,
                       description=_("The bug task which is "
                                     "the context for this message."),
                       required=True, readonly=True)
    index = Int(title=_("Index"),
                description=_("The index of this message in the list "
                              "of messages in its context."))


class IndexedMessage:
    """Adds the `inside` and `index` attributes to an IMessage."""
    delegates(IMessage)
    implements(IIndexedMessage)

    def __init__(self, context, inside, index, parent=None):
        self.context = context
        self.inside = inside
        self.index = index
        self._parent = parent

    @property
    def parent(self):
        return self._parent


class IMessageChunk(Interface):
    id = Int(title=_('ID'), required=True, readonly=True)
    message = Int(title=_('Message'), required=True, readonly=True)
    sequence = Int(title=_('Sequence order'), required=True, readonly=True)
    content = Text(title=_('Text content'), required=False, readonly=True)
    blob = Int(title=_('Binary content'), required=False, readonly=True)


class QuotaReachedError(Exception):
    """The user-to-user contact email quota has been reached for today."""

    def __init__(self, sender, authorization):
        Exception.__init__(self)
        self.sender = sender
        self.authorization = authorization


class IUserToUserEmail(Interface):
    """User to user direct email communications."""

    sender = Object(
        schema=Interface,
        title=_("The message sender"),
        required=True, readonly=True)

    recipient = Object(
        schema=Interface,
        title=_("The message recipient"),
        required=True, readonly=True)

    date_sent = Datetime(
        title=_('Date sent'),
        description=_(
            'The date this message was sent from sender to recipient.'),
        required=True, readonly=True)

    subject = TextLine(
        title=_('Subject'),
        required=True, readonly=True)

    message_id = TextLine(
        title=_('RFC 2822 Message-ID'),
        required=True, readonly=True)


class IDirectEmailAuthorization(Interface):
    """Can a Launchpad user contact another Launchpad user?"""

    is_allowed = Bool(
        title=_(
            'Is the sender allowed to send a message to a Launchpad user?'),
        description=_(
            'True if the sender allowed to send a message to another '
            'Launchpad user.'),
        readonly=True)

    throttle_date = Datetime(
        title=_('The earliest date used to throttle senders.'),
        readonly=True,
        )

    message_quota = Int(
        title=_('The maximum number of messages allowed per quota period'),
        readonly=True)

    def record(message):
        """Record that the message was sent.

        :param message: The email message that was sent.
        :type message: `email.Message.Message`
        """


class UnknownSender(NotFoundError):
    """Raised if we cannot lookup an email message's sender in the database"""


class MissingSubject(ValueError):
    """Raised if we get an email message with no Subject: header"""


class DuplicateMessageId(ValueError):
    """Raised if we attempt to store a new email with an existing Message-Id

    Indicates a broken mail client or MTA.
    """


class InvalidEmailMessage(ValueError):
    """Raised if the email message is too broken for us to deal with.

    This indicates broken mail clients or MTAs, and is raised on conditions
    such as missing Message-Id or missing From: headers.
    """
