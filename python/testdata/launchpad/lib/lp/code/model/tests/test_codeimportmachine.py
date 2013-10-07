# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for methods of CodeImportMachine.

Other tests are in codeimport-machine.txt."""

from zope.component import getUtility

from lp.code.enums import (
    CodeImportMachineOfflineReason,
    CodeImportMachineState,
    )
from lp.code.interfaces.codeimportjob import ICodeImportJobWorkflow
from lp.services.database.constants import UTC_NOW
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestCodeImportMachineShouldLookForJob(TestCaseWithFactory):
    """Tests for  `CodeImportMachine.shouldLookForJob`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportMachineShouldLookForJob, self).setUp(
            'admin@canonical.com')
        self.machine = self.factory.makeCodeImportMachine(set_online=True)

    def createJobRunningOnMachine(self, machine):
        """Create a job in the database and mark it as running on `machine`.
        """
        job = self.factory.makeCodeImportJob()
        getUtility(ICodeImportJobWorkflow).startJob(job, machine)

    def test_machineIsOffline(self):
        # When the machine is offline, we shouldn't look for any jobs.
        self.machine.setOffline(CodeImportMachineOfflineReason.STOPPED)
        self.assertFalse(self.machine.shouldLookForJob(10))

    def test_machineIsQuiescingNoJobsRunning(self):
        # When the machine is quiescing and no jobs are running on this
        # machine, we should set the machine to OFFLINE and not look for jobs.
        self.machine.setQuiescing(self.factory.makePerson())
        self.assertFalse(self.machine.shouldLookForJob(10))
        self.assertEqual(self.machine.state, CodeImportMachineState.OFFLINE)

    def test_machineIsQuiescingWithJobsRunning(self):
        # When the machine is quiescing and there are jobs running on this
        # machine, we shouldn't look for any more jobs.
        self.createJobRunningOnMachine(self.machine)
        self.machine.setQuiescing(self.factory.makePerson())
        self.assertFalse(self.machine.shouldLookForJob(10))
        self.assertEqual(self.machine.state, CodeImportMachineState.QUIESCING)

    def test_enoughJobsRunningOnMachine(self):
        # When there are already enough jobs running on this machine, we
        # shouldn't look for any more jobs.
        self.createJobRunningOnMachine(self.machine)
        self.assertFalse(self.machine.shouldLookForJob(worker_limit=1))

    def test_shouldLook(self):
        # If the machine is online and there are not already
        # max_jobs_per_machine jobs running, then we should look for a job.
        self.assertTrue(self.machine.shouldLookForJob(worker_limit=1))

    def test_noHeartbeatWhenCreated(self):
        # Machines are created with a NULL heartbeat.
        self.assertTrue(self.machine.heartbeat is None)

    def test_noHeartbeatUpdateWhenOffline(self):
        # When the machine is offline, the heartbeat is not updated.
        self.machine.setOffline(CodeImportMachineOfflineReason.STOPPED)
        self.machine.shouldLookForJob(10)
        self.assertTrue(self.machine.heartbeat is None)

    def test_heartbeatUpdateWhenQuiescing(self):
        # When the machine is quiescing, the heartbeat is updated.
        self.machine.setQuiescing(self.factory.makePerson())
        self.machine.shouldLookForJob(10)
        self.assertSqlAttributeEqualsDate(self.machine, 'heartbeat', UTC_NOW)

    def test_heartbeatUpdateWhenOnline(self):
        # When the machine is online, the heartbeat is updated.
        self.machine.shouldLookForJob(10)
        self.assertSqlAttributeEqualsDate(self.machine, 'heartbeat', UTC_NOW)
