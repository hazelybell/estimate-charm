# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'CodeReviewCommentAddView',
    'CodeReviewCommentContextMenu',
    'CodeReviewCommentPrimaryContext',
    'CodeReviewCommentView',
    'CodeReviewDisplayComment',
    ]

from lazr.delegates import delegates
from lazr.restful.interface import copy_field
from zope.formlib.widgets import (
    DropdownWidget,
    TextAreaWidget,
    )
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import Text

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.code.interfaces.codereviewcomment import ICodeReviewComment
from lp.code.interfaces.codereviewvote import ICodeReviewVoteReference
from lp.services.comments.browser.comment import download_body
from lp.services.comments.browser.messagecomment import MessageComment
from lp.services.comments.interfaces.conversation import IComment
from lp.services.config import config
from lp.services.librarian.interfaces import ILibraryFileAlias
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    LaunchpadView,
    Link,
    )
from lp.services.webapp.interfaces import IPrimaryContext


class ICodeReviewDisplayComment(IComment, ICodeReviewComment):
    """Marker interface for displaying code review comments."""


class CodeReviewDisplayComment(MessageComment):
    """A code review comment or activity or both.

    The CodeReviewComment itself does not implement the IComment interface as
    this is purely a display interface, and doesn't make sense to have display
    only code in the model itself.
    """

    implements(ICodeReviewDisplayComment)

    delegates(ICodeReviewComment, 'comment')

    def __init__(self, comment, from_superseded=False, limit_length=True):
        if limit_length:
            comment_limit = config.malone.max_comment_size
        else:
            comment_limit = None
        super(CodeReviewDisplayComment, self).__init__(comment_limit)
        self.comment = comment
        get_property_cache(self).has_body = bool(self.comment.message_body)
        self.has_footer = self.comment.vote is not None
        # The date attribute is used to sort the comments in the conversation.
        self.date = self.comment.message.datecreated
        self.from_superseded = from_superseded

    @property
    def index(self):
        return self.comment.id

    @property
    def extra_css_class(self):
        if self.from_superseded:
            return 'from-superseded'
        else:
            return ''

    @cachedproperty
    def body_text(self):
        """Get the body text for the message."""
        return self.comment.message_body

    @cachedproperty
    def all_attachments(self):
        return self.comment.getAttachments()

    @cachedproperty
    def display_attachments(self):
        # Attachments to show.
        return [DiffAttachment(alias) for alias in self.all_attachments[0]]

    @cachedproperty
    def other_attachments(self):
        # Attachments to not show.
        return self.all_attachments[1]

    @property
    def download_url(self):
        return canonical_url(self.comment, view_name='+download')


def get_message(display_comment):
    """Adapt an ICodeReviwComment to an IMessage."""
    return display_comment.comment.message


class CodeReviewCommentPrimaryContext:
    """The primary context is the comment is that of the source branch."""

    implements(IPrimaryContext)

    def __init__(self, comment):
        self.context = IPrimaryContext(
            comment.branch_merge_proposal).context


class CodeReviewCommentContextMenu(ContextMenu):
    """Context menu for branches."""

    usedfor = ICodeReviewComment
    links = ['reply']

    def reply(self):
        enabled = self.context.branch_merge_proposal.isMergable()
        return Link('+reply', 'Reply', icon='add', enabled=enabled)


class DiffAttachment:
    """An attachment that we are going to display."""

    implements(ILibraryFileAlias)

    delegates(ILibraryFileAlias, 'alias')

    def __init__(self, alias):
        self.alias = alias

    @cachedproperty
    def text(self):
        """Read the text out of the librarin."""
        self.alias.open()
        try:
            return self.alias.read(config.diff.max_read_size)
        finally:
            self.alias.close()

    @cachedproperty
    def diff_text(self):
        """Get the text and attempt to decode it."""
        try:
            diff = self.text.decode('utf-8')
        except UnicodeDecodeError:
            diff = self.text.decode('windows-1252', 'replace')
        # Strip off the trailing carriage returns.
        return diff.rstrip('\n')


class CodeReviewCommentView(LaunchpadView):
    """Standard view of a CodeReviewComment"""

    page_title = "Code review comment"

    @cachedproperty
    def comment(self):
        """The decorated code review comment."""
        return CodeReviewDisplayComment(self.context, limit_length=False)

    @property
    def page_description(self):
        return self.context.message_body

    def download(self):
        return download_body(
            CodeReviewDisplayComment(self.context), self.request)

    # Should the comment be shown in full?
    full_comment = True
    # Show comment expanders?
    show_expanders = False


class CodeReviewCommentIndexView(CodeReviewCommentView):

    def __call__(self):
        """View redirects to +download if comment is too long to render."""
        if self.comment.too_long_to_render:
            return self.request.response.redirect(self.comment.download_url)
        return super(CodeReviewCommentIndexView, self).__call__()


class IEditCodeReviewComment(Interface):
    """Interface for use as a schema for CodeReviewComment forms."""

    vote = copy_field(ICodeReviewComment['vote'], required=False)

    review_type = copy_field(
        ICodeReviewVoteReference['review_type'],
        description=u'Lowercase keywords describing the type of review you '
                     'are performing.')

    comment = Text(title=_('Comment'), required=False)


class CodeReviewCommentAddView(LaunchpadFormView):
    """View for adding a CodeReviewComment."""

    class MyDropWidget(DropdownWidget):
        "Override the default none-selected display name to -Select-."
        _messageNoValue = 'Comment only'

    schema = IEditCodeReviewComment

    custom_widget('comment', TextAreaWidget, cssClass='comment-text')
    custom_widget('vote', MyDropWidget)

    page_title = 'Reply to code review comment'

    @property
    def initial_values(self):
        """The initial values are used to populate the form fields.

        In this case, the default value of the comment should be the
        quoted comment being replied to.
        """
        if self.is_reply:
            comment = self.reply_to.as_quoted_email
        else:
            comment = ''
        return {'comment': comment}

    @property
    def is_reply(self):
        """True if this comment is a reply to another comment, else False."""
        return ICodeReviewComment.providedBy(self.context)

    @property
    def branch_merge_proposal(self):
        """The BranchMergeProposal being commented on."""
        if self.is_reply:
            return self.context.branch_merge_proposal
        else:
            return self.context

    @cachedproperty
    def reply_to(self):
        """The comment being replied to, or None."""
        if self.is_reply:
            return CodeReviewDisplayComment(self.context)
        else:
            return None

    @action('Save Comment', name='add')
    def add_action(self, action, data):
        """Create the comment..."""
        vote = data.get('vote')
        review_type = data.get('review_type')
        self.branch_merge_proposal.createComment(
            self.user, subject=None, content=data['comment'],
            parent=self.reply_to, vote=vote, review_type=review_type)

    @property
    def next_url(self):
        """Always take the user back to the merge proposal itself."""
        return canonical_url(self.branch_merge_proposal)

    cancel_url = next_url
