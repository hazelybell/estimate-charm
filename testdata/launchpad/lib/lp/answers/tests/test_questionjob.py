# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for QuestionJobs classes."""

__metaclass__ = type

from testtools.content import Content
from testtools.content_type import UTF8_TEXT
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.answers.enums import (
    QuestionJobType,
    QuestionRecipientSet,
    )
from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.answers.interfaces.questionjob import (
    IQuestionEmailJob,
    IQuestionEmailJobSource,
    IQuestionJob,
    )
from lp.answers.model.questionjob import (
    QuestionEmailJob,
    QuestionJob,
    )
from lp.services.database.interfaces import IStore
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.tests import (
    block_on_job,
    pop_remote_notifications,
    )
from lp.services.log.logger import BufferLogger
from lp.services.mail import stub
from lp.services.mail.sendmail import (
    format_address,
    format_address_for_person,
    )
from lp.services.scripts import log
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    run_script,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    CeleryJobLayer,
    DatabaseFunctionalLayer,
    )


class QuestionJobTestCase(TestCaseWithFactory):
    """Test case for base QuestionJob class."""

    layer = DatabaseFunctionalLayer

    def test_instantiate(self):
        question = self.factory.makeQuestion()
        metadata = ('some', 'arbitrary', 'metadata')
        job = QuestionJob(
            question, QuestionJobType.EMAIL, metadata)
        self.assertEqual(QuestionJobType.EMAIL, job.job_type)
        self.assertEqual(question, job.question)
        # Metadata is unserialized from JSON.
        metadata_expected = list(metadata)
        self.assertEqual(metadata_expected, job.metadata)
        self.assertProvides(job, IQuestionJob)

    def test_repr(self):
        question = self.factory.makeQuestion()
        metadata = []
        question_job = QuestionJob(
            question, QuestionJobType.EMAIL, metadata)
        self.assertEqual(
            '<QuestionJob for question %s; status=Waiting>' % question.id,
            repr(question_job))


def make_user_subject_body_headers(factory):
    user = factory.makePerson()
    subject = 'email subject'
    body = 'email body'
    headers = {'X-Launchpad-Question': 'question metadata'}
    return user, subject, body, headers


def make_question_job(factory, recipient_set=QuestionRecipientSet.SUBSCRIBER,
                      body=None, question=None, user=None):
    if question is None:
        question = factory.makeQuestion()
    default_user, subject, default_body, headers = (
        make_user_subject_body_headers(factory))
    if body is None:
        body = default_body
    if user is None:
        user = default_user
    contact = factory.makePerson()
    with person_logged_in(contact):
        lang_set = getUtility(ILanguageSet)
        contact.addLanguage(lang_set['en'])
        question.target.addAnswerContact(contact, contact)
    return QuestionEmailJob.create(
        question, user, recipient_set,
        subject, body, headers)


class QuestionEmailJobTestCase(TestCaseWithFactory):
    """Test case for QuestionEmailJob class."""

    layer = DatabaseFunctionalLayer

    def test_create(self):
        # The create class method converts the extra job arguments
        # to metadata.
        question = self.factory.makeQuestion()
        user, subject, body, headers = make_user_subject_body_headers(
            self.factory)
        job = QuestionEmailJob.create(
            question, user, QuestionRecipientSet.SUBSCRIBER,
            subject, body, headers)
        self.assertEqual(QuestionJobType.EMAIL, job.job_type)
        self.assertEqual(question, job.question)
        self.assertContentEqual(
            ['body', 'headers', 'recipient_set', 'subject', 'user'],
            job.metadata.keys())
        self.assertEqual(user.id, job.metadata['user'])
        self.assertEqual(
            QuestionRecipientSet.SUBSCRIBER.name,
            job.metadata['recipient_set'])
        self.assertEqual(subject, job.metadata['subject'])
        self.assertEqual(body, job.metadata['body'])
        self.assertEqual(
            headers['X-Launchpad-Question'],
            job.metadata['headers']['X-Launchpad-Question'])
        self.assertProvides(job, IQuestionEmailJob)

    def test_iterReady(self):
        # Jobs in the ready state are returned by the iterator.
        # Creating a question implicitly created an question email job.
        asker = self.factory.makePerson()
        product = self.factory.makeProduct()
        naked_question_set = removeSecurityProxy(getUtility(IQuestionSet))
        question = naked_question_set.new(
            title='title', description='description', owner=asker,
            language=getUtility(ILanguageSet)['en'],
            product=product, distribution=None, sourcepackagename=None)
        job_1 = make_question_job(self.factory, question=question, body='one')
        job_2 = make_question_job(self.factory, question=question, body='two')
        job_3 = make_question_job(
            self.factory, question=question, body='three')
        job_1.start()
        job_1.complete()
        job_ids = [job.id for job in QuestionEmailJob.iterReady()]
        self.assertContentEqual([job_2.id, job_3.id], job_ids)

    def test_user(self):
        # The user property matches the user passed to create().
        user = self.factory.makePerson()
        job = make_question_job(self.factory, user=user)
        self.assertEqual(user, job.user)

    def test_subject(self):
        # The subject property matches the subject passed to create().
        body = 'email body'
        job = make_question_job(self.factory, body=body)
        self.assertEqual(body, job.body)

    def test_body(self):
        # The body property matches the body passed to create().
        body = 'email body'
        job = make_question_job(self.factory, body=body)
        self.assertEqual(body, job.body)

    def test_headers(self):
        # The headers property matches the headers passed to create().
        question = self.factory.makeQuestion()
        user, subject, body, headers = make_user_subject_body_headers(
            self.factory)
        job = QuestionEmailJob.create(
            question, user, QuestionRecipientSet.SUBSCRIBER,
            subject, body, headers)
        self.assertEqual(headers, job.headers)

    def test_from_address(self):
        # The from_address is the question with the user displayname.
        question = self.factory.makeQuestion()
        user, subject, body, headers = make_user_subject_body_headers(
            self.factory)
        job = QuestionEmailJob.create(
            question, user, QuestionRecipientSet.SUBSCRIBER,
            subject, body, headers)
        address = format_address(
            user.displayname,
            "question%s@answers.launchpad.net" % question.id)
        self.assertEqual(address, job.from_address)

    def test_log_name(self):
        # The log_name property matches the class name.
        job = make_question_job(self.factory)
        self.assertEqual(job.__class__.__name__, job.log_name)

    def test_getOopsVars(self):
        # The getOopsVars() method adds the question and user to the vars.
        question = self.factory.makeQuestion()
        user, subject, body, headers = make_user_subject_body_headers(
            self.factory)
        job = QuestionEmailJob.create(
            question, user, QuestionRecipientSet.SUBSCRIBER,
            subject, body, headers)
        oops_vars = job.getOopsVars()
        self.assertTrue(('question', question.id) in oops_vars)
        self.assertTrue(('user', user.name) in oops_vars)

    def test_getErrorRecipients(self):
        # The getErrorRecipients method matches the user.
        job = make_question_job(self.factory)
        self.assertEqual(
            [format_address_for_person(job.user)], job.getErrorRecipients())

    def test_recipients_asker(self):
        # The recipients property contains the question owner.
        job = make_question_job(self.factory, QuestionRecipientSet.ASKER)
        recipients = [
            person for email, person in job.recipients.getRecipientPersons()]
        self.assertEqual(1, len(recipients))
        self.assertEqual(job.question.owner, recipients[0])

    def test_recipients_subscriber(self):
        # The recipients property matches the question recipients,
        # excluding the question owner.
        job = make_question_job(self.factory)
        recipients = [
            person for email, person in job.recipients.getRecipientPersons()]
        self.assertFalse(job.question.owner in recipients)
        question_recipients = [
            person for em, person in
            job.question.getRecipients().getRecipientPersons()
            if person != job.question.owner]
        self.assertContentEqual(
            question_recipients, recipients)

    def test_recipients_asker_subscriber(self):
        # The recipients property matches the question recipients.
        job = make_question_job(
            self.factory, QuestionRecipientSet.ASKER_SUBSCRIBER)
        self.assertContentEqual(
            job.question.getRecipients().getRecipientPersons(),
            job.recipients.getRecipientPersons())

    def test_recipients_contact(self):
        # The recipients property matches the question target answer contacts.
        job = make_question_job(
            self.factory, QuestionRecipientSet.CONTACT)
        recipients = [
            person for email, person in job.recipients.getRecipientPersons()]
        self.assertContentEqual(
            job.question.target.getAnswerContactRecipients(None),
            recipients)

    def test_buildBody_with_separator(self):
        # A body with a separator is preserved.
        job = make_question_job(self.factory, body='body\n-- ')
        formatted_body = job.buildBody('rationale')
        self.assertEqual(
            'body\n-- \nrationale', formatted_body)

    def test_buildBody_without_separator(self):
        # A separator will added to body if one is not present.
        job = make_question_job(self.factory, body='body -- mdash')
        formatted_body = job.buildBody('rationale')
        self.assertEqual(
            'body -- mdash\n-- \nrationale', formatted_body)

    def test_buildBody_wrapping(self):
        # The rationale is wrapped and added to the body.
        body = 'body\n-- '
        job = make_question_job(self.factory, body=body)
        rationale_1 = (
            'You received this email because you are indirectly subscribed '
            'to this')
        rationale_2 = 'question via the ~illuminati team.'
        rationale = '%s %s' % (rationale_1, rationale_2)
        formatted_body = job.buildBody(rationale)
        expected_rationale = '%s\n%s' % (rationale_1, rationale_2)
        self.assertEqual(
            body + '\n' + expected_rationale, formatted_body)

    def test_run(self):
        # The email is sent to all the recipients.
        job = make_question_job(
            self.factory, QuestionRecipientSet.ASKER_SUBSCRIBER)
        logger = BufferLogger()
        with log.use(logger):
            job.run()
        self.assertEqual(
            ["DEBUG QuestionEmailJob will send email for question %s." %
             job.question.id,
             "DEBUG QuestionEmailJob has sent email for question %s." %
             job.question.id],
            logger.getLogBuffer().splitlines())
        transaction.commit()
        self.assertEqual(2, len(stub.test_emails))

    def test_run_cronscript(self):
        # The cronscript is configured: schema-lazr.conf and security.cfg.
        job = make_question_job(
            self.factory, QuestionRecipientSet.ASKER_SUBSCRIBER)
        question = job.question
        with person_logged_in(question.target.owner):
            question.linkBug(self.factory.makeBug(target=question.target))
            question.linkFAQ(
                question.target.owner,
                self.factory.makeFAQ(target=question.target),
                'test FAQ link')
        user = job.user
        with person_logged_in(user):
            lang_set = getUtility(ILanguageSet)
            user.addLanguage(lang_set['en'])
            question.target.addAnswerContact(user, user)
        transaction.commit()

        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IQuestionEmailJobSource.getName()))
        self.addDetail("stdout", Content(UTF8_TEXT, lambda: out))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: err))
        self.assertEqual(0, exit_code)
        self.assertTrue(
            'Traceback (most recent call last)' not in err)
        message = (
            'QuestionEmailJob has sent email for question %s.' % question.id)
        self.assertTrue(
            message in err,
            'Cound not find "%s" in err log:\n%s.' % (message, err))
        IStore(job.job).invalidate()
        self.assertEqual(JobStatus.COMPLETED, job.job.status)


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_run(self):
        # The email is sent to all the recipients.
        # Create the question before turning on the feature flag to avoid
        # running two jobs via Celery.
        question = self.factory.makeQuestion()
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'QuestionEmailJob',
        }))
        body = self.factory.getUniqueString('body')
        make_question_job(
            self.factory, QuestionRecipientSet.ASKER_SUBSCRIBER,
            question=question, body=body)
        with block_on_job(self):
            transaction.commit()
        transaction.commit()
        mail = pop_remote_notifications()
        self.assertEqual(2, len(mail))
        for message in mail:
            self.assertIn(body, message.get_payload())
