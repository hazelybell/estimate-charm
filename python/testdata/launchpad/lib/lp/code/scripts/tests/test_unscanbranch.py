# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from storm.exceptions import LostObjectError
from storm.store import Store

from lp.code.model.branchjob import BranchJob
from lp.code.scripts.unscanbranch import UnscanBranchScript
from lp.services.log.logger import DevNullLogger
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer


class TestUnscanBranchScript(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_unscanbranch_script(self):
        branch = self.factory.makeAnyBranch()
        self.factory.makeRevisionsForBranch(branch=branch)
        head = branch.getBranchRevision(revision_id=branch.last_scanned_id)
        self.assertEqual(5, head.sequence)
        self.assertEqual(5, branch.revision_count)
        self.assertEqual(
            1, Store.of(branch).find(BranchJob, branch=branch).count())

        UnscanBranchScript(
            "unscan-branch", test_args=['--rescan', branch.displayname],
            logger=DevNullLogger()).main()

        self.assertIs(None, branch.last_scanned_id)
        self.assertRaises(LostObjectError, getattr, head, 'sequence')
        self.assertEqual(
            2, Store.of(branch).find(BranchJob, branch=branch).count())
