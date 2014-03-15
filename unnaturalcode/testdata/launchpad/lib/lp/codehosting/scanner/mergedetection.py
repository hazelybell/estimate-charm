# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The way the branch scanner handles merges."""

__metaclass__ = type
__all__ = [
    'auto_merge_branches',
    'auto_merge_proposals',
    ]

from bzrlib.revision import NULL_REVISION
from zope.component import getUtility

from lp.code.enums import BranchLifecycleStatus
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.branchmergeproposal import (
    BRANCH_MERGE_PROPOSAL_FINAL_STATES,
    notify_modified,
    )
from lp.services.utils import CachingIterator


def is_series_branch(branch):
    """Is 'branch' associated with a series?"""
    # XXX: JonathanLange 2009-05-07 spec=package-branches: This assumes that
    # we only care about whether a branch is a product series. What about poor
    # old distroseries?
    return not branch.associatedProductSeries().is_empty()


def is_development_focus(branch):
    """Is 'branch' the development focus?"""
    # XXX: JonathanLange 2009-05-07 spec=package-branches: What if the branch
    # is the development focus of a source package?
    dev_focus = branch.product.development_focus
    return branch == dev_focus.branch


def mark_branch_merged(logger, branch):
    """Mark 'branch' as merged."""
    # If the branch is a series branch, then don't change the
    # lifecycle status of it at all.
    if is_series_branch(branch):
        return
    # In other cases, we now want to update the lifecycle status of the
    # source branch to merged.
    logger.info("%s now Merged.", branch.bzr_identity)
    branch.lifecycle_status = BranchLifecycleStatus.MERGED


def merge_detected(logger, source, target, proposal=None, merge_revno=None):
    """Handle the merge of source into target."""
    # If the target branch is not the development focus, then don't update
    # the status of the source branch.
    logger.info(
        'Merge detected: %s => %s',
        source.bzr_identity, target.bzr_identity)
    if proposal is None:
        # If there's no explicit merge proposal, only change the branch's
        # status when it has been merged into the development focus.
        if is_development_focus(target):
            mark_branch_merged(logger, source)
    else:
        notify_modified(proposal, proposal.markAsMerged, merge_revno)
        # If there is an explicit merge proposal, change the branch's
        # status when it's been merged into a development focus or any
        # other series branch.
        if is_series_branch(proposal.target_branch):
            mark_branch_merged(logger, proposal.source_branch)


def auto_merge_branches(scan_completed):
    """Detect branches that have been merged.

    We only check branches that have been merged into the branch that is being
    scanned as we already have the ancestry handy. It is much more work to
    determine which other branches this branch has been merged into.
    """
    db_branch = scan_completed.db_branch
    new_ancestry = scan_completed.new_ancestry
    logger = scan_completed.logger

    # XXX: JonathanLange 2009-05-05 spec=package-branches: Yet another thing
    # that assumes that product is None implies junk.
    #
    # Only do this for non-junk branches.
    if db_branch.product is None:
        return
    # Get all the active branches for the product, and if the
    # last_scanned_revision is in the ancestry, then mark it as merged.
    #
    # XXX: JonathanLange 2009-05-11 spec=package-branches: This assumes that
    # merge detection only works with product branches.
    branches = getUtility(IAllBranches).inProduct(db_branch.product)
    branches = branches.withLifecycleStatus(
        BranchLifecycleStatus.DEVELOPMENT,
        BranchLifecycleStatus.EXPERIMENTAL,
        BranchLifecycleStatus.MATURE,
        BranchLifecycleStatus.ABANDONED).getBranches(eager_load=False)
    for branch in branches:
        last_scanned = branch.last_scanned_id
        # If the branch doesn't have any revisions, not any point setting
        # anything.
        if last_scanned is None or last_scanned == NULL_REVISION:
            # Skip this branch.
            pass
        elif branch == db_branch:
            # No point merging into ourselves.
            pass
        elif db_branch.last_scanned_id == last_scanned:
            # If the tip revisions are the same, then it is the same
            # branch, not one merged into the other.
            pass
        elif last_scanned in new_ancestry:
            merge_detected(logger, branch, db_branch)


def find_merged_revno(merge_sorted, tip_rev_id):
    """Find the mainline revno that merged tip_rev_id.

    This method traverses the merge sorted graph looking for the first
    """
    last_mainline = None
    iterator = iter(merge_sorted)
    while True:
        try:
            rev_id, depth, revno, ignored = iterator.next()
        except StopIteration:
            break
        if depth == 0:
            last_mainline = revno[0]
        if rev_id == tip_rev_id:
            return last_mainline
    # The only reason we get here is that the tip_rev_id isn't in the merge
    # sorted graph.
    return None


def auto_merge_proposals(scan_completed):
    """Detect merged proposals."""
    db_branch = scan_completed.db_branch
    new_ancestry = scan_completed.new_ancestry
    logger = scan_completed.logger

    # Check landing candidates in non-terminal states to see if their tip
    # is in our ancestry. If it is, set the state of the proposal to
    # 'merged'.
    #
    # At this stage we are not going to worry about the revno
    # which introduced the change, that will either be set through the web
    # ui by a person, or by PQM once it is integrated.

    if scan_completed.bzr_branch is None:
        # Only happens in tests.
        merge_sorted = []
    else:
        merge_sorted = CachingIterator(
            scan_completed.bzr_branch.iter_merge_sorted_revisions())
    for proposal in db_branch.landing_candidates:
        tip_rev_id = proposal.source_branch.last_scanned_id
        if tip_rev_id in new_ancestry:
            merged_revno = find_merged_revno(merge_sorted, tip_rev_id)
            # Remember so we can find the merged revision number.
            merge_detected(
                logger, proposal.source_branch, db_branch, proposal,
                merged_revno)

    # Now check the landing targets.  We should probably get rid of this,
    # especially if we are trying to get rid of the branch revision table.
    final_states = BRANCH_MERGE_PROPOSAL_FINAL_STATES
    tip_rev_id = db_branch.last_scanned_id
    for proposal in db_branch.landing_targets:
        if proposal.queue_status not in final_states:
            # If there is a branch revision record for target branch with
            # the tip_rev_id of the source branch, then it is merged.
            branch_revision = proposal.target_branch.getBranchRevision(
                revision_id=tip_rev_id)
            if branch_revision is not None:
                merge_detected(
                    logger, db_branch, proposal.target_branch, proposal)
