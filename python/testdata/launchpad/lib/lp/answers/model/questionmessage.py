# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SQLBase implementation of IQuestionMessage."""

__metaclass__ = type

__all__ = [
    'QuestionMessage',
    ]

from lazr.delegates import delegates
from sqlobject import ForeignKey
from zope.interface import implements

from lp.answers.enums import (
    QuestionAction,
    QuestionStatus,
    )
from lp.answers.interfaces.questionmessage import IQuestionMessage
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.messages.interfaces.message import IMessage
from lp.services.propertycache import cachedproperty


class QuestionMessage(SQLBase):
    """A table linking questions and messages."""

    implements(IQuestionMessage)

    delegates(IMessage, context='message')

    _table = 'QuestionMessage'

    question = ForeignKey(
        dbName='question', foreignKey='Question', notNull=True)
    message = ForeignKey(dbName='message', foreignKey='Message', notNull=True)

    action = EnumCol(
        schema=QuestionAction, notNull=True, default=QuestionAction.COMMENT)

    new_status = EnumCol(
        schema=QuestionStatus, notNull=True, default=QuestionStatus.OPEN)

    owner = ForeignKey(dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    def __init__(self, **kwargs):
        if 'owner' not in kwargs:
            # Although a trigger will set the owner after the SQL
            # INSERT has been executed, we must specify the parameter
            # explicitly to fulfill the DB constraint OWNER NOT NULL,
            # otherweise we'll get an error from the DB server.
            kwargs['owner'] = kwargs['message'].owner
        super(QuestionMessage, self).__init__(**kwargs)

    def __iter__(self):
        """See IMessage."""
        # Delegates do not proxy __ methods, because of the name mangling.
        return iter(self.chunks)

    @cachedproperty
    def index(self):
        return list(self.question.messages).index(self)

    @cachedproperty
    def display_index(self):
        # Return the index + 1 so that messages appear 1-indexed in the UI.
        return self.index + 1

    @property
    def visible(self):
        """See `IQuestionMessage.`"""
        return self.message.visible
