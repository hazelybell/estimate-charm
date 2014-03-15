# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code import scheduler interfaces."""

__metaclass__ = type
__all__ = [
    'ICodeImportScheduler',
    'ICodeImportSchedulerApplication',
    ]


from zope.interface import Interface

from lp.services.webapp.interfaces import ILaunchpadApplication


class ICodeImportSchedulerApplication(ILaunchpadApplication):
    """Code import scheduler application root."""


class ICodeImportScheduler(Interface):
    """The code import scheduler.

    The code import scheduler is responsible for allocating import jobs to
    machines.  Code import slave machines call the getJobForMachine() method
    when they need more work to do.
    """

    def getJobForMachine(hostname, worker_limit):
        """Get a job to run on the slave 'hostname'.

        This method selects the most appropriate job for the machine,
        mark it as having started on said machine and return its id,
        or 0 if there are no jobs pending.
        """

    def getImportDataForJobID(job_id):
        """Get data about the import with job id `job_id`.

        :return: ``(worker_arguments, branch_url, log_file_name)`` where:
            * ``worker_arguments`` are the arguments to pass to the code
              import worker subprocess.
           * ``branch_url`` is the URL of the import branch (only used to put
             in OOPS reports)
           * ``log_file_name`` is the name of the log file to create in the
             librarian.
        :raise NoSuchCodeImportJob: if no job with id `job_id` exists.
        """

    def updateHeartbeat(job_id, log_tail):
        """Call `ICodeImportJobWorkflow.updateHeartbeat` for job `job_id`.

        :raise NoSuchCodeImportJob: if no job with id `job_id` exists.
        """

    def finishJobID(job_id, status_name, log_file_alias_url):
        """Call `ICodeImportJobWorkflow.finishJob` for job `job_id`.

        :raise NoSuchCodeImportJob: if no job with id `job_id` exists.
        """
