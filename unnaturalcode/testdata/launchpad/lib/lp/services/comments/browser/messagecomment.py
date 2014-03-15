# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = ['MessageComment']


from lp.services.comments.browser.comment import MAX_RENDERABLE
from lp.services.messages.interfaces.message import IMessage
from lp.services.propertycache import cachedproperty


class MessageComment:
    """Mixin to partially implement IComment in terms of IMessage."""

    extra_css_class = ''

    has_footer = False

    def __init__(self, comment_limit):
        self.comment_limit = comment_limit

    @property
    def display_attachments(self):
        return []

    @cachedproperty
    def comment_author(self):
        """The author of the comment."""
        return IMessage(self).owner

    @cachedproperty
    def has_body(self):
        """Is there body text?"""
        return bool(self.body_text)

    @cachedproperty
    def comment_date(self):
        """The date of the comment."""
        return IMessage(self).datecreated

    @property
    def body_text(self):
        return IMessage(self).text_contents

    @property
    def too_long(self):
        if self.comment_limit is None:
            return False
        return len(self.body_text) > self.comment_limit

    @property
    def too_long_to_render(self):
        return len(self.body_text) > MAX_RENDERABLE

    @cachedproperty
    def text_for_display(self):
        if not self.too_long:
            return self.body_text
        # Note here that we truncate at comment_limit, and not
        # comment_limit - 3; while it would be nice to account for
        # the ellipsis, this breaks down when the comment limit is
        # less than 3 (which can happen in a testcase) and it makes
        # counting the strings harder.
        return "%s..." % self.body_text[:self.comment_limit]
