# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for events used in the launchpad code application."""

__metaclass__ = type
__all__ = [
    'IBranchMergeProposalStatusChangeEvent',
    'IBranchMergeProposalNeedsReviewEvent',
    'INewBranchMergeProposalEvent',
    'INewCodeReviewCommentEvent',
    'IReviewerNominatedEvent',
    ]


from zope.component.interfaces import IObjectEvent
from zope.interface import Attribute


class IBranchMergeProposalStatusChangeEvent(IObjectEvent):
    """A merge proposal has changed state."""

    user = Attribute("The user who updated the proposal.")
    from_state = Attribute("The previous queue_status.")
    to_state = Attribute("The updated queue_status.")


class INewBranchMergeProposalEvent(IObjectEvent):
    """A new merge has been proposed."""


class IReviewerNominatedEvent(IObjectEvent):
    """A reviewer has been nominated."""


class INewCodeReviewCommentEvent(IObjectEvent):
    """A new comment has been added to the merge proposal."""


class IBranchMergeProposalNeedsReviewEvent(IObjectEvent):
    """The merge proposal has moved from work in progress to needs reivew."""
