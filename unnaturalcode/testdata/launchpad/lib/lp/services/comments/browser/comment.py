# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'download_body',
    'MAX_RENDERABLE',
    ]


from lp.app.browser.tales import download_link
from lp.services.utils import obfuscate_email
from lp.services.webapp.publisher import (
    DataDownloadView,
    LaunchpadView,
    UserAttributeCache,
    )


MAX_RENDERABLE = 10000


class CommentBodyDownloadView(DataDownloadView, UserAttributeCache):
    """Download the body text of a comment."""

    content_type = 'text/plain'

    @property
    def filename(self):
        return 'comment-%d.txt' % self.context.index

    def getBody(self):
        """The body of the HTTP response is the message body."""
        text = self.context.body_text
        if self.user is None:
            text = obfuscate_email(text)
        return text


class CommentView(LaunchpadView):
    """Base class for viewing IComment implementations."""

    def download_link(self):
        """Return an HTML link to download this comment's body."""
        url = self.context.download_url
        length = len(self.context.body_text)
        return download_link(url, "Download full text", length)


def download_body(comment, request):
    """Respond to a request with the full message body as a download."""
    return CommentBodyDownloadView(comment, request)()
