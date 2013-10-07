# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['BugMessage', 'BugMessageSet']

from email.Utils import make_msgid

from sqlobject import (
    ForeignKey,
    IntCol,
    StringCol,
    )
from storm.store import Store
from zope.interface import implements

from lp.bugs.interfaces.bugmessage import (
    IBugMessage,
    IBugMessageSet,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.messages.model.message import (
    Message,
    MessageChunk,
    )


class BugMessage(SQLBase):
    """A table linking bugs and messages."""

    implements(IBugMessage)

    _table = 'BugMessage'

    def __init__(self, *args, **kw):
        # This is maintained by triggers to ensure validity, but we
        # also set it here to ensure it is visible to the transaction
        # creating a BugMessage.
        kw['owner'] = owner = kw['message'].owner
        assert owner is not None, "BugMessage's Message must have an owner"
        super(BugMessage, self).__init__(*args, **kw)

    # db field names
    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)
    message = ForeignKey(dbName='message', foreignKey='Message', notNull=True)
    bugwatch = ForeignKey(dbName='bugwatch', foreignKey='BugWatch',
        notNull=False, default=None)
    remote_comment_id = StringCol(notNull=False, default=None)
    # -- The index of the message is cached in the DB.
    index = IntCol(notNull=True)
    # -- The owner, cached from the message table using triggers.
    owner = ForeignKey(dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    def __repr__(self):
        return "<BugMessage at 0x%x message=%s index=%s>" % (
            id(self), self.message, self.index)


class BugMessageSet:
    """See `IBugMessageSet`."""

    implements(IBugMessageSet)

    def createMessage(self, subject, bug, owner, content=None):
        """See `IBugMessageSet`."""
        msg = Message(
            parent=bug.initial_message, owner=owner,
            rfc822msgid=make_msgid('malone'), subject=subject)
        MessageChunk(message=msg, content=content, sequence=1)
        bugmsg = BugMessage(bug=bug, message=msg,
            index=bug.bug_messages.count())

        # XXX 2008-05-27 jamesh:
        # Ensure that BugMessages get flushed in same order as they
        # are created.
        Store.of(bugmsg).flush()
        return bugmsg

    def get(self, bugmessageid):
        """See `IBugMessageSet`."""
        return BugMessage.get(bugmessageid)

    def getByBugAndMessage(self, bug, message):
        """See`IBugMessageSet`."""
        return BugMessage.selectOneBy(bug=bug, message=message)

    def getImportedBugMessages(self, bug):
        """See IBugMessageSet."""
        return BugMessage.select("""
            BugMessage.bug = %s
            AND BugMessage.bugwatch IS NOT NULL
            """ % sqlvalues(bug), orderBy='id')
