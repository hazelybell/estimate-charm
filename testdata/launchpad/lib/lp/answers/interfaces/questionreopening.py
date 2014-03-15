# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for a QuestionReopening."""

__metaclass__ = type

__all__ = [
    'IQuestionReopening',
    ]

from zope.interface import Interface
from zope.schema import (
    Choice,
    Datetime,
    Object,
    )

from lp import _
from lp.answers.enums import QuestionStatus
from lp.answers.interfaces.question import IQuestion
from lp.registry.interfaces.person import IPerson


class IQuestionReopening(Interface):
    """A record of the re-opening of a question.

    An IQuestionReopening is created each time that a question that had its
    answer attribute set is moved back to the OPEN state.
    """

    question = Object(
        title=_("The question reopened."), required=True, readonly=True,
        schema=IQuestion)

    datecreated = Datetime(
        title=_("The date this question was re-opened."), required=True,
        readonly=True)

    reopener = Object(
        title=_("The person who re-opened the question."), required=True,
        readonly=True, schema=IPerson)

    answerer = Object(
        title=_("The person who, previously, was listed as the answerer of "
                "the question."),
        required=True, readonly=True, schema=IPerson)

    date_solved = Datetime(
        title=_("The date it had previously been solved."), required=True,
        readonly=True)

    priorstate = Choice(
        title=_(
            "The previous state of the question, before it was re-opened."),
        vocabulary=QuestionStatus, required=True, readonly=True)
