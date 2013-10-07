# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for job-running facilities."""

import logging
import re
import sys
from textwrap import dedent
from time import sleep

from lazr.jobrunner.jobrunner import (
    LeaseHeld,
    SuspendJobException,
    )
from testtools.matchers import MatchesRegex
from testtools.testcase import ExpectedException
import transaction
from zope.interface import implements

from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import (
    IRunnableJob,
    JobStatus,
    )
from lp.services.job.model.job import Job
from lp.services.job.runner import (
    BaseRunnableJob,
    celery_enabled,
    JobRunner,
    TwistedJobRunner,
    )
from lp.services.log.logger import BufferLogger
from lp.services.webapp import errorlog
from lp.testing import (
    TestCaseWithFactory,
    ZopeTestInSubProcess,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.mail_helpers import pop_notifications


class NullJob(BaseRunnableJob):
    """A job that does nothing but append a string to a list."""

    implements(IRunnableJob)

    JOB_COMPLETIONS = []

    def __init__(self, completion_message, oops_recipients=None,
                 error_recipients=None):
        self.message = completion_message
        self.job = Job()
        self.oops_recipients = oops_recipients
        if self.oops_recipients is None:
            self.oops_recipients = []
        self.error_recipients = error_recipients
        if self.error_recipients is None:
            self.error_recipients = []

    def run(self):
        NullJob.JOB_COMPLETIONS.append(self.message)

    def getOopsRecipients(self):
        return self.oops_recipients

    def getOopsVars(self):
        return [('foo', 'bar')]

    def getErrorRecipients(self):
        return self.error_recipients

    def getOperationDescription(self):
        return 'appending a string to a list'


class RaisingJobException(Exception):
    """Raised by the RaisingJob when run."""


class RaisingJob(NullJob):
    """A job that raises when it runs."""

    def run(self):
        raise RaisingJobException(self.message)


class RaisingJobUserError(NullJob):
    """A job that raises a user error when it runs."""

    user_error_types = (RaisingJobException, )

    def run(self):
        raise RaisingJobException(self.message)


class RaisingJobRaisingNotifyOops(NullJob):
    """A job that raises when it runs, and when calling notifyOops."""

    def run(self):
        raise RaisingJobException(self.message)

    def notifyOops(self, oops):
        raise RaisingJobException('oops notifying oops')


class RaisingJobRaisingNotifyUserError(NullJob):
    """A job that raises when it runs, and when notifying user errors."""

    user_error_types = (RaisingJobException, )

    def run(self):
        raise RaisingJobException(self.message)

    def notifyUserError(self, error):
        raise RaisingJobException('oops notifying users')


class RetryError(Exception):
    pass


class RaisingRetryJob(NullJob):

    retry_error_types = (RetryError,)

    max_retries = 1

    def run(self):
        raise RetryError()


class TestJobRunner(TestCaseWithFactory):
    """Ensure JobRunner behaves as expected."""

    layer = LaunchpadZopelessLayer

    def makeTwoJobs(self):
        """Test fixture.  Create two jobs."""
        return NullJob("job 1"), NullJob("job 2")

    def test_runJob(self):
        """Ensure status is set to completed when a job runs to completion."""
        job_1, job_2 = self.makeTwoJobs()
        runner = JobRunner(job_1)
        runner.runJob(job_1, None)
        self.assertEqual(JobStatus.COMPLETED, job_1.job.status)
        self.assertEqual([job_1], runner.completed_jobs)

    def test_runAll(self):
        """Ensure runAll works in the normal case."""
        job_1, job_2 = self.makeTwoJobs()
        runner = JobRunner([job_1, job_2])
        runner.runAll()
        self.assertEqual(JobStatus.COMPLETED, job_1.job.status)
        self.assertEqual(JobStatus.COMPLETED, job_2.job.status)
        msg1 = NullJob.JOB_COMPLETIONS.pop()
        msg2 = NullJob.JOB_COMPLETIONS.pop()
        self.assertEqual(msg1, "job 2")
        self.assertEqual(msg2, "job 1")
        self.assertEqual([job_1, job_2], runner.completed_jobs)

    def test_runAll_skips_lease_failures(self):
        """Ensure runAll skips jobs whose leases can't be acquired."""
        job_1, job_2 = self.makeTwoJobs()
        job_2.job.acquireLease()
        runner = JobRunner([job_1, job_2])
        runner.runAll()
        self.assertEqual(JobStatus.COMPLETED, job_1.job.status)
        self.assertEqual(JobStatus.WAITING, job_2.job.status)
        self.assertEqual([job_1], runner.completed_jobs)
        self.assertEqual([job_2], runner.incomplete_jobs)
        self.assertEqual([], self.oopses)

    def test_runAll_reports_oopses(self):
        """When an error is encountered, report an oops and continue."""
        job_1, job_2 = self.makeTwoJobs()

        def raiseError():
            # Ensure that jobs which call transaction.abort work, too.
            transaction.abort()
            raise Exception('Fake exception.  Foobar, I say!')
        job_1.run = raiseError
        runner = JobRunner([job_1, job_2])
        runner.runAll()
        self.assertEqual([], pop_notifications())
        self.assertEqual([job_2], runner.completed_jobs)
        self.assertEqual([job_1], runner.incomplete_jobs)
        self.assertEqual(JobStatus.FAILED, job_1.job.status)
        self.assertEqual(JobStatus.COMPLETED, job_2.job.status)
        oops = self.oopses[-1]
        self.assertIn('Fake exception.  Foobar, I say!', oops['tb_text'])
        self.assertEqual(["{'foo': 'bar'}"], oops['req_vars'].values())

    def test_oops_messages_used_when_handling(self):
        """Oops messages should appear even when exceptions are handled."""
        job_1, job_2 = self.makeTwoJobs()

        def handleError():
            reporter = errorlog.globalErrorUtility
            try:
                raise ValueError('Fake exception.  Foobar, I say!')
            except ValueError:
                reporter.raising(sys.exc_info())
        job_1.run = handleError
        runner = JobRunner([job_1, job_2])
        runner.runAll()
        oops = self.oopses[-1]
        self.assertEqual(["{'foo': 'bar'}"], oops['req_vars'].values())

    def test_runAll_aborts_transaction_on_error(self):
        """runAll should abort the transaction on oops."""

        class DBAlterJob(NullJob):

            def __init__(self):
                super(DBAlterJob, self).__init__('')

            def run(self):
                self.job.log = 'hello'
                raise ValueError

        job = DBAlterJob()
        runner = JobRunner([job])
        runner.runAll()
        # If the transaction was committed, job.log == 'hello'.  If it was
        # aborted, it is None.
        self.assertIs(None, job.job.log)

    def test_runAll_mails_oopses(self):
        """Email interested parties about OOPses."""
        job_1, job_2 = self.makeTwoJobs()

        def raiseError():
            # Ensure that jobs which call transaction.abort work, too.
            transaction.abort()
            raise Exception('Fake exception.  Foobar, I say!')
        job_1.run = raiseError
        job_1.oops_recipients = ['jrandom@example.org']
        runner = JobRunner([job_1, job_2])
        runner.runAll()
        (notification,) = pop_notifications()
        oops = self.oopses[-1]
        self.assertIn(
            'Launchpad encountered an internal error during the following'
            ' operation: appending a string to a list.  It was logged with id'
            ' %s.  Sorry for the inconvenience.' % oops['id'],
            notification.get_payload(decode=True))
        self.assertNotIn('Fake exception.  Foobar, I say!',
                         notification.get_payload(decode=True))
        self.assertEqual('Launchpad internal error', notification['subject'])

    def test_runAll_mails_user_errors(self):
        """User errors should be mailed out without oopsing.

        User errors are identified by the RunnableJob.user_error_types
        attribute.  They do not cause an oops to be recorded, and their
        error messages are mailed to interested parties verbatim.
        """
        job_1, job_2 = self.makeTwoJobs()

        class ExampleError(Exception):
            pass

        def raiseError():
            raise ExampleError('Fake exception.  Foobar, I say!')
        job_1.run = raiseError
        job_1.user_error_types = (ExampleError,)
        job_1.error_recipients = ['jrandom@example.org']
        runner = JobRunner([job_1, job_2])
        runner.runAll()
        self.assertEqual([], self.oopses)
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        body = notifications[0].get_payload(decode=True)
        self.assertEqual(
            'Launchpad encountered an error during the following operation:'
            ' appending a string to a list.  Fake exception.  Foobar, I say!',
            body)
        self.assertEqual(
            'Launchpad error while appending a string to a list',
            notifications[0]['subject'])

    def test_runAll_requires_IRunnable(self):
        """Supplied classes must implement IRunnableJob.

        If they don't, we get a TypeError.  If they do, then we get an
        AttributeError, because we don't actually implement the interface.
        """
        runner = JobRunner([object()])
        self.assertRaises(TypeError, runner.runAll)

        class Runnable:
            implements(IRunnableJob)
        runner = JobRunner([Runnable()])
        self.assertRaises(AttributeError, runner.runAll)

    def test_runJob_records_failure(self):
        """When a job fails, the failure needs to be recorded."""
        job = RaisingJob('boom')
        runner = JobRunner([job])
        self.assertRaises(RaisingJobException, runner.runJob, job, None)
        # Abort the transaction to confirm that the update of the job status
        # has been committed.
        transaction.abort()
        self.assertEqual(JobStatus.FAILED, job.job.status)

    def test_runJobHandleErrors_oops_generated(self):
        """The handle errors method records an oops for raised errors."""
        job = RaisingJob('boom')
        runner = JobRunner([job])
        runner.runJobHandleError(job)
        self.assertEqual(1, len(self.oopses))

    def test_runJobHandleErrors_user_error_no_oops(self):
        """If the job raises a user error, there is no oops."""
        job = RaisingJobUserError('boom')
        runner = JobRunner([job])
        runner.runJobHandleError(job)
        self.assertEqual(0, len(self.oopses))

    def test_runJob_raising_retry_error(self):
        """If a job raises a retry_error, it should be re-queued."""
        job = RaisingRetryJob('completion')
        runner = JobRunner([job])
        with self.expectedLog('Scheduling retry due to RetryError'):
            runner.runJob(job, None)
        self.assertEqual(JobStatus.WAITING, job.status)
        self.assertNotIn(job, runner.completed_jobs)
        self.assertIn(job, runner.incomplete_jobs)

    def test_runJob_exceeding_max_retries(self):
        """If a job exceeds maximum retries, it should raise normally."""
        job = RaisingRetryJob('completion')
        JobRunner([job]).runJob(job, None)
        self.assertEqual(JobStatus.WAITING, job.status)
        runner = JobRunner([job])
        with ExpectedException(RetryError, ''):
            runner.runJob(job, None)
        self.assertEqual(JobStatus.FAILED, job.status)
        self.assertNotIn(job, runner.completed_jobs)
        self.assertIn(job, runner.incomplete_jobs)

    def test_runJobHandleErrors_oops_generated_notify_fails(self):
        """A second oops is logged if the notification of the oops fails."""
        job = RaisingJobRaisingNotifyOops('boom')
        runner = JobRunner([job])
        runner.runJobHandleError(job)
        self.assertEqual(2, len(self.oopses))

    def test_runJobHandleErrors_oops_generated_user_notify_fails(self):
        """A second oops is logged if the notification of the oops fails.

        In this test case the error is a user expected error, so the
        notifyUserError is called, and in this case the notify raises too.
        """
        job = RaisingJobRaisingNotifyUserError('boom')
        runner = JobRunner([job])
        runner.runJobHandleError(job)
        self.assertEqual(1, len(self.oopses))

    def test_runJob_with_SuspendJobException(self):
        # A job that raises SuspendJobError should end up suspended.
        job = NullJob('suspended')
        job.run = FakeMethod(failure=SuspendJobException())
        runner = JobRunner([job])
        runner.runJob(job, None)

        self.assertEqual(JobStatus.SUSPENDED, job.status)
        self.assertNotIn(job, runner.completed_jobs)
        self.assertIn(job, runner.incomplete_jobs)

    def test_taskId(self):
        # BaseRunnableJob.taskId() creates a task ID that consists
        # of the Job's class name, the job ID and a UUID.
        job = NullJob(completion_message="doesn't matter")
        task_id = job.taskId()
        uuid_expr = (
            '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
        mo = re.search('^NullJob_%s_%s$' % (job.job_id, uuid_expr), task_id)
        self.assertIsNot(None, mo)


class StaticJobSource(BaseRunnableJob):

    @classmethod
    def iterReady(cls):
        if not cls.done:
            for index, args in enumerate(cls.jobs):
                yield cls.get(index)
        cls.done = True

    @classmethod
    def get(cls, index):
        args = cls.jobs[index]
        return cls(index, *args)


class StuckJob(StaticJobSource):
    """Simulation of a job that stalls."""
    implements(IRunnableJob)

    done = False

    # A list of jobs to run: id, lease_length, delay.
    #
    # For the first job, have a very long lease, so that it
    # doesn't expire and so we soak up the ZCML loading time.  For the
    # second job, have a short lease so we hit the timeout.
    jobs = [
        (10000, 0),
        (5, 30),
        ]

    def __init__(self, id, lease_length, delay):
        self.id = id
        self.lease_length = lease_length
        self.delay = delay
        self.job = Job()

    def __repr__(self):
        return '<%s(%r, lease_length=%s, delay=%s)>' % (
            self.__class__.__name__, self.id, self.lease_length, self.delay)

    def acquireLease(self):
        return self.job.acquireLease(self.lease_length)

    def run(self):
        sleep(self.delay)


class ShorterStuckJob(StuckJob):
    """Simulation of a job that stalls."""

    jobs = [
        (10000, 0),
        (0.05, 30),
        ]


class InitialFailureJob(StaticJobSource):

    implements(IRunnableJob)

    jobs = [(True,), (False,)]

    has_failed = False

    done = False

    def __init__(self, id, fail):
        self.id = id
        self.job = Job()
        self.fail = fail

    def run(self):
        if self.fail:
            InitialFailureJob.has_failed = True
            raise ValueError('I failed.')
        else:
            if InitialFailureJob.has_failed:
                raise ValueError('Previous failure.')


class ProcessSharingJob(StaticJobSource):

    implements(IRunnableJob)

    jobs = [(True,), (False,)]

    initial_job_was_here = False

    done = False

    def __init__(self, id, first):
        self.id = id
        self.job = Job()
        self.first = first

    def run(self):
        if self.first:
            ProcessSharingJob.initial_job_was_here = True
        else:
            if not ProcessSharingJob.initial_job_was_here:
                raise ValueError('Different process.')


class MemoryHogJob(StaticJobSource):

    implements(IRunnableJob)

    jobs = [()]

    done = False

    memory_limit = 0

    def __init__(self, id):
        self.job = Job()
        self.id = id

    def run(self):
        self.x = '*' * (10 ** 6)


class NoJobs(StaticJobSource):

    done = False

    jobs = []


class LeaseHeldJob(StaticJobSource):

    implements(IRunnableJob)

    jobs = [()]

    done = False

    def __init__(self, id):
        self.job = Job()
        self.id = id

    def acquireLease(self):
        raise LeaseHeld()


class TestTwistedJobRunner(ZopeTestInSubProcess, TestCaseWithFactory):

    # Needs AMQP
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTwistedJobRunner, self).setUp()
        # The test relies on _pythonpath being importable. Thus we need to add
        # a directory that contains _pythonpath to the sys.path. We can rely
        # on the root directory of the checkout containing _pythonpath.
        if config.root not in sys.path:
            sys.path.append(config.root)
            self.addCleanup(sys.path.remove, config.root)

    def test_timeout_long(self):
        """When a job exceeds its lease, an exception is raised.

        Unfortunately, timeouts include the time it takes for the zope
        machinery to start up, so we run a job that will not time out first,
        followed by a job that is sure to time out.
        """
        logger = BufferLogger()
        logger.setLevel(logging.INFO)
        # StuckJob is actually a source of two jobs. The first is fast, the
        # second slow.
        runner = TwistedJobRunner.runFromSource(
            StuckJob, 'branchscanner', logger)

        self.assertEqual(
            (1, 1), (len(runner.completed_jobs), len(runner.incomplete_jobs)))
        self.oops_capture.sync()
        oops = self.oopses[0]
        expected_exception = ('TimeoutError', 'Job ran too long.')
        self.assertEqual(expected_exception, (oops['type'], oops['value']))
        self.assertThat(logger.getLogBuffer(), MatchesRegex(
            dedent("""\
                INFO Running through Twisted.
                INFO Running <StuckJob.*?> \(ID .*?\).
                INFO Running <StuckJob.*?> \(ID .*?\).
                INFO Job resulted in OOPS: .*
            """)))

    # XXX: BradCrittenden 2012-05-09 bug=994777: Disabled as a spurious
    # failure.  In isolation this test fails 5% of the time.
    def disabled_test_timeout_short(self):
        """When a job exceeds its lease, an exception is raised.

        Unfortunately, timeouts include the time it takes for the zope
        machinery to start up, so we run a job that will not time out first,
        followed by a job that is sure to time out.
        """
        logger = BufferLogger()
        logger.setLevel(logging.INFO)
        # StuckJob is actually a source of two jobs. The first is fast, the
        # second slow.
        runner = TwistedJobRunner.runFromSource(
            ShorterStuckJob, 'branchscanner', logger)
        self.oops_capture.sync()
        oops = self.oopses[0]
        self.assertEqual(
            (1, 1), (len(runner.completed_jobs), len(runner.incomplete_jobs)))
        self.assertThat(
            logger.getLogBuffer(), MatchesRegex(
                dedent("""\
                INFO Running through Twisted.
                INFO Running <ShorterStuckJob.*?> \(ID .*?\).
                INFO Running <ShorterStuckJob.*?> \(ID .*?\).
                INFO Job resulted in OOPS: %s
                """) % oops['id']))
        self.assertEqual(('TimeoutError', 'Job ran too long.'),
                         (oops['type'], oops['value']))

    def test_previous_failure_gives_new_process(self):
        """Failed jobs cause their worker to be terminated.

        When a job fails, it's not clear whether its process can be safely
        reused for a new job, so we kill the worker.
        """
        logger = BufferLogger()
        runner = TwistedJobRunner.runFromSource(
            InitialFailureJob, 'branchscanner', logger)
        self.assertEqual(
            (1, 1), (len(runner.completed_jobs), len(runner.incomplete_jobs)))

    def test_successful_jobs_share_process(self):
        """Successful jobs allow process reuse.

        When a job succeeds, we assume that its process can be safely reused
        for a new job, so we reuse the worker.
        """
        logger = BufferLogger()
        runner = TwistedJobRunner.runFromSource(
            ProcessSharingJob, 'branchscanner', logger)
        self.assertEqual(
            (2, 0), (len(runner.completed_jobs), len(runner.incomplete_jobs)))

    def disable_test_memory_hog_job(self):
        """A job with a memory limit will trigger MemoryError on excess."""
        # XXX: frankban 2012-03-29 bug=963455: This test fails intermittently,
        # especially in parallel tests.
        logger = BufferLogger()
        logger.setLevel(logging.INFO)
        runner = TwistedJobRunner.runFromSource(
            MemoryHogJob, 'branchscanner', logger)
        self.assertEqual(
            (0, 1), (len(runner.completed_jobs), len(runner.incomplete_jobs)))
        self.assertIn('Job resulted in OOPS', logger.getLogBuffer())
        self.oops_capture.sync()
        self.assertEqual('MemoryError', self.oopses[0]['type'])

    def test_no_jobs(self):
        logger = BufferLogger()
        logger.setLevel(logging.INFO)
        runner = TwistedJobRunner.runFromSource(
            NoJobs, 'branchscanner', logger)
        self.assertEqual(
            (0, 0), (len(runner.completed_jobs), len(runner.incomplete_jobs)))

    def test_lease_held_handled(self):
        """Jobs that raise LeaseHeld are handled correctly."""
        logger = BufferLogger()
        logger.setLevel(logging.DEBUG)
        runner = TwistedJobRunner.runFromSource(
            LeaseHeldJob, 'branchscanner', logger)
        self.assertIn('Could not acquire lease', logger.getLogBuffer())
        self.assertEqual(
            (0, 1), (len(runner.completed_jobs), len(runner.incomplete_jobs)))


class TestCeleryEnabled(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_no_flag(self):
        """With no flag set, result is False."""
        self.assertFalse(celery_enabled('foo'))

    def test_matching_flag(self):
        """A matching flag returns True."""
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'foo bar'}))
        self.assertTrue(celery_enabled('foo'))
        self.assertTrue(celery_enabled('bar'))

    def test_non_matching_flag(self):
        """A non-matching flag returns false."""
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'foo bar'}))
        self.assertFalse(celery_enabled('baz'))
        self.assertTrue(celery_enabled('bar'))

    def test_substring(self):
        """A substring of an enabled class does not match."""
        self.useFixture(FeatureFixture(
            {'jobs.celery.enabled_classes': 'foobar'}))
        self.assertFalse(celery_enabled('bar'))
