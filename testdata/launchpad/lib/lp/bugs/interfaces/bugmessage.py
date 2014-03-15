# Copyright 2004-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug message interfaces."""

__metaclass__ = type
__all__ = [
    'IBugComment',
    'IBugMessage',
    'IBugMessageAddForm',
    'IBugMessageSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Bytes,
    Int,
    Object,
    Text,
    TextLine,
    )

from lp.app.validators.attachment import attachment_size_constraint
from lp.bugs.interfaces.bug import IBug
from lp.bugs.interfaces.bugwatch import IBugWatch
from lp.bugs.interfaces.hasbug import IHasBug
from lp.registry.interfaces.person import IPerson
from lp.services.comments.interfaces.conversation import IComment
from lp.services.fields import Title
from lp.services.messages.interfaces.message import IMessage


class IBugMessage(IHasBug):
    """A link between a bug and a message."""

    bug = Object(schema=IBug, title=u"The bug.")
    # The index field is being populated in the DB; once complete it will be
    # made required. Whether to make it readonly or not is dependent on UI
    # considerations. If, once populated, it becomes read-write, we probably
    # want to ensure that only actions like bug import or spam hiding can
    # change it, rather than arbitrary API scripts.
    index = Int(title=u'The comment number', required=False, readonly=False,
        default=None)
    messageID = Int(title=u"The message id.", readonly=True)
    message = Object(schema=IMessage, title=u"The message.")
    bugwatch = Object(schema=IBugWatch,
        title=u"A bugwatch to which the message pertains.")
    bugwatchID = Int(title=u'The bugwatch id.', readonly=True)
    remote_comment_id = TextLine(
        title=u"The id this comment has in the bugwatch's bug tracker.")
    ownerID = Attribute("The ID of the owner mirrored from the message")
    owner = Object(schema=IPerson,
        title=u"The Message owner mirrored from the message.", readonly=True)


class IBugMessageSet(Interface):
    """The set of all IBugMessages."""

    def createMessage(subject, bug, owner, content=None):
        """Create an IBugMessage.

        title -- a string
        bug -- an IBug
        owner -- an IPerson
        content -- a string

        The created message will have the bug's initial message as its
        parent.

        Returns the created IBugMessage.
        """

    def get(bugmessageid):
        """Retrieve an IBugMessage by its ID."""

    def getByBugAndMessage(bug, message):
        """Return the corresponding IBugMesssage.

        Return None if no such IBugMesssage exists.
        """

    def getImportedBugMessages(bug):
        """Return all the imported IBugMesssages for a bug.

        An IBugMesssage is considered imported if it's linked to a bug
        watch.
        """


class IBugMessageAddForm(Interface):
    """Schema used to build the add form for bug comment/attachment."""

    subject = Title(title=u"Subject", required=True)
    comment = Text(title=u"Comment", required=False)
    filecontent = Bytes(
        title=u"Attachment", required=False,
        constraint=attachment_size_constraint)
    patch = Bool(
        title=u"This attachment contains a solution (patch) for this bug",
        required=False, default=False)
    attachment_description = Title(title=u'Description', required=False)
    email_me = Bool(
        title=u"E-mail me about changes to this bug report",
        required=False, default=False)
    bugwatch_id = Int(
        title=(u"Synchronize this comment with a remote bug "
               "tracker using the bug watch with this id."),
        required=False, default=None)


class IBugComment(IMessage, IComment):
    """A bug comment for displaying in the web UI."""

    bugtask = Attribute(
        """The bug task the comment belongs to.

        Comments are global to bugs, but the bug task is needed in order
        to construct the correct URL.
        """)
    bugwatch = Attribute('The bugwatch to which the comment pertains.')
    show_for_admin = Bool(
        title=u'A hidden comment still displayed for admins.',
        readonly=True)
    display_title = Attribute('Whether or not to show the title.')
    synchronized = Attribute(
        'Has the comment been synchronized with a remote bug tracker?')
    add_comment_url = Attribute(
        'The URL for submitting replies to this comment.')
    activity = Attribute(
        "A list of BugActivityItems associated with this comment.")
    show_footer = Attribute(
        "Whether or not to show a footer for the comment.")
    patches = Attribute(
        "Patches attched to this comment.")
