# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mixin classes to implement methods for IHas<code related bits>."""

__metaclass__ = type
__all__ = [
    'HasBranchesMixin',
    'HasCodeImportsMixin',
    'HasMergeProposalsMixin',
    'HasRequestedReviewsMixin',
    ]

from zope.component import getUtility

from lp.code.enums import BranchMergeProposalStatus
from lp.code.interfaces.branch import DEFAULT_BRANCH_STATUS_IN_LISTING
from lp.code.interfaces.branchcollection import (
    IAllBranches,
    IBranchCollection,
    )
from lp.code.interfaces.branchtarget import IBranchTarget


class HasBranchesMixin:
    """A mixin implementation for `IHasBranches`."""

    def getBranches(self, status=None, visible_by_user=None,
                    modified_since=None, eager_load=False):
        """See `IHasBranches`."""
        if status is None:
            status = DEFAULT_BRANCH_STATUS_IN_LISTING

        collection = IBranchCollection(self).visibleByUser(visible_by_user)
        collection = collection.withLifecycleStatus(*status)
        if modified_since is not None:
            collection = collection.modifiedSince(modified_since)
        return collection.getBranches(eager_load=eager_load)


class HasMergeProposalsMixin:
    """A mixin implementation class for `IHasMergeProposals`."""

    def getMergeProposals(self, status=None, visible_by_user=None,
                          eager_load=False):
        """See `IHasMergeProposals`."""
        if not status:
            status = (
                BranchMergeProposalStatus.CODE_APPROVED,
                BranchMergeProposalStatus.NEEDS_REVIEW,
                BranchMergeProposalStatus.WORK_IN_PROGRESS)

        collection = IBranchCollection(self).visibleByUser(visible_by_user)
        return collection.getMergeProposals(status, eager_load=eager_load)


class HasRequestedReviewsMixin:
    """A mixin implementation class for `IHasRequestedReviews`."""

    def getRequestedReviews(self, status=None, visible_by_user=None):
        """See `IHasRequestedReviews`."""
        if not status:
            status = (BranchMergeProposalStatus.NEEDS_REVIEW,)

        visible_branches = getUtility(IAllBranches).visibleByUser(
            visible_by_user)
        return visible_branches.getMergeProposalsForReviewer(self, status)


class HasCodeImportsMixin:

    def newCodeImport(self, registrant=None, branch_name=None,
            rcs_type=None, url=None, cvs_root=None, cvs_module=None,
            owner=None):
        """See `IHasCodeImports`."""
        return IBranchTarget(self).newCodeImport(registrant, branch_name,
                rcs_type, url=url, cvs_root=cvs_root, cvs_module=cvs_module,
                owner=owner)
