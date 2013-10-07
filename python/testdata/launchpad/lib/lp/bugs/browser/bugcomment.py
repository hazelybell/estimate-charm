# Copyright 2006-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug comment browser view classes."""

__metaclass__ = type
__all__ = [
    'BugComment',
    'BugCommentBoxExpandedReplyView',
    'BugCommentBoxView',
    'BugCommentBreadcrumb',
    'BugCommentView',
    'BugCommentXHTMLRepresentation',
    'build_comments_from_chunks',
    'group_comments_with_activity',
    ]

from datetime import timedelta
from itertools import (
    chain,
    groupby,
    )
from operator import itemgetter

from lazr.delegates import delegates
from lazr.restful.interfaces import IWebServiceClientRequest
from zope.component import (
    adapts,
    getMultiAdapter,
    getUtility,
    )
from zope.interface import (
    implements,
    Interface,
    )
from zope.security.proxy import removeSecurityProxy

from lp.bugs.interfaces.bugattachment import BugAttachmentType
from lp.bugs.interfaces.bugmessage import IBugComment
from lp.services.comments.browser.comment import download_body
from lp.services.comments.browser.messagecomment import MessageComment
from lp.services.config import config
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.messages.interfaces.message import IMessage
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.interfaces import ILaunchBag


COMMENT_ACTIVITY_GROUPING_WINDOW = timedelta(minutes=5)


def build_comments_from_chunks(
        bugtask, truncate=False, slice_info=None, show_spam_controls=False,
        user=None, hide_first=False):
    """Build BugComments from MessageChunks.

    :param truncate: Perform truncation of large messages.
    :param slice_info: If not None, an iterable of slices to retrieve.
    """
    chunks = bugtask.bug.getMessagesForView(slice_info=slice_info)
    # This would be better as part of indexed_messages eager loading.
    comments = {}
    for bugmessage, message, chunk in chunks:
        cache = get_property_cache(message)
        if getattr(cache, 'chunks', None) is None:
            cache.chunks = []
        cache.chunks.append(removeSecurityProxy(chunk))
        bug_comment = comments.get(message.id)
        if bug_comment is None:
            if bugmessage.index == 0 and hide_first:
                display = 'hide'
            elif truncate:
                display = 'truncate'
            else:
                display = 'full'
            bug_comment = BugComment(
                bugmessage.index, message, bugtask,
                show_spam_controls=show_spam_controls, user=user,
                display=display)
            comments[message.id] = bug_comment
            # This code path is currently only used from a BugTask view which
            # has already loaded all the bug watches. If we start lazy loading
            # those, or not needing them we will need to batch lookup watches
            # here.
            if bugmessage.bugwatchID is not None:
                bug_comment.bugwatch = bugmessage.bugwatch
                bug_comment.synchronized = (
                    bugmessage.remote_comment_id is not None)
    return comments


def group_comments_with_activity(comments, activities):
    """Group comments and activity together for human consumption.

    Generates a stream of comment instances (with the activity grouped within)
    or `list`s of grouped activities.

    :param comments: An iterable of `BugComment` instances, which should be
        sorted by index already.
    :param activities: An iterable of `BugActivity` instances.
    """
    window = COMMENT_ACTIVITY_GROUPING_WINDOW

    comment_kind = "comment"
    if comments:
        max_index = comments[-1].index + 1
    else:
        max_index = 0
    comments = (
        (comment.datecreated, comment.index,
            comment.owner, comment_kind, comment)
        for comment in comments)
    activity_kind = "activity"
    activity = (
        (activity.datechanged, max_index,
            activity.person, activity_kind, activity)
        for activity in activities)
    # when an action and a comment happen at the same time, the action comes
    # second, when two events are tied the comment index is used to
    # disambiguate.
    events = sorted(chain(comments, activity), key=itemgetter(0, 1, 2))

    def gen_event_windows(events):
        """Generate event windows.

        Yields `(window_index, kind, event)` tuples, where `window_index` is
        an integer, and is incremented each time the windowing conditions are
        triggered.

        :param events: An iterable of `(date, ignored, actor, kind, event)`
            tuples in order.
        """
        window_comment, window_actor = None, None
        window_index, window_end = 0, None
        for date, _, actor, kind, event in events:
            window_ended = (
                # A window may contain only one comment.
                (window_comment is not None and kind is comment_kind) or
                # All events must have happened within a given timeframe.
                (window_end is None or date >= window_end) or
                # All events within the window must belong to the same actor.
                (window_actor is None or actor != window_actor))
            if window_ended:
                window_comment, window_actor = None, actor
                window_index, window_end = window_index + 1, date + window
            if kind is comment_kind:
                window_comment = event
            yield window_index, kind, event

    event_windows = gen_event_windows(events)
    event_windows_grouper = groupby(event_windows, itemgetter(0))
    for window_index, window_group in event_windows_grouper:
        window_group = [
            (kind, event) for (index, kind, event) in window_group]
        for kind, event in window_group:
            if kind is comment_kind:
                window_comment = event
                window_comment.activity.extend(
                    event for (kind, event) in window_group
                    if kind is activity_kind)
                yield window_comment
                # There's only one comment per window.
                break
        else:
            yield [event for (kind, event) in window_group]


class BugComment(MessageComment):
    """Data structure that holds all data pertaining to a bug comment.

    It keeps track of which index it has in the bug comment list and
    also provides functionality to truncate the comment.

    Note that although this class is called BugComment it really takes
    as an argument a bugtask. The reason for this is to allow
    canonical_url()s of BugComments to take you to the correct
    (task-specific) location.
    """
    implements(IBugComment)

    delegates(IMessage, '_message')

    def __init__(
            self, index, message, bugtask, activity=None,
            show_spam_controls=False, user=None, display='full'):
        if display == 'truncate':
            comment_limit = config.malone.max_comment_size
        else:
            comment_limit = None
        super(BugComment, self).__init__(comment_limit)

        self.index = index
        self.bugtask = bugtask
        self.bugwatch = None

        self._message = message
        self.display_title = False

        self.patches = []

        if activity is None:
            activity = []

        self.activity = activity

        self.synchronized = False
        # We use a feature flag to control users deleting their own comments.
        user_owns_comment = user is not None and user == self.owner
        self.show_spam_controls = show_spam_controls or user_owns_comment
        self.hide_text = (display == 'hide')

    @cachedproperty
    def bugattachments(self):
        return [attachment for attachment in self._message.bugattachments if
         attachment.type != BugAttachmentType.PATCH]

    @property
    def show_for_admin(self):
        """Show hidden comments for Launchpad admins.

        This is used in templates to add a class to hidden
        comments to enable display for admins, so the admin
        can see the comment even after it is hidden. Since comments
        aren't published unless the user is registry or admin, this
        can just check if the comment is visible.
        """
        return not self.visible

    @cachedproperty
    def text_for_display(self):
        if self.hide_text:
            return ''
        else:
            return super(BugComment, self).text_for_display

    def isIdenticalTo(self, other):
        """Compare this BugComment to another and return True if they are
        identical.
        """
        if self.owner != other.owner:
            return False
        if self.text_for_display != other.text_for_display:
            return False
        if self.title != other.title:
            return False
        if (self.bugattachments or self.patches or other.bugattachments or
            other.patches):
            # We shouldn't collapse comments which have attachments;
            # there's really no possible identity in that case.
            return False
        return True

    def isEmpty(self):
        """Return True if text_for_display is empty."""

        return (len(self.text_for_display) == 0 and
            len(self.bugattachments) == 0 and len(self.patches) == 0)

    @property
    def add_comment_url(self):
        return canonical_url(self.bugtask, view_name='+addcomment')

    @property
    def download_url(self):
        return canonical_url(self, view_name='+download')

    @property
    def show_footer(self):
        """Return True if the footer should be shown for this comment."""
        return bool(
            len(self.activity) > 0 or
            self.bugwatch or
            self.show_spam_controls)


class BugCommentView(LaunchpadView):
    """View for a single bug comment."""

    def __init__(self, context, request):
        # We use the current bug task as the context in order to get the
        # menu and portlets working.
        bugtask = getUtility(ILaunchBag).bugtask
        LaunchpadView.__init__(self, bugtask, request)
        self.comment = context

    def __call__(self):
        """View redirects to +download if comment is too long to render."""
        if self.comment.too_long_to_render:
            return self.request.response.redirect(self.comment.download_url)
        return super(BugCommentView, self).__call__()

    def download(self):
        return download_body(self.comment, self.request)

    @property
    def show_spam_controls(self):
        return self.comment.show_spam_controls

    def page_title(self):
        return 'Comment %d for bug %d' % (
            self.comment.index, self.context.bug.id)

    @property
    def page_description(self):
        return self.comment.text_contents

    @property
    def privacy_notice_classes(self):
        if not self.context.bug.private:
            return 'hidden'
        else:
            return ''


class BugCommentBoxViewMixin:
    """A class which provides proxied Librarian URLs for bug attachments."""

    @property
    def show_spam_controls(self):
        if hasattr(self.context, 'show_spam_controls'):
            return self.context.show_spam_controls
        elif (hasattr(self, 'comment') and
            hasattr(self.comment, 'show_spam_controls')):
            return self.comment.show_spam_controls
        else:
            return False

    def proxiedUrlOfLibraryFileAlias(self, attachment):
        """Return the proxied URL for the Librarian file of the attachment."""
        return ProxiedLibraryFileAlias(
            attachment.libraryfile, attachment).http_url


class BugCommentBoxView(LaunchpadView, BugCommentBoxViewMixin):
    """Render a comment box with reply field collapsed."""

    expand_reply_box = False


class BugCommentBoxExpandedReplyView(LaunchpadView, BugCommentBoxViewMixin):
    """Render a comment box with reply field expanded."""

    expand_reply_box = True


class BugCommentXHTMLRepresentation:
    adapts(IBugComment, IWebServiceClientRequest)
    implements(Interface)

    def __init__(self, comment, request):
        self.comment = comment
        self.request = request

    def __call__(self):
        """Render `BugComment` as XHTML using the webservice."""
        comment_view = getMultiAdapter(
            (self.comment, self.request), name="+box")
        return comment_view()


class BugCommentBreadcrumb(Breadcrumb):
    """Breadcrumb for an `IBugComment`."""

    def __init__(self, context):
        super(BugCommentBreadcrumb, self).__init__(context)

    @property
    def text(self):
        return "Comment #%d" % self.context.index
