# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Facilities for running Jobs."""

__metaclass__ = type

__all__ = [
    'BaseJobRunner',
    'BaseRunnableJob',
    'BaseRunnableJobSource',
    'celery_enabled',
    'JobRunner',
    'JobRunnerProcess',
    'TwistedJobRunner',
    ]


from calendar import timegm
import contextlib
from datetime import (
    datetime,
    timedelta,
    )
import logging
import os
from resource import (
    getrlimit,
    RLIMIT_AS,
    setrlimit,
    )
from signal import (
    SIGHUP,
    signal,
    )
import sys
from uuid import uuid4

from ampoule import (
    child,
    main,
    pool,
    )
from lazr.delegates import delegates
from lazr.jobrunner.jobrunner import (
    JobRunner as LazrJobRunner,
    LeaseHeld,
    )
from storm.exceptions import LostObjectError
import transaction
from twisted.internet import reactor
from twisted.internet.defer import (
    inlineCallbacks,
    succeed,
    )
from twisted.protocols import amp
from twisted.python import (
    failure,
    log,
    )
from zope.security.proxy import removeSecurityProxy

from lp.services import scripts
from lp.services.config import (
    config,
    dbconfig,
    )
from lp.services.features import getFeatureFlag
from lp.services.job.interfaces.job import (
    IJob,
    IRunnableJob,
    )
from lp.services.mail.sendmail import (
    MailController,
    set_immediate_mail_delivery,
    )
from lp.services.twistedsupport import run_reactor
from lp.services.webapp import errorlog


class BaseRunnableJobSource:
    """Base class for job sources for the job runner."""

    memory_limit = None

    @staticmethod
    @contextlib.contextmanager
    def contextManager():
        yield


class BaseRunnableJob(BaseRunnableJobSource):
    """Base class for jobs to be run via JobRunner.

    Derived classes should implement IRunnableJob, which requires implementing
    IRunnableJob.run.  They should have a `job` member which implements IJob.

    Subclasses may provide getOopsRecipients, to send mail about oopses.
    If so, they should also provide getOperationDescription.
    """
    delegates(IJob, 'job')

    user_error_types = ()

    retry_error_types = ()

    task_queue = 'launchpad_job'

    celery_responses = None

    retry_delay = timedelta(minutes=10)

    # We redefine __eq__ and __ne__ here to prevent the security proxy
    # from mucking up our comparisons in tests and elsewhere.
    def __eq__(self, job):
        naked_job = removeSecurityProxy(job)
        return (
            self.__class__ is naked_job.__class__ and
            self.__dict__ == naked_job.__dict__)

    def __ne__(self, job):
        return not (self == job)

    def __lt__(self, job):
        naked_job = removeSecurityProxy(job)
        if self.__class__ is naked_job.__class__:
            return self.__dict__ < naked_job.__dict__
        else:
            return NotImplemented

    def getOopsRecipients(self):
        """Return a list of email-ids to notify about oopses."""
        return self.getErrorRecipients()

    def getOperationDescription(self):
        return 'unspecified operation'

    def getErrorRecipients(self):
        """Return a list of email-ids to notify about user errors."""
        return []

    def getOopsMailController(self, oops_id):
        """Return a MailController for notifying people about oopses.

        Return None if there is no-one to notify.
        """
        recipients = self.getOopsRecipients()
        if len(recipients) == 0:
            return None
        subject = 'Launchpad internal error'
        body = (
            'Launchpad encountered an internal error during the following'
            ' operation: %s.  It was logged with id %s.  Sorry for the'
            ' inconvenience.' % (self.getOperationDescription(), oops_id))
        from_addr = config.canonical.noreply_from_address
        return MailController(from_addr, recipients, subject, body)

    def getUserErrorMailController(self, e):
        """Return a MailController for notifying about user errors.

        Return None if there is no-one to notify.
        """
        recipients = self.getErrorRecipients()
        if len(recipients) == 0:
            return None
        subject = 'Launchpad error while %s' % self.getOperationDescription()
        body = (
            'Launchpad encountered an error during the following'
            ' operation: %s.  %s' % (self.getOperationDescription(), str(e)))
        from_addr = config.canonical.noreply_from_address
        return MailController(from_addr, recipients, subject, body)

    def notifyOops(self, oops):
        """Report this oops."""
        ctrl = self.getOopsMailController(oops['id'])
        if ctrl is not None:
            ctrl.send()

    def getOopsVars(self):
        """See `IRunnableJob`."""
        return [('job_id', self.job.id)]

    def notifyUserError(self, e):
        """See `IRunnableJob`."""
        ctrl = self.getUserErrorMailController(e)
        if ctrl is not None:
            ctrl.send()

    def makeOopsReport(self, oops_config, info):
        """Generate an OOPS report using the given OOPS configuration."""
        return oops_config.create(
            context=dict(exc_info=info))

    def taskId(self):
        """Return a task ID that gives a clue what this job is about.

        Though we intend to drop the result return by a Celery job
        (in the sense that we don't care what
        lazr.jobrunner.celerytask.RunJob.run() returns), we might
        accidentally create result queues, for example, when a job fails.
        The messages stored in these queues are often not very specific,
        the queues names are just the IDs of the task, which are by
        default just strings returned by Celery's uuid() function.

        If we put the job's class name and the job ID into the task ID,
        we have better chances to figure out what went wrong than by just
        look for example at a message like

            {'status': 'FAILURE',
            'traceback': None,
            'result': SoftTimeLimitExceeded(1,),
            'task_id': 'cba7d07b-37fe-4f1d-a5f6-79ad7c30222f'}
        """
        return '%s_%s_%s' % (
            self.__class__.__name__, self.job_id, uuid4())

    def runViaCelery(self, ignore_result=False):
        """Request that this job be run via celery."""
        # Avoid importing from lp.services.job.celeryjob where not needed, to
        # avoid configuring Celery when Rabbit is not configured.
        from lp.services.job.celeryjob import (
            CeleryRunJob, CeleryRunJobIgnoreResult)
        if ignore_result:
            cls = CeleryRunJobIgnoreResult
        else:
            cls = CeleryRunJob
        db_class = self.getDBClass()
        ujob_id = (self.job_id, db_class.__module__, db_class.__name__)
        if self.job.lease_expires is not None:
            eta = datetime.now() + self.retry_delay
        else:
            eta = None
        return cls.apply_async(
            (ujob_id, self.config.dbuser), queue=self.task_queue, eta=eta,
            task_id=self.taskId())

    def getDBClass(self):
        return self.context.__class__

    def celeryCommitHook(self, succeeded):
        """Hook function to call when a commit completes."""
        if succeeded:
            ignore_result = bool(BaseRunnableJob.celery_responses is None)
            response = self.runViaCelery(ignore_result)
            if not ignore_result:
                BaseRunnableJob.celery_responses.append(response)

    def celeryRunOnCommit(self):
        """Configure transaction so that commit runs this job via Celery."""
        if not celery_enabled(self.__class__.__name__):
            return
        current = transaction.get()
        current.addAfterCommitHook(self.celeryCommitHook)

    def queue(self, manage_transaction=False, abort_transaction=False):
        """See `IJob`."""
        self.job.queue(
            manage_transaction, abort_transaction,
            add_commit_hook=self.celeryRunOnCommit)


class BaseJobRunner(LazrJobRunner):
    """Runner of Jobs."""

    def __init__(self, logger=None, error_utility=None):
        self.oops_ids = []
        if error_utility is None:
            self.error_utility = errorlog.globalErrorUtility
        else:
            self.error_utility = error_utility
        super(BaseJobRunner, self).__init__(
            logger, oops_config=self.error_utility._oops_config,
            oopsMessage=self.error_utility.oopsMessage)

    def acquireLease(self, job):
        self.logger.debug(
            'Trying to acquire lease for job in state %s' % (
                job.status.title,))
        try:
            job.acquireLease()
        except LeaseHeld:
            self.logger.info(
                'Could not acquire lease for %s' % self.job_str(job))
            self.incomplete_jobs.append(job)
            return False
        return True

    def runJob(self, job, fallback):
        super(BaseJobRunner, self).runJob(IRunnableJob(job), fallback)

    def userErrorTypes(self, job):
        return removeSecurityProxy(job).user_error_types

    def retryErrorTypes(self, job):
        return removeSecurityProxy(job).retry_error_types

    def _doOops(self, job, info):
        """Report an OOPS for the provided job and info.

        :param job: The IRunnableJob whose run failed.
        :param info: The standard sys.exc_info() value.
        :return: the Oops that was reported.
        """
        oops = self.error_utility.raising(info)
        job.notifyOops(oops)
        self._logOopsId(oops['id'])
        return oops

    def _logOopsId(self, oops_id):
        """Report oopses by id to the log."""
        if self.logger is not None:
            self.logger.info('Job resulted in OOPS: %s' % oops_id)
        self.oops_ids.append(oops_id)


class JobRunner(BaseJobRunner):

    def __init__(self, jobs, logger=None):
        BaseJobRunner.__init__(self, logger=logger)
        self.jobs = jobs

    @classmethod
    def fromReady(cls, job_class, logger=None):
        """Return a job runner for all ready jobs of a given class."""
        return cls(job_class.iterReady(), logger)

    @classmethod
    def runFromSource(cls, job_source, dbuser, logger):
        """Run all ready jobs provided by the specified source.

        The dbuser parameter is ignored.
        """
        with removeSecurityProxy(job_source.contextManager()):
            logger.info("Running synchronously.")
            runner = cls.fromReady(job_source, logger)
            runner.runAll()
        return runner

    def runAll(self):
        """Run all the Jobs for this JobRunner."""
        for job in self.jobs:
            job = IRunnableJob(job)
            if not self.acquireLease(job):
                continue
            # Commit transaction to clear the row lock.
            transaction.commit()
            self.runJobHandleError(job)


class RunJobCommand(amp.Command):

    arguments = [('job_id', amp.Integer())]
    response = [('success', amp.Integer()), ('oops_id', amp.String())]


def import_source(job_source_name):
    """Return the IJobSource specified by its full name."""
    module, name = job_source_name.rsplit('.', 1)
    source_module = __import__(module, fromlist=[name])
    return getattr(source_module, name)


class JobRunnerProcess(child.AMPChild):
    """Base class for processes that run jobs."""

    def __init__(self, job_source_name, dbuser):
        child.AMPChild.__init__(self)
        self.job_source = import_source(job_source_name)
        self.context_manager = self.job_source.contextManager()
        # icky, but it's really a global value anyhow.
        self.__class__.dbuser = dbuser

    @classmethod
    def __enter__(cls):
        def handler(signum, frame):
            # We raise an exception **and** schedule a call to exit the
            # process hard.  This is because we cannot rely on the exception
            # being raised during useful code.  Sometimes, it will be raised
            # while the reactor is looping, which means that it will be
            # ignored.
            #
            # If the exception is raised during the actual job, then we'll get
            # a nice traceback indicating what timed out, and that will be
            # logged as an OOPS.
            #
            # Regardless of where the exception is raised, we'll hard exit the
            # process and have a TimeoutError OOPS logged, although that will
            # have a crappy traceback. See the job_raised callback in
            # TwistedJobRunner.runJobInSubprocess for the other half of that.
            reactor.callFromThread(
                reactor.callLater, 0, os._exit, TwistedJobRunner.TIMEOUT_CODE)
            raise TimeoutError
        scripts.execute_zcml_for_scripts(use_web_security=False)
        signal(SIGHUP, handler)
        dbconfig.override(dbuser=cls.dbuser, isolation_level='read_committed')
        # XXX wgrant 2011-09-24 bug=29744: initZopeless used to do this.
        # Should be removed from callsites verified to not need it.
        set_immediate_mail_delivery(True)

    @staticmethod
    def __exit__(exc_type, exc_val, exc_tb):
        pass

    def makeConnection(self, transport):
        """The Job context is entered on connect."""
        child.AMPChild.makeConnection(self, transport)
        self.context_manager.__enter__()

    def connectionLost(self, reason):
        """The Job context is left on disconnect."""
        self.context_manager.__exit__(None, None, None)
        child.AMPChild.connectionLost(self, reason)

    @RunJobCommand.responder
    def runJobCommand(self, job_id):
        """Run a job from this job_source according to its job id."""
        runner = BaseJobRunner()
        job = self.job_source.get(job_id)
        if self.job_source.memory_limit is not None:
            soft_limit, hard_limit = getrlimit(RLIMIT_AS)
            if soft_limit != self.job_source.memory_limit:
                limits = (self.job_source.memory_limit, hard_limit)
                setrlimit(RLIMIT_AS, limits)
        oops = runner.runJobHandleError(job)
        if oops is None:
            oops_id = ''
        else:
            oops_id = oops['id']
        return {'success': len(runner.completed_jobs), 'oops_id': oops_id}


class TwistedJobRunner(BaseJobRunner):
    """Run Jobs via twisted."""

    TIMEOUT_CODE = 42

    def __init__(self, job_source, dbuser, logger=None, error_utility=None):
        env = {'PATH': os.environ['PATH']}
        if 'LPCONFIG' in os.environ:
            env['LPCONFIG'] = os.environ['LPCONFIG']
        env['PYTHONPATH'] = os.pathsep.join(sys.path)
        starter = main.ProcessStarter(env=env)
        super(TwistedJobRunner, self).__init__(logger, error_utility)
        self.job_source = job_source
        self.import_name = '%s.%s' % (
            removeSecurityProxy(job_source).__module__, job_source.__name__)
        self.pool = pool.ProcessPool(
            JobRunnerProcess, ampChildArgs=[self.import_name, str(dbuser)],
            starter=starter, min=0, timeout_signal=SIGHUP)

    def runJobInSubprocess(self, job):
        """Run the job_class with the specified id in the process pool.

        :return: a Deferred that fires when the job has completed.
        """
        job = IRunnableJob(job)
        if not self.acquireLease(job):
            return succeed(None)
        # Commit transaction to clear the row lock.
        transaction.commit()
        job_id = job.id
        deadline = timegm(job.lease_expires.timetuple())

        # Log the job class and database ID for debugging purposes.
        self.logger.info(
            'Running %s.' % self.job_str(job))
        self.logger.debug(
            'Running %r, lease expires %s', job, job.lease_expires)
        deferred = self.pool.doWork(
            RunJobCommand, job_id=job_id, _deadline=deadline)

        def update(response):
            if response is None:
                self.incomplete_jobs.append(job)
                self.logger.debug('No response for %r', job)
                return
            if response['success']:
                self.completed_jobs.append(job)
                self.logger.debug('Finished %r', job)
            else:
                self.incomplete_jobs.append(job)
                self.logger.debug('Incomplete %r', job)
                # Kill the worker that experienced a failure; this only
                # works because there's a single worker.
                self.pool.stopAWorker()
            if response['oops_id'] != '':
                self._logOopsId(response['oops_id'])

        def job_raised(failure):
            try:
                exit_code = getattr(failure.value, 'exitCode', None)
                if exit_code == self.TIMEOUT_CODE:
                    # The process ended with the error code that we have
                    # arbitrarily chosen to indicate a timeout. Rather than log
                    # that error (ProcessDone), we log a TimeoutError instead.
                    self._logTimeout(job)
                else:
                    info = (failure.type, failure.value, failure.tb)
                    oops = self._doOops(job, info)
                    self._logOopsId(oops['id'])
            except LostObjectError:
                # The job may have been deleted, so we can ignore this error.
                pass
            else:
                self.incomplete_jobs.append(job)
        deferred.addCallbacks(update, job_raised)
        return deferred

    def _logTimeout(self, job):
        try:
            raise TimeoutError
        except TimeoutError:
            oops = self._doOops(job, sys.exc_info())
            self._logOopsId(oops['id'])

    @inlineCallbacks
    def runAll(self):
        """Run all ready jobs."""
        self.pool.start()
        try:
            try:
                job = None
                for job in self.job_source.iterReady():
                    yield self.runJobInSubprocess(job)
                if job is None:
                    self.logger.info('No jobs to run.')
                self.terminated()
            except:
                self.failed(failure.Failure())
        except:
            self.terminated()
            raise

    def terminated(self, ignored=None):
        """Callback to stop the processpool and reactor."""
        deferred = self.pool.stop()
        deferred.addBoth(lambda ignored: reactor.stop())

    def failed(self, failure):
        """Callback for when the job fails."""
        failure.printTraceback()
        self.terminated()

    @classmethod
    def runFromSource(cls, job_source, dbuser, logger, _log_twisted=False):
        """Run all ready jobs provided by the specified source.

        The dbuser parameter is not ignored.
        :param _log_twisted: For debugging: If True, emit verbose Twisted
            messages to stderr.
        """
        logger.info("Running through Twisted.")
        if _log_twisted:
            logging.getLogger().setLevel(0)
            logger_object = logging.getLogger('twistedjobrunner')
            handler = logging.StreamHandler(sys.stderr)
            logger_object.addHandler(handler)
            observer = log.PythonLoggingObserver(
                loggerName='twistedjobrunner')
            log.startLoggingWithObserver(observer.emit)
        runner = cls(job_source, dbuser, logger)
        reactor.callWhenRunning(runner.runAll)
        run_reactor()
        return runner


class TimeoutError(Exception):

    def __init__(self):
        Exception.__init__(self, "Job ran too long.")


def celery_enabled(class_name):
    """Determine whether a given class is configured to run via Celery.

    The name of a BaseRunnableJob must be specified.
    """
    flag = getFeatureFlag('jobs.celery.enabled_classes')
    if flag is None:
        return False
    return class_name in flag.split(' ')
