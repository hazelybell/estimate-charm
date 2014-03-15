#! /usr/bin/python
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the scan_branches script."""


from storm.locals import Store
import transaction

from lp.code.enums import (
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.model.branchjob import (
    BranchJob,
    BranchJobType,
    BranchScanJob,
    )
from lp.services.job.model.job import (
    Job,
    JobStatus,
    )
from lp.services.osutils import override_environ
from lp.services.scripts.tests import run_script
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer


class TestScanBranches(TestCaseWithFactory):
    """Test the scan_branches script."""

    layer = ZopelessAppServerLayer

    def make_branch_with_commits_and_scan_job(self, db_branch):
        """Create a branch from a db_branch, make commits and a scan job."""
        target, target_tree = self.create_branch_and_tree(db_branch=db_branch)
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            target_tree.commit('First commit', rev_id='rev1')
            target_tree.commit('Second commit', rev_id='rev2')
            target_tree.commit('Third commit', rev_id='rev3')
        BranchScanJob.create(db_branch)
        transaction.commit()

    def run_script_and_assert_success(self):
        """Run the scan_branches script and assert it ran successfully."""
        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py', ['IBranchScanJobSource'],
            expect_returncode=0)
        self.assertEqual('', stdout)
        self.assertIn(
            'INFO    Ran 1 BranchScanJob jobs.\n', stderr)

    def test_scan_branch(self):
        """Test that scan branches adds revisions to the database."""
        self.useBzrBranches()

        db_branch = self.factory.makeAnyBranch()
        self.make_branch_with_commits_and_scan_job(db_branch)
        db_branch.subscribe(
            db_branch.registrant,
            BranchSubscriptionNotificationLevel.FULL,
            BranchSubscriptionDiffSize.WHOLEDIFF,
            CodeReviewNotificationLevel.FULL,
            db_branch.registrant)
        transaction.commit()

        self.run_script_and_assert_success()
        self.assertEqual(db_branch.revision_count, 3)

        store = Store.of(db_branch)
        result = store.find(
            BranchJob,
            BranchJob.jobID == Job.id,
            Job._status == JobStatus.WAITING,
            BranchJob.job_type == BranchJobType.REVISION_MAIL,
            BranchJob.branch == db_branch)
        self.assertEqual(result.count(), 1)

    def test_scan_packagebranch(self):
        """Test that scan_branches can scan package branches."""
        self.useBzrBranches()

        db_branch = self.factory.makePackageBranch()
        self.make_branch_with_commits_and_scan_job(db_branch)

        self.run_script_and_assert_success()
        self.assertEqual(db_branch.revision_count, 3)
