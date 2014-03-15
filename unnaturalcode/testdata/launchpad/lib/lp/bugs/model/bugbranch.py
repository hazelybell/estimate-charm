# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes for linking bugtasks and branches."""

__metaclass__ = type

__all__ = ["BugBranch",
           "BugBranchSet"]

from sqlobject import (
    ForeignKey,
    IN,
    IntCol,
    StringCol,
    )
from zope.interface import implements

from lp.bugs.interfaces.bugbranch import (
    IBugBranch,
    IBugBranchSet,
    )
from lp.code.interfaces.branchtarget import IHasBranchTarget
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import SQLBase


class BugBranch(SQLBase):
    """See `IBugBranch`."""
    implements(IBugBranch, IHasBranchTarget)

    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    bug = ForeignKey(dbName="bug", foreignKey="Bug", notNull=True)
    branch_id = IntCol(dbName="branch", notNull=True)
    branch = ForeignKey(dbName="branch", foreignKey="Branch", notNull=True)
    revision_hint = StringCol(default=None)

    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    @property
    def target(self):
        """See `IHasBranchTarget`."""
        return self.branch.target

    @property
    def bug_task(self):
        """See `IBugBranch`."""
        task = self.bug.getBugTask(self.branch.product)
        if task is None:
            # Just choose the first task for the bug.
            task = self.bug.bugtasks[0]
        return task


class BugBranchSet:

    implements(IBugBranchSet)

    def getBugBranch(self, bug, branch):
        """See `IBugBranchSet`."""
        return BugBranch.selectOneBy(bugID=bug.id, branchID=branch.id)

    def getBranchesWithVisibleBugs(self, branches, user):
        """See `IBugBranchSet`."""
        # Avoid circular imports.
        from lp.bugs.model.bugtaskflat import BugTaskFlat
        from lp.bugs.model.bugtasksearch import get_bug_privacy_filter

        branch_ids = [branch.id for branch in branches]
        if not branch_ids:
            return []

        visible = get_bug_privacy_filter(user)
        return IStore(BugBranch).find(
            BugBranch.branchID,
            BugBranch.branch_id.is_in(branch_ids),
            BugTaskFlat.bug_id == BugBranch.bugID,
            visible).config(distinct=True)

    def getBugBranchesForBugTasks(self, tasks):
        """See `IBugBranchSet`."""
        bug_ids = [task.bugID for task in tasks]
        if not bug_ids:
            return []
        bugbranches = BugBranch.select(IN(BugBranch.q.bugID, bug_ids),
                                       orderBy=['branch'])
        return bugbranches.prejoin(
            ['branch', 'branch.owner', 'branch.product'])
