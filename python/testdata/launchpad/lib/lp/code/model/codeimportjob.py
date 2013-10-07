# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes for the CodeImportJob table."""

__metaclass__ = type
__all__ = [
    'CodeImportJob',
    'CodeImportJobSet',
    'CodeImportJobWorkflow',
    ]

import datetime

from sqlobject import (
    ForeignKey,
    IntCol,
    SQLObjectNotFound,
    StringCol,
    )
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.code.enums import (
    CodeImportJobState,
    CodeImportMachineState,
    CodeImportResultStatus,
    CodeImportReviewStatus,
    )
from lp.code.interfaces.codeimportevent import ICodeImportEventSet
from lp.code.interfaces.codeimportjob import (
    ICodeImportJob,
    ICodeImportJobSet,
    ICodeImportJobSetPublic,
    ICodeImportJobWorkflow,
    )
from lp.code.interfaces.codeimportmachine import ICodeImportMachineSet
from lp.code.interfaces.codeimportresult import ICodeImportResultSet
from lp.code.model.codeimportresult import CodeImportResult
from lp.registry.interfaces.person import validate_public_person
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )


class CodeImportJob(SQLBase):
    """See `ICodeImportJob`."""

    implements(ICodeImportJob)

    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    code_import = ForeignKey(
        dbName='code_import', foreignKey='CodeImport', notNull=True)

    machine = ForeignKey(
        dbName='machine', foreignKey='CodeImportMachine',
        notNull=False, default=None)

    date_due = UtcDateTimeCol(notNull=True)

    state = EnumCol(
        enum=CodeImportJobState, notNull=True,
        default=CodeImportJobState.PENDING)

    requesting_user = ForeignKey(
        dbName='requesting_user', foreignKey='Person',
        storm_validator=validate_public_person,
        notNull=False, default=None)

    ordering = IntCol(notNull=False, default=None)

    heartbeat = UtcDateTimeCol(notNull=False, default=None)

    logtail = StringCol(notNull=False, default=None)

    date_started = UtcDateTimeCol(notNull=False, default=None)

    def isOverdue(self):
        """See `ICodeImportJob`."""
        # SQLObject offers no easy way to compare a timestamp to UTC_NOW, so
        # we must use trickery here.

        # First we flush any pending update to self to ensure that the
        # following database query will give the correct result even if
        # date_due was modified in this transaction.
        self.syncUpdate()

        # Then, we try to find a CodeImportJob object with the id of self, and
        # a date_due of now or past. If we find one, this means self is
        # overdue.
        import_job = CodeImportJob.selectOne(
            "id = %s AND date_due <= %s" % sqlvalues(self.id, UTC_NOW))
        return import_job is not None


class CodeImportJobSet(object):
    """See `ICodeImportJobSet`."""

    implements(ICodeImportJobSet, ICodeImportJobSetPublic)

    # CodeImportJob database objects are created using
    # CodeImportJobWorkflow.newJob.

    def getById(self, id):
        """See `ICodeImportJobSet`."""
        try:
            return CodeImportJob.get(id)
        except SQLObjectNotFound:
            return None

    def getJobForMachine(self, hostname, worker_limit):
        """See `ICodeImportJobSet`."""
        job_workflow = getUtility(ICodeImportJobWorkflow)
        for job in self.getReclaimableJobs():
            job_workflow.reclaimJob(job)
        machine = getUtility(ICodeImportMachineSet).getByHostname(hostname)
        if machine is None:
            machine = getUtility(ICodeImportMachineSet).new(
                hostname, CodeImportMachineState.ONLINE)
        elif not machine.shouldLookForJob(worker_limit):
            return None
        job = CodeImportJob.selectOne(
            """id IN (SELECT id FROM CodeImportJob
               WHERE date_due <= %s AND state = %s
               ORDER BY requesting_user IS NULL, date_due
               LIMIT 1)"""
            % sqlvalues(UTC_NOW, CodeImportJobState.PENDING))
        if job is not None:
            job_workflow.startJob(job, machine)
            return job
        else:
            return None

    def getReclaimableJobs(self):
        """See `ICodeImportJobSet`."""
        return IStore(CodeImportJob).find(
            CodeImportJob,
            "state = %s and heartbeat < %s + '-%s seconds'"
            % sqlvalues(CodeImportJobState.RUNNING, UTC_NOW,
                        config.codeimportworker.maximum_heartbeat_interval))


class CodeImportJobWorkflow:
    """See `ICodeImportJobWorkflow`."""

    implements(ICodeImportJobWorkflow)

    def newJob(self, code_import, interval=None):
        """See `ICodeImportJobWorkflow`."""
        assert code_import.review_status == CodeImportReviewStatus.REVIEWED, (
            "Review status of %s is not REVIEWED: %s" % (
            code_import.branch.unique_name, code_import.review_status.name))
        assert code_import.import_job is None, (
            "Already associated to a CodeImportJob: %s" % (
            code_import.branch.unique_name))

        if interval is None:
            interval = code_import.effective_update_interval

        job = CodeImportJob(code_import=code_import, date_due=UTC_NOW)

        # Find the most recent CodeImportResult for this CodeImport. We
        # sort by date_created because we do not have an index on
        # date_job_started in the database, and that should give the same
        # sort order.
        most_recent_result_list = list(CodeImportResult.selectBy(
            code_import=code_import).orderBy(['-date_created']).limit(1))

        if len(most_recent_result_list) != 0:
            [most_recent_result] = most_recent_result_list
            date_due = most_recent_result.date_job_started + interval
            job.date_due = max(job.date_due, date_due)

        return job

    def deletePendingJob(self, code_import):
        """See `ICodeImportJobWorkflow`."""
        assert code_import.review_status != CodeImportReviewStatus.REVIEWED, (
            "The review status of %s is %s." % (
            code_import.branch.unique_name, code_import.review_status.name))
        assert code_import.import_job is not None, (
            "Not associated to a CodeImportJob: %s" % (
            code_import.branch.unique_name,))
        assert code_import.import_job.state == CodeImportJobState.PENDING, (
            "The CodeImportJob associated to %s is %s." % (
            code_import.branch.unique_name,
            code_import.import_job.state.name))
        # CodeImportJobWorkflow is the only class that is allowed to delete
        # CodeImportJob rows, so destroySelf is not exposed in ICodeImportJob.
        removeSecurityProxy(code_import).import_job.destroySelf()

    def requestJob(self, import_job, user):
        """See `ICodeImportJobWorkflow`."""
        assert import_job.state == CodeImportJobState.PENDING, (
            "The CodeImportJob associated with %s is %s."
            % (import_job.code_import.branch.unique_name,
               import_job.state.name))
        assert import_job.requesting_user is None, (
            "The CodeImportJob associated with %s "
            "was already requested by %s."
            % (import_job.code_import.branch.unique_name,
               import_job.requesting_user.name))
        # CodeImportJobWorkflow is the only class that is allowed to set the
        # date_due and requesting_user attributes of CodeImportJob, they are
        # not settable through ICodeImportJob. So we must use
        # removeSecurityProxy here.
        if not import_job.isOverdue():
            removeSecurityProxy(import_job).date_due = UTC_NOW
        removeSecurityProxy(import_job).requesting_user = user
        getUtility(ICodeImportEventSet).newRequest(
            import_job.code_import, user)

    def startJob(self, import_job, machine):
        """See `ICodeImportJobWorkflow`."""
        assert import_job.state == CodeImportJobState.PENDING, (
            "The CodeImportJob associated with %s is %s."
            % (import_job.code_import.branch.unique_name,
               import_job.state.name))
        assert machine.state == CodeImportMachineState.ONLINE, (
            "The machine %s is %s."
            % (machine.hostname, machine.state.name))
        # CodeImportJobWorkflow is the only class that is allowed to set the
        # date_created, heartbeat, logtail, machine and state attributes of
        # CodeImportJob, they are not settable through ICodeImportJob. So we
        # must use removeSecurityProxy here.
        naked_job = removeSecurityProxy(import_job)
        naked_job.date_started = UTC_NOW
        naked_job.heartbeat = UTC_NOW
        naked_job.logtail = u''
        naked_job.machine = machine
        naked_job.state = CodeImportJobState.RUNNING
        getUtility(ICodeImportEventSet).newStart(
            import_job.code_import, machine)

    def updateHeartbeat(self, import_job, logtail):
        """See `ICodeImportJobWorkflow`."""
        assert import_job.state == CodeImportJobState.RUNNING, (
            "The CodeImportJob associated with %s is %s."
            % (import_job.code_import.branch.unique_name,
               import_job.state.name))
        # CodeImportJobWorkflow is the only class that is allowed to
        # set the heartbeat and logtail attributes of CodeImportJob,
        # they are not settable through ICodeImportJob. So we must use
        # removeSecurityProxy here.
        naked_job = removeSecurityProxy(import_job)
        naked_job.heartbeat = UTC_NOW
        naked_job.logtail = logtail

    def _makeResultAndDeleteJob(self, import_job, status, logfile_alias):
        """Create a result for and delete 'import_job'.

        This method does some of the housekeeping required when a job has
        ended, no matter if it has finished normally or been killed or
        reclaimed.

        :param import_job: The job that has ended.
        :param status: The member of CodeImportResultStatus to create the
            result with.
        :param logfile_alias: A reference to the log file of the job, can be
            None.
        """
        result = getUtility(ICodeImportResultSet).new(
            code_import=import_job.code_import, machine=import_job.machine,
            log_excerpt=import_job.logtail,
            requesting_user=import_job.requesting_user,
            log_file=logfile_alias, status=status,
            date_job_started=import_job.date_started)
        # CodeImportJobWorkflow is the only class that is allowed to delete
        # CodeImportJob objects, there is no method in the ICodeImportJob
        # interface to do this. So we must use removeSecurityProxy here.
        naked_job = removeSecurityProxy(import_job)
        naked_job.destroySelf()
        return result

    def finishJob(self, import_job, status, logfile_alias):
        """See `ICodeImportJobWorkflow`."""
        assert import_job.state == CodeImportJobState.RUNNING, (
            "The CodeImportJob associated with %s is %s."
            % (import_job.code_import.branch.unique_name,
               import_job.state.name))
        code_import = import_job.code_import
        machine = import_job.machine
        result = self._makeResultAndDeleteJob(
            import_job, status, logfile_alias)
        # If the import has failed too many times in a row, mark it as
        # FAILING.
        failure_limit = config.codeimport.consecutive_failure_limit
        failure_count = code_import.consecutive_failure_count
        if failure_count >= failure_limit:
            code_import.updateFromData(
                dict(review_status=CodeImportReviewStatus.FAILING), None)
        elif status == CodeImportResultStatus.SUCCESS_PARTIAL:
            interval = datetime.timedelta(0)
        elif failure_count > 0:
            interval = (code_import.effective_update_interval *
                        (2 ** (failure_count - 1)))
        else:
            interval = code_import.effective_update_interval
        # Only start a new one if the import is still in the REVIEWED state.
        if code_import.review_status == CodeImportReviewStatus.REVIEWED:
            self.newJob(code_import, interval=interval)
        # If the status was successful, update date_last_successful.
        if status in [CodeImportResultStatus.SUCCESS,
                      CodeImportResultStatus.SUCCESS_NOCHANGE]:
            naked_import = removeSecurityProxy(code_import)
            naked_import.date_last_successful = result.date_created
        # If the status was successful and revisions were imported, arrange
        # for the branch to be mirrored.
        if status == CodeImportResultStatus.SUCCESS:
            code_import.branch.requestMirror()
        getUtility(ICodeImportEventSet).newFinish(
            code_import, machine)

    def reclaimJob(self, import_job):
        """See `ICodeImportJobWorkflow`."""
        assert import_job.state == CodeImportJobState.RUNNING, (
            "The CodeImportJob associated with %s is %s."
            % (import_job.code_import.branch.unique_name,
               import_job.state.name))
        # Cribbing from codeimport-job.txt, this method does four things:
        # 1) deletes the passed in job,
        # 2) creates a CodeImportResult with a status of 'RECLAIMED',
        # 3) creates a new, already due, job for the code import, and
        # 4) logs a 'RECLAIM' CodeImportEvent.
        job_id = import_job.id
        code_import = import_job.code_import
        machine = import_job.machine
        # 1) and 2)
        self._makeResultAndDeleteJob(
            import_job, CodeImportResultStatus.RECLAIMED, None)
        # 3)
        if code_import.review_status == CodeImportReviewStatus.REVIEWED:
            self.newJob(code_import, datetime.timedelta(0))
        # 4)
        getUtility(ICodeImportEventSet).newReclaim(
            code_import, machine, job_id)
