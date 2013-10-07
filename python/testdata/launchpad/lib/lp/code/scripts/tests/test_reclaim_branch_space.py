# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the script that reclaims the disk space used by deleted branches."""

import datetime
import os
import shutil

import transaction

from lp.code.model.branchjob import (
    BranchJob,
    BranchJobType,
    )
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.scripts.tests import run_script
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer


class TestReclaimBranchSpaceScript(TestCaseWithFactory):

    layer = ZopelessAppServerLayer

    def test_reclaimbranchspace_script(self):
        # When the reclaimbranchspace script is run, it removes from the file
        # system any branches that were deleted from the database more than a
        # week ago.
        db_branch = self.factory.makeAnyBranch()
        mirrored_path = self.getBranchPath(
            db_branch, config.codehosting.mirrored_branches_root)
        if os.path.exists(mirrored_path):
            shutil.rmtree(mirrored_path)
        os.makedirs(mirrored_path)
        db_branch.destroySelf()
        transaction.commit()
        # The first run doesn't remove anything yet.
        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py',
            ['IReclaimBranchSpaceJobSource'])
        self.assertEqual('', stdout)
        self.assertEqual(
            'INFO    Creating lockfile: /var/lock/'
            'launchpad-process-job-source-IReclaimBranchSpaceJobSource.lock\n'
            'INFO    Running synchronously.\n', stderr)
        self.assertEqual(0, retcode)
        self.assertTrue(
            os.path.exists(mirrored_path))
        # Now pretend that the branch was deleted 8 days ago.
        reclaim_job = IStore(BranchJob).find(
            BranchJob,
            BranchJob.job_type == BranchJobType.RECLAIM_BRANCH_SPACE).one()
        reclaim_job.job.scheduled_start -= datetime.timedelta(days=8)
        transaction.commit()
        # The script will now remove the branch from disk.
        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py',
            ['IReclaimBranchSpaceJobSource'])
        self.assertEqual('', stdout)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            'INFO    Creating lockfile: /var/lock/'
            'launchpad-process-job-source-IReclaimBranchSpaceJobSource.lock\n'
            'INFO    Running synchronously.\n'
            'INFO    Running <RECLAIM_BRANCH_SPACE branch job \(\d+\) for '
            '\d+> \(ID %s\) in status Waiting\n'
            'INFO    Ran 1 ReclaimBranchSpaceJob jobs.\n' % reclaim_job.job.id,
            stderr)
        self.assertEqual(0, retcode)
        self.assertFalse(
            os.path.exists(mirrored_path))
