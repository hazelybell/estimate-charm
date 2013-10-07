# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug attachment interfaces."""

__metaclass__ = type

__all__ = [
    'BugAttachmentType',
    'IBugAttachment',
    'IBugAttachmentSet',
    'IBugAttachmentEditForm',
    'IBugAttachmentIsPatchConfirmationForm',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_write_operation,
    exported,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Bool,
    Bytes,
    Choice,
    Int,
    TextLine,
    )

from lp import _
from lp.bugs.interfaces.hasbug import IHasBug
from lp.services.fields import Title
from lp.services.messages.interfaces.message import IMessage


class BugAttachmentType(DBEnumeratedType):
    """Bug Attachment Type.

    An attachment to a bug can be of different types, since for example
    a patch is more important than a screenshot. This schema describes the
    different types.
    """

    PATCH = DBItem(1, """
        Patch

        A patch that potentially fixes the bug.
        """)

    UNSPECIFIED = DBItem(2, """
        Unspecified

        Any attachment other than a patch. For example: a screenshot,
        a log file, a core dump, or anything else that adds more information
        to the bug.
        """)


class IBugAttachment(IHasBug):
    """A file attachment to an IBug.

    Launchpadlib example of accessing content of an attachment::

        for attachment in bug.attachments:
            buffer = attachment.data.open()
            for line in buffer:
                print line
            buffer.close()

    Launchpadlib example of accessing metadata about an attachment::

        attachment = bug.attachments[0]
        print "title:", attachment.title
        print "ispatch:", attachment.type

    For information about the file-like object returned by
    attachment.data.open() see lazr.restfulclient's documentation of the
    HostedFile object.

    Details about the message associated with an attachment can be found on
    the "message" attribute::

        message = attachment.message
        print "subject:", message.subject.encode('utf-8')
        print "owner:", message.owner.display_name.encode('utf-8')
        print "created:", message.date_created
    """
    export_as_webservice_entry()

    id = Int(title=_('ID'), required=True, readonly=True)
    bug = exported(
        Reference(Interface, title=_('The bug the attachment belongs to.')))
    type = exported(
        Choice(
            title=_('Attachment Type'),
            description=_('The type of the attachment, for example Patch or '
                          'Unspecified.'),
            vocabulary=BugAttachmentType,
            default=BugAttachmentType.UNSPECIFIED,
            required=True))
    title = exported(
        Title(title=_('Title'),
              description=_(
                'A short and descriptive description of the attachment'),
              required=True))
    libraryfile = Bytes(title=_("The attachment content."),
              required=True)
    data = exported(
        Bytes(title=_("The attachment content."),
              required=True,
              readonly=True))
    message = exported(
        Reference(IMessage, title=_("The message that was created when we "
                                    "added this attachment.")))
    is_patch = Bool(
        title=_('Patch?'),
        description=_('Is this attachment a patch?'),
        readonly=True)

    @call_with(user=REQUEST_USER)
    @export_write_operation()
    def removeFromBug(user):
        """Remove the attachment from the bug."""

    def destroySelf():
        """Delete this record.

        The library file content for this attachment is set to None.
        """

    def getFileByName(filename):
        """Return the `ILibraryFileAlias for the given file name.

        NotFoundError is raised if the given filename does not match
        libraryfile.filename.
        """


# Need to do this here because of circular imports.
IMessage['bugattachments'].value_type.schema = IBugAttachment


class IBugAttachmentSet(Interface):
    """A set for IBugAttachment objects."""

    def create(bug, filealias, title, message,
               type=IBugAttachment['type'].default, send_notifications=False):
        """Create a new attachment and return it.

        :param bug: The `IBug` to which the new attachment belongs.
        :param filealias: The `IFilealias` containing the data.
        :param message: The `IMessage` to which this attachment belongs.
        :param type: The type of attachment. See `BugAttachmentType`.
        :param send_notifications: If True, a notification is sent to
            subscribers of the bug.
        """

    def __getitem__(id):
        """Get an IAttachment by its id.

        Return NotFoundError if no such id exists.
        """


class IBugAttachmentEditForm(Interface):
    """Schema used to build the edit form for bug attachments."""

    title = IBugAttachment['title']
    contenttype = TextLine(
        title=u'Content Type',
        description=(
            u"The content type is only settable if the attachment isn't "
            "a patch. If it's a patch, the content type will be set to "
            "text/plain"),
        required=True)
    patch = Bool(
        title=u"This attachment contains a solution (patch) for this bug",
        required=True, default=False)


class IBugAttachmentIsPatchConfirmationForm(Interface):
    """Schema used to confirm the setting of the "patch" flag."""

    patch = Bool(title=u"Is this file a patch", required=True, default=False)
