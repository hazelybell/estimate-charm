# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SQLBase implementation of IQuestionReopening."""

__metaclass__ = type

__all__ = ['QuestionReopening',
           'create_questionreopening']

from lazr.lifecycle.event import ObjectCreatedEvent
from sqlobject import ForeignKey
from zope.event import notify
from zope.interface import implements
from zope.security.proxy import ProxyFactory

from lp.answers.enums import QuestionStatus
from lp.answers.interfaces.questionreopening import IQuestionReopening
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import DEFAULT
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase


class QuestionReopening(SQLBase):
    """A table recording each time a question is re-opened."""

    implements(IQuestionReopening)

    _table = 'QuestionReopening'

    question = ForeignKey(
        dbName='question', foreignKey='Question', notNull=True)
    datecreated = UtcDateTimeCol(notNull=True, default=DEFAULT)
    reopener = ForeignKey(
        dbName='reopener', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    answerer = ForeignKey(
        dbName='answerer', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False, default=None)
    date_solved = UtcDateTimeCol(notNull=False, default=None)
    priorstate = EnumCol(schema=QuestionStatus, notNull=True)


def create_questionreopening(
        question,
        reopen_msg,
        old_status,
        old_answerer,
        old_date_solved):
    """Helper function to handle question reopening.

    A QuestionReopening is created when question with an answer changes back
    to the OPEN state.
    """
    # XXX jcsackett This guard has to be maintained because reopen can
    # be called with the question in a bad state.
    if old_answerer is None:
        return
    reopening = QuestionReopening(
            question=question,
            reopener=reopen_msg.owner,
            datecreated=reopen_msg.datecreated,
            answerer=old_answerer,
            date_solved=old_date_solved,
            priorstate=old_status)
    reopening = ProxyFactory(reopening)
    notify(ObjectCreatedEvent(reopening, user=reopen_msg.owner))
