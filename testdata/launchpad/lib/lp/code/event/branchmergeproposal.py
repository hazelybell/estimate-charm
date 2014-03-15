# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Event implementation classes for branch merge proposal events."""

__metaclass__ = type
__all__ = [
    'BranchMergeProposalNeedsReviewEvent',
    'BranchMergeProposalStatusChangeEvent',
    'NewBranchMergeProposalEvent',
    'NewCodeReviewCommentEvent',
    'ReviewerNominatedEvent',
    ]

from zope.component.interfaces import ObjectEvent
from zope.interface import implements

from lp.code.interfaces.event import (
    IBranchMergeProposalNeedsReviewEvent,
    IBranchMergeProposalStatusChangeEvent,
    INewBranchMergeProposalEvent,
    INewCodeReviewCommentEvent,
    IReviewerNominatedEvent,
    )


class BranchMergeProposalStatusChangeEvent(ObjectEvent):
    """See `IBranchMergeProposalStatusChangeEvent`."""

    implements(IBranchMergeProposalStatusChangeEvent)

    def __init__(self, proposal, user, from_state, to_state):
        ObjectEvent.__init__(self, proposal)
        self.user = user
        self.from_state = from_state
        self.to_state = to_state


class NewBranchMergeProposalEvent(ObjectEvent):
    """A new merge has been proposed."""
    implements(INewBranchMergeProposalEvent)


class BranchMergeProposalNeedsReviewEvent(ObjectEvent):
    """The merge proposal has moved from work in progress to needs reivew."""
    implements(IBranchMergeProposalNeedsReviewEvent)


class ReviewerNominatedEvent(ObjectEvent):
    """A reviewer has been nominated."""
    implements(IReviewerNominatedEvent)


class NewCodeReviewCommentEvent(ObjectEvent):
    """A new comment has been added to the merge proposal."""
    implements(INewCodeReviewCommentEvent)

    def __init__(self, code_review_comment, original_email):
        ObjectEvent.__init__(self, code_review_comment)
        self.email = original_email
