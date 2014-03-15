# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the upgrade_branches script."""


from bzrlib.branch import Branch as BzrBranch
import transaction

from lp.code.model.branch import (
    BranchFormat,
    RepositoryFormat,
    )
from lp.code.model.branchjob import BranchUpgradeJob
from lp.services.scripts.tests import run_script
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer


class TestUpgradeBranches(TestCaseWithFactory):

    layer = ZopelessAppServerLayer

    def test_upgrade_branches(self):
        """Test that upgrade_branches upgrades branches."""
        self.useBzrBranches()
        target, target_tree = self.create_branch_and_tree(format='knit')
        target.branch_format = BranchFormat.BZR_BRANCH_5
        target.repository_format = RepositoryFormat.BZR_KNIT_1

        self.assertEqual(
            target_tree.branch.repository._format.get_format_string(),
            'Bazaar-NG Knit Repository Format 1')

        BranchUpgradeJob.create(target, self.factory.makePerson())
        transaction.commit()

        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py', ['IBranchUpgradeJobSource'],
            expect_returncode=0)
        self.assertEqual('', stdout)
        self.assertIn(
            'INFO    Ran 1 BranchUpgradeJob jobs.\n', stderr)

        target_branch = BzrBranch.open(target_tree.branch.base)
        self.assertEqual(
            target_branch.repository._format.get_format_string(),
            'Bazaar repository format 2a (needs bzr 1.16 or later)\n')

    def test_upgrade_branches_packagebranch(self):
        """Test that upgrade_branches can upgrade package branches."""
        self.useBzrBranches()
        package_branch = self.factory.makePackageBranch()
        target, target_tree = self.create_branch_and_tree(
            db_branch=package_branch, format='knit')
        target.branch_format = BranchFormat.BZR_BRANCH_5
        target.repository_format = RepositoryFormat.BZR_KNIT_1

        self.assertEqual(
            target_tree.branch.repository._format.get_format_string(),
            'Bazaar-NG Knit Repository Format 1')

        BranchUpgradeJob.create(target, self.factory.makePerson())
        transaction.commit()

        retcode, stdout, stderr = run_script(
            'cronscripts/process-job-source.py', ['IBranchUpgradeJobSource'],
            expect_returncode=0)
        self.assertEqual('', stdout)
        self.assertIn(
            'INFO    Ran 1 BranchUpgradeJob jobs.\n', stderr)

        target_branch = BzrBranch.open(target_tree.branch.base)
        self.assertEqual(
            target_branch.repository._format.get_format_string(),
            'Bazaar repository format 2a (needs bzr 1.16 or later)\n')
