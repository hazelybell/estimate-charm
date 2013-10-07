# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'SpecificationMessage',
    'SpecificationMessageSet'
    ]

from email.Utils import make_msgid

from sqlobject import (
    BoolCol,
    ForeignKey,
    )
from zope.interface import implements

from lp.blueprints.interfaces.specificationmessage import (
    ISpecificationMessage,
    ISpecificationMessageSet,
    )
from lp.services.database.sqlbase import SQLBase
from lp.services.messages.model.message import (
    Message,
    MessageChunk,
    )


class SpecificationMessage(SQLBase):
    """A table linking specifictions and messages."""

    implements(ISpecificationMessage)

    _table = 'SpecificationMessage'

    specification = ForeignKey(
        dbName='specification', foreignKey='Specification', notNull=True)
    message = ForeignKey(dbName='message', foreignKey='Message', notNull=True)
    visible = BoolCol(notNull=True, default=True)


class SpecificationMessageSet:
    """See ISpecificationMessageSet."""

    implements(ISpecificationMessageSet)

    def createMessage(self, subject, spec, owner, content=None):
        """See ISpecificationMessageSet."""
        msg = Message(
            owner=owner, rfc822msgid=make_msgid('blueprint'), subject=subject)
        MessageChunk(message=msg, content=content, sequence=1)
        return SpecificationMessage(specification=spec, message=msg)

    def get(self, specmessageid):
        """See ISpecificationMessageSet."""
        return SpecificationMessage.get(specmessageid)

    def getBySpecificationAndMessage(self, spec, message):
        """See ISpecificationMessageSet."""
        return SpecificationMessage.selectOneBy(
            specification=spec, message=message)
