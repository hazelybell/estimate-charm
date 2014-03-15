# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['BugAttachment', 'BugAttachmentSet']

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectDeletedEvent,
    )
from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.store import Store
from zope.event import notify
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.bugs.interfaces.bugattachment import (
    BugAttachmentType,
    IBugAttachment,
    IBugAttachmentSet,
    )
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.propertycache import cachedproperty


class BugAttachment(SQLBase):
    """A bug attachment."""

    implements(IBugAttachment)

    _table = 'BugAttachment'

    bug = ForeignKey(
        foreignKey='Bug', dbName='bug', notNull=True)
    type = EnumCol(
        schema=BugAttachmentType, notNull=True,
        default=IBugAttachment['type'].default)
    title = StringCol(notNull=True)
    libraryfile = ForeignKey(
        foreignKey='LibraryFileAlias', dbName='libraryfile', notNull=True)
    data = ForeignKey(
        foreignKey='LibraryFileAlias', dbName='libraryfile', notNull=True)
    _message = ForeignKey(
        foreignKey='Message', dbName='message', notNull=True)

    @cachedproperty
    def message(self):
        """This is a cachedproperty to allow message to be an IIndexedMessage.

        This is needed for the bug/attachments API call which needs to index
        an IIndexedMessage rather than a simple DB model IMessage. See
        Bug.attachments where the injection occurs.
        """
        return self._message

    @property
    def is_patch(self):
        """See IBugAttachment."""
        return self.type == BugAttachmentType.PATCH

    def removeFromBug(self, user):
        """See IBugAttachment."""
        notify(ObjectDeletedEvent(self, user))
        self.destroySelf()

    def destroySelf(self):
        """See IBugAttachment."""
        # Delete the reference to the LibraryFileContent record right now,
        # in order to avoid problems with not deleted files as described
        # in bug 387188.
        self.libraryfile.content = None
        super(BugAttachment, self).destroySelf()

    def getFileByName(self, filename):
        """See IBugAttachment."""
        if filename == self.libraryfile.filename:
            return self.libraryfile
        raise NotFoundError(filename)


class BugAttachmentSet:
    """A set for bug attachments."""

    implements(IBugAttachmentSet)

    def __getitem__(self, attach_id):
        """See IBugAttachmentSet."""
        try:
            attach_id = int(attach_id)
        except ValueError:
            raise NotFoundError(attach_id)
        try:
            item = BugAttachment.get(attach_id)
        except SQLObjectNotFound:
            raise NotFoundError(attach_id)
        return item

    def create(self, bug, filealias, title, message,
               attach_type=None, send_notifications=False):
        """See `IBugAttachmentSet`."""
        if attach_type is None:
            # XXX kiko 2005-08-03 bug=1659: this should use DEFAULT.
            attach_type = IBugAttachment['type'].default
        attachment = BugAttachment(
            bug=bug, libraryfile=filealias, type=attach_type, title=title,
            _message=message)
        # canonial_url(attachment) (called by notification subscribers
        # to generate the download URL of the attachments) blows up if
        # attachment.id is not (yet) set.
        Store.of(attachment).flush()
        if send_notifications:
            notify(ObjectCreatedEvent(attachment, user=message.owner))
        return attachment
