# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Assign karma for code domain activity."""

from lp.code.enums import BranchMergeProposalStatus
from lp.registry.interfaces.person import IPerson
from lp.services.database.sqlbase import block_implicit_flushes


@block_implicit_flushes
def branch_created(branch, event):
    """Assign karma to the user who registered the branch."""
    branch.target.assignKarma(branch.registrant, 'branchcreated')


@block_implicit_flushes
def branch_merge_proposed(proposal, event):
    """Assign karma to the user who proposed the merge."""
    proposal.source_branch.target.assignKarma(
        proposal.registrant, 'branchmergeproposed')


@block_implicit_flushes
def code_review_comment_added(code_review_comment, event):
    """Assign karma to the user who commented on the review."""
    proposal = code_review_comment.branch_merge_proposal
    target = proposal.source_branch.target
    # If the user is commenting on their own proposal, then they don't
    # count as a reviewer for that proposal.
    user = code_review_comment.message.owner
    reviewer = user.inTeam(proposal.target_branch.code_reviewer)
    if reviewer and user != proposal.registrant:
        target.assignKarma(user, 'codereviewreviewercomment')
    else:
        target.assignKarma(user, 'codereviewcomment')


@block_implicit_flushes
def branch_merge_status_changed(proposal, event):
    """Assign karma to the user who approved the merge."""
    target = proposal.source_branch.target
    user = IPerson(event.user)

    in_progress_states = (
        BranchMergeProposalStatus.WORK_IN_PROGRESS,
        BranchMergeProposalStatus.NEEDS_REVIEW)

    if ((event.to_state == BranchMergeProposalStatus.CODE_APPROVED) and
        (event.from_state in (in_progress_states))):
        if user == proposal.registrant:
            target.assignKarma(user, 'branchmergeapprovedown')
        else:
            target.assignKarma(user, 'branchmergeapproved')
    elif ((event.to_state == BranchMergeProposalStatus.REJECTED) and
          (event.from_state in (in_progress_states))):
        if user == proposal.registrant:
            target.assignKarma(user, 'branchmergerejectedown')
        else:
            target.assignKarma(user, 'branchmergerejected')
    else:
        # Only care about approved and rejected right now.
        pass
