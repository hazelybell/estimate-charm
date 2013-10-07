# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Question expiration logic."""

__metaclass__ = type

from logging import getLogger

from zope.component import getUtility

from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.config import config
from lp.services.webapp.interaction import (
    endInteraction,
    setupInteraction,
    )
from lp.services.webapp.interfaces import IPlacelessAuthUtility


class QuestionJanitor:
    """Object that takes the responsability of expiring questions
    without activity in a configurable period.
    """

    def __init__(self, days_before_expiration=None, log=None):
        """Create a new QuestionJanitor.

        :days_before_expiration: Days of inactivity before a question is
            expired. Defaults to config.answertracker.days_before_expiration
        :log: A logger instance to use for logging. Defaults to the default
            logger.
        """

        if days_before_expiration is None:
            days_before_expiration = (
                config.answertracker.days_before_expiration)

        if log is None:
            log = getLogger()
        self.days_before_expiration = days_before_expiration
        self.log = log

        self.janitor = (
            getUtility(ILaunchpadCelebrities).janitor)

    def expireQuestions(self, transaction_manager):
        """Expire old questions.

        All questions in the OPEN or NEEDSINFO state without activity
        in the last X days are expired.

        This method will login as the support_tracker_janitor celebrity and
        logout after the expiration is done.
        """
        self.log.info(
            'Expiring OPEN and NEEDSINFO questions without activity for the '
            'last %d days.' % self.days_before_expiration)
        self._login()
        try:
            count = 0
            expired_questions = getUtility(IQuestionSet).findExpiredQuestions(
                self.days_before_expiration)
            self.log.info(
                'Found %d questions to expire.' % expired_questions.count())
            for question in expired_questions:
                question.expireQuestion(
                    self.janitor,
                    "This question was expired because it remained in "
                    "the '%s' state without activity for the last %d days." %
                        (question.status.title, self.days_before_expiration))
                # XXX flacoste 2006-10-24 bug=29744: We commit after each and
                # every expiration because of bug #29744 (emails are sent
                # immediately in zopeless). This minimuze the risk of
                # duplicate expiration email being sent in case an error
                # occurs later on.
                transaction_manager.commit()
                count += 1
            self.log.info('Expired %d questions.' % count)
        finally:
            self._logout()
        self.log.info('Finished expiration run.')

    def _login(self):
        """Setup an interaction as the Launchpad Janitor."""
        auth_utility = getUtility(IPlacelessAuthUtility)
        janitor_email = self.janitor.preferredemail.email
        setupInteraction(
            auth_utility.getPrincipalByLogin(janitor_email),
            login=janitor_email)

    def _logout(self):
        """Removed the Launchpad Janitor interaction."""
        endInteraction()
