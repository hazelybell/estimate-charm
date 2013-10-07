# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Notifications for the Answers system."""

__metaclass__ = type
__all__ = [
    'QuestionNotification',
    ]

import os

from zope.component import getUtility

from lp.answers.enums import (
    QuestionAction,
    QuestionRecipientSet,
    )
from lp.answers.interfaces.questionjob import IQuestionEmailJobSource
from lp.registry.interfaces.person import IPerson
from lp.services.config import config
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.propertycache import cachedproperty
from lp.services.webapp.publisher import canonical_url


def get_email_template(filename):
    """Returns the email template with the given file name.

    The templates are located in 'emailtemplates'.
    """
    base = os.path.dirname(__file__)
    fullpath = os.path.join(base, 'emailtemplates', filename)
    return open(fullpath).read()


class QuestionNotification:
    """Base class for a notification related to a question.

    Creating an instance of that class will build the notification and
    send it to the appropriate recipients. That way, subclasses of
    QuestionNotification can be registered as event subscribers.
    """

    recipient_set = QuestionRecipientSet.ASKER_SUBSCRIBER

    def __init__(self, question, event):
        """Base constructor.

        It saves the question and event in attributes and then call
        the initialize() and send() method.
        """
        self.question = question
        self.event = event
        self._user = IPerson(self.event.user)
        self.initialize()
        self.job = None
        if self.shouldNotify():
            self.job = self.enqueue()

    @property
    def user(self):
        """Return the user from the event. """
        return self._user

    def getSubject(self):
        """Return the subject of the notification.

        Default to [Question #dd]: Title
        """
        return '[Question #%s]: %s' % (self.question.id, self.question.title)

    def getBody(self):
        """Return the content of the notification message.

        This method must be implemented by a subclass.
        """
        raise NotImplementedError

    def getHeaders(self):
        """Return additional headers to add to the email.

        Default implementation adds a X-Launchpad-Question header.
        """
        question = self.question
        headers = dict()
        if self.question.distribution:
            if question.sourcepackagename:
                sourcepackage = question.sourcepackagename.name
            else:
                sourcepackage = 'None'
            target = 'distribution=%s; sourcepackage=%s;' % (
                question.distribution.name, sourcepackage)
        else:
            target = 'product=%s;' % question.product.name
        if question.assignee:
            assignee = question.assignee.name
        else:
            assignee = 'None'

        headers['X-Launchpad-Question'] = (
            '%s status=%s; assignee=%s; priority=%s; language=%s' % (
                target, question.status.title, assignee,
                question.priority.title, question.language.code))
        headers['Reply-To'] = 'question%s@%s' % (
            self.question.id, config.answertracker.email_domain)

        return headers

    def initialize(self):
        """Initialization hook for subclasses.

        This method is called before send() and can be use for any
        setup purpose.

        Default does nothing.
        """
        pass

    def shouldNotify(self):
        """Return if there is something to notify about.

        When this method returns False, no notification will be sent.
        By default, all event trigger a notification.
        """
        return True

    def enqueue(self):
        """Create a job to send email about the event."""
        subject = self.getSubject()
        body = self.getBody()
        headers = self.getHeaders()
        job_source = getUtility(IQuestionEmailJobSource)
        job = job_source.create(
            self.question, self.user, self.recipient_set,
            subject, body, headers)
        return job

    @property
    def unsupported_language(self):
        """Whether the question language is unsupported or not."""
        supported_languages = self.question.target.getSupportedLanguages()
        return self.question.language not in supported_languages

    @property
    def unsupported_language_warning(self):
        """Warning about the fact that the question is written in an
        unsupported language."""
        return get_email_template(
                'question-unsupported-language-warning.txt') % {
                'question_language': self.question.language.englishname,
                'target_name': self.question.target.displayname}


class QuestionAddedNotification(QuestionNotification):
    """Notification sent when a question is added."""

    @property
    def user(self):
        """Return the question owner.

        Questions can be created by other users for the owner; the
        question is from the owner.
        """
        return self.question.owner

    def getBody(self):
        """See QuestionNotification."""
        question = self.question
        body = get_email_template('question-added-notification.txt') % {
            'target_name': question.target.displayname,
            'question_id': question.id,
            'question_url': canonical_url(question),
            'comment': question.description}
        if self.unsupported_language:
            body += self.unsupported_language_warning
        return body


class QuestionModifiedDefaultNotification(QuestionNotification):
    """Base implementation of a notification when a question is modified."""

    recipient_set = QuestionRecipientSet.SUBSCRIBER
    # Email template used to render the body.
    body_template = "question-modified-notification.txt"

    def initialize(self):
        """Save the old question for comparison. It also set the new_message
        attribute if a new message was added.
        """
        self.old_question = self.event.object_before_modification

        new_messages = set(
            self.question.messages).difference(self.old_question.messages)
        assert len(new_messages) <= 1, (
                "There shouldn't be more than one message for a "
                "notification.")
        if new_messages:
            self.new_message = new_messages.pop()
        else:
            self.new_message = None

        self.wrapper = MailWrapper()

    @cachedproperty
    def metadata_changes_text(self):
        """Textual representation of the changes to the question metadata."""
        question = self.question
        old_question = self.old_question
        indent = 4 * ' '
        info_fields = []
        if question.status != old_question.status:
            info_fields.append(indent + 'Status: %s => %s' % (
                old_question.status.title, question.status.title))
        if question.target != old_question.target:
            info_fields.append(
                indent + 'Project: %s => %s' % (
                old_question.target.displayname, question.target.displayname))

        if question.assignee != old_question.assignee:
            if old_question.assignee is None:
                old_assignee = None
            else:
                old_assignee = old_question.assignee.displayname
            if question.assignee is None:
                assignee = None
            else:
                assignee = question.assignee.displayname
            info_fields.append(indent + 'Assignee: %s => %s' % (
               old_assignee, assignee))

        old_bugs = set(old_question.bugs)
        bugs = set(question.bugs)
        for linked_bug in bugs.difference(old_bugs):
            info_fields.append(
                indent + 'Linked to bug: #%s\n' % linked_bug.id +
                indent + '%s\n' % canonical_url(linked_bug) +
                indent + '"%s"' % linked_bug.title)
        for unlinked_bug in old_bugs.difference(bugs):
            info_fields.append(
                indent + 'Removed link to bug: #%s\n' % unlinked_bug.id +
                indent + '%s\n' % canonical_url(unlinked_bug) +
                indent + '"%s"' % unlinked_bug.title)

        if question.faq != old_question.faq:
            if question.faq is None:
                info_fields.append(
                    indent + 'Related FAQ was removed:\n' +
                    indent + old_question.faq.title + '\n' +
                    indent + canonical_url(old_question.faq))
            else:
                info_fields.append(
                    indent + 'Related FAQ set to:\n' +
                    indent + question.faq.title + '\n' +
                    indent + canonical_url(question.faq))

        if question.title != old_question.title:
            info_fields.append('Summary changed to:\n%s' % question.title)
        if question.description != old_question.description:
            info_fields.append(
                'Description changed to:\n%s' % (
                    self.wrapper.format(question.description)))

        question_changes = '\n\n'.join(info_fields)
        return question_changes

    def getSubject(self):
        """The reply subject line."""
        line = super(QuestionModifiedDefaultNotification, self).getSubject()
        return 'Re: %s' % line

    def getHeaders(self):
        """Add a References header."""
        headers = QuestionNotification.getHeaders(self)
        if self.new_message:
            # XXX flacoste 2007-02-02 bug=83846:
            # The first message cannot contain a References
            # because we don't create a Message instance for the
            # question description, so we don't have a Message-ID.
            messages = list(self.question.messages)
            assert self.new_message in messages, (
                "Question %s: message id %s not in %s." % (
                    self.question.id, self.new_message.id,
                    [m.id for m in messages]))
            index = messages.index(self.new_message)
            if index > 0:
                headers['References'] = (
                    self.question.messages[index - 1].rfc822msgid)
        return headers

    def shouldNotify(self):
        """Only send a notification when a message was added or some
        metadata was changed.
        """
        return self.new_message or self.metadata_changes_text

    def getBody(self):
        """See QuestionNotification."""
        body = self.metadata_changes_text
        replacements = dict(
            question_id=self.question.id,
            target_name=self.question.target.displayname,
            question_url=canonical_url(self.question))

        if self.new_message:
            if body:
                body += '\n\n'
            body += self.getNewMessageText()
            replacements['new_message_id'] = list(
                self.question.messages).index(self.new_message)

        replacements['body'] = body

        return get_email_template(self.body_template) % replacements

    # Header template used when a new message is added to the question.
    action_header_template = {
        QuestionAction.REQUESTINFO:
            '%(person)s requested more information:',
        QuestionAction.CONFIRM:
            '%(person)s confirmed that the question is solved:',
        QuestionAction.COMMENT:
            '%(person)s posted a new comment:',
        QuestionAction.GIVEINFO:
            '%(person)s gave more information on the question:',
        QuestionAction.REOPEN:
            '%(person)s is still having a problem:',
        QuestionAction.ANSWER:
            '%(person)s proposed the following answer:',
        QuestionAction.EXPIRE:
            '%(person)s expired the question:',
        QuestionAction.REJECT:
            '%(person)s rejected the question:',
        QuestionAction.SETSTATUS:
            '%(person)s changed the question status:',
    }

    def getNewMessageText(self):
        """Should return the notification text related to a new message."""
        if not self.new_message:
            return ''

        header = self.action_header_template.get(
            self.new_message.action, '%(person)s posted a new message:') % {
            'person': self.new_message.owner.displayname}

        return '\n'.join([
            header, self.wrapper.format(self.new_message.text_contents)])


class QuestionModifiedOwnerNotification(QuestionModifiedDefaultNotification):
    """Notification sent to the owner when his question is modified."""

    recipient_set = QuestionRecipientSet.ASKER
    # These actions will be done by the owner, so use the second person.
    action_header_template = dict(
        QuestionModifiedDefaultNotification.action_header_template)
    action_header_template.update({
        QuestionAction.CONFIRM:
            'You confirmed that the question is solved:',
        QuestionAction.GIVEINFO:
            'You gave more information on the question:',
        QuestionAction.REOPEN:
            'You are still having a problem:',
        })

    body_template = 'question-modified-owner-notification.txt'

    body_template_by_action = {
        QuestionAction.ANSWER: "question-answered-owner-notification.txt",
        QuestionAction.EXPIRE: "question-expired-owner-notification.txt",
        QuestionAction.REJECT: "question-rejected-owner-notification.txt",
        QuestionAction.REQUESTINFO: (
            "question-info-requested-owner-notification.txt"),
    }

    def initialize(self):
        """Set the template based on the new comment action."""
        QuestionModifiedDefaultNotification.initialize(self)
        if self.new_message:
            self.body_template = self.body_template_by_action.get(
                self.new_message.action, self.body_template)

    def getBody(self):
        """See QuestionNotification."""
        body = QuestionModifiedDefaultNotification.getBody(self)
        if self.unsupported_language:
            body += self.unsupported_language_warning
        return body


class QuestionUnsupportedLanguageNotification(QuestionNotification):
    """Notification sent to answer contacts for unsupported languages."""

    recipient_set = QuestionRecipientSet.CONTACT

    def getSubject(self):
        """See QuestionNotification."""
        return '[Question #%s]: (%s) %s' % (
            self.question.id, self.question.language.englishname,
            self.question.title)

    def shouldNotify(self):
        """Return True when the question is in an unsupported language."""
        return self.unsupported_language

    def getBody(self):
        """See QuestionNotification."""
        question = self.question
        return get_email_template(
                'question-unsupported-languages-added.txt') % {
            'target_name': question.target.displayname,
            'question_id': question.id,
            'question_url': canonical_url(question),
            'question_language': question.language.englishname,
            'comment': question.description}
