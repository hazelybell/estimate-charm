# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for BugBranches."""

__metaclass__ = type

from lp.services.webapp.interfaces import IPrimaryContext
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugBranchPrimaryContext(TestCaseWithFactory):
    # Tests the adaptation of a bug branch link into a primary context.

    layer = DatabaseFunctionalLayer

    def testPrimaryContext(self):
        # The primary context of a bug branch link is the same as the
        # primary context of the branch that is linked to the bug.
        branch = self.factory.makeProductBranch()
        bug = self.factory.makeBug(target=branch.product)
        login_person(branch.owner)
        bugbranch = bug.linkBranch(branch, branch.owner)
        self.assertEqual(
            IPrimaryContext(bugbranch).context,
            IPrimaryContext(bugbranch.branch).context)
