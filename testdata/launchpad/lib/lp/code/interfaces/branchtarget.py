# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for branch targets.

A branch target is the 'thing' that a branch is on. Branches in Launchpad are
owned by an IPerson and can be either junk branches, product branches or
package branches. A branch target is the product or package that a branch is
on. If the branch is a junk branch, then the target is the branch owner.
"""

__metaclass__ = type
__all__ = [
    'check_default_stacked_on',
    'IBranchTarget',
    'IHasBranchTarget',
    ]

from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.code.enums import BranchType


def check_default_stacked_on(branch):
    """Return 'branch' if suitable to be a default stacked-on branch.

    Only certain branches are suitable to be default stacked-on branches.
    Branches that are *not* suitable include:
      - remote branches
      - branches the user cannot see
      - branches that have no last revision information set (hosted branches
        where a push hasn't completed or a mirrored branch that hasn't been
        mirrored, etc).

    If the given branch is not suitable, return None. For convenience, also
    returns None if passed None. Otherwise, return the branch.
    """
    if branch is None:
        return None
    try:
        branch_type = branch.branch_type
    except Unauthorized:
        return None
    if branch_type == BranchType.REMOTE:
        return None
    if branch.last_mirrored_id is None:
        return None
    return branch


class IHasBranchTarget(Interface):
    """A thing that has a branch target."""

    target = Attribute("The branch target, as an `IBranchTarget`.")


class IBranchTarget(Interface):
    """A target of branches.

    A product contains branches, a source package on a distroseries contains
    branches, and a person contains 'junk' branches.
    """

    context = Attribute('The primary context.')

    name = Attribute("The name of the target.")

    components = Attribute(
        "An iterable of the objects that make up this branch target, from "
        "most-general to most-specific. In a URL, these would normally "
        "appear from left to right.")

    displayname = Attribute("The display name of this branch target.")

    default_stacked_on_branch = Reference(
        # Should be an IBranch, but circular imports prevent it.
        schema=Interface,
        title=_("Default stacked-on branch"),
        required=True, readonly=True,
        description=_(
            'The branch that new branches will be stacked on by default.'))

    default_merge_target = Attribute(
        "The branch to merge other branches into for this target.")

    supports_merge_proposals = Attribute(
        "Does this target support merge proposals at all?")

    supports_short_identites = Attribute(
        "Does this target support shortened bazaar identities?")

    supports_code_imports = Attribute(
        "Does this target support code imports at all?")

    def areBranchesMergeable(other_target):
        """Are branches from other_target mergeable into this target."""

    def __eq__(other):
        """Is this target the same as another target?

        Generally implemented in terms of `IPrimaryContext.context`.
        """

    def __ne__(other):
        """Is this target not the same as another target?

        Generally implemented in terms of `IPrimaryContext.context`.
        """

    def getNamespace(owner):
        """Return a `IBranchNamespace` for 'owner' and this target."""

    collection = Attribute("An IBranchCollection for this target.")

    def assignKarma(person, action_name, date_created=None):
        """Assign karma to the person on the appropriate target."""

    def getBugTask(bug):
        """Get the BugTask for a given bug related to the branch target."""

    def newCodeImport(registrant, branch_name, rcs_type, url=None,
                      cvs_root=None, cvs_module=None, owner=None):
        """Create a new code import for this target.

        :param registrant: the `IPerson` who should be recorded as creating
            the import and will own the resulting branch.
        :param branch_name: the name the resulting branch should have.
        :param rcs_type: the type of the foreign VCS.
        :param url: the url to import from if the import isn't CVS.
        :param cvs_root: if the import is from CVS the CVSROOT to import from.
        :param cvs_module: if the import is from CVS the module to import.
        :param owner: the `IPerson` to own the resulting branch, or None to
            use registrant.
        :returns: an `ICodeImport`.
        :raises AssertionError: if supports_code_imports is False.
        """

    def getRelatedSeriesBranchInfo(parent_branch, limit_results=None):
        """Find development branch info related to this parent branch.

        The result is a list of tuples:
            (branch, product_series)
        where:
            branch: the related branch.
            product_series: the product series associated with the branch.

        The development focus is first in the list.

        :param parent_branch: `IBranch` we are finding related branches for.
        :param limit_results: if not None, limit the number of results to the
            specified value.
        """

    def getRelatedPackageBranchInfo(parent_branch, limit_results=None):
        """Find package branch info related to this parent branch.

        The result is a list of tuples:
            (branch, distro_series)
        where:
            branch: the related branch.
            distro_series: the distro series associated with the branch.

        :param parent_branch: `IBranch` we are finding related branches for.
        :param limit_results: if not None, limit the number of results to the
            specified value.
        """
