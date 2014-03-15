# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces including and related to IJob."""

__metaclass__ = type

__all__ = [
    'IJob',
    'IJobSource',
    'IRunnableJob',
    'ITwistedJobSource',
    'JobStatus',
    'JobType',
    ]


from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Text,
    )

from lp import _
from lp.registry.interfaces.person import IPerson


class JobStatus(DBEnumeratedType):
    """Values that IJob.status can take."""

    WAITING = DBItem(0, """
        Waiting

        The job is waiting to be run.
        """)

    RUNNING = DBItem(1, """
        Running

        The job is currently running.
        """)

    COMPLETED = DBItem(2, """
        Completed

        The job has run to successful completion.
        """)

    FAILED = DBItem(3, """
        Failed

        The job was run, but failed.  Will not be run again.
        """)

    SUSPENDED = DBItem(4, """
        Suspended

        The job is suspended, so should not be run.
        """)


class JobType(DBEnumeratedType):

    GENERATE_PACKAGE_DIFF = DBItem(0, """
        Generate Package Diff

        Job to generate the diff between two SourcePackageReleases.
        """)

    UPLOAD_PACKAGE_TRANSLATIONS = DBItem(1, """
        Upload Package Translations

        Job to upload package translations files and attach them to a
        SourcePackageRelease.
        """)


class IJob(Interface):
    """Basic attributes of a job."""

    job_id = Int(title=_(
        'A unique identifier for this job.'))

    scheduled_start = Datetime(
        title=_('Time when the IJob was scheduled to start.'))

    date_created = Datetime(title=_('Time when the IJob was created.'))

    date_started = Datetime(title=_('Time when the IJob started.'))

    date_finished = Datetime(title=_('Time when the IJob ended.'))

    lease_expires = Datetime(title=_('Time when the lease expires.'))

    log = Text(title=_('The log of the job.'))

    status = Choice(
        vocabulary=JobStatus, readonly=True,
        description=_("The current state of the job."))

    attempt_count = Int(title=_(
        'The number of attempts to perform this job that have been made.'))

    max_retries = Int(title=_(
        'The number of retries permitted before this job permanently fails.'))

    requester = Reference(
        IPerson, title=_("The person who requested the job"),
        required=False, readonly=True
        )

    is_pending = Bool(
        title=_("Whether or not this job's status is such that it "
                "could eventually complete."))

    is_runnable = Bool(
        title=_("Whether or not this job is ready to be run immediately."))

    base_json_data = Attribute("A dict of data about the job.")

    base_job_type = Choice(
        vocabulary=JobType, readonly=True,
        description=_("What type of job this is, only used for jobs that "
            "do not have their own tables."))

    def acquireLease(duration=300):
        """Acquire the lease for this Job, or raise LeaseHeld."""

    def getTimeout():
        """Determine how long this job can run before timing out."""

    def start(manage_transaction=False):
        """Mark the job as started."""

    def complete(manage_transaction=False):
        """Mark the job as completed."""

    def fail(manage_transaction=False):
        """Indicate that the job has failed permanently.

        Only running jobs can fail.
        """

    def queue(manage_transaction=False, abort_transaction=False):
        """Mark the job as queued for processing."""

    def suspend(manage_transaction=False):
        """Mark the job as suspended.

        Only waiting jobs can be suspended."""

    def resume():
        """Mark the job as waiting.

        Only suspended jobs can be resumed."""


class IRunnableJob(IJob):
    """Interface for jobs that can be run via the JobRunner."""

    def notifyOops(oops):
        """Notify interested parties that this job produced an OOPS.

        :param oops: The oops produced by this Job.
        """

    def getOopsVars():
        """Return a list of variables to appear in the OOPS.

        These vars should help determine why the jobs OOPsed.
        """

    def getOperationDescription():
        """Describe the operation being performed, for use in oops emails.

        Should grammatically fit the phrase "error while FOO", e.g. "error
        while sending mail."
        """

    user_error_types = Attribute(
        'A tuple of exception classes which result from user error.')

    retry_error_types = Attribute(
        'A tuple of exception classes which should cause a retry.')

    def notifyUserError(e):
        """Notify interested parties that this job encountered a user error.

        :param e: The exception encountered by this job.
        """

    def run():
        """Run this job."""

    def celeryRunOnCommit():
        """Request Celery to run this job on transaction commit."""


class IJobSource(Interface):
    """Interface for creating and getting jobs."""

    memory_limit = Int(
        title=_('Maximum amount of memory which may be used by the process.'))

    def iterReady():
        """Iterate through all jobs."""

    def contextManager():
        """Get a context for running this kind of job in."""


class ITwistedJobSource(IJobSource):
    """Interface for a job source that is usable by the TwistedJobRunner."""

    def get(id):
        """Get a job by its id."""
