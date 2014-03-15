# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The code import dispatcher.

The code import dispatcher is responsible for checking if any code
imports need to be processed and launching child processes to handle
them.
"""

__metaclass__ = type
__all__ = [
    'CodeImportDispatcher',
    ]

import os
import socket
import subprocess
import time

from lp.services.config import config


class CodeImportDispatcher:
    """A CodeImportDispatcher kicks off the processing of a job if needed.

    The entry point is `findAndDispatchJob`.

    :ivar txn: A transaction manager.
    :ivar logger: A `Logger` object.
    """

    worker_script = os.path.join(
        config.root, 'scripts', 'code-import-worker-monitor.py')

    def __init__(self, logger, worker_limit, _sleep=time.sleep):
        """Initialize an instance.

        :param logger: A `Logger` object.
        """
        self.logger = logger
        self.worker_limit = worker_limit
        self._sleep = _sleep

    def getHostname(self):
        """Return the hostname of this machine.

        This usually calls `socket.gethostname` but it can be
        overridden by the config for tests and developer machines.
        """
        if config.codeimportdispatcher.forced_hostname:
            return config.codeimportdispatcher.forced_hostname
        else:
            return socket.gethostname()

    def dispatchJob(self, job_id):
        """Start the processing of job `job_id`."""
        # Just launch the process and forget about it.
        log_file = os.path.join(
            config.codeimportdispatcher.worker_log_dir,
            'code-import-worker-%d.log' % (job_id,))
        # Return the Popen object to make testing easier.
        interpreter = "%s/bin/py" % config.root
        return subprocess.Popen(
            [interpreter, self.worker_script, str(job_id), '-vv',
             '--log-file', log_file])


    def findAndDispatchJob(self, scheduler_client):
        """Check for and dispatch a job if necessary.

        :return: A boolean, true if a job was found and dispatched.
        """

        job_id = scheduler_client.getJobForMachine(
            self.getHostname(), self.worker_limit)

        if job_id == 0:
            self.logger.info("No jobs pending.")
            return False

        self.logger.info("Dispatching job %d." % job_id)

        self.dispatchJob(job_id)
        return True

    def _getSleepInterval(self):
        """How long to sleep for until asking for a new job.

        The basic idea is to wait longer if the machine is more heavily
        loaded, so that less loaded slaves get a chance to grab some jobs.

        We assume worker_limit will be roughly the number of CPUs in the
        machine, so load/worker_limit is roughly how loaded the machine is.
        """
        return 5*os.getloadavg()[0]/self.worker_limit

    def findAndDispatchJobs(self, scheduler_client):
        """Call findAndDispatchJob until no job is found."""
        while True:
            found = self.findAndDispatchJob(scheduler_client)
            if not found:
                break
            self._sleep(self._getSleepInterval())
