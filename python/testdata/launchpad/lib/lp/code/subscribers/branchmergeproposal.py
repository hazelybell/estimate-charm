# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Event subscribers for branch merge proposals."""

__metaclass__ = type


from zope.component import getUtility
from zope.principalregistry.principalregistry import UnauthenticatedPrincipal

from lp.code.adapters.branch import BranchMergeProposalNoPreviewDiffDelta
from lp.code.enums import BranchMergeProposalStatus
from lp.code.interfaces.branchmergeproposal import (
    IMergeProposalNeedsReviewEmailJobSource,
    IMergeProposalUpdatedEmailJobSource,
    IReviewRequestedEmailJobSource,
    IUpdatePreviewDiffJobSource,
    )
from lp.registry.interfaces.person import IPerson
from lp.services.utils import text_delta


def merge_proposal_created(merge_proposal, event):
    """A new merge proposal has been created.

    Create a job to update the diff for the merge proposal.
    Also create a job to email the subscribers about the new proposal.
    """
    getUtility(IUpdatePreviewDiffJobSource).create(merge_proposal)


def merge_proposal_needs_review(merge_proposal, event):
    """A new merge proposal needs a review.

    This event is raised when the proposal moves from work in progress to
    needs review.
    """
    getUtility(IMergeProposalNeedsReviewEmailJobSource).create(
        merge_proposal)


def merge_proposal_modified(merge_proposal, event):
    """Notify branch subscribers when merge proposals are updated."""
    # Check the user.
    if event.user is None:
        return
    if isinstance(event.user, UnauthenticatedPrincipal):
        from_person = None
    else:
        from_person = IPerson(event.user)
    # If the merge proposal was work in progress, then we don't want to send
    # out an email as the needs review email will cover that.
    old_status = event.object_before_modification.queue_status
    if old_status == BranchMergeProposalStatus.WORK_IN_PROGRESS:
        # Unless the new status is merged.  If this occurs we really should
        # send out an email.
        if merge_proposal.queue_status != BranchMergeProposalStatus.MERGED:
            return
    # Create a delta of the changes.  If there are no changes to report, then
    # we're done.
    delta = BranchMergeProposalNoPreviewDiffDelta.construct(
        event.object_before_modification, merge_proposal)
    if delta is None:
        return
    changes = text_delta(
        delta, delta.delta_values, delta.new_values, delta.interface)
    # Now create the job to send the email.
    getUtility(IMergeProposalUpdatedEmailJobSource).create(
        merge_proposal, changes, from_person)


def review_requested(vote_reference, event):
    """Notify the reviewer that they have been requested to review."""
    # Don't send email if the proposal is work in progress.
    bmp_status = vote_reference.branch_merge_proposal.queue_status
    if bmp_status != BranchMergeProposalStatus.WORK_IN_PROGRESS:
        getUtility(IReviewRequestedEmailJobSource).create(vote_reference)
