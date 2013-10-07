# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""SQLBase implementation of IQuestionSubscription."""

__metaclass__ = type

__all__ = ['QuestionSubscription']

import pytz
from sqlobject import ForeignKey
from storm.locals import (
    DateTime,
    Int,
    )
from zope.interface import implements

from lp.answers.interfaces.questionsubscription import IQuestionSubscription
from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.role import IPersonRoles
from lp.services.database.constants import UTC_NOW
from lp.services.database.sqlbase import SQLBase


class QuestionSubscription(SQLBase):
    """A subscription for person to a question."""

    implements(IQuestionSubscription)

    _table = 'QuestionSubscription'

    id = Int(primary=True)
    question_id = Int("question", allow_none=False)
    question = ForeignKey(
        dbName='question', foreignKey='Question', notNull=True)

    person_id = Int(
        "person", allow_none=False, validator=validate_public_person)
    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    date_created = DateTime(
        allow_none=False, default=UTC_NOW, tzinfo=pytz.UTC)

    def canBeUnsubscribedByUser(self, user):
        """See `IQuestionSubscription`."""
        if user is None:
            return False
        # The people who can unsubscribe someone are:
        # - lp admins
        # - the person themselves
        # - the question owner
        # - people who can reject questions (eg target owner, answer contacts)
        return (user.inTeam(self.question.owner) or
                user.inTeam(self.person) or
                IPersonRoles(user).in_admin or
                self.question.canReject(user))
