# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Handle incoming Answers email."""

__metaclass__ = type
__all__ = [
    "AnswerTrackerHandler",
    ]

import re

from zope.component import getUtility
from zope.interface import implements

from lp.answers.enums import QuestionStatus
from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.services.mail.interfaces import IMailHandler
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.interfaces import ILaunchBag


class AnswerTrackerHandler:
    """Handles emails sent to the Answer Tracker."""

    implements(IMailHandler)

    allow_unknown_users = False

    # XXX flacoste 2007-04-23: The 'ticket' part is there for backward
    # compatibility with the old notification address. We probably want to
    # remove it in the future.
    _question_address = re.compile(r'^(ticket|question)(?P<id>\d+)@.*')

    def process(self, signed_msg, to_addr, filealias=None, log=None):
        """See IMailHandler."""
        match = self._question_address.match(to_addr)
        if not match:
            return False

        question_id = int(match.group('id'))
        question = getUtility(IQuestionSet).get(question_id)
        if question is None:
            # No such question, don't process the email.
            return False

        messageset = getUtility(IMessageSet)
        message = messageset.fromEmail(
            signed_msg.parsed_string,
            owner=getUtility(ILaunchBag).user,
            filealias=filealias,
            parsed_message=signed_msg)

        if message.owner == question.owner:
            self.processOwnerMessage(question, message)
        else:
            self.processUserMessage(question, message)
        return True

    def processOwnerMessage(self, question, message):
        """Choose the right workflow action for a message coming from
        the question owner.

        When the question status is OPEN or NEEDINFO,
        the message is a GIVEINFO action; when the status is ANSWERED
        or EXPIRED, we interpret the message as a reopenening request;
        otherwise it's a comment.
        """
        if question.status in [
            QuestionStatus.OPEN, QuestionStatus.NEEDSINFO]:
            question.giveInfo(message)
        elif question.status in [
            QuestionStatus.ANSWERED, QuestionStatus.EXPIRED]:
            question.reopen(message)
        else:
            question.addComment(message.owner, message)

    def processUserMessage(self, question, message):
        """Choose the right workflow action for a message coming from a user
        that is not the question owner.

        When the question status is OPEN, NEEDSINFO, or ANSWERED, we interpret
        the message as containing an answer. (If it was really a request for
        more information, the owner will still be able to answer it while
        reopening the request.)

        In the other status, the message is a comment without status change.
        """
        if question.status in [
            QuestionStatus.OPEN, QuestionStatus.NEEDSINFO,
        QuestionStatus.ANSWERED]:
            question.giveAnswer(message.owner, message)
        else:
            # In the other states, only a comment can be added.
            question.addComment(message.owner, message)
