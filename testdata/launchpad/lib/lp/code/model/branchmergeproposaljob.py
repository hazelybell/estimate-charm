# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job classes related to BranchMergeProposals are in here.

This includes both jobs for the proposals themselves, or jobs that are
creating proposals, or diffs relating to the proposals.
"""

__metaclass__ = type

__all__ = [
    'BranchMergeProposalJob',
    'BranchMergeProposalJobSource',
    'BranchMergeProposalJobType',
    'CodeReviewCommentEmailJob',
    'GenerateIncrementalDiffJob',
    'MergeProposalNeedsReviewEmailJob',
    'MergeProposalUpdatedEmailJob',
    'ReviewRequestedEmailJob',
    'UpdatePreviewDiffJob',
    ]

import contextlib
from datetime import (
    datetime,
    timedelta,
    )

from lazr.delegates import delegates
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
import pytz
import simplejson
from sqlobject import SQLObjectNotFound
from storm.expr import (
    And,
    Desc,
    Or,
    )
from storm.info import ClassAlias
from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.code.adapters.branch import BranchMergeProposalDelta
from lp.code.enums import BranchType
from lp.code.errors import (
    BranchHasPendingWrites,
    UpdatePreviewDiffNotReady,
    )
from lp.code.interfaces.branchmergeproposal import (
    IBranchMergeProposalJob,
    IBranchMergeProposalJobSource,
    ICodeReviewCommentEmailJob,
    ICodeReviewCommentEmailJobSource,
    IGenerateIncrementalDiffJob,
    IGenerateIncrementalDiffJobSource,
    IMergeProposalNeedsReviewEmailJob,
    IMergeProposalNeedsReviewEmailJobSource,
    IMergeProposalUpdatedEmailJob,
    IMergeProposalUpdatedEmailJobSource,
    IReviewRequestedEmailJob,
    IReviewRequestedEmailJobSource,
    IUpdatePreviewDiffJob,
    IUpdatePreviewDiffJobSource,
    )
from lp.code.interfaces.revision import IRevisionSet
from lp.code.mail.branch import RecipientReason
from lp.code.mail.branchmergeproposal import BMPMailer
from lp.code.mail.codereviewcomment import CodeReviewCommentMailer
from lp.code.model.branchmergeproposal import BranchMergeProposal
from lp.code.model.diff import PreviewDiff
from lp.codehosting.bzrutils import server
from lp.codehosting.vfs import get_ro_server
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import (
    EnumeratedSubclass,
    Job,
    )
from lp.services.job.runner import (
    BaseRunnableJob,
    BaseRunnableJobSource,
    )
from lp.services.mail.sendmail import format_address_for_person
from lp.services.webapp import errorlog


class BranchMergeProposalJobType(DBEnumeratedType):
    """Values that ICodeImportJob.state can take."""

    MERGE_PROPOSAL_NEEDS_REVIEW = DBItem(0, """
        Merge proposal needs review

        This job sends mail to all interested parties about the proposal.
        """)

    UPDATE_PREVIEW_DIFF = DBItem(1, """
        Update the preview diff for the BranchMergeProposal.

        This job generates the preview diff for a BranchMergeProposal.
        """)

    CODE_REVIEW_COMMENT_EMAIL = DBItem(2, """
        Send the code review comment to the subscribers.

        This job sends the email to the merge proposal subscribers and
        reviewers.
        """)

    REVIEW_REQUEST_EMAIL = DBItem(3, """
        Send the review request email to the requested reviewer.

        This job sends an email to the requested reviewer, or members of the
        requested reviewer team asking them to review the proposal.
        """)

    MERGE_PROPOSAL_UPDATED = DBItem(4, """
        Merge proposal updated

        This job sends an email to the subscribers informing them of fields
        that have been changed on the merge proposal itself.
        """)

    GENERATE_INCREMENTAL_DIFF = DBItem(5, """
        Generate incremental diff

        This job generates an incremental diff for a merge proposal.""")


class BranchMergeProposalJob(StormBase):
    """Base class for jobs related to branch merge proposals."""

    implements(IBranchMergeProposalJob)

    __storm_table__ = 'BranchMergeProposalJob'

    id = Int(primary=True)

    jobID = Int('job')
    job = Reference(jobID, Job.id)

    branch_merge_proposalID = Int('branch_merge_proposal', allow_none=False)
    branch_merge_proposal = Reference(
        branch_merge_proposalID, BranchMergeProposal.id)

    job_type = EnumCol(enum=BranchMergeProposalJobType, notNull=True)

    _json_data = Unicode('json_data')

    @property
    def metadata(self):
        return simplejson.loads(self._json_data)

    def __init__(self, branch_merge_proposal, job_type, metadata):
        """Constructor.

        :param branch_merge_proposal: The proposal this job relates to.
        :param job_type: The BranchMergeProposalJobType of this job.
        :param metadata: The type-specific variables, as a JSON-compatible
            dict.
        """
        super(BranchMergeProposalJob, self).__init__()
        json_data = simplejson.dumps(metadata)
        self.job = Job()
        self.branch_merge_proposal = branch_merge_proposal
        self.job_type = job_type
        # XXX AaronBentley 2009-01-29 bug=322819: This should be a bytestring,
        # but the DB representation is unicode.
        self._json_data = json_data.decode('utf-8')

    def sync(self):
        store = Store.of(self)
        store.flush()
        store.autoreload(self)

    def destroySelf(self):
        Store.of(self).remove(self)

    @classmethod
    def selectBy(klass, **kwargs):
        """Return selected instances of this class.

        At least one pair of keyword arguments must be supplied.
        foo=bar is interpreted as 'select all instances of
        BranchMergeProposalJob whose property "foo" is equal to "bar"'.
        """
        assert len(kwargs) > 0
        return IStore(klass).find(klass, **kwargs)

    @classmethod
    def get(klass, key):
        """Return the instance of this class whose key is supplied.

        :raises: SQLObjectNotFound
        """
        instance = IStore(klass).get(klass, key)
        if instance is None:
            raise SQLObjectNotFound(
                'No occurrence of %s has key %s' % (klass.__name__, key))
        return instance

    def makeDerived(self):
        return BranchMergeProposalJobDerived.makeSubclass(self)


class BranchMergeProposalJobDerived(BaseRunnableJob):
    """Intermediate class for deriving from BranchMergeProposalJob."""

    __metaclass__ = EnumeratedSubclass

    delegates(IBranchMergeProposalJob)

    def __init__(self, job):
        self.context = job

    def __repr__(self):
        bmp = self.branch_merge_proposal
        return '<%(job_type)s job for merge %(merge_id)s on %(branch)s>' % {
            'job_type': self.context.job_type.name,
            'merge_id': bmp.id,
            'branch': bmp.source_branch.unique_name,
            }

    @classmethod
    def create(cls, bmp):
        """See `IMergeProposalCreationJob`."""
        return cls._create(bmp, {})

    @classmethod
    def _create(cls, bmp, metadata):
        base_job = BranchMergeProposalJob(
            bmp, cls.class_job_type, metadata)
        job = cls(base_job)
        job.celeryRunOnCommit()
        return job

    @classmethod
    def get(cls, job_id):
        """Get a job by id.

        :return: the BranchMergeProposalJob with the specified id, as the
            current BranchMergeProposalJobDereived subclass.
        :raises: SQLObjectNotFound if there is no job with the specified id,
            or its job_type does not match the desired subclass.
        """
        job = BranchMergeProposalJob.get(job_id)
        if job.job_type != cls.class_job_type:
            raise SQLObjectNotFound(
                'No object found with id %d and type %s' % (job_id,
                cls.class_job_type.title))
        return cls(job)

    @classmethod
    def iterReady(klass):
        """Iterate through all ready BranchMergeProposalJobs."""
        from lp.code.model.branch import Branch
        jobs = IMasterStore(Branch).find(
            (BranchMergeProposalJob),
            And(BranchMergeProposalJob.job_type == klass.class_job_type,
                BranchMergeProposalJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs),
                BranchMergeProposalJob.branch_merge_proposal
                    == BranchMergeProposal.id,
                BranchMergeProposal.source_branch == Branch.id,
                # A proposal isn't considered ready if it has no revisions,
                # or if it is hosted but pending a mirror.
                Branch.revision_count > 0,
                Or(Branch.next_mirror_time == None,
                   Branch.branch_type != BranchType.HOSTED)))
        return (klass(job) for job in jobs)

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BaseRunnableJob.getOopsVars(self)
        bmp = self.context.branch_merge_proposal
        vars.extend([
            ('branchmergeproposal_job_id', self.context.id),
            ('branchmergeproposal_job_type', self.context.job_type.title),
            ('source_branch', bmp.source_branch.unique_name),
            ('target_branch', bmp.target_branch.unique_name)])
        return vars


class MergeProposalNeedsReviewEmailJob(BranchMergeProposalJobDerived):
    """See `IMergeProposalNeedsReviewEmailJob`."""

    implements(IMergeProposalNeedsReviewEmailJob)

    classProvides(IMergeProposalNeedsReviewEmailJobSource)

    class_job_type = BranchMergeProposalJobType.MERGE_PROPOSAL_NEEDS_REVIEW

    config = config.IBranchMergeProposalJobSource

    def run(self):
        """See `IMergeProposalNeedsReviewEmailJob`."""
        mailer = BMPMailer.forCreation(
            self.branch_merge_proposal, self.branch_merge_proposal.registrant)
        mailer.sendAll()

    def getOopsRecipients(self):
        return [self.branch_merge_proposal.registrant.preferredemail.email]

    def getOperationDescription(self):
        return ('notifying people about the proposal to merge %s into %s' %
            (self.branch_merge_proposal.source_branch.bzr_identity,
             self.branch_merge_proposal.target_branch.bzr_identity))


class UpdatePreviewDiffJob(BranchMergeProposalJobDerived):
    """A job to update the preview diff for a branch merge proposal.

    Provides class methods to create and retrieve such jobs.
    """

    implements(IUpdatePreviewDiffJob)

    classProvides(IUpdatePreviewDiffJobSource)

    class_job_type = BranchMergeProposalJobType.UPDATE_PREVIEW_DIFF

    task_queue = 'bzrsyncd_job'

    config = config.IBranchMergeProposalJobSource

    user_error_types = (UpdatePreviewDiffNotReady, )

    retry_error_types = (BranchHasPendingWrites, )

    max_retries = 20

    def checkReady(self):
        """Is this job ready to run?"""
        bmp = self.branch_merge_proposal
        if bmp.source_branch.last_scanned_id is None:
            raise UpdatePreviewDiffNotReady(
                'The source branch has no revisions.')
        if bmp.target_branch.last_scanned_id is None:
            raise UpdatePreviewDiffNotReady(
                'The target branch has no revisions.')
        if bmp.source_branch.pending_writes:
            raise BranchHasPendingWrites(
                'The source branch has pending writes.')

    def acquireLease(self, duration=600):
        return self.job.acquireLease(duration)

    def run(self):
        """See `IRunnableJob`."""
        self.checkReady()
        with server(get_ro_server(), no_replace=True):
            with BranchMergeProposalDelta.monitor(self.branch_merge_proposal):
                PreviewDiff.fromBranchMergeProposal(self.branch_merge_proposal)

    def getOperationDescription(self):
        return ('generating the diff for a merge proposal')

    def getErrorRecipients(self):
        """Return a list of email-ids to notify about user errors."""
        registrant = self.branch_merge_proposal.registrant
        return format_address_for_person(registrant)


class CodeReviewCommentEmailJob(BranchMergeProposalJobDerived):
    """A job to send a code review comment.

    Provides class methods to create and retrieve such jobs.
    """

    implements(ICodeReviewCommentEmailJob)

    classProvides(ICodeReviewCommentEmailJobSource)

    class_job_type = BranchMergeProposalJobType.CODE_REVIEW_COMMENT_EMAIL

    config = config.IBranchMergeProposalJobSource

    def run(self):
        """See `IRunnableJob`."""
        mailer = CodeReviewCommentMailer.forCreation(self.code_review_comment)
        mailer.sendAll()

    @classmethod
    def create(cls, code_review_comment):
        """See `ICodeReviewCommentEmailJobSource`."""
        metadata = cls.getMetadata(code_review_comment)
        bmp = code_review_comment.branch_merge_proposal
        return cls._create(bmp, metadata)

    @staticmethod
    def getMetadata(code_review_comment):
        return {'code_review_comment': code_review_comment.id}

    @property
    def code_review_comment(self):
        """Get the code review comment."""
        return self.branch_merge_proposal.getComment(
            self.metadata['code_review_comment'])

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BranchMergeProposalJobDerived.getOopsVars(self)
        vars.extend([
            ('code_review_comment', self.metadata['code_review_comment']),
            ])
        return vars

    def getErrorRecipients(self):
        """Return a list of email-ids to notify about user errors."""
        commenter = self.code_review_comment.message.owner
        return [format_address_for_person(commenter)]

    def getOperationDescription(self):
        return 'emailing a code review comment'


class ReviewRequestedEmailJob(BranchMergeProposalJobDerived):
    """Send email to the reviewer telling them to review the proposal.

    Provides class methods to create and retrieve such jobs.
    """

    implements(IReviewRequestedEmailJob)

    classProvides(IReviewRequestedEmailJobSource)

    class_job_type = BranchMergeProposalJobType.REVIEW_REQUEST_EMAIL

    config = config.IBranchMergeProposalJobSource

    def run(self):
        """See `IRunnableJob`."""
        reason = RecipientReason.forReviewer(
            self.branch_merge_proposal, True, self.reviewer)
        mailer = BMPMailer.forReviewRequest(
            reason, self.branch_merge_proposal, self.requester)
        mailer.sendAll()

    @classmethod
    def create(cls, review_request):
        """See `IReviewRequestedEmailJobSource`."""
        metadata = cls.getMetadata(review_request)
        bmp = review_request.branch_merge_proposal
        return cls._create(bmp, metadata)

    @staticmethod
    def getMetadata(review_request):
        return {
            'reviewer': review_request.reviewer.name,
            'requester': review_request.registrant.name,
            }

    @property
    def reviewer(self):
        """The person or team who has been asked to review."""
        return getUtility(IPersonSet).getByName(self.metadata['reviewer'])

    @property
    def requester(self):
        """The person who requested the review to be done."""
        return getUtility(IPersonSet).getByName(self.metadata['requester'])

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BranchMergeProposalJobDerived.getOopsVars(self)
        vars.extend([
            ('reviewer', self.metadata['reviewer']),
            ('requester', self.metadata['requester']),
            ])
        return vars

    def getErrorRecipients(self):
        """Return a list of email-ids to notify about user errors."""
        recipients = []
        if self.requester is not None:
            recipients.append(format_address_for_person(self.requester))
        return recipients

    def getOperationDescription(self):
        return 'emailing a reviewer requesting a review'


class MergeProposalUpdatedEmailJob(BranchMergeProposalJobDerived):
    """Send email to the subscribers informing them of updated fields.

    When attributes of the merge proposal are edited, we inform the
    subscribers.
    """

    implements(IMergeProposalUpdatedEmailJob)

    classProvides(IMergeProposalUpdatedEmailJobSource)

    class_job_type = BranchMergeProposalJobType.MERGE_PROPOSAL_UPDATED

    config = config.IBranchMergeProposalJobSource

    def run(self):
        """See `IRunnableJob`."""
        mailer = BMPMailer.forModification(
            self.branch_merge_proposal, self.delta_text, self.editor)
        mailer.sendAll()

    @classmethod
    def create(cls, merge_proposal, delta_text, editor):
        """See `IReviewRequestedEmailJobSource`."""
        metadata = cls.getMetadata(delta_text, editor)
        return cls._create(merge_proposal, metadata)

    @staticmethod
    def getMetadata(delta_text, editor):
        metadata = {'delta_text': delta_text}
        if editor is not None:
            metadata['editor'] = editor.name
        return metadata

    @property
    def editor(self):
        """The person who updated the merge proposal."""
        editor_name = self.metadata.get('editor')
        if editor_name is None:
            return None
        else:
            return getUtility(IPersonSet).getByName(editor_name)

    @property
    def delta_text(self):
        """The changes that were made to the merge proposal."""
        return self.metadata['delta_text']

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BranchMergeProposalJobDerived.getOopsVars(self)
        vars.extend([
            ('editor', self.metadata.get('editor', '(not set)')),
            ('delta_text', self.metadata['delta_text']),
            ])
        return vars

    def getErrorRecipients(self):
        """Return a list of email-ids to notify about user errors."""
        recipients = []
        if self.editor is not None:
            recipients.append(format_address_for_person(self.editor))
        return recipients

    def getOperationDescription(self):
        return 'emailing subscribers about merge proposal changes'


class GenerateIncrementalDiffJob(BranchMergeProposalJobDerived):
    """A job to generate an incremental diff for a branch merge proposal.

    Provides class methods to create and retrieve such jobs.
    """

    implements(IGenerateIncrementalDiffJob)

    classProvides(IGenerateIncrementalDiffJobSource)

    class_job_type = BranchMergeProposalJobType.GENERATE_INCREMENTAL_DIFF

    task_queue = 'bzrsyncd_job'

    config = config.IBranchMergeProposalJobSource

    def acquireLease(self, duration=600):
        return self.job.acquireLease(duration)

    def run(self):
        revision_set = getUtility(IRevisionSet)
        old_revision = revision_set.getByRevisionId(self.old_revision_id)
        new_revision = revision_set.getByRevisionId(self.new_revision_id)
        with server(get_ro_server(), no_replace=True):
            self.branch_merge_proposal.generateIncrementalDiff(
                old_revision, new_revision)

    @classmethod
    def create(cls, merge_proposal, old_revision_id, new_revision_id):
        metadata = cls.getMetadata(old_revision_id, new_revision_id)
        return cls._create(merge_proposal, metadata)

    @staticmethod
    def getMetadata(old_revision_id, new_revision_id):
        return {
            'old_revision_id': old_revision_id,
            'new_revision_id': new_revision_id,
        }

    @property
    def old_revision_id(self):
        """The old revision id for the diff."""
        return self.metadata['old_revision_id']

    @property
    def new_revision_id(self):
        """The new revision id for the diff."""
        return self.metadata['new_revision_id']

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = BranchMergeProposalJobDerived.getOopsVars(self)
        vars.extend([
            ('old_revision_id', self.metadata['old_revision_id']),
            ('new_revision_id', self.metadata['new_revision_id']),
            ])
        return vars

    def getOperationDescription(self):
        return ('generating an incremental diff for a merge proposal')

    def getErrorRecipients(self):
        """Return a list of email-ids to notify about user errors."""
        registrant = self.branch_merge_proposal.registrant
        return format_address_for_person(registrant)


class BranchMergeProposalJobSource(BaseRunnableJobSource):
    """Provide a job source for all merge proposal jobs.

    Only one job for any particular merge proposal is returned.
    """

    classProvides(IBranchMergeProposalJobSource)

    @staticmethod
    def get(job_id):
        """Get a job by id.

        :return: the BranchMergeProposalJob with the specified id, as the
            current BranchMergeProposalJobDereived subclass.
        :raises: SQLObjectNotFound if there is no job with the specified id,
            or its job_type does not match the desired subclass.
        """
        job = BranchMergeProposalJob.get(job_id)
        return job.makeDerived()

    @staticmethod
    def iterReady(job_type=None):
        from lp.code.model.branch import Branch
        SourceBranch = ClassAlias(Branch)
        TargetBranch = ClassAlias(Branch)
        clauses = [
            BranchMergeProposalJob.job == Job.id,
            Job._status.is_in([JobStatus.WAITING, JobStatus.RUNNING]),
            BranchMergeProposalJob.branch_merge_proposal ==
            BranchMergeProposal.id, BranchMergeProposal.source_branch ==
            SourceBranch.id, BranchMergeProposal.target_branch ==
            TargetBranch.id,
            ]
        if job_type is not None:
            clauses.append(BranchMergeProposalJob.job_type == job_type)
        jobs = IMasterStore(Branch).find(
            (BranchMergeProposalJob, Job, BranchMergeProposal,
             SourceBranch, TargetBranch), And(*clauses))
        # Order by the job status first (to get running before waiting), then
        # the date_created, then job type.  This should give us all creation
        # jobs before comment jobs.
        jobs = jobs.order_by(
            Desc(Job._status), Job.date_created,
            Desc(BranchMergeProposalJob.job_type))
        # Now only return one job for any given merge proposal.
        ready_jobs = []
        seen_merge_proposals = set()
        for bmp_job, job, bmp, source, target in jobs:
            # If we've seen this merge proposal already, skip this job.
            if bmp.id in seen_merge_proposals:
                continue
            # We have now seen this merge proposal.
            seen_merge_proposals.add(bmp.id)
            # If the job is running, then skip it
            if job.status == JobStatus.RUNNING:
                continue
            derived_job = bmp_job.makeDerived()
            # If the job is an update preview diff, then check that it is
            # ready.
            if IUpdatePreviewDiffJob.providedBy(derived_job):
                try:
                    derived_job.checkReady()
                except (UpdatePreviewDiffNotReady, BranchHasPendingWrites):
                    # If the job was created under 15 minutes ago wait a bit.
                    minutes = (
                        config.codehosting.update_preview_diff_ready_timeout)
                    cut_off_time = (
                        datetime.now(pytz.UTC) - timedelta(minutes=minutes))
                    if job.date_created > cut_off_time:
                        continue
            ready_jobs.append(derived_job)
        return ready_jobs
