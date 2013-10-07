# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Celery-specific Job code.

Because celery sets up configuration at import time, code that is not designed
to use Celery may break if this is used.
"""

__metaclass__ = type

__all__ = [
    'CeleryRunJob',
    'CeleryRunJobIgnoreResult',
    ]

from logging import info
import os
from uuid import uuid4


os.environ.setdefault('CELERY_CONFIG_MODULE', 'lp.services.job.celeryconfig')
from celery.task import Task
from lazr.jobrunner.celerytask import RunJob
from storm.zope.interfaces import IZStorm
import transaction
from zope.component import getUtility

from lp.code.model.branchjob import BranchScanJob
from lp.scripts.helpers import TransactionFreeOperation
from lp.services.config import dbconfig
from lp.services.database.interfaces import IStore
from lp.services.features import (
    install_feature_controller,
    make_script_feature_controller,
    )
from lp.services.mail.sendmail import set_immediate_mail_delivery
from lp.services.job.model.job import (
    Job,
    UniversalJobSource,
    )
from lp.services.job.runner import (
    BaseJobRunner,
    celery_enabled,
    )
from lp.services import scripts


class CeleryRunJob(RunJob):
    """The Celery Task that runs a job."""

    job_source = UniversalJobSource

    def getJobRunner(self):
        """Return a BaseJobRunner, to support customization."""
        return BaseJobRunner()

    def run(self, job_id, dbuser):
        """Run the specified job.

        :param job_id: The job to run, as expected by UniversalJobSource.
            (Job.id, module_name, class_name)
        :param dbuser: The database user to run under.  This should match the
            dbuser specified by the job's config.
        """
        task_init(dbuser)
        super(CeleryRunJob, self).run(job_id)


class CeleryRunJobIgnoreResult(CeleryRunJob):

    ignore_result = True


class FindMissingReady:

    def __init__(self, job_source):
        from lp.services.job.celeryjob import CeleryRunJob
        from lazr.jobrunner.celerytask import list_queued
        self.job_source = job_source
        self.queue_contents = list_queued(CeleryRunJob.app,
                                          [job_source.task_queue])
        self.queued_job_ids = set(task[1][0][0] for task in
                                  self.queue_contents)

    def find_missing_ready(self):
        return [job for job in self.job_source.iterReady()
                if job.job_id not in self.queued_job_ids]


def find_missing_ready(job_source):
    """Find ready jobs that are not queued."""
    return FindMissingReady(job_source).find_missing_ready()


class RunMissingReady(Task):
    """Task to run any jobs that are ready but not scheduled.

    Currently supports only BranchScanJob.
    :param _no_init: For tests.  If True, do not perform the initialization.
    """
    ignore_result = True

    def run(self, _no_init=False):
        if not _no_init:
            task_init('run_missing_ready')
        with TransactionFreeOperation():
            count = 0
            for job in find_missing_ready(BranchScanJob):
                if not celery_enabled(job.__class__.__name__):
                    continue
                job.celeryCommitHook(True)
                count += 1
            info('Scheduled %d missing jobs.', count)
            transaction.commit()

    def apply_async(self, args=None, kwargs=None, task_id=None, publisher=None,
                    connection=None, router=None, queues=None, **options):
        """Create a task_id if none is specified.

        Override the quite generic default task_id with one containing
        the class name.

        See also `celery.task.Task.apply_async()`.
        """
        if task_id is None:
            task_id = '%s_%s' % (self.__class__.__name__, uuid4())
        return super(RunMissingReady, self).apply_async(
            args, kwargs, task_id, publisher, connection, router, queues,
            **options)


needs_zcml = True


def ensure_zcml():
    """Ensure the zcml has been executed for the current process."""
    global needs_zcml
    if not needs_zcml:
        return
    transaction.abort()
    scripts.execute_zcml_for_scripts(use_web_security=False)
    set_immediate_mail_delivery(True)
    needs_zcml = False


def task_init(dbuser):
    """Prepare to run a task.

    :param dbuser: The database user to use for running the task.
    """
    ensure_zcml()
    transaction.abort()
    store = IStore(Job)
    getUtility(IZStorm).remove(store)
    store.close()
    dbconfig.override(dbuser=dbuser, isolation_level='read_committed')
    install_feature_controller(make_script_feature_controller('celery'))
