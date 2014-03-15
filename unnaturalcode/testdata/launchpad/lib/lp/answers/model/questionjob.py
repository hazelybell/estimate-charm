# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job classes related to QuestionJob."""

__metaclass__ = type
__all__ = [
    'QuestionJob',
    ]

from lazr.delegates import delegates
import simplejson
from storm.expr import And
from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.answers.enums import (
    QuestionJobType,
    QuestionRecipientSet,
    )
from lp.answers.interfaces.questionjob import (
    IQuestionEmailJob,
    IQuestionEmailJobSource,
    IQuestionJob,
    )
from lp.answers.model.question import Question
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IMasterStore
from lp.services.database.stormbase import StormBase
from lp.services.job.model.job import Job
from lp.services.job.runner import BaseRunnableJob
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.mail.notificationrecipientset import NotificationRecipientSet
from lp.services.mail.sendmail import (
    format_address,
    format_address_for_person,
    simple_sendmail,
    )
from lp.services.propertycache import cachedproperty
from lp.services.scripts import log


class QuestionJob(StormBase):
    """A Job for queued question emails."""

    implements(IQuestionJob)

    __storm_table__ = 'QuestionJob'

    id = Int(primary=True)

    job_id = Int(name='job')
    job = Reference(job_id, Job.id)

    job_type = EnumCol(enum=QuestionJobType, notNull=True)

    question_id = Int(name='question')
    question = Reference(question_id, Question.id)

    _json_data = Unicode('json_data')

    def __init__(self, question, job_type, metadata):
        """Constructor.

        :param question: The question related to this job.
        :param job_type: The specific job being performed for the question.
        :param metadata: The type-specific variables, as a JSON-compatible
            dict.
        """
        super(QuestionJob, self).__init__()
        self.job = Job()
        self.job_type = job_type
        self.question = question
        json_data = simplejson.dumps(metadata)
        self._json_data = json_data.decode('utf-8')

    def __repr__(self):
        return (
            "<{self.__class__.__name__} for question {self.question.id}; "
            "status={self.job.status}>").format(self=self)

    @property
    def metadata(self):
        """See `IQuestionJob`."""
        return simplejson.loads(self._json_data)

    def makeDerived(self):
        if self.job_type != QuestionJobType.EMAIL:
            raise ValueError('Unsupported Job type')
        return QuestionEmailJob(self)


class QuestionEmailJob(BaseRunnableJob):
    """Intermediate class for deriving from QuestionJob."""

    delegates(IQuestionJob)
    implements(IQuestionEmailJob)
    classProvides(IQuestionEmailJobSource)
    config = config.IQuestionEmailJobSource

    def __init__(self, job):
        self.context = job

    class_job_type = QuestionJobType.EMAIL

    @classmethod
    def create(cls, question, user, recipient_set, subject, body, headers):
        """See `IQuestionJob`."""
        metadata = {
            'user': user.id,
            'recipient_set': recipient_set.name,
            'subject': subject,
            'body': body,
            'headers': headers,
            }
        job = QuestionJob(
            question=question, job_type=cls.class_job_type, metadata=metadata)
        derived = cls(job)
        derived.celeryRunOnCommit()
        return derived

    @classmethod
    def iterReady(cls):
        """See `IJobSource`."""
        store = IMasterStore(QuestionJob)
        jobs = store.find(
            QuestionJob,
            And(QuestionJob.job_type == cls.class_job_type,
                QuestionJob.job_id.is_in(Job.ready_jobs)))
        return (cls(job) for job in jobs)

    @cachedproperty
    def user(self):
        """See `IQuestionEmailJob`."""
        return getUtility(IPersonSet).get(self.metadata['user'])

    @property
    def subject(self):
        """See `IQuestionEmailJob`."""
        return self.metadata['subject']

    @property
    def body(self):
        """See `IQuestionEmailJob`."""
        return self.metadata['body']

    @property
    def headers(self):
        """See `IQuestionEmailJob`."""
        return self.metadata['headers']

    @property
    def log_name(self):
        """See `IRunnableJob`."""
        return self.__class__.__name__

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BaseRunnableJob.getOopsVars(self)
        vars.extend([
            ('question', self.question.id),
            ('user', self.user.name),
            ])
        return vars

    def getErrorRecipients(self):
        """See `IRunnableJob`."""
        return [format_address_for_person(self.user)]

    @property
    def from_address(self):
        """See `IQuestionEmailJob`."""
        address = 'question%s@%s' % (
            self.question.id, config.answertracker.email_domain)
        return format_address(self.user.displayname, address)

    @property
    def recipients(self):
        """See `IQuestionEmailJob`."""
        term = QuestionRecipientSet.getTermByToken(
            self.metadata['recipient_set'])
        question_recipient_set = term.value
        if question_recipient_set == QuestionRecipientSet.ASKER:
            recipients = NotificationRecipientSet()
            owner = self.question.owner
            original_recipients = self.question.direct_recipients
            if owner in original_recipients:
                rationale, header = original_recipients.getReason(owner)
                recipients.add(owner, rationale, header)
            return recipients
        elif question_recipient_set == QuestionRecipientSet.SUBSCRIBER:
            recipients = self.question.getRecipients()
            if self.question.owner in recipients:
                recipients.remove(self.question.owner)
            return recipients
        elif question_recipient_set == QuestionRecipientSet.ASKER_SUBSCRIBER:
            return self.question.getRecipients()
        elif question_recipient_set == QuestionRecipientSet.CONTACT:
            return self.question.target.getAnswerContactRecipients(None)
        else:
            raise ValueError(
                'Unsupported QuestionRecipientSet value: %s' %
                question_recipient_set)

    def buildBody(self, rationale):
        """See `IQuestionEmailJob`."""
        wrapper = MailWrapper()
        body_parts = [self.body, wrapper.format(rationale)]
        if '\n-- ' not in self.body:
            body_parts.insert(1, '-- ')
        return '\n'.join(body_parts)

    def run(self):
        """See `IRunnableJob`.

        Send emails to all the question recipients.
        """
        log.debug(
            "%s will send email for question %s.",
            self.log_name, self.question.id)
        headers = self.headers
        recipients = self.recipients
        for email in recipients.getEmails():
            rationale, header = recipients.getReason(email)
            headers['X-Launchpad-Message-Rationale'] = header
            formatted_body = self.buildBody(rationale)
            simple_sendmail(
                self.from_address, email, self.subject, formatted_body,
                headers)
        log.debug(
            "%s has sent email for question %s.",
            self.log_name, self.question.id)
