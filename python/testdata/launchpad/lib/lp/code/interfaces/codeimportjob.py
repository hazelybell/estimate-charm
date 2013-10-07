# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces and enumeratrions for CodeImportJobs.

CodeImportJobs represent pending and running updates of a code import.
"""

__metaclass__ = type
__all__ = [
    'ICodeImportJob',
    'ICodeImportJobSet',
    'ICodeImportJobSetPublic',
    'ICodeImportJobWorkflow',
    ]

from zope.interface import Interface
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Object,
    Text,
    )

from lp import _
from lp.code.enums import CodeImportJobState
from lp.code.interfaces.codeimport import ICodeImport
from lp.code.interfaces.codeimportmachine import ICodeImportMachine
from lp.registry.interfaces.person import IPerson


class ICodeImportJob(Interface):
    """A pending or active code import job.

    There is always such a row for any active import, but it will not
    run until date_due is in the past.
    """

    # Some of these attributes are not conceptually read-only but are
    # set to be read-only here to force client code to use methods
    # that update the audit trail appropriately.

    id = Int(readonly=True, required=True)

    date_created = Datetime(required=True, readonly=True)

    code_import = Object(
        schema=ICodeImport, required=True, readonly=True,
        description=_("The code import that is being worked upon."))

    machine = Object(
        schema=ICodeImportMachine, required=False, readonly=False,
        description=_("The machine job is currently scheduled to run on, or "
                      "where the job is currently running."))

    date_due = Datetime(
        required=True, readonly=True,
        description=_("When the import should happen."))

    state = Choice(
        vocabulary=CodeImportJobState, required=True, readonly=True,
        description=_("The current state of the job."))

    requesting_user = Object(
        schema=IPerson, required=False, readonly=True,
        description=_("The user who requested the import, if any."))

    ordering = Int(
        required=False, readonly=True,
        description=_("A measure of how urgent the job is -- queue entries "
                      "with lower 'ordering' should be processed first, or "
                      "in other words 'ORDER BY ordering' returns the most "
                      "import jobs first."))

    heartbeat = Datetime(
        required=False, readonly=True,
        description=_("While the job is running, this field should be "
                      "updated frequently to indicate that the import job "
                      "hasn't crashed."))

    logtail = Text(
        required=False, readonly=True,
        description=_("The last few lines of output produced by the running "
                      "job. It should be updated at the same time as the "
                      "heartbeat."))

    date_started = Datetime(
        required=False, readonly=True,
        description=_("When the import began to be processed."))

    def isOverdue():
        """Return whether `self.date_due` is now or in the past.

        This method should be used in preference to comparing date_due to the
        system clock. It does the correct thing, which is to compare date_due
        to the time of the current transaction.
        """


class ICodeImportJobSet(Interface):
    """The set of pending and active code import jobs."""

    def getById(id):
        """Get a `CodeImportJob` by its database id.

        :return: A `CodeImportJob` or None if this database id is not found.
        """

    def getReclaimableJobs():
        """Get the set of jobs that can be reclaimed.

        A job is reclaimable if its heartbeat has not been updated for
        config.codeimportworker.maximum_heartbeat_interval seconds.
        """


class ICodeImportJobSetPublic(Interface):
    """Parts of the CodeImportJobSet interface that need to be public.

    These are accessed by the getJobForMachine XML-RPC method, requests to
    which are not authenticated.
    """
    # XXX MichaelHudson 2008-02-28 bug=196345: This interface can go away when
    # we implement endpoint specific authentication for the private xml-rpc
    # server.

    def getJobForMachine(hostname, worker_limit):
        """Select a job for the given machine to run and mark it as started.

        If there is not already a CodeImportMachine with the given hostname,
        one will be created in the ONLINE state.

        This method selects a job that is due to be run for running on the
        given machine and calls ICodeImportJobWorkflowPublic.startJob() on it.
        It will return None if there is no such job.
        """


class ICodeImportJobWorkflow(Interface):
    """Utility to manage `CodeImportJob` objects through their life cycle."""

    def newJob(code_import, interval=None):
        """Create a `CodeImportJob` associated with a reviewed `CodeImport`.

        Call this method from `CodeImport.updateFromData` when the
        review_status of `code_import` changes to REVIEWED.

        :param code_import: `CodeImport` object.
        :param interval: Schedule the job this far ahead of the start of the
            last update of this import.  Defaults to
            ``code_import.effective_update_interval``.  This parameter is
            ignored and the job scheduled for right now if this is the first
            run of the import.
        :precondition: `code_import` has REVIEWED review_status.
        :precondition: `code_import` has no associated `CodeImportJob`.
        :return: A new `CodeImportJob` object associated to `code_import`.
        """

    def deletePendingJob(code_import):
        """Delete a pending `CodeImportJob` associated with a `CodeImport`.

        Call this method from `CodeImport.updateFromData` when the
        review_status of `code_import` changes from REVIEWED.

        :param code_import: `CodeImport` object.
        :precondition: `code_import`.review_status != REVIEWED.
        :precondition: `code_import` is associated to a `CodeImportJob`.
        :precondition: `code_import`.import_job.state == PENDING.
        :postcondition: `code_import`.import_job is None.
        """

    def requestJob(import_job, user):
        """Request that a job be run as soon as possible.

        :param import_job: `CodeImportJob` object.
        :param user: `Person` who makes the request.
        :precondition: `import_job`.states == PENDING.
        :precondition: `import_job`.requesting_user is None.
        :postcondition: `import_job`.date_due is now or in the past.
        :postcondition: `import_job`.request_user is set to `user`.
        :postcondition: A REQUEST `CodeImportEvent` was created.
        """

    def updateHeartbeat(import_job, logtail):
        """Updates the heartbeat of a running `CodeImportJob`.

        Call this method at regular intervals while a job is running to provide
        progress information for users and prevent the job from being reclaimed
        by the code-import watchdog.

        :param import_job: `CodeImportJob` with RUNNING state.
        :param logtail: string containing the last few lines of the progress
            output from the job.
        :precondition: `import_job`.state == RUNNING.
        :postcondition: `import_job`.heartbeat == UTC_NOW.
        :postcondition: `import_job`.logtail == logtail.
        """

    def startJob(import_job, machine):
        """Record that `machine` is about to start work on `import_job`.

        :param import_job: `CodeImportJob` object.
        :param machine: `CodeImportMachine` that will be working on the job.
        :precondition: `import_job`.state == PENDING.
        :precondition: `machine`.state == ONLINE.
        :postcondition: `import_job`.state == RUNNING.
        :postcondition: `import_job`.machine == machine.
        :postcondition: `import_job`.date_started == UTC_NOW.
        :postcondition: `import_job`.heartbeat == UTC_NOW.
        :postcondition: A START `CodeImportEvent` was created.
        """

    def finishJob(import_job, status, logfile_alias):
        """Record that a job finished running.

        This method creates a CodeImportResult object that records the outcome
        of the run, deletes `import_job` from the database and creates a new
        job that is due appropriately far into the future.

        In the conditions below, let `code_import = import_job.code_import`.

        :param import_job: `CodeImportJob` with RUNNING state.
        :param status: outcome of the job as a `CodeImportResultStatus`.
        :param logfile_alias: `LibraryFileAlias` containing a log file to
            display for diagnostics. May be None.
        :precondition: `import_job`.state == RUNNING.
        :postcondition: `import_job` is deleted.
        :postcondition: `code_import.import_job` is not None unless the job
            has failed more than consecutive_failure_limit times in a row.
        :postcondition: `code_import.import_job.date_due` is
            import_job.date_due + code_import.effective_update_interval`, with
            scaling to retry failing imports less often.
        :postcondition: A `CodeImportResult` was created.
        :postcondition: A FINISH `CodeImportEvent` was created.
        """

    def reclaimJob(import_job):
        """Record that `import_job` has been reclaimed.

        This should be called when the job's heartbeat has not been updated
        for what the code import watchdog deems is 'too long'.

        This method creates a CodeImportResult object that records that the
        job was reclaimed, deletes `import_job` from the database and creates
        a new job that is due again immediately.

        In the conditions below, let `code_import = import_job.code_import`.

        :param import_job: `CodeImportJob` object.
        :precondition: `import_job`.state == RUNNING.
        :postcondition: `import_job` is deleted.
        :postcondition: `code_import.import_job` is not None.
        :postcondition: `code_import.import_job.date_due` is UTC_NOW.
        :postcondition: A `CodeImportResult` was created.
        :postcondition: A FINISH `CodeImportEvent` was created.
        """
