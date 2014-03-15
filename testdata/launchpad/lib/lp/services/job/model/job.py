# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ORM object representing jobs."""

__metaclass__ = type
__all__ = [
    'EnumeratedSubclass',
    'InvalidTransition',
    'Job',
    'UniversalJobSource',
    ]


from calendar import timegm
import datetime
import time

from lazr.jobrunner.jobrunner import LeaseHeld
import pytz
from sqlobject import StringCol
from storm.expr import (
    And,
    Or,
    Select,
    )
from storm.locals import (
    Int,
    JSON,
    Reference,
    )
import transaction
from zope.interface import implements

from lp.services.database import bulk
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import SQLBase
from lp.services.job.interfaces.job import (
    IJob,
    JobStatus,
    JobType,
    )


UTC = pytz.timezone('UTC')


class InvalidTransition(Exception):
    """Invalid transition from one job status to another attempted."""

    def __init__(self, current_status, requested_status):
        Exception.__init__(
            self, 'Transition from %s to %s is invalid.' %
            (current_status, requested_status))


class Job(SQLBase):
    """See `IJob`."""

    implements(IJob)

    @property
    def job_id(self):
        return self.id

    scheduled_start = UtcDateTimeCol()

    date_created = UtcDateTimeCol()

    date_started = UtcDateTimeCol()

    date_finished = UtcDateTimeCol()

    lease_expires = UtcDateTimeCol()

    log = StringCol()

    _status = EnumCol(
        enum=JobStatus, notNull=True, default=JobStatus.WAITING,
        dbName='status')

    attempt_count = Int(default=0)

    max_retries = Int(default=0)

    requester_id = Int(name='requester', allow_none=True)
    requester = Reference(requester_id, 'Person.id')

    base_json_data = JSON(name='json_data')

    base_job_type = EnumCol(enum=JobType, dbName='job_type')

    # Mapping of valid target states from a given state.
    _valid_transitions = {
        JobStatus.WAITING:
            (JobStatus.RUNNING,
             JobStatus.SUSPENDED),
        JobStatus.RUNNING:
            (JobStatus.COMPLETED,
             JobStatus.FAILED,
             JobStatus.SUSPENDED,
             JobStatus.WAITING),
        JobStatus.FAILED: (),
        JobStatus.COMPLETED: (),
        JobStatus.SUSPENDED:
            (JobStatus.WAITING,),
        }

    # Set of all states where the job could eventually complete.
    PENDING_STATUSES = frozenset(
        (JobStatus.WAITING,
         JobStatus.RUNNING,
         JobStatus.SUSPENDED))

    def _set_status(self, status):
        if status not in self._valid_transitions[self._status]:
            raise InvalidTransition(self._status, status)
        self._status = status

    status = property(lambda x: x._status)

    @property
    def is_pending(self):
        """See `IJob`."""
        return self.status in self.PENDING_STATUSES

    @property
    def is_runnable(self):
        """See `IJob`."""
        return self.status == JobStatus.WAITING

    @classmethod
    def createMultiple(self, store, num_jobs, requester=None):
        """Create multiple `Job`s at once.

        :param store: `Store` to ceate the jobs in.
        :param num_jobs: Number of `Job`s to create.
        :param request: The `IPerson` requesting the jobs.
        :return: An iterable of `Job.id` values for the new jobs.
        """
        return bulk.create(
                (Job._status, Job.requester),
                [(JobStatus.WAITING, requester) for i in range(num_jobs)],
                get_primary_keys=True)

    def acquireLease(self, duration=300):
        """See `IJob`."""
        if (self.lease_expires is not None
            and self.lease_expires >= datetime.datetime.now(UTC)):
            raise LeaseHeld
        expiry = datetime.datetime.fromtimestamp(time.time() + duration,
            UTC)
        self.lease_expires = expiry

    def getTimeout(self):
        """Return the number of seconds until the job should time out.

        Jobs timeout when their leases expire.  If the lease for this job has
        already expired, return 0.
        """
        expiry = timegm(self.lease_expires.timetuple())
        return max(0, expiry - time.time())

    def start(self, manage_transaction=False):
        """See `IJob`."""
        self._set_status(JobStatus.RUNNING)
        self.date_started = datetime.datetime.now(UTC)
        self.date_finished = None
        self.attempt_count += 1
        if manage_transaction:
            transaction.commit()

    def complete(self, manage_transaction=False):
        """See `IJob`."""
        # Commit the transaction to update the DB time.
        if manage_transaction:
            transaction.commit()
        self._set_status(JobStatus.COMPLETED)
        self.date_finished = datetime.datetime.now(UTC)
        if manage_transaction:
            transaction.commit()

    def fail(self, manage_transaction=False):
        """See `IJob`."""
        if manage_transaction:
            transaction.abort()
        self._set_status(JobStatus.FAILED)
        self.date_finished = datetime.datetime.now(UTC)
        if manage_transaction:
            transaction.commit()

    def queue(self, manage_transaction=False, abort_transaction=False,
              add_commit_hook=None):
        """See `IJob`."""
        if manage_transaction:
            if abort_transaction:
                transaction.abort()
            # Commit the transaction to update the DB time.
            transaction.commit()
        self._set_status(JobStatus.WAITING)
        self.date_finished = datetime.datetime.now(UTC)
        if add_commit_hook is not None:
            add_commit_hook()
        if manage_transaction:
            transaction.commit()

    def suspend(self, manage_transaction=False):
        """See `IJob`."""
        self._set_status(JobStatus.SUSPENDED)
        if manage_transaction:
            transaction.commit()

    def resume(self):
        """See `IJob`."""
        if self.status is not JobStatus.SUSPENDED:
            raise InvalidTransition(self._status, JobStatus.WAITING)
        self._set_status(JobStatus.WAITING)
        self.lease_expires = None


class EnumeratedSubclass(type):
    """Metaclass for when subclasses are assigned enums."""

    def __init__(cls, name, bases, dict_):
        if getattr(cls, '_subclass', None) is None:
            cls._subclass = {}
        job_type = dict_.get('class_job_type')
        if job_type is not None:
            value = cls._subclass.setdefault(job_type, cls)
            assert value is cls, (
                '%s already registered to %s.' % (
                    job_type.name, value.__name__))
        # Perform any additional set-up requested by class.
        cls._register_subclass(cls)

    @staticmethod
    def _register_subclass(cls):
        pass

    def makeSubclass(cls, job):
        return cls._subclass[job.job_type](job)


Job.ready_jobs = Select(
    Job.id,
    And(
        Job._status == JobStatus.WAITING,
        Or(Job.lease_expires == None, Job.lease_expires < UTC_NOW),
        Or(Job.scheduled_start == None, Job.scheduled_start <= UTC_NOW),
        ))


class UniversalJobSource:
    """Returns the RunnableJob associated with a Job.id."""

    memory_limit = 2 * (1024 ** 3)

    @staticmethod
    def get(ujob_id):
        """Return the named job database class.

        :param ujob_id: A tuple of Job.id, module name, class name for the
            class to retrieve.
        Return derived job class.
        """
        job_id, module_name, class_name = ujob_id
        bc_module = __import__(module_name, fromlist=[class_name])
        db_class = getattr(bc_module, class_name)
        factory = getattr(db_class, 'makeInstance', None)
        if factory is not None:
            return factory(job_id)
        # This method can be called with two distinct types of Jobs:
        # - Jobs that are backed by a DB table with a foreign key onto Job.
        # - Jobs that have no backing, and are only represented by a row in
        #   the Job table, but the class name we are given is the abstract 
        #   job class.
        # If there is no __storm_table__, it is the second type, and we have
        # to look it up via the Job table.
        if getattr(db_class, '__storm_table__', None) is None:
            db_job = IStore(Job).find(Job, Job.id == job_id).one()
            # Job.makeDerived() would be a mess of circular imports, so it is
            # cleaner to just return the bare Job wrapped in the class.
            return db_class(db_job)
        # Otherwise, we have the concrete DB class, so use its FK.
        db_job = IStore(db_class).find(db_class, db_class.job == job_id).one()
        if db_job is None:
            return None
        return db_job.makeDerived()
