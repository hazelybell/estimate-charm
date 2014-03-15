# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views, navigation and actions for BranchMergeProposals."""

__metaclass__ = type
__all__ = [
    'BranchMergeCandidateView',
    'BranchMergeProposalActionNavigationMenu',
    'BranchMergeProposalAddVoteView',
    'BranchMergeProposalChangeStatusView',
    'BranchMergeProposalCommitMessageEditView',
    'BranchMergeProposalContextMenu',
    'BranchMergeProposalDeleteView',
    'BranchMergeProposalDequeueView',
    'BranchMergeProposalDescriptionEditView',
    'BranchMergeProposalEditMenu',
    'BranchMergeProposalEditView',
    'BranchMergeProposalEnqueueView',
    'BranchMergeProposalInlineDequeueView',
    'BranchMergeProposalJumpQueueView',
    'BranchMergeProposalNavigation',
    'BranchMergeProposalMergedView',
    'BranchMergeProposalPrimaryContext',
    'BranchMergeProposalRequestReviewView',
    'BranchMergeProposalResubmitView',
    'BranchMergeProposalSubscribersView',
    'BranchMergeProposalView',
    'BranchMergeProposalVoteView',
    'latest_proposals_for_each_branch',
    ]

from functools import wraps
import operator

from lazr.delegates import delegates
from lazr.restful.interface import copy_field
from lazr.restful.interfaces import (
    IJSONRequestCache,
    IWebServiceClientRequest,
    )
import simplejson
from zope.component import (
    adapts,
    getMultiAdapter,
    getUtility,
    )
from zope.formlib import form
from zope.formlib.widgets import TextAreaWidget
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    Text,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.browser.lazrjs import (
    TextAreaEditorWidget,
    vocabulary_to_choice_edit_items,
    )
from lp.app.browser.tales import DateTimeFormatterAPI
from lp.app.longpoll import subscribe
from lp.code.adapters.branch import BranchMergeProposalNoPreviewDiffDelta
from lp.code.browser.codereviewcomment import CodeReviewDisplayComment
from lp.code.browser.decorations import DecoratedBranch
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchType,
    CodeReviewNotificationLevel,
    CodeReviewVote,
    )
from lp.code.errors import (
    BranchMergeProposalExists,
    ClaimReviewFailed,
    InvalidBranchMergeProposal,
    WrongBranchMergeProposal,
    )
from lp.code.interfaces.branchmergeproposal import IBranchMergeProposal
from lp.code.interfaces.codereviewcomment import ICodeReviewComment
from lp.code.interfaces.codereviewvote import ICodeReviewVoteReference
from lp.code.interfaces.diff import IPreviewDiff
from lp.registry.interfaces.person import IPersonSet
from lp.services.comments.interfaces.conversation import (
    IComment,
    IConversation,
    )
from lp.services.config import config
from lp.services.features import getFeatureFlag
from lp.services.fields import (
    Summary,
    Whiteboard,
    )
from lp.services.librarian.interfaces.client import LibrarianServerError
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    stepthrough,
    stepto,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import IPrimaryContext
from lp.services.webapp.menu import NavigationMenu


def latest_proposals_for_each_branch(proposals):
    """Returns the most recent merge proposals for any particular branch.

    Also filters out proposals that the logged in user can't see.
    """
    targets = {}
    for proposal in proposals:
        # Don't show the proposal if the user can't see it.
        if not check_permission('launchpad.View', proposal):
            continue
        # Only show the must recent proposal for any given target.
        date_created = proposal.date_created
        target_id = proposal.target_branch.id

        if target_id not in targets or date_created > targets[target_id][1]:
            targets[target_id] = (proposal, date_created)

    return sorted(
        [proposal for proposal, date_created in targets.itervalues()],
        key=operator.attrgetter('date_created'), reverse=True)


class BranchMergeProposalPrimaryContext:
    """The primary context is the proposal is that of the source branch."""

    implements(IPrimaryContext)

    def __init__(self, branch_merge_proposal):
        self.context = IPrimaryContext(
            branch_merge_proposal.source_branch).context


class BranchMergeProposalBreadcrumb(Breadcrumb):
    """An `IBreadcrumb` for a merge proposal."""

    @property
    def text(self):
        return 'Merge into %s' % self.context.target_branch.name


def notify(func):
    """Decorate a view method to send a notification."""
    @wraps(func)
    def decorator(view, *args, **kwargs):
        with BranchMergeProposalNoPreviewDiffDelta.monitor(view.context):
            return func(view, *args, **kwargs)
    return decorator


def update_and_notify(func):
    """Decorate an action to update from a form and send a notification."""

    @notify
    def decorator(view, action, data):
        result = func(view, action, data)
        form.applyChanges(
            view.context, view.form_fields, data, view.adapters)
        return result
    return decorator


class BranchMergeCandidateView(LaunchpadView):
    """Provides a small fragment of landing targets"""

    def friendly_text(self):
        """Prints friendly text for a branch."""
        friendly_texts = {
            BranchMergeProposalStatus.WORK_IN_PROGRESS: 'On hold',
            BranchMergeProposalStatus.NEEDS_REVIEW: 'Ready for review',
            BranchMergeProposalStatus.CODE_APPROVED: 'Approved',
            BranchMergeProposalStatus.REJECTED: 'Rejected',
            BranchMergeProposalStatus.MERGED: 'Merged',
            BranchMergeProposalStatus.MERGE_FAILED:
                'Approved [Merge Failed]',
            BranchMergeProposalStatus.QUEUED: 'Queued',
            BranchMergeProposalStatus.SUPERSEDED: 'Superseded',
        }
        return friendly_texts[self.context.queue_status]

    @property
    def status_title(self):
        """The title for the status text.

        Only set if the status is approved or rejected.
        """
        result = ''
        if self.context.queue_status in (
            BranchMergeProposalStatus.CODE_APPROVED,
            BranchMergeProposalStatus.REJECTED):
            formatter = DateTimeFormatterAPI(self.context.date_reviewed)
            result = '%s %s' % (
                self.context.reviewer.displayname,
                formatter.displaydate())
        return result


class BranchMergeProposalMenuMixin:
    """Mixin class for merge proposal menus."""

    @enabled_with_permission('launchpad.AnyPerson')
    def add_comment(self):
        return Link('+comment', 'Add a review or comment', icon='add')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Edit details'
        enabled = self.context.isMergable()
        return Link('+edit', text, icon='edit', enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def set_description(self):
        text = 'Set description'
        return Link('+edit-description', text, icon='add')

    @enabled_with_permission('launchpad.Edit')
    def set_commit_message(self):
        text = 'Set commit message'
        enabled = self.context.isMergable()
        return Link('+edit-commit-message', text, icon='add',
                    enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def edit_status(self):
        text = 'Change status'
        return Link('+edit-status', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def delete(self):
        text = 'Delete proposal to merge'
        return Link('+delete', text, icon='trash-icon')

    def _enabledForStatus(self, next_state):
        """True if the next_state is a valid transition for the current user.

        Return False if the current state is next_state.
        """
        bmp = self.branch_merge_proposal
        status = bmp.queue_status
        if status == next_state:
            return False
        else:
            return bmp.isValidTransition(next_state, self.user)

    @enabled_with_permission('launchpad.Edit')
    def request_review(self):
        text = 'Request a review'
        enabled = self._enabledForStatus(
            BranchMergeProposalStatus.NEEDS_REVIEW)
        if (self.context.queue_status ==
            BranchMergeProposalStatus.NEEDS_REVIEW):
            enabled = True
            if (self.context.votes.count()) > 0:
                text = 'Request another review'
        return Link('+request-review', text, icon='add', enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def merge(self):
        text = 'Mark as merged'
        enabled = self._enabledForStatus(
            BranchMergeProposalStatus.MERGED)
        return Link('+merged', text, enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def update_merge_revno(self):
        text = 'Update revision number'
        return Link('+merged', text)

    @enabled_with_permission('launchpad.Edit')
    def enqueue(self):
        text = 'Queue for merging'
        enabled = self._enabledForStatus(
            BranchMergeProposalStatus.QUEUED)
        return Link('+enqueue', text, enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def dequeue(self):
        text = 'Remove from queue'
        enabled = (self.context.queue_status ==
                   BranchMergeProposalStatus.QUEUED)
        return Link('+dequeue', text, enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def resubmit(self):
        text = 'Resubmit proposal'
        enabled = self._enabledForStatus(
            BranchMergeProposalStatus.SUPERSEDED)
        return Link('+resubmit', text, enabled=enabled, icon='edit')


class BranchMergeProposalEditMenu(NavigationMenu,
                                  BranchMergeProposalMenuMixin):
    """Edit menu for Branch Merge Proposals."""

    usedfor = IBranchMergeProposal
    title = 'Edit Proposal'
    facet = 'branches'
    links = ['resubmit', 'delete']

    @property
    def branch_merge_proposal(self):
        return self.context


class BranchMergeProposalContextMenu(ContextMenu,
                                     BranchMergeProposalMenuMixin):
    """Context menu for merge proposals."""

    usedfor = IBranchMergeProposal
    links = [
        'add_comment',
        'dequeue',
        'set_commit_message',
        'set_description',
        'edit_status',
        'enqueue',
        'merge',
        'request_review',
        'resubmit',
        'update_merge_revno',
        ]

    @property
    def branch_merge_proposal(self):
        return self.context


class IBranchMergeProposalActionMenu(Interface):
    """A marker interface for the global action navigation menu."""


class BranchMergeProposalActionNavigationMenu(NavigationMenu,
                                              BranchMergeProposalMenuMixin):
    """A sub-menu for acting upon a Product."""

    usedfor = IBranchMergeProposalActionMenu
    facet = 'branches'
    links = ('resubmit', 'delete')

    @property
    def branch_merge_proposal(self):
        # This context is the view, the view's context is the bmp.
        return self.context.context


class UnmergedRevisionsMixin:
    """Provides the methods needed to show unmerged revisions."""

    @cachedproperty
    def unlanded_revisions(self):
        """Return the unlanded revisions from the source branch."""
        return self.context.getUnlandedSourceBranchRevisions()

    @property
    def pending_writes(self):
        """Needed to make the branch-revisions metal macro work."""
        return False

    @property
    def codebrowse_url(self):
        """Return the link to codebrowse for this branch."""
        return self.context.source_branch.codebrowse_url()


class BranchMergeProposalRevisionIdMixin:
    """A mixin class to provide access to the revision ids."""

    def _getRevisionNumberForRevisionId(self, revision_id):
        """Find the revision number that corresponds to the revision id.

        If there was no last reviewed revision, None is returned.

        If the reviewed revision is no longer in the revision history of
        the source branch, then a message is returned.
        """
        if revision_id is None:
            return None
        # If the source branch is REMOTE, then there won't be any ids.
        source_branch = self.context.source_branch
        if source_branch.branch_type == BranchType.REMOTE:
            return revision_id
        else:
            branch_revision = source_branch.getBranchRevision(
                revision_id=revision_id)
            if branch_revision is None:
                return "no longer in the source branch."
            elif branch_revision.sequence is None:
                return (
                    "no longer in the revision history of the source branch.")
            else:
                return branch_revision.sequence

    @cachedproperty
    def reviewed_revision_number(self):
        """Return the number of the reviewed revision."""
        return self._getRevisionNumberForRevisionId(
            self.context.reviewed_revision_id)

    @cachedproperty
    def queued_revision_number(self):
        """Return the number of the queued revision."""
        return self._getRevisionNumberForRevisionId(
            self.context.queued_revision_id)


class BranchMergeProposalNavigation(Navigation):
    """Navigation from BranchMergeProposal to CodeReviewComment views."""

    usedfor = IBranchMergeProposal

    @stepthrough('reviews')
    def traverse_review(self, id):
        """Navigate to a CodeReviewVoteReference through its BMP."""
        try:
            id = int(id)
        except ValueError:
            return None
        try:
            return self.context.getVoteReference(id)
        except WrongBranchMergeProposal:
            return None

    @stepthrough('comments')
    def traverse_comment(self, id):
        try:
            id = int(id)
        except ValueError:
            return None
        try:
            return self.context.getComment(id)
        except WrongBranchMergeProposal:
            return None

    @stepto("+preview-diff")
    def preview_diff(self):
        """Step to the preview diff."""
        return self.context.preview_diff

    @stepthrough('+review')
    def review(self, id):
        """Step to the CodeReviewVoteReference."""
        try:
            id = int(id)
        except ValueError:
            return None
        try:
            return self.context.getVoteReference(id)
        except WrongBranchMergeProposal:
            return None


class CodeReviewConversation:
    """A code review conversation."""

    implements(IConversation)

    def __init__(self, comments):
        self.comments = comments


class ClaimButton(Interface):
    """A simple interface to populate the form to enqueue a proposal."""

    review_id = Int(required=True)


class BranchMergeProposalStatusMixin:
    '''A mixin for generating status vocabularies.'''

    def _createStatusVocabulary(self):
        # Create the vocabulary that is used for the status widget.
        possible_next_states = (
            BranchMergeProposalStatus.WORK_IN_PROGRESS,
            BranchMergeProposalStatus.NEEDS_REVIEW,
            BranchMergeProposalStatus.CODE_APPROVED,
            BranchMergeProposalStatus.REJECTED,
            # BranchMergeProposalStatus.QUEUED,
            BranchMergeProposalStatus.MERGED,
            )
        terms = []
        for status in possible_next_states:
            if not self.context.isValidTransition(status, self.user):
                continue
            else:
                title = status.title
            terms.append(SimpleTerm(status, status.name, title))
        return SimpleVocabulary(terms)


class DiffRenderingMixin:
    """A mixin class for handling diff text."""

    @property
    def diff_available(self):
        """Is the preview diff available from the librarian?"""
        if getattr(self, '_diff_available', None) is None:
            # Load the cache so that the answer is known.
            self.preview_diff_text
        return self._diff_available

    @cachedproperty
    def preview_diff_text(self):
        """Return a (hopefully) intelligently encoded review diff."""
        self._diff_available = True
        preview_diff = self.preview_diff
        if preview_diff is None:
            return None
        try:
            diff = preview_diff.text.decode('utf-8')
        except UnicodeDecodeError:
            diff = preview_diff.text.decode('windows-1252', 'replace')
        except LibrarianServerError:
            self._diff_available = False
            diff = ''
        # Strip off the trailing carriage returns.
        return diff.rstrip('\n')

    @cachedproperty
    def diff_oversized(self):
        """Return True if the preview_diff is over the configured size limit.

        The diff can be over the limit in two ways.  If the diff is oversized
        in bytes it will be cut off at the Diff.text method.  If the number of
        lines is over the max_format_lines, then it is cut off at the fmt:diff
        processing.
        """
        preview_diff = self.preview_diff
        if preview_diff is None:
            return False
        diff_text = self.preview_diff_text
        return diff_text.count('\n') >= config.diff.max_format_lines


class ICodeReviewNewRevisions(IComment):
    """Marker interface used to register views for CodeReviewNewRevisions."""


class CodeReviewNewRevisions:
    """Represents a logical grouping of revisions.

    Each object instance represents a number of revisions scanned at a
    particular time.
    """
    implements(ICodeReviewNewRevisions)

    def __init__(self, revisions, date, branch, diff):
        self.revisions = revisions
        self.branch = branch
        self.has_body = False
        self.has_footer = True
        # The date attribute is used to sort the comments in the conversation.
        self.date = date
        self.diff = diff

        # Other standard IComment attributes are not used.
        self.extra_css_class = None
        self.comment_author = None
        self.body_text = None
        self.text_for_display = None
        self.download_url = None
        self.too_long = False
        self.too_long_to_render = False
        self.comment_date = None
        self.display_attachments = False
        self.index = None

    def download(self, request):
        pass


class CodeReviewNewRevisionsView(LaunchpadView):
    """The view for rendering the new revisions."""

    @property
    def codebrowse_url(self):
        """Return the link to codebrowse for this branch."""
        return self.context.branch.codebrowse_url()


class BranchMergeProposalView(LaunchpadFormView, UnmergedRevisionsMixin,
                              BranchMergeProposalRevisionIdMixin,
                              BranchMergeProposalStatusMixin,
                              DiffRenderingMixin):
    """A basic view used for the index page."""

    implements(IBranchMergeProposalActionMenu)

    schema = ClaimButton

    def initialize(self):
        super(BranchMergeProposalView, self).initialize()
        cache = IJSONRequestCache(self.request)
        cache.objects.update({
            'branch_diff_link':
                'https://%s/+loggerhead/%s/diff/' % (
                    config.launchpad.code_domain,
                    self.context.source_branch.unique_name),
            })
        if getFeatureFlag("longpoll.merge_proposals.enabled"):
            cache.objects['merge_proposal_event_key'] = (
                subscribe(self.context).event_key)

    @action('Claim', name='claim')
    def claim_action(self, action, data):
        """Claim this proposal."""
        request = self.context.getVoteReference(data['review_id'])
        if request is not None:
            try:
                request.claimReview(self.user)
            except ClaimReviewFailed as e:
                self.request.response.addErrorNotification(unicode(e))
        self.next_url = canonical_url(self.context)

    @property
    def comment_location(self):
        """Location of page for commenting on this proposal."""
        return canonical_url(self.context, view_name='+comment')

    @cachedproperty
    def conversation(self):
        """Return a conversation that is to be rendered."""
        # Sort the comments by date order.
        merge_proposal = self.context
        groups = list(merge_proposal.getRevisionsSinceReviewStart())
        source = DecoratedBranch(merge_proposal.source_branch)
        comments = []
        if getFeatureFlag('code.incremental_diffs.enabled'):
            ranges = [
                (revisions[0].revision.getLefthandParent(),
                 revisions[-1].revision)
                for revisions in groups]
            diffs = merge_proposal.getIncrementalDiffs(ranges)
        else:
            diffs = [None] * len(groups)
        for revisions, diff in zip(groups, diffs):
            newrevs = CodeReviewNewRevisions(
                revisions, revisions[-1].revision.date_created, source, diff)
            comments.append(newrevs)
        while merge_proposal is not None:
            from_superseded = merge_proposal != self.context
            comments.extend(
                CodeReviewDisplayComment(
                    comment, from_superseded, limit_length=True)
                for comment in merge_proposal.all_comments)
            merge_proposal = merge_proposal.supersedes
        comments = sorted(comments, key=operator.attrgetter('date'))
        return CodeReviewConversation(comments)

    @property
    def comments(self):
        """Return comments associated with this proposal, plus styling info.

        Comments are in threaded order, and the style indicates indenting
        for use with threads.
        """
        message_to_comment = {}
        messages = []
        for comment in self.context.all_comments:
            message_to_comment[comment.message] = comment
            messages.append(comment.message)
        message_set = getUtility(IMessageSet)
        threads = message_set.threadMessages(messages)
        result = []
        for depth, message in message_set.flattenThreads(threads):
            comment = message_to_comment[message]
            style = 'margin-left: %dem;' % (2 * depth)
            result.append(dict(style=style, comment=comment))
        return result

    @property
    def label(self):
        return "Merge %s into %s" % (
            self.context.source_branch.bzr_identity,
            self.context.target_branch.bzr_identity)

    @property
    def pending_diff(self):
        return (
            self.context.next_preview_diff_job is not None or
            self.context.source_branch.pending_writes)

    @cachedproperty
    def preview_diff(self):
        """Return a `Diff` of the preview.

        If no preview is available, try using the review diff.
        """
        if self.context.preview_diff is not None:
            return self.context.preview_diff
        return None

    @property
    def has_bug_or_spec(self):
        """Return whether or not the merge proposal has a linked bug or spec.
        """
        return self.linked_bugtasks or self.spec_links

    @property
    def spec_links(self):
        return list(
            self.context.source_branch.getSpecificationLinks(self.user))

    @cachedproperty
    def linked_bugtasks(self):
        """Return BugTasks linked to the source branch."""
        return self.context.getRelatedBugTasks(self.user)

    @property
    def edit_description_link_class(self):
        if self.context.description:
            return "hidden"
        else:
            return ""

    @property
    def description_html(self):
        """The description as widget HTML."""
        mp = self.context
        description = IBranchMergeProposal['description']
        title = "Description of the Change"
        return TextAreaEditorWidget(
            mp, description, title, edit_view='+edit-description')

    @property
    def edit_commit_message_link_class(self):
        if self.context.commit_message:
            return "hidden"
        else:
            return ""

    @property
    def commit_message_html(self):
        """The commit message as widget HTML."""
        mp = self.context
        commit_message = IBranchMergeProposal['commit_message']
        title = "Commit Message"
        return TextAreaEditorWidget(
            mp, commit_message, title, edit_view='+edit-commit-message')

    @property
    def status_config(self):
        """The config to configure the ChoiceSource JS widget."""
        return simplejson.dumps({
            'status_widget_items': vocabulary_to_choice_edit_items(
                self._createStatusVocabulary(),
                css_class_prefix='mergestatus'),
            'status_value': self.context.queue_status.title,
            'source_revid': self.context.source_branch.last_scanned_id,
            'user_can_edit_status': check_permission(
                'launchpad.Edit', self.context),
            })


class DecoratedCodeReviewVoteReference:
    """Provide a code review vote that knows if it is important or not."""

    delegates(ICodeReviewVoteReference)

    status_text_map = {
        CodeReviewVote.DISAPPROVE: CodeReviewVote.DISAPPROVE.title,
        CodeReviewVote.APPROVE: CodeReviewVote.APPROVE.title,
        CodeReviewVote.ABSTAIN: CodeReviewVote.ABSTAIN.title,
        CodeReviewVote.NEEDS_INFO: CodeReviewVote.NEEDS_INFO.title,
        CodeReviewVote.NEEDS_FIXING: CodeReviewVote.NEEDS_FIXING.title,
        CodeReviewVote.RESUBMIT: CodeReviewVote.RESUBMIT.title,
        }

    def __init__(self, context, user, users_vote):
        self.context = context
        self.can_change_review = (user == context.reviewer)
        if user is None:
            self.user_can_review = False
        else:
            # The user cannot review for a requested team review if the user
            # has already reviewed this proposal.
            self.user_can_review = (self.can_change_review or
                 (user.inTeam(context.reviewer) and (users_vote is None)))
        if context.reviewer == user:
            self.user_can_claim = False
        else:
            self.user_can_claim = self.user_can_review
        if user in (context.reviewer, context.registrant):
            self.user_can_reassign = True
        else:
            self.user_can_reassign = False

    @cachedproperty
    def trusted(self):
        """ Is the person a trusted reviewer."""
        proposal = self.context.branch_merge_proposal
        return proposal.target_branch.isPersonTrustedReviewer(
            self.context.reviewer)

    @property
    def show_date_requested(self):
        """Show the requested date if the reviewer is not the requester."""
        return self.context.registrant != self.context.reviewer

    @property
    def date_requested(self):
        """When the review was requested or None."""
        return self.context.date_created

    @property
    def review_type_str(self):
        """We want '' not 'None' if no type set."""
        if self.context.review_type is None:
            return ''
        return self.context.review_type

    @property
    def date_of_comment(self):
        """The date of the comment, not the date_created of the vote."""
        return self.context.comment.message.datecreated

    @property
    def status_text(self):
        """The text shown in the table of the users vote."""
        return self.status_text_map[self.context.comment.vote]


class BranchMergeProposalVoteView(LaunchpadView):
    """The view used for the tables of votes and requested reviews."""

    @property
    def show_table(self):
        """Should the reviewer table be shown at all?

        We want to show the table when there is something for the user to do
        with it. If the user can request a review, or is a reviewer with
        reviews to do, then show the table.
        """
        # The user can request a review if the user has edit permissions, and
        # the branch is not in a final state.  We want to show the table as
        # the menu link is now shown in the table itself.
        can_request_review = (
            check_permission('launchpad.Edit', self.context) and
            self.context.isMergable())

        # Show the table if there are review to show, or the user can review,
        # or if the user can request a review.
        return (len(self.reviews) > 0 or can_request_review)

    @cachedproperty
    def reviews(self):
        """Return the decorated votes for the proposal."""
        users_vote = self.context.getUsersVoteReference(self.user)
        return [DecoratedCodeReviewVoteReference(vote, self.user, users_vote)
                for vote in self.context.votes
                if check_permission('launchpad.LimitedView', vote.reviewer)]

    @cachedproperty
    def current_reviews(self):
        """The current votes ordered by vote then date."""
        # We want the reviews in a specific order.
        # Disapprovals first, then approvals, then abstentions.
        reviews = [review for review in self.reviews
                   if review.comment is not None]
        return sorted(reviews, key=operator.attrgetter('date_of_comment'),
                      reverse=True)

    @cachedproperty
    def requested_reviews(self):
        """Reviews requested but not yet done."""
        reviews = [review for review in self.reviews
                   if review.comment is None]
        # Now sort so the most recently created is first.
        return sorted(reviews, key=operator.attrgetter('date_created'),
                      reverse=True)


class IReviewRequest(Interface):
    """Schema for requesting a review."""

    reviewer = copy_field(ICodeReviewVoteReference['reviewer'])

    review_type = copy_field(
        ICodeReviewVoteReference['review_type'],
        description=u'Lowercase keywords describing the type of review you '
                     'would like to be performed.')


class BranchMergeProposalRequestReviewView(LaunchpadEditFormView):
    """The view used to request a review of the merge proposal."""

    schema = IReviewRequest
    page_title = label = "Request review"

    @property
    def initial_values(self):
        """Force the non-BMP values to None."""
        return {'reviewer': None, 'review_type': None}

    @property
    def adapters(self):
        """Force IReviewRequest handling for BranchMergeProposal."""
        return {IReviewRequest: self.context}

    @property
    def is_needs_review(self):
        """Return True if queue status is NEEDS_REVIEW."""
        return (self.context.queue_status ==
            BranchMergeProposalStatus.NEEDS_REVIEW)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    def requestReview(self, candidate, review_type):
        """Request a `review_type` review from `candidate` and email them."""
        self.context.nominateReviewer(candidate, self.user, review_type)

    @action('Request Review', name='review')
    @notify
    def review_action(self, action, data):
        """Set 'Needs review' status, nominate reviewers, send emails."""
        self.context.requestReview()
        candidate = data.pop('reviewer', None)
        review_type = data.pop('review_type', None)
        if candidate is not None:
            self.requestReview(candidate, review_type)

    def validate(self, data):
        """Ensure that the proposal is in an appropriate state."""
        if not self.context.isMergable():
            self.addError("The merge proposal is not an a valid state to "
                          "mark as 'Needs review'.")


class ReviewForm(Interface):
    """A simple interface to define the revision number field."""

    revision_number = Int(
        title=_("Reviewed Revision"), required=True,
        description=_("The revision number on the source branch which "
                      "has been reviewed."))

    whiteboard = Whiteboard(
        title=_('Whiteboard'), required=False,
        description=_('Notes about the merge.'))


class MergeProposalEditView(LaunchpadEditFormView,
                            BranchMergeProposalRevisionIdMixin):
    """A base class for merge proposal edit views."""

    def initialize(self):
        # Record next_url and cancel url now
        self.next_url = canonical_url(self.context)
        self.cancel_url = self.next_url
        super(MergeProposalEditView, self).initialize()

    def _getRevisionId(self, data):
        """Translate the revision number that was entered into a revision id.

        If the branch is REMOTE we won't have any scanned revisions to compare
        against, so store the raw integer revision number as the revision id.
        """
        source_branch = self.context.source_branch
        # Get the revision number out of the data.
        if source_branch.branch_type == BranchType.REMOTE:
            return str(data.pop('revision_number'))
        else:
            branch_revision = source_branch.getBranchRevision(
                sequence=data.pop('revision_number'))
            return branch_revision.revision.revision_id

    def _validateRevisionNumber(self, data, revision_name):
        """Check to make sure that the revision number entered is valid."""
        rev_no = data.get('revision_number')
        if rev_no is not None:
            try:
                rev_no = int(rev_no)
            except ValueError:
                self.setFieldError(
                    'revision_number',
                    'The %s revision must be a positive number.'
                    % revision_name)
            else:
                if rev_no < 1:
                    self.setFieldError(
                        'revision_number',
                        'The %s revision must be a positive number.'
                        % revision_name)
                # Accept any positive integer for a REMOTE branch.
                source_branch = self.context.source_branch
                if (source_branch.branch_type != BranchType.REMOTE and
                    rev_no > source_branch.revision_count):
                    self.setFieldError(
                        'revision_number',
                        'The %s revision cannot be larger than the '
                        'tip revision of the source branch.'
                        % revision_name)


class ResubmitSchema(IBranchMergeProposal):

    break_link = Bool(
        title=u'Start afresh',
        description=(
            u'Do not show old conversation and do not link to superseded'
            ' proposal.'),
        default=False,)


class BranchMergeProposalResubmitView(LaunchpadFormView,
                                      UnmergedRevisionsMixin):
    """The view to resubmit a proposal to merge."""

    schema = ResubmitSchema
    for_input = True
    page_title = label = "Resubmit proposal to merge"
    field_names = [
        'source_branch',
        'target_branch',
        'prerequisite_branch',
        'description',
        'break_link',
        ]

    def initialize(self):
        self.cancel_url = canonical_url(self.context)
        super(BranchMergeProposalResubmitView, self).initialize()

    @property
    def initial_values(self):
        UNSET = object()
        items = ((key, getattr(self.context, key, UNSET)) for key in
                  self.field_names if key != 'break_link')
        return dict(item for item in items if item[1] is not UNSET)

    @action('Resubmit', name='resubmit')
    def resubmit_action(self, action, data):
        """Resubmit this proposal."""
        try:
            proposal = self.context.resubmit(
                self.user, data['source_branch'], data['target_branch'],
                data['prerequisite_branch'], data['description'],
                data['break_link'])
        except BranchMergeProposalExists as e:
            message = structured(
                'Cannot resubmit because <a href="%(url)s">a similar merge'
                ' proposal</a> is already active.',
                url=canonical_url(e.existing_proposal))
            self.request.response.addErrorNotification(message)
            self.next_url = canonical_url(self.context)
            return None
        except InvalidBranchMergeProposal as e:
            self.addError(str(e))
            return None
        self.next_url = canonical_url(proposal)
        return proposal


class BranchMergeProposalEditView(MergeProposalEditView):
    """The view to control the editing of merge proposals."""
    schema = IBranchMergeProposal
    page_title = label = "Edit branch merge proposal"
    field_names = ["commit_message", "whiteboard"]

    @action('Update', name='update')
    def update_action(self, action, data):
        """Update the whiteboard and go back to the source branch."""
        self.updateContextFromData(data)


class BranchMergeProposalCommitMessageEditView(MergeProposalEditView):
    """The view to edit the commit message of merge proposals."""

    schema = IBranchMergeProposal
    label = "Edit merge proposal commit message"
    page_title = label
    field_names = ['commit_message']

    @action('Update', name='update')
    def update_action(self, action, data):
        """Update the commit message."""
        self.updateContextFromData(data)


class BranchMergeProposalDescriptionEditView(MergeProposalEditView):
    """The view to edit the description of merge proposals."""

    schema = IBranchMergeProposal
    label = "Edit merge proposal description"
    page_title = label
    field_names = ['description']

    @action('Update', name='update')
    def update_action(self, action, data):
        """Update the commit message."""
        self.updateContextFromData(data)


class BranchMergeProposalDeleteView(MergeProposalEditView):
    """The view to control the deletion of merge proposals."""
    schema = IBranchMergeProposal
    field_names = []
    page_title = label = 'Delete proposal to merge branch'

    def initialize(self):
        # Store the source branch for `next_url` to make sure that
        # it is available in the situation where the merge proposal
        # is deleted.
        self.source_branch = self.context.source_branch
        super(BranchMergeProposalDeleteView, self).initialize()

    @action('Delete proposal', name='delete')
    def delete_action(self, action, data):
        """Delete the merge proposal and go back to the source branch."""
        self.context.deleteProposal()
        # Override the next url to be the source branch.
        self.next_url = canonical_url(self.source_branch)


class BranchMergeProposalMergedView(LaunchpadEditFormView):
    """The view to mark a merge proposal as merged."""
    schema = IBranchMergeProposal
    page_title = label = "Edit branch merge proposal"
    field_names = ["merged_revno"]
    for_input = True

    @property
    def initial_values(self):
        # Default to the tip of the target branch, on the assumption that the
        # source branch has just been merged into it.
        if self.context.merged_revno is not None:
            revno = self.context.merged_revno
        else:
            revno = self.context.target_branch.revision_count
        return {'merged_revno': revno}

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @action('Mark as Merged', name='mark_merged')
    @notify
    def mark_merged_action(self, action, data):
        """Update the whiteboard and go back to the source branch."""
        revno = data['merged_revno']
        if self.context.queue_status == BranchMergeProposalStatus.MERGED:
            self.context.markAsMerged(merged_revno=revno)
            self.request.response.addNotification(
                'The proposal\'s merged revision has been updated.')
        else:
            self.context.markAsMerged(revno, merge_reporter=self.user)
            self.request.response.addNotification(
                'The proposal has now been marked as merged.')

    def validate(self, data):
        # Ensure a positive integer value.
        revno = data.get('merged_revno')
        if revno is not None:
            if revno <= 0:
                self.setFieldError(
                    'merged_revno',
                    'Revision numbers must be positive integers.')


class EnqueueForm(Interface):
    """A simple interface to populate the form to enqueue a proposal."""

    revision_number = Int(
        title=_("Queue Revision"), required=True,
        description=_("The revision number of the source branch "
                      "which is to be merged into the target branch."))

    commit_message = Summary(
        title=_("Commit Message"), required=True,
        description=_("The commit message to be used when merging "
                      "the source branch."))

    whiteboard = Whiteboard(
        title=_('Whiteboard'), required=False,
        description=_('Notes about the merge.'))


class BranchMergeProposalEnqueueView(MergeProposalEditView,
                                     UnmergedRevisionsMixin):
    """The view to submit a merge proposal for merging."""

    schema = EnqueueForm
    page_title = label = "Queue branch for merging"

    @property
    def initial_values(self):
        # If the user is a valid reviewer, then default the revision
        # number to be the tip.
        if self.context.target_branch.isPersonTrustedReviewer(self.user):
            revision_number = self.context.source_branch.revision_count
        else:
            revision_number = self._getRevisionNumberForRevisionId(
                self.context.reviewed_revision_id)

        return {'revision_number': revision_number}

    @property
    def adapters(self):
        """See `LaunchpadFormView`"""
        return {EnqueueForm: self.context}

    def setUpFields(self):
        super(BranchMergeProposalEnqueueView, self).setUpFields()
        # If the user is not a valid reviewer for the target branch,
        # then the revision number should be read only, so an
        # untrusted user cannot land changes that have not bee reviewed.
        if not self.context.target_branch.isPersonTrustedReviewer(self.user):
            self.form_fields['revision_number'].for_display = True

    @action('Enqueue', name='enqueue')
    @update_and_notify
    def enqueue_action(self, action, data):
        """Update the whiteboard and enqueue the merge proposal."""
        if self.context.target_branch.isPersonTrustedReviewer(self.user):
            revision_id = self._getRevisionId(data)
        else:
            revision_id = self.context.reviewed_revision_id
        self.context.enqueue(self.user, revision_id)

    def validate(self, data):
        """Make sure that the proposal has been reviewed.

        Or that the logged in user is able to review the branch as well.
        """
        if not self.context.isValidTransition(
            BranchMergeProposalStatus.QUEUED, self.user):
            self.addError(
                "The merge proposal is cannot be queued as it has not "
                "been reviewed.")

        self._validateRevisionNumber(data, 'enqueued')


class BranchMergeProposalDequeueView(LaunchpadEditFormView):
    """The view to remove a merge proposal from the merge queue."""

    schema = IBranchMergeProposal
    field_names = ["whiteboard"]
    page_title = label = "Dequeue branch"

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @action('Dequeue', name='dequeue')
    @update_and_notify
    def dequeue_action(self, action, data):
        """Update the whiteboard and remove the proposal from the queue."""
        self.context.dequeue()

    def validate(self, data):
        """Make sure the proposal is queued before removing."""
        if self.context.queue_status != BranchMergeProposalStatus.QUEUED:
            self.addError("The merge proposal is not queued.")


class BranchMergeProposalInlineDequeueView(LaunchpadEditFormView):
    """The view to provide a 'dequeue' button to the queue view."""

    schema = IBranchMergeProposal
    field_names = []

    @property
    def next_url(self):
        return canonical_url(self.context.target_branch) + '/+merge-queue'

    cancel_url = next_url

    @action('Dequeue', name='dequeue')
    @notify
    def dequeue_action(self, action, data):
        """Remove the proposal from the queue if queued."""
        if self.context.queue_status == BranchMergeProposalStatus.QUEUED:
            self.context.dequeue()

    @property
    def prefix(self):
        return "field%s" % self.context.id

    @property
    def action_url(self):
        return "%s/+dequeue-inline" % canonical_url(self.context)


class BranchMergeProposalJumpQueueView(LaunchpadEditFormView):
    """The view to provide a move the proposal to the front of the queue."""

    schema = IBranchMergeProposal
    field_names = []

    @property
    def next_url(self):
        return canonical_url(self.context.target_branch) + '/+merge-queue'

    @action('Move to front', name='move')
    @notify
    def move_action(self, action, data):
        """Move the proposal to the front of the queue (if queued)."""
        if (self.context.queue_status == BranchMergeProposalStatus.QUEUED and
            check_permission('launchpad.Edit', self.context.target_branch)):
            self.context.moveToFrontOfQueue()

    @property
    def prefix(self):
        return "field%s" % self.context.id

    @property
    def action_url(self):
        return "%s/+jump-queue" % canonical_url(self.context)


class BranchMergeProposalSubscribersView(LaunchpadView):
    """Used to show the pagelet subscribers on the main proposal page."""

    def initialize(self):
        """See `LaunchpadView`."""
        # Get the subscribers and dump them into two sets.
        self._full_subscribers = set()
        self._status_subscribers = set()
        # Add subscribers from the source and target branches.
        self._add_subscribers_for_branch(self.context.source_branch)
        self._add_subscribers_for_branch(self.context.target_branch)
        # Remove all the people from the comment_subscribers from the
        # status_and_vote_subscribers as they recipients will get the email
        # only once, and for the most detailed subscription from the source
        # and target branches.
        self._status_subscribers = (
            self._status_subscribers - self._full_subscribers)

    def _add_subscribers_for_branch(self, branch):
        """Add the subscribers to the subscription sets for the branch."""
        for subscription in branch.subscriptions:
            level = subscription.review_level
            if level == CodeReviewNotificationLevel.FULL:
                self._full_subscribers.add(subscription.person)
            elif level == CodeReviewNotificationLevel.STATUS:
                self._status_subscribers.add(subscription.person)
            else:
                # We don't do anything right now with people who say they
                # don't want to see anything.
                pass

    @cachedproperty
    def full_subscribers(self):
        """A list of full subscribers ordered by displayname."""
        return sorted(
            self._full_subscribers, key=operator.attrgetter('displayname'))

    @cachedproperty
    def status_subscribers(self):
        """A list of full subscribers ordered by displayname."""
        return sorted(
            self._status_subscribers, key=operator.attrgetter('displayname'))

    @property
    def has_subscribers(self):
        """True if there are subscribers to the branch."""
        return len(self.full_subscribers) + len(self.status_subscribers)


class BranchMergeProposalChangeStatusView(MergeProposalEditView,
                                          BranchMergeProposalStatusMixin):

    page_title = label = "Change merge proposal status"
    schema = IBranchMergeProposal
    field_names = []

    def setUpFields(self):
        MergeProposalEditView.setUpFields(self)
        # Add the custom restricted queue status widget.
        status_field = self.schema['queue_status']

        status_choice = Choice(
                __name__='queue_status', title=status_field.title,
                required=True, vocabulary=self._createStatusVocabulary())
        status_field = form.Fields(
            status_choice, render_context=self.render_context)
        self.form_fields = status_field + self.form_fields

    @action('Change Status', name='update')
    @notify
    def update_action(self, action, data):
        """Update the status."""

        curr_status = self.context.queue_status
        # Assume for now that the queue_status in the data is a valid
        # transition from where we are.
        rev_id = self.request.form['revno']
        new_status = data['queue_status']
        # Don't do anything if the user hasn't changed the status.
        if new_status == curr_status:
            return

        assert new_status != BranchMergeProposalStatus.SUPERSEDED, (
            'Superseded is done via an action, not by setting status.')
        self.context.setStatus(new_status, self.user, rev_id)


class IAddVote(Interface):
    """Interface for use as a schema for CodeReviewComment forms."""

    vote = copy_field(ICodeReviewComment['vote'], required=True)

    review_type = copy_field(
        ICodeReviewVoteReference['review_type'],
        description=u'Lowercase keywords describing the type of review you '
                     'are performing.')

    comment = Text(title=_('Comment'), required=False)


class BranchMergeProposalAddVoteView(LaunchpadFormView):
    """View for adding a CodeReviewComment."""

    schema = IAddVote
    field_names = ['vote', 'review_type', 'comment']

    custom_widget('comment', TextAreaWidget, cssClass='comment-text')

    @cachedproperty
    def initial_values(self):
        """The initial values are used to populate the form fields."""
        # Look to see if there is a vote reference already for the user.
        if self.users_vote_ref is None:
            # Look at the request to see if there is something there.
            review_type = self.request.form.get('review_type', '')
        else:
            review_type = self.users_vote_ref.review_type
        # We'll be positive here and default the vote to approve.
        return {'vote': CodeReviewVote.APPROVE,
                'review_type': review_type}

    def initialize(self):
        """Get the users existing vote reference."""
        self.users_vote_ref = self.context.getUsersVoteReference(self.user)
        # If the user is not in the review team, nor in any team that has been
        # requested to review and doesn't already have a vote reference, then
        # error out as the user must have URL hacked to get here.

        # XXX: Tim Penhey, 2008-10-02, bug=277000
        # Move valid_voter db class to expose for API.

        if self.user is None:
            # Anonymous users are not valid voters.
            raise AssertionError('Invalid voter')
        LaunchpadFormView.initialize(self)

    def setUpFields(self):
        LaunchpadFormView.setUpFields(self)
        self.reviewer = self.user.name
        # claim_review is set in situations where a user is reviewing on
        # behalf of a team.
        claim_review = self.request.form.get('claim')
        if claim_review and self.users_vote_ref is None:
            team = getUtility(IPersonSet).getByName(claim_review)
            if team is not None and self.user.inTeam(team):
                # If the review type is None, then don't show the field.
                self.reviewer = team.name
                if self.initial_values['review_type'] == '':
                    self.form_fields = self.form_fields.omit('review_type')
                else:
                    # Disable the review_type field
                    self.form_fields['review_type'].for_display = True

    @property
    def label(self):
        """The pagetitle and heading."""
        return "Review merge proposal for %s" % (
            self.context.source_branch.bzr_identity)
    page_title = label

    @action('Save Review', name='vote')
    def vote_action(self, action, data):
        """Create the comment."""
        # Get the review type from the data dict.  If the setUpFields set the
        # review_type field as for_display then 'review_type' will not be in
        # the data dict.  If this is the case, get the review_type from the
        # hidden field that we so cunningly added to the form.
        review_type = data.get(
            'review_type',
            self.request.form.get('review_type'))
        # Translate the request parameter back into what our object model
        # needs.
        if review_type == '':
            review_type = None
        # Get the reviewer from the hidden input.
        reviewer_name = self.request.form.get('reviewer')
        reviewer = getUtility(IPersonSet).getByName(reviewer_name)
        if (reviewer.is_team and self.user.inTeam(reviewer) and
            self.users_vote_ref is None):
            vote_ref = self.context.getUsersVoteReference(
                reviewer, review_type)
            if vote_ref is not None:
                # Claim this vote reference, i.e. say that the individual
                # self. user is doing this review ond behalf of the 'reviewer'
                # team.
                vote_ref.claimReview(self.user)

        self.context.createComment(
            self.user, subject=None, content=data['comment'],
            vote=data['vote'], review_type=review_type)

    @property
    def next_url(self):
        """Always take the user back to the merge proposal itself."""
        return canonical_url(self.context)

    cancel_url = next_url


class FormatPreviewDiffView(LaunchpadView, DiffRenderingMixin):
    """A simple view to render a diff formatted nicely."""

    @property
    def preview_diff(self):
        return self.context


class PreviewDiffHTMLRepresentation:
    adapts(IPreviewDiff, IWebServiceClientRequest)
    implements(Interface)

    def __init__(self, diff, request):
        self.diff = diff
        self.request = request

    def __call__(self):
        """Render `BugBranch` as XHTML using the webservice."""
        diff_view = getMultiAdapter(
            (self.diff, self.request), name="+diff")
        return diff_view()
