#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

""" Expire all questions in the OPEN and NEEDSINFO states that didn't receive
any activity in the last X days.

The expiration period is configured through
config.answertracker.days_before_expiration
"""

__metaclass__ = type

__all__ = ['ExpireQuestions']


import _pythonpath

from lp.answers.scripts.questionexpiration import QuestionJanitor
from lp.services.scripts.base import LaunchpadCronScript


class ExpireQuestions(LaunchpadCronScript):
    """Expire old questions.

    This script expires questions in the OPEN and NEEDSINFO states that
    didn't have any activity in the last X days. The number of days is
    configured through config.answertracker.days_before_expiration.
    """
    usage = "usage: %prog [options]"
    description = __doc__

    def main(self):
        """Expire old questions."""
        janitor = QuestionJanitor(log=self.logger)
        janitor.expireQuestions(self.txn)


if __name__ == '__main__':
    script = ExpireQuestions(
        'expire-questions', dbuser='expire_questions')
    script.lock_and_run()
