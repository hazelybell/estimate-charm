# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for branch merge prosals."""

__metaclass__ = type
__all__ = [
    'BranchMergeProposal',
    'BranchMergeProposalGetter',
    'is_valid_transition',
    ]

from email.Utils import make_msgid

from sqlobject import (
    ForeignKey,
    IntCol,
    SQLMultipleJoin,
    StringCol,
    )
from storm.expr import (
    And,
    Desc,
    Join,
    LeftJoin,
    Or,
    Select,
    SQL,
    )
from storm.locals import Reference
from storm.store import Store
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements

from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    CodeReviewVote,
    )
from lp.code.errors import (
    BadBranchMergeProposalSearchContext,
    BadStateTransition,
    BranchMergeProposalExists,
    UserNotBranchReviewer,
    WrongBranchMergeProposal,
    )
from lp.code.event.branchmergeproposal import (
    BranchMergeProposalNeedsReviewEvent,
    BranchMergeProposalStatusChangeEvent,
    NewCodeReviewCommentEvent,
    ReviewerNominatedEvent,
    )
from lp.code.interfaces.branch import IBranchNavigationMenu
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.branchmergeproposal import (
    BRANCH_MERGE_PROPOSAL_FINAL_STATES as FINAL_STATES,
    IBranchMergeProposal,
    IBranchMergeProposalGetter,
    )
from lp.code.interfaces.branchrevision import IBranchRevision
from lp.code.interfaces.branchtarget import IHasBranchTarget
from lp.code.mail.branch import RecipientReason
from lp.code.model.branchrevision import BranchRevision
from lp.code.model.codereviewcomment import CodeReviewComment
from lp.code.model.codereviewvote import CodeReviewVoteReference
from lp.code.model.diff import (
    Diff,
    IncrementalDiff,
    PreviewDiff,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    validate_person,
    validate_public_person,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.model.person import Person
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.config import config
from lp.services.database.bulk import load_related
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    quote,
    SQLBase,
    sqlvalues,
    )
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.mail.sendmail import validate_message
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )


def is_valid_transition(proposal, from_state, next_state, user=None):
    """Is it valid for this user to move this proposal to to next_state?

    :param proposal: The merge proposal.
    :param from_state: The previous state
    :param to_state: The new state to change to
    :param user: The user who may change the state
    """
    # Trivial acceptance case.
    if from_state == next_state:
        return True
    if from_state in FINAL_STATES and next_state not in FINAL_STATES:
        dupes = BranchMergeProposalGetter.activeProposalsForBranches(
            proposal.source_branch, proposal.target_branch)
        if not dupes.is_empty():
            return False

    [
        wip,
        needs_review,
        code_approved,
        rejected,
        merged,
        merge_failed,
        queued,
        superseded,
    ] = BranchMergeProposalStatus.items

    # Transitioning to code approved, rejected, failed or queued from
    # work in progress, needs review or merge failed needs the
    # user to be a valid reviewer, other states are fine.
    valid_reviewer = proposal.target_branch.isPersonTrustedReviewer(user)
    reviewed_ok_states = (code_approved, queued, merge_failed)
    if not valid_reviewer:
        # Non reviewers cannot reject proposals [XXX: what about their own?]
        if next_state == rejected:
            return False
        # Non-reviewers can toggle within the reviewed ok states
        # (approved/queued/failed): they can dequeue something they spot an
        # environmental issue with (queued or failed to approved). Retry
        # things that had an environmental issue (failed or approved to
        # queued) and note things as failing (approved and queued to failed).
        # This is perhaps more generous than needed, but its not clearly wrong
        # - a key concern is to prevent non reviewers putting things in the
        # queue that haven't been approved (and thus moved to approved or one
        # of the workflow states that approved leads to).
        elif (next_state in reviewed_ok_states and
              from_state not in reviewed_ok_states):
            return False
        else:
            return True
    else:
        return True


class BranchMergeProposal(SQLBase):
    """A relationship between a person and a branch."""

    implements(IBranchMergeProposal, IBranchNavigationMenu, IHasBranchTarget)

    _table = 'BranchMergeProposal'
    _defaultOrder = ['-date_created', 'id']

    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    source_branch = ForeignKey(
        dbName='source_branch', foreignKey='Branch', notNull=True)

    target_branch = ForeignKey(
        dbName='target_branch', foreignKey='Branch', notNull=True)

    prerequisite_branch = ForeignKey(
        dbName='dependent_branch', foreignKey='Branch', notNull=False)

    description = StringCol(default=None)

    whiteboard = StringCol(default=None)

    queue_status = EnumCol(
        enum=BranchMergeProposalStatus, notNull=True,
        default=BranchMergeProposalStatus.WORK_IN_PROGRESS)

    @property
    def private(self):
        return (
            (self.source_branch.information_type
             in PRIVATE_INFORMATION_TYPES) or
            (self.target_branch.information_type
             in PRIVATE_INFORMATION_TYPES) or
            (self.prerequisite_branch is not None and
             (self.prerequisite_branch.information_type in
              PRIVATE_INFORMATION_TYPES)))

    reviewer = ForeignKey(
        dbName='reviewer', foreignKey='Person',
        storm_validator=validate_person, notNull=False,
        default=None)

    @property
    def next_preview_diff_job(self):
        # circular dependencies
        from lp.code.model.branchmergeproposaljob import (
            BranchMergeProposalJob,
            BranchMergeProposalJobType,
        )
        jobs = Store.of(self).find(
            BranchMergeProposalJob,
            BranchMergeProposalJob.branch_merge_proposal == self,
            BranchMergeProposalJob.job_type ==
            BranchMergeProposalJobType.UPDATE_PREVIEW_DIFF,
            BranchMergeProposalJob.job == Job.id,
            Job._status.is_in([JobStatus.WAITING, JobStatus.RUNNING]))
        job = jobs.order_by(Job.scheduled_start, Job.date_created).first()
        if job is not None:
            return job.makeDerived()
        else:
            return None

    reviewed_revision_id = StringCol(default=None)

    commit_message = StringCol(default=None)

    queue_position = IntCol(default=None)

    queuer = ForeignKey(
        dbName='queuer', foreignKey='Person', notNull=False,
        default=None)
    queued_revision_id = StringCol(default=None)

    date_merged = UtcDateTimeCol(default=None)
    merged_revno = IntCol(default=None)

    merge_reporter = ForeignKey(
        dbName='merge_reporter', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False,
        default=None)

    def getRelatedBugTasks(self, user):
        """Bug tasks which are linked to the source but not the target.

        Implies that these would be fixed, in the target, by the merge.
        """
        source_tasks = self.source_branch.getLinkedBugTasks(user)
        target_tasks = self.target_branch.getLinkedBugTasks(user)
        return [bugtask
            for bugtask in source_tasks if bugtask not in target_tasks]

    @property
    def address(self):
        return 'mp+%d@%s' % (self.id, config.launchpad.code_domain)

    superseded_by = ForeignKey(
        dbName='superseded_by', foreignKey='BranchMergeProposal',
        notNull=False, default=None)

    supersedes = Reference("<primary key>", "superseded_by", on_remote=True)

    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)
    date_review_requested = UtcDateTimeCol(notNull=False, default=None)
    date_reviewed = UtcDateTimeCol(notNull=False, default=None)

    @property
    def target(self):
        """See `IHasBranchTarget`."""
        return self.source_branch.target

    root_message_id = StringCol(default=None)

    @property
    def title(self):
        """See `IBranchMergeProposal`."""
        return "[Merge] %(source)s into %(target)s" % {
            'source': self.source_branch.bzr_identity,
            'target': self.target_branch.bzr_identity}

    @property
    def all_comments(self):
        """See `IBranchMergeProposal`."""
        return CodeReviewComment.selectBy(branch_merge_proposal=self.id)

    def getComment(self, id):
        """See `IBranchMergeProposal`.

        This function can raise WrongBranchMergeProposal."""
        comment = CodeReviewComment.get(id)
        if comment.branch_merge_proposal != self:
            raise WrongBranchMergeProposal
        return comment

    def getVoteReference(self, id):
        """See `IBranchMergeProposal`.

        This function can raise WrongBranchMergeProposal."""
        vote = CodeReviewVoteReference.get(id)
        if vote.branch_merge_proposal != self:
            raise WrongBranchMergeProposal
        return vote

    @property
    def _preview_diffs(self):
        return Store.of(self).find(
            PreviewDiff,
            PreviewDiff.branch_merge_proposal_id == self.id).order_by(
                PreviewDiff.date_created)

    @cachedproperty
    def preview_diffs(self):
        return list(self._preview_diffs)

    @cachedproperty
    def preview_diff(self):
        return self._preview_diffs.last()

    date_queued = UtcDateTimeCol(notNull=False, default=None)

    votes = SQLMultipleJoin(
        'CodeReviewVoteReference', joinColumn='branch_merge_proposal')

    def getNotificationRecipients(self, min_level):
        """See IBranchMergeProposal.getNotificationRecipients"""
        recipients = {}
        branch_identity_cache = {
            self.source_branch: self.source_branch.bzr_identity,
            self.target_branch: self.target_branch.bzr_identity,
            }
        branches = [self.source_branch, self.target_branch]
        if self.prerequisite_branch is not None:
            branches.append(self.prerequisite_branch)
        for branch in branches:
            branch_recipients = branch.getNotificationRecipients()
            for recipient in branch_recipients:
                # If the recipient cannot see either of the branches, skip
                # them.
                if (not self.source_branch.visibleByUser(recipient) or
                    not self.target_branch.visibleByUser(recipient)):
                    continue
                subscription, rationale = branch_recipients.getReason(
                    recipient)
                if (subscription.review_level < min_level):
                    continue
                recipients[recipient] = RecipientReason.forBranchSubscriber(
                    subscription, recipient, rationale, self,
                    branch_identity_cache=branch_identity_cache)
        # Add in all the individuals that have been asked for a review,
        # or who have reviewed.  These people get added to the recipients
        # with the rationale of "Reviewer".
        # Don't add a team reviewer to the recipients as they are only going
        # to get emails normally if they are subscribed to one of the
        # branches, and if they are subscribed, they'll be getting this email
        # aleady.
        for review in self.votes:
            reviewer = review.reviewer
            pending = review.comment is None
            recipients[reviewer] = RecipientReason.forReviewer(
                self, pending, reviewer,
                branch_identity_cache=branch_identity_cache)
        # If the registrant of the proposal is getting emails, update the
        # rationale to say that they registered it.  Don't however send them
        # emails if they aren't asking for any.
        if self.registrant in recipients:
            recipients[self.registrant] = RecipientReason.forRegistrant(
                self, branch_identity_cache=branch_identity_cache)
        # If the owner of the source branch is getting emails, override the
        # rationale to say they are the owner of the souce branch.
        source_owner = self.source_branch.owner
        if source_owner in recipients:
            reason = RecipientReason.forSourceOwner(
                self, branch_identity_cache=branch_identity_cache)
            if reason is not None:
                recipients[source_owner] = reason

        return recipients

    def isValidTransition(self, next_state, user=None):
        """See `IBranchMergeProposal`."""
        return is_valid_transition(self, self.queue_status, next_state, user)

    def _transitionToState(self, next_state, user=None):
        """Update the queue_status of the proposal.

        Raise an error if the proposal is in a final state.
        """
        if not self.isValidTransition(next_state, user):
            raise BadStateTransition(
                'Invalid state transition for merge proposal: %s -> %s'
                % (self.queue_status.title, next_state.title))
        # Transition to the same state occur in two particular
        # situations:
        #  * stale posts
        #  * approving a later revision
        # In both these cases, there is no real reason to disallow
        # transitioning to the same state.
        self.queue_status = next_state

    def setStatus(self, status, user=None, revision_id=None):
        """See `IBranchMergeProposal`."""
        # XXX - rockstar - 9 Oct 2008 - jml suggested in a review that this
        # would be better as a dict mapping.
        # See bug #281060.
        if (self.queue_status == BranchMergeProposalStatus.QUEUED and
            status != BranchMergeProposalStatus.QUEUED):
            self.dequeue()
        if status == BranchMergeProposalStatus.WORK_IN_PROGRESS:
            self.setAsWorkInProgress()
        elif status == BranchMergeProposalStatus.NEEDS_REVIEW:
            self.requestReview()
        elif status == BranchMergeProposalStatus.CODE_APPROVED:
            self.approveBranch(user, revision_id)
        elif status == BranchMergeProposalStatus.REJECTED:
            self.rejectBranch(user, revision_id)
        elif status == BranchMergeProposalStatus.QUEUED:
            self.enqueue(user, revision_id)
        elif status == BranchMergeProposalStatus.MERGED:
            self.markAsMerged(merge_reporter=user)
        elif status == BranchMergeProposalStatus.MERGE_FAILED:
            self._transitionToState(status, user=user)
        else:
            raise AssertionError('Unexpected queue status: %s' % status)

    def setAsWorkInProgress(self):
        """See `IBranchMergeProposal`."""
        self._transitionToState(BranchMergeProposalStatus.WORK_IN_PROGRESS)
        self._mark_unreviewed()

    def _mark_unreviewed(self):
        """Clear metadata about a previous review."""
        self.reviewer = None
        self.date_reviewed = None
        self.reviewed_revision_id = None

    def requestReview(self, _date_requested=None):
        """See `IBranchMergeProposal`.

        :param _date_requested: used only for testing purposes to override
            the normal UTC_NOW for when the review was requested.
        """
        # Don't reset the date_review_requested if we are already in the
        # review state.
        if _date_requested is None:
            _date_requested = UTC_NOW
        # If we are going from work in progress to needs review, then reset
        # the root message id and trigger a job to send out the email.
        if self.queue_status == BranchMergeProposalStatus.WORK_IN_PROGRESS:
            self.root_message_id = None
            notify(BranchMergeProposalNeedsReviewEvent(self))
        if self.queue_status != BranchMergeProposalStatus.NEEDS_REVIEW:
            self._transitionToState(BranchMergeProposalStatus.NEEDS_REVIEW)
            self.date_review_requested = _date_requested
            # Clear out any reviewed or queued values.
            self._mark_unreviewed()
            self.queuer = None
            self.queued_revision_id = None

    def isMergable(self):
        """See `IBranchMergeProposal`."""
        # As long as the source branch has not been merged, rejected
        # or superseded, then it is valid to be merged.
        return (self.queue_status not in FINAL_STATES)

    def _reviewProposal(self, reviewer, next_state, revision_id,
                        _date_reviewed=None):
        """Set the proposal to next_state."""
        # Check the reviewer can review the code for the target branch.
        old_state = self.queue_status
        if not self.target_branch.isPersonTrustedReviewer(reviewer):
            raise UserNotBranchReviewer
        # Check the current state of the proposal.
        self._transitionToState(next_state, reviewer)
        # Record the reviewer
        self.reviewer = reviewer
        if _date_reviewed is None:
            _date_reviewed = UTC_NOW
        self.date_reviewed = _date_reviewed
        # Record the reviewed revision id
        self.reviewed_revision_id = revision_id
        notify(BranchMergeProposalStatusChangeEvent(
                self, reviewer, old_state, next_state))

    def approveBranch(self, reviewer, revision_id, _date_reviewed=None):
        """See `IBranchMergeProposal`."""
        self._reviewProposal(
            reviewer, BranchMergeProposalStatus.CODE_APPROVED, revision_id,
            _date_reviewed)

    def rejectBranch(self, reviewer, revision_id, _date_reviewed=None):
        """See `IBranchMergeProposal`."""
        self._reviewProposal(
            reviewer, BranchMergeProposalStatus.REJECTED, revision_id,
            _date_reviewed)

    def enqueue(self, queuer, revision_id):
        """See `IBranchMergeProposal`."""
        if self.queue_status != BranchMergeProposalStatus.CODE_APPROVED:
            self.approveBranch(queuer, revision_id)

        last_entry = BranchMergeProposal.selectOne("""
            BranchMergeProposal.queue_position = (
                SELECT coalesce(MAX(queue_position), 0)
                FROM BranchMergeProposal)
            """)

        # The queue_position will wrap if we ever get to
        # two billion queue entries where the queue has
        # never become empty.  Perhaps sometime in the future
        # we may want to (maybe) consider keeping track of
        # the maximum value here.  I doubt that it'll ever be
        # a problem -- thumper.
        if last_entry is None:
            position = 1
        else:
            position = last_entry.queue_position + 1

        self.queue_status = BranchMergeProposalStatus.QUEUED
        self.queue_position = position
        self.queuer = queuer
        self.queued_revision_id = revision_id or self.reviewed_revision_id
        self.date_queued = UTC_NOW
        self.syncUpdate()

    def dequeue(self):
        """See `IBranchMergeProposal`."""
        if self.queue_status != BranchMergeProposalStatus.QUEUED:
            raise BadStateTransition(
                'Invalid state transition for merge proposal: %s -> %s'
                % (self.queue_state.title,
                   BranchMergeProposalStatus.QUEUED.title))
        self.queue_status = BranchMergeProposalStatus.CODE_APPROVED
        # Clear out the queued values.
        self.queuer = None
        self.queued_revision_id = None
        self.date_queued = None
        # Remove from the queue.
        self.queue_position = None

    def moveToFrontOfQueue(self):
        """See `IBranchMergeProposal`."""
        if self.queue_status != BranchMergeProposalStatus.QUEUED:
            return
        first_entry = BranchMergeProposal.selectOne("""
            BranchMergeProposal.queue_position = (
                SELECT MIN(queue_position)
                FROM BranchMergeProposal)
            """)

        self.queue_position = first_entry.queue_position - 1
        self.syncUpdate()

    def markAsMerged(self, merged_revno=None, date_merged=None,
                     merge_reporter=None):
        """See `IBranchMergeProposal`."""
        old_state = self.queue_status
        self._transitionToState(
            BranchMergeProposalStatus.MERGED, merge_reporter)
        self.merged_revno = merged_revno
        self.merge_reporter = merge_reporter
        # Remove from the queue.
        self.queue_position = None

        # The reviewer of a merged proposal is assumed to have approved, if
        # they rejected it remove the review metadata to avoid confusion.
        if old_state == BranchMergeProposalStatus.REJECTED:
            self._mark_unreviewed()

        if merged_revno is not None:
            branch_revision = Store.of(self).find(
                BranchRevision,
                BranchRevision.branch == self.target_branch,
                BranchRevision.sequence == merged_revno).one()
            if branch_revision is not None:
                date_merged = branch_revision.revision.revision_date

        if date_merged is None:
            date_merged = UTC_NOW
        self.date_merged = date_merged

    def resubmit(self, registrant, source_branch=None, target_branch=None,
                 prerequisite_branch=DEFAULT, description=None,
                 break_link=False):
        """See `IBranchMergeProposal`."""
        if source_branch is None:
            source_branch = self.source_branch
        if target_branch is None:
            target_branch = self.target_branch
        # DEFAULT instead of None, because None is a valid value.
        proposals = BranchMergeProposalGetter.activeProposalsForBranches(
            source_branch, target_branch)
        for proposal in proposals:
            if proposal is not self:
                raise BranchMergeProposalExists(proposal)
        if prerequisite_branch is DEFAULT:
            prerequisite_branch = self.prerequisite_branch
        if description is None:
            description = self.description
        # You can transition from REJECTED to SUPERSEDED, but
        # not from MERGED or SUPERSEDED.
        self._transitionToState(
            BranchMergeProposalStatus.SUPERSEDED, registrant)
        # This sync update is needed as the add landing target does
        # a database query to identify if there are any active proposals
        # with the same source and target branches.
        self.syncUpdate()
        review_requests = list(set(
            (vote.reviewer, vote.review_type) for vote in self.votes))
        proposal = source_branch.addLandingTarget(
            registrant=registrant,
            target_branch=target_branch,
            prerequisite_branch=prerequisite_branch,
            description=description,
            needs_review=True, review_requests=review_requests)
        if not break_link:
            self.superseded_by = proposal
        # This sync update is needed to ensure that the transitive
        # properties of supersedes and superseded_by are visible to
        # the old and the new proposal.
        self.syncUpdate()
        return proposal

    def _normalizeReviewType(self, review_type):
        """Normalse the review type.

        If review_type is None, it stays None.  Otherwise the review_type is
        converted to lower case, and if the string is empty is gets changed to
        None.
        """
        if review_type is not None:
            review_type = review_type.strip()
            if review_type == '':
                review_type = None
            else:
                review_type = review_type.lower()
        return review_type

    def _subscribeUserToStackedBranch(self, branch, user,
                                      checked_branches=None):
        """Subscribe the user to the branch and those it is stacked on."""
        if checked_branches is None:
            checked_branches = []
        branch.subscribe(
            user,
            BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.FULL,
            user)
        if branch.stacked_on is not None:
            checked_branches.append(branch)
            if branch.stacked_on not in checked_branches:
                self._subscribeUserToStackedBranch(
                    branch.stacked_on, user, checked_branches)

    def _acceptable_to_give_visibility(self, branch, reviewer):
        # If the branch is private, only exclusive teams can be subscribed to
        # prevent leaks.
        if (branch.information_type in PRIVATE_INFORMATION_TYPES and
            reviewer.is_team and reviewer.anyone_can_join()):
            return False
        return True

    def _ensureAssociatedBranchesVisibleToReviewer(self, reviewer):
        """ A reviewer must be able to see the source and target branches.

        Currently, we ensure the required visibility by subscribing the user
        to the branch and those on which it is stacked. We do not subscribe
        the reviewer if the branch is private and the reviewer is an open
        team.
        """
        source = self.source_branch
        if (not source.visibleByUser(reviewer) and
            self._acceptable_to_give_visibility(source, reviewer)):
            self._subscribeUserToStackedBranch(source, reviewer)
        target = self.target_branch
        if (not target.visibleByUser(reviewer) and
            self._acceptable_to_give_visibility(source, reviewer)):
            self._subscribeUserToStackedBranch(target, reviewer)

    def nominateReviewer(self, reviewer, registrant, review_type=None,
                         _date_created=DEFAULT, _notify_listeners=True):
        """See `IBranchMergeProposal`."""
        # Return the existing vote reference or create a new one.
        # Lower case the review type.
        review_type = self._normalizeReviewType(review_type)
        vote_reference = self.getUsersVoteReference(reviewer, review_type)
        # If there is no existing review for the reviewer, then create a new
        # one.  If the reviewer is a team, then we don't care if there is
        # already an existing pending review, as some projects expect multiple
        # reviews from a team.
        if vote_reference is None or reviewer.is_team:
            vote_reference = CodeReviewVoteReference(
                branch_merge_proposal=self,
                registrant=registrant,
                reviewer=reviewer,
                date_created=_date_created)
            self._ensureAssociatedBranchesVisibleToReviewer(reviewer)
        vote_reference.review_type = review_type
        if _notify_listeners:
            notify(ReviewerNominatedEvent(vote_reference))
        return vote_reference

    def deleteProposal(self):
        """See `IBranchMergeProposal`."""
        # Delete this proposal, but keep the superseded chain linked.
        if self.supersedes is not None:
            self.supersedes.superseded_by = self.superseded_by
        # Delete the related CodeReviewVoteReferences.
        for vote in self.votes:
            vote.destroySelf()
        # Delete the related CodeReviewComments.
        for comment in self.all_comments:
            comment.destroySelf()
        # Delete all jobs referring to the BranchMergeProposal, whether
        # or not they have completed.
        from lp.code.model.branchmergeproposaljob import BranchMergeProposalJob
        for job in BranchMergeProposalJob.selectBy(
            branch_merge_proposal=self.id):
            job.destroySelf()
        self._preview_diffs.remove()
        self.destroySelf()

    def getUnlandedSourceBranchRevisions(self):
        """See `IBranchMergeProposal`."""
        store = Store.of(self)
        source = SQL("""source AS (SELECT BranchRevision.branch,
            BranchRevision.revision, Branchrevision.sequence FROM
            BranchRevision WHERE BranchRevision.branch = %s and
            BranchRevision.sequence IS NOT NULL ORDER BY BranchRevision.branch
            DESC, BranchRevision.sequence DESC
            LIMIT 10)""" % self.source_branch.id)
        where = SQL("""BranchRevision.revision NOT IN (SELECT revision from
            BranchRevision AS target where target.branch = %s and
            BranchRevision.revision = target.revision)""" %
            self.target_branch.id)
        using = SQL("""source as BranchRevision""")
        revisions = store.with_(source).using(using).find(
            BranchRevision, where)
        return list(revisions.order_by(
            Desc(BranchRevision.sequence)).config(limit=10))

    def createComment(self, owner, subject, content=None, vote=None,
                      review_type=None, parent=None, _date_created=DEFAULT,
                      _notify_listeners=True):
        """See `IBranchMergeProposal`."""
        #:param _date_created: The date the message was created.  Provided
        #    only for testing purposes, as it can break
        # BranchMergeProposal.root_message.
        review_type = self._normalizeReviewType(review_type)
        assert owner is not None, 'Merge proposal messages need a sender'
        parent_message = None
        if parent is not None:
            assert parent.branch_merge_proposal == self, \
                    'Replies must use the same merge proposal as their parent'
            parent_message = parent.message
        if not subject:
            # Get the subject from the parent if there is one, or use a nice
            # default.
            if parent is None:
                subject = self.title
            else:
                subject = parent.message.subject
            if not subject.startswith('Re: '):
                subject = 'Re: ' + subject

        # Avoid circular dependencies.
        from lp.services.messages.model.message import Message, MessageChunk
        msgid = make_msgid('codereview')
        message = Message(
            parent=parent_message, owner=owner, rfc822msgid=msgid,
            subject=subject, datecreated=_date_created)
        MessageChunk(message=message, content=content, sequence=1)
        return self.createCommentFromMessage(
            message, vote, review_type, original_email=None,
            _notify_listeners=_notify_listeners, _validate=False)

    def getUsersVoteReference(self, user, review_type=None):
        """Get the existing vote reference for the given user."""
        # Lower case the review type.
        review_type = self._normalizeReviewType(review_type)
        if user is None:
            return None
        if user.is_team:
            query = And(CodeReviewVoteReference.reviewer == user,
                        CodeReviewVoteReference.review_type == review_type)
        else:
            query = CodeReviewVoteReference.reviewer == user
        return Store.of(self).find(
            CodeReviewVoteReference,
            CodeReviewVoteReference.branch_merge_proposal == self,
            query).order_by(CodeReviewVoteReference.date_created).first()

    def _getTeamVoteReference(self, user, review_type):
        """Get a vote reference where the user is in the review team.

        Only return those reviews where the review_type matches.
        """
        refs = Store.of(self).find(
            CodeReviewVoteReference,
            CodeReviewVoteReference.branch_merge_proposal == self,
            CodeReviewVoteReference.review_type == review_type,
            CodeReviewVoteReference.comment == None)
        for ref in refs.order_by(CodeReviewVoteReference.date_created):
            if user.inTeam(ref.reviewer):
                return ref
        return None

    def _getVoteReference(self, user, review_type):
        """Get the vote reference for the user.

        The returned vote reference will either:
          * the existing vote reference for the user
          * a vote reference of the same type that has been requested of a
            team that the user is a member of
          * a new vote reference for the user
        """
        # Firstly look for a vote reference for the user.
        ref = self.getUsersVoteReference(user)
        if ref is not None:
            return ref
        # Get all the unclaimed CodeReviewVoteReferences with the review_type
        # specified.
        team_ref = self._getTeamVoteReference(user, review_type)
        if team_ref is not None:
            return team_ref
        # If the review_type is not None, check to see if there is an
        # outstanding team review requested with no specified type.
        if review_type is not None:
            team_ref = self._getTeamVoteReference(user, None)
            if team_ref is not None:
                return team_ref
        # Create a new reference.
        return CodeReviewVoteReference(
            branch_merge_proposal=self,
            registrant=user,
            reviewer=user,
            review_type=review_type)

    def createCommentFromMessage(self, message, vote, review_type,
                                 original_email, _notify_listeners=True,
                                 _validate=True):
        """See `IBranchMergeProposal`."""
        if _validate:
            validate_message(original_email)
        review_type = self._normalizeReviewType(review_type)
        code_review_message = CodeReviewComment(
            branch_merge_proposal=self, message=message, vote=vote,
            vote_tag=review_type)
        # Get the appropriate CodeReviewVoteReference for the reviewer.
        # If there isn't one, then create one, otherwise set the comment
        # reference.
        if vote is not None:
            vote_reference = self._getVoteReference(
                message.owner, review_type)
            # Just set the reviewer and review type again on the off chance
            # that the user has edited the review_type or claimed a team
            # review.
            vote_reference.reviewer = message.owner
            vote_reference.review_type = review_type
            vote_reference.comment = code_review_message
        if _notify_listeners:
            notify(NewCodeReviewCommentEvent(
                    code_review_message, original_email))
        return code_review_message

    def updatePreviewDiff(self, diff_content, source_revision_id,
                          target_revision_id, prerequisite_revision_id=None,
                          conflicts=None):
        """See `IBranchMergeProposal`."""
        return PreviewDiff.create(
            self, diff_content, source_revision_id, target_revision_id,
            prerequisite_revision_id, conflicts)

    def getIncrementalDiffRanges(self):
        groups = self.getRevisionsSinceReviewStart()
        return [
            (group[0].revision.getLefthandParent(), group[-1].revision)
            for group in groups]

    def generateIncrementalDiff(self, old_revision, new_revision, diff=None):
        """See `IBranchMergeProposal`."""
        if diff is None:
            source_branch = self.source_branch.getBzrBranch()
            ignore_branches = [self.target_branch.getBzrBranch()]
            if self.prerequisite_branch is not None:
                ignore_branches.append(
                    self.prerequisite_branch.getBzrBranch())
            diff = Diff.generateIncrementalDiff(
                old_revision, new_revision, source_branch, ignore_branches)
        incremental_diff = IncrementalDiff()
        incremental_diff.diff = diff
        incremental_diff.branch_merge_proposal = self
        incremental_diff.old_revision = old_revision
        incremental_diff.new_revision = new_revision
        IMasterStore(IncrementalDiff).add(incremental_diff)
        return incremental_diff

    def getIncrementalDiffs(self, revision_list):
        """See `IBranchMergeProposal`."""
        diffs = Store.of(self).find(IncrementalDiff,
            IncrementalDiff.branch_merge_proposal_id == self.id)
        diff_dict = dict(
            ((diff.old_revision, diff.new_revision), diff)
            for diff in diffs)
        return [diff_dict.get(revisions) for revisions in revision_list]

    @property
    def revision_end_date(self):
        """The cutoff date for showing revisions.

        If the proposal has been merged, then we stop at the merged date. If
        it is rejected, we stop at the reviewed date. For superseded
        proposals, it should ideally use the non-existant date_last_modified,
        but could use the last comment date.
        """
        status = self.queue_status
        if status == BranchMergeProposalStatus.MERGED:
            return self.date_merged
        if status == BranchMergeProposalStatus.REJECTED:
            return self.date_reviewed
        # Otherwise return None representing an open end date.
        return None

    def _getNewerRevisions(self):
        start_date = self.date_review_requested
        if start_date is None:
            start_date = self.date_created
        return self.source_branch.getMainlineBranchRevisions(
            start_date, self.revision_end_date, oldest_first=True)

    def getRevisionsSinceReviewStart(self):
        """Get the grouped revisions since the review started."""
        entries = [
            ((comment.date_created, -1), comment) for comment
            in self.all_comments]
        revisions = self._getNewerRevisions()
        entries.extend(
            ((revision.date_created, branch_revision.sequence),
                branch_revision)
            for branch_revision, revision in revisions)
        entries.sort()
        current_group = []
        for sortkey, entry in entries:
            if IBranchRevision.providedBy(entry):
                current_group.append(entry)
            else:
                if current_group != []:
                    yield current_group
                    current_group = []
        if current_group != []:
            yield current_group

    def getMissingIncrementalDiffs(self):
        ranges = self.getIncrementalDiffRanges()
        diffs = self.getIncrementalDiffs(ranges)
        return [range_ for range_, diff in zip(ranges, diffs) if diff is None]

    @staticmethod
    def preloadDataForBMPs(branch_merge_proposals, user):
        # Utility to load the data related to a list of bmps.
        # Circular imports.
        from lp.code.model.branch import Branch
        from lp.code.model.branchcollection import GenericBranchCollection
        from lp.registry.model.product import Product
        from lp.registry.model.distroseries import DistroSeries

        ids = set()
        source_branch_ids = set()
        person_ids = set()
        for mp in branch_merge_proposals:
            ids.add(mp.id)
            source_branch_ids.add(mp.source_branchID)
            person_ids.add(mp.registrantID)
            person_ids.add(mp.merge_reporterID)

        branches = load_related(
            Branch, branch_merge_proposals, (
                "target_branchID", "prerequisite_branchID",
                "source_branchID"))
        # The stacked on branches are used to check branch visibility.
        GenericBranchCollection.preloadVisibleStackedOnBranches(
            branches, user)

        if len(branches) == 0:
            return

        # Pre-load PreviewDiffs and Diffs.
        preview_diffs = IStore(BranchMergeProposal).find(
            PreviewDiff,
            PreviewDiff.branch_merge_proposal_id.is_in(ids)).order_by(
                PreviewDiff.branch_merge_proposal_id,
                Desc(PreviewDiff.date_created)).config(
                    distinct=[PreviewDiff.branch_merge_proposal_id])
        load_related(Diff, preview_diffs, ['diff_id'])
        for previewdiff in preview_diffs:
            cache = get_property_cache(previewdiff.branch_merge_proposal)
            cache.preview_diff = previewdiff

        # Add source branch owners' to the list of pre-loaded persons.
        person_ids.update(
            branch.ownerID for branch in branches
            if branch.id in source_branch_ids)

        # Pre-load Person and ValidPersonCache.
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            person_ids, need_validity=True))

        # Pre-load branches' data.
        load_related(SourcePackageName, branches, ['sourcepackagenameID'])
        load_related(DistroSeries, branches, ['distroseriesID'])
        load_related(Product, branches, ['productID'])
        GenericBranchCollection.preloadDataForBranches(branches)


class BranchMergeProposalGetter:
    """See `IBranchMergeProposalGetter`."""

    implements(IBranchMergeProposalGetter)

    @staticmethod
    def get(id):
        """See `IBranchMergeProposalGetter`."""
        return BranchMergeProposal.get(id)

    @staticmethod
    def getProposalsForContext(context, status=None, visible_by_user=None):
        """See `IBranchMergeProposalGetter`."""
        collection = getUtility(IAllBranches).visibleByUser(visible_by_user)
        if context is None:
            pass
        elif IProduct.providedBy(context):
            collection = collection.inProduct(context)
        elif IPerson.providedBy(context):
            collection = collection.ownedBy(context)
        else:
            raise BadBranchMergeProposalSearchContext(context)
        return collection.getMergeProposals(status)

    @staticmethod
    def getProposalsForParticipant(participant, status=None,
        visible_by_user=None):
        """See `IBranchMergeProposalGetter`."""
        registrant_select = Select(
            BranchMergeProposal.id,
            BranchMergeProposal.registrantID == participant.id)

        review_select = Select(
                [CodeReviewVoteReference.branch_merge_proposalID],
                [CodeReviewVoteReference.reviewerID == participant.id])

        query = Store.of(participant).find(
            BranchMergeProposal,
            BranchMergeProposal.queue_status.is_in(status),
            Or(BranchMergeProposal.id.is_in(registrant_select),
                BranchMergeProposal.id.is_in(review_select)))
        return query

    @staticmethod
    def getVotesForProposals(proposals):
        """See `IBranchMergeProposalGetter`."""
        if len(proposals) == 0:
            return {}
        ids = [proposal.id for proposal in proposals]
        store = Store.of(proposals[0])
        result = dict([(proposal, []) for proposal in proposals])
        # Make sure that the Person and the review comment are loaded in the
        # storm cache as the reviewer is displayed in a title attribute on the
        # merge proposal listings page, and the message is needed to get to
        # the actual vote for that person.
        tables = [
            CodeReviewVoteReference,
            Join(Person, CodeReviewVoteReference.reviewerID == Person.id),
            LeftJoin(
                CodeReviewComment,
                CodeReviewVoteReference.commentID == CodeReviewComment.id)]
        results = store.using(*tables).find(
            (CodeReviewVoteReference, Person, CodeReviewComment),
            CodeReviewVoteReference.branch_merge_proposalID.is_in(ids))
        for reference, person, comment in results:
            result[reference.branch_merge_proposal].append(reference)
        return result

    @staticmethod
    def getVoteSummariesForProposals(proposals):
        """See `IBranchMergeProposalGetter`."""
        if len(proposals) == 0:
            return {}
        ids = quote([proposal.id for proposal in proposals])
        store = Store.of(proposals[0])
        # First get the count of comments.
        query = """
            SELECT bmp.id, count(crm.*)
            FROM BranchMergeProposal bmp, CodeReviewMessage crm,
                 Message m, MessageChunk mc
            WHERE bmp.id IN %s
              AND bmp.id = crm.branch_merge_proposal
              AND crm.message = m.id
              AND mc.message = m.id
              AND mc.content is not NULL
            GROUP BY bmp.id
            """ % ids
        comment_counts = dict(store.execute(query))
        # Now get the vote counts.
        query = """
            SELECT bmp.id, crm.vote, count(crv.*)
            FROM BranchMergeProposal bmp, CodeReviewVote crv,
                 CodeReviewMessage crm
            WHERE bmp.id IN %s
              AND bmp.id = crv.branch_merge_proposal
              AND crv.vote_message = crm.id
            GROUP BY bmp.id, crm.vote
            """ % ids
        vote_counts = {}
        for proposal_id, vote_value, count in store.execute(query):
            vote = CodeReviewVote.items[vote_value]
            vote_counts.setdefault(proposal_id, {})[vote] = count
        # Now assemble the resulting dict.
        result = {}
        for proposal in proposals:
            summary = result.setdefault(proposal, {})
            summary['comment_count'] = (
                comment_counts.get(proposal.id, 0))
            summary.update(vote_counts.get(proposal.id, {}))
        return result

    @staticmethod
    def activeProposalsForBranches(source_branch, target_branch):
        return BranchMergeProposal.select("""
            BranchMergeProposal.source_branch = %s AND
            BranchMergeProposal.target_branch = %s AND
            BranchMergeProposal.queue_status NOT IN %s
                """ % sqlvalues(source_branch, target_branch, FINAL_STATES))
