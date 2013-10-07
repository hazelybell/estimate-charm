# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The code import scheduler XML-RPC API."""

__metaclass__ = type
__all__ = [
    'CodeImportSchedulerAPI',
    ]

from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.code.enums import CodeImportResultStatus
from lp.code.interfaces.codeimportjob import (
    ICodeImportJobSet,
    ICodeImportJobWorkflow,
    )
from lp.code.interfaces.codeimportscheduler import ICodeImportScheduler
from lp.codehosting.codeimport.worker import CodeImportSourceDetails
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.webapp import (
    canonical_url,
    LaunchpadXMLRPCView,
    )
from lp.xmlrpc.faults import NoSuchCodeImportJob
from lp.xmlrpc.helpers import return_fault


class CodeImportSchedulerAPI(LaunchpadXMLRPCView):
    """See `ICodeImportScheduler`."""

    implements(ICodeImportScheduler)

    def getJobForMachine(self, hostname, worker_limit):
        """See `ICodeImportScheduler`."""
        job = getUtility(ICodeImportJobSet).getJobForMachine(
            hostname, worker_limit)
        if job is not None:
            return job.id
        else:
            return 0

    def _getJob(self, job_id):
        job_set = removeSecurityProxy(getUtility(ICodeImportJobSet))
        job = removeSecurityProxy(job_set.getById(job_id))
        if job is None:
            raise NoSuchCodeImportJob(job_id)
        return job

    # Because you can't use a decorated function as the implementation of a
    # method exported over XML-RPC, the implementations just thunk to an
    # implementation wrapped with @return_fault.

    def getImportDataForJobID(self, job_id):
        """See `ICodeImportScheduler`."""
        return self._getImportDataForJobID(job_id)

    def updateHeartbeat(self, job_id, log_tail):
        """See `ICodeImportScheduler`."""
        return self._updateHeartbeat(job_id, log_tail)

    def finishJobID(self, job_id, status_name, log_file_alias_url):
        """See `ICodeImportScheduler`."""
        return self._finishJobID(job_id, status_name, log_file_alias_url)

    @return_fault
    def _getImportDataForJobID(self, job_id):
        job = self._getJob(job_id)
        arguments = CodeImportSourceDetails.fromCodeImport(
            job.code_import).asArguments()
        branch = job.code_import.branch
        branch_url = canonical_url(branch)
        log_file_name = '%s.log' % branch.unique_name[1:].replace('/', '-')
        return (arguments, branch_url, log_file_name)

    @return_fault
    def _updateHeartbeat(self, job_id, log_tail):
        job = self._getJob(job_id)
        workflow = removeSecurityProxy(getUtility(ICodeImportJobWorkflow))
        workflow.updateHeartbeat(job, log_tail)
        return 0

    @return_fault
    def _finishJobID(self, job_id, status_name, log_file_alias_url):
        job = self._getJob(job_id)
        status = CodeImportResultStatus.items[status_name]
        workflow = removeSecurityProxy(getUtility(ICodeImportJobWorkflow))
        if log_file_alias_url:
            library_file_alias_set = getUtility(ILibraryFileAliasSet)
            # XXX This is so so so terrible:
            log_file_alias_id = int(log_file_alias_url.split('/')[-2])
            log_file_alias = library_file_alias_set[log_file_alias_id]
        else:
            log_file_alias = None
        workflow.finishJob(job, status, log_file_alias)
