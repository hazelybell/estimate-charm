# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""CodeReviewVoteReference database class."""

__metaclass__ = type
__all__ = [
    'CodeReviewVoteReference',
    ]

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements
from zope.schema import Int

from lp.code.errors import (
    ClaimReviewFailed,
    ReviewNotPending,
    UserHasExistingReview,
    )
from lp.code.interfaces.codereviewvote import ICodeReviewVoteReference
from lp.services.database.constants import DEFAULT
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase


class CodeReviewVoteReference(SQLBase):
    """See `ICodeReviewVote`"""

    implements(ICodeReviewVoteReference)

    _table = 'CodeReviewVote'
    id = Int()
    branch_merge_proposal = ForeignKey(
        dbName='branch_merge_proposal', foreignKey='BranchMergeProposal',
        notNull=True)
    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)
    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person', notNull=True)
    reviewer = ForeignKey(
        dbName='reviewer', foreignKey='Person', notNull=True)
    review_type = StringCol(default=None)
    comment = ForeignKey(
        dbName='vote_message', foreignKey='CodeReviewComment', default=None)

    @property
    def is_pending(self):
        """See `ICodeReviewVote`"""
        # Reviews are pending if there is no associated comment.
        return self.comment is None

    def _validatePending(self):
        """Raise if the review is not pending."""
        if not self.is_pending:
            raise ReviewNotPending('The review is not pending.')

    def _validateNoReviewForUser(self, user):
        """Make sure there isn't an existing review for the user."""
        bmp = self.branch_merge_proposal
        existing_review = bmp.getUsersVoteReference(user)
        if existing_review is not None:
            if existing_review.is_pending:
                error_str = '%s has already been asked to review this'
            else:
                error_str = '%s has already reviewed this'
            raise UserHasExistingReview(error_str % user.unique_displayname)

    def validateClaimReview(self, claimant):
        """See `ICodeReviewVote`"""
        self._validatePending()
        if not self.reviewer.is_team:
            raise ClaimReviewFailed('Cannot claim non-team reviews.')
        if not claimant.inTeam(self.reviewer):
            raise ClaimReviewFailed(
                '%s is not a member of %s' %
                (claimant.unique_displayname,
                 self.reviewer.unique_displayname))
        self._validateNoReviewForUser(claimant)

    def claimReview(self, claimant):
        """See `ICodeReviewVote`"""
        if self.reviewer == claimant:
            return
        self.validateClaimReview(claimant)
        self.reviewer = claimant

    def validateReasignReview(self, reviewer):
        """See `ICodeReviewVote`"""
        self._validatePending()
        if not reviewer.is_team:
            self._validateNoReviewForUser(reviewer)

    def reassignReview(self, reviewer):
        """See `ICodeReviewVote`"""
        self.validateReasignReview(reviewer)
        self.reviewer = reviewer

    def delete(self):
        """See `ICodeReviewVote`"""
        if not self.is_pending:
            raise ReviewNotPending('The review is not pending.')
        self.destroySelf()
