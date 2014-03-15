# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for linking BugTasks and Branches."""

__metaclass__ = type

__all__ = [
    "IBugBranch",
    "IBugBranchSet",
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import ReferenceChoice
from zope.interface import Interface
from zope.schema import (
    Int,
    Object,
    TextLine,
    )

from lp import _
from lp.app.interfaces.launchpad import IHasDateCreated
from lp.bugs.interfaces.bugtask import IBugTask
from lp.bugs.interfaces.hasbug import IHasBug
from lp.code.interfaces.branch import IBranch
from lp.code.interfaces.branchtarget import IHasBranchTarget
from lp.registry.interfaces.person import IPerson
from lp.services.fields import BugField


class IBugBranch(IHasDateCreated, IHasBug, IHasBranchTarget):
    """A branch linked to a bug."""

    export_as_webservice_entry()

    id = Int(title=_("Bug Branch #"))
    bug = exported(
        BugField(
            title=_("Bug #"),
            required=True, readonly=True))
    branch_id = Int(title=_("Branch ID"), required=True, readonly=True)
    branch = exported(
        ReferenceChoice(
            title=_("Branch"), schema=IBranch,
            vocabulary="Branch", required=True))
    revision_hint = TextLine(title=_("Revision Hint"))

    bug_task = Object(
        schema=IBugTask, title=_("The bug task that the branch fixes"),
        description=_(
            "the bug task reported against this branch's product or the "
            "first bug task (in case where there is no task reported "
            "against the branch's product)."),
        readonly=True)

    registrant = Object(
        schema=IPerson, readonly=True, required=True,
        title=_("The person who linked the bug to the branch"))


class IBugBranchSet(Interface):

    def getBugBranch(bug, branch):
        """Return the BugBranch for the given bug and branch.

        Return None if there is no such link.
        """

    def getBranchesWithVisibleBugs(branches, user):
        """Find which of `branches` are for bugs that `user` can see.

        :param branches: A sequence of `Branch`es to limit the search
            to.
        :return: A result set of `Branch` ids: a subset of the ids
            found in `branches`, but limited to branches that are
            visible to `user`.
        """

    def getBugBranchesForBugTasks(tasks):
        """Return a sequence of IBugBranch instances associated with
        the bugs for the given tasks."""
