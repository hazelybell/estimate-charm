# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SQLBase implementation of IQuestionBug."""

__metaclass__ = type

__all__ = ['QuestionBug']

from sqlobject import ForeignKey
from zope.interface import implements

from lp.coop.answersbugs.interfaces import IQuestionBug
from lp.services.database.sqlbase import SQLBase


class QuestionBug(SQLBase):
    """A link between a question and a bug."""

    implements(IQuestionBug)

    _table = 'QuestionBug'

    question = ForeignKey(
        dbName='question', foreignKey='Question', notNull=True)
    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)

    @property
    def target(self):
        """See IBugLink."""
        return self.question

