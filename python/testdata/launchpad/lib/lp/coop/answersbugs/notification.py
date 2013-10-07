# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Notifications related to linking bugs and questions."""

__metaclass__ = type
__all__ = []

import os

from lazr.lifecycle.interfaces import IObjectModifiedEvent

from lp.answers.notification import QuestionNotification
from lp.bugs.interfaces.bugtask import IBugTask
from lp.services.webapp.publisher import canonical_url


def get_email_template(filename):
    """Returns the email template with the given file name.

    The templates are located in 'emailtemplates'.
    """
    base = os.path.dirname(__file__)
    fullpath = os.path.join(base, 'emailtemplates', filename)
    return open(fullpath).read()


def dispatch_linked_question_notifications(bugtask, event):
    """Send notifications to linked question subscribers when the bugtask
    status change.
    """
    for question in bugtask.bug.questions:
        QuestionLinkedBugStatusChangeNotification(question, event)


class QuestionLinkedBugStatusChangeNotification(QuestionNotification):
    """Notification sent when a linked bug status is changed."""

    def initialize(self):
        """Create a notifcation for a linked bug status change."""
        assert IObjectModifiedEvent.providedBy(self.event), (
            "Should only be subscribed for IObjectModifiedEvent.")
        assert IBugTask.providedBy(self.event.object), (
            "Should only be subscribed for IBugTask modification.")
        self.bugtask = self.event.object
        self.old_bugtask = self.event.object_before_modification

    def shouldNotify(self):
        """Only send notification when the status changed."""
        return (self.bugtask.status != self.old_bugtask.status
                and self.bugtask.bug.private == False)

    def getSubject(self):
        """See QuestionNotification."""
        return "[Question #%s]: Status of bug #%s changed to '%s' in %s" % (
            self.question.id, self.bugtask.bug.id, self.bugtask.status.title,
            self.bugtask.target.displayname)

    def getBody(self):
        """See QuestionNotification."""
        return get_email_template(
            'question-linked-bug-status-updated.txt') % {
                'bugtask_target_name': self.bugtask.target.displayname,
                'question_id': self.question.id,
                'question_title': self.question.title,
                'question_url': canonical_url(self.question),
                'bugtask_url': canonical_url(self.bugtask),
                'bug_id': self.bugtask.bug.id,
                'bugtask_title': self.bugtask.bug.title,
                'old_status': self.old_bugtask.status.title,
                'new_status': self.bugtask.status.title}
