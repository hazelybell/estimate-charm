# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for handling mailing lists."""

__metaclass__ = type
__all__ = [
    'HeldMessageView',
    'enabled_with_active_mailing_list',
    ]


from textwrap import TextWrapper
from urllib import quote

from zope.component import getUtility

from lp.app.browser.tales import PersonFormatterAPI
from lp.registry.interfaces.mailinglist import (
    IHeldMessageDetails,
    IMailingListSet,
    )
from lp.registry.interfaces.person import ITeam
from lp.services.webapp import LaunchpadView
from lp.services.webapp.escaping import html_escape


class HeldMessageView(LaunchpadView):
    """A little helper view for held messages."""

    def __init__(self, context, request):
        super(HeldMessageView, self).__init__(context, request)
        self.context = context
        self.request = request
        # The context object is an IMessageApproval, but we need some extra
        # details in order to present the u/i.  We need to adapt the
        # IMessageApproval into an IHeldMessageDetails in order to get most of
        # that extra detailed information.
        self.details = IHeldMessageDetails(self.context)
        # Some of the attributes are clear pass-throughs.
        self.message_id = self.details.message_id
        self.subject = self.details.subject
        self.date = self.details.date
        self.widget_name = 'field.' + quote(self.message_id)
        self.author = PersonFormatterAPI(self.details.author).link(None)

    def initialize(self):
        """See `LaunchpadView`."""
        # Finally, the body text summary and details must be calculated from
        # the plain text body of the details object.
        #
        # Try to find a reasonable way to split the text of the message for
        # presentation as both a summary and a revealed detail.  This is
        # fraught with potential ugliness, so let's just do an 80% solution
        # that's safe and easy.
        text_lines = self._remove_leading_blank_lines()
        details = self._split_body(text_lines)
        # Now, ideally we'd like to wrap the details in <pre> tags so as to
        # preserve things like newlines in the original message body, but this
        # doesn't work very well with the JavaScript folding ellipsis control.
        # The next best, and easiest thing, is simply to replace all empty
        # blank lines in the details text with a <p> tag to give some
        # separation in the paragraphs.  No more than 20 lines in total
        # though, and here we don't worry about format="flowed".
        #
        # Again, 80% is good enough.
        paragraphs = []
        current_paragraph = []
        for lineno, line in enumerate(details.splitlines()):
            if lineno > 20:
                break
            if len(line.strip()) == 0:
                self._append_paragraph(paragraphs, current_paragraph)
                current_paragraph = []
            else:
                current_paragraph.append(line)
        self._append_paragraph(paragraphs, current_paragraph)
        self.body_details = u''.join(paragraphs)

    def _append_paragraph(self, paragraphs, current_paragraph):
        if len(current_paragraph) == 0:
            # There is nothing to append. The message has multiple
            # blank lines.
            return
        paragraphs.append(u'\n<p>\n')
        paragraphs.append(u'\n'.join(current_paragraph))
        paragraphs.append(u'\n</p>\n')

    def _remove_leading_blank_lines(self):
        """Strip off any leading blank lines.

        :return: The list of body text lines after stripping.
        """
        # Escape the text so that there's no chance of cross-site scripting,
        # then split into lines.
        text_lines = html_escape(self.details.body).splitlines()
        # Strip off any whitespace only lines from the start of the message.
        text_lines.reverse()
        while len(text_lines) > 0:
            first_line = text_lines.pop()
            if len(first_line.strip()) > 0:
                text_lines.append(first_line)
                break
        text_lines.reverse()
        return text_lines

    def _split_body(self, text_lines):
        """Split the body into summary and details.

        This will assign to self.body_summary the summary text, but it will
        return the details text for further santization.

        :return: the raw details text.
        """
        # If there are no non-blank lines, then we're done.
        if len(text_lines) == 0:
            self.body_summary = u''
            return u''
        # If the first line is of a completely arbitrarily chosen reasonable
        # length, then we'll just use that as the summary.
        elif len(text_lines[0]) < 60:
            self.body_summary = text_lines[0]
            return u'\n'.join(text_lines[1:])
        # It could be the case that the text is actually flowed using RFC
        # 3676 format="flowed" parameters.  In that case, just split the line
        # at the first whitespace after, again, our arbitrarily chosen limit.
        else:
            first_line = text_lines.pop(0)
            wrapper = TextWrapper(width=60)
            filled_lines = wrapper.fill(first_line).splitlines()
            self.body_summary = filled_lines[0]
            text_lines.insert(0, u''.join(filled_lines[1:]))
            return u'\n'.join(text_lines)


class enabled_with_active_mailing_list:
    """Disable the output link if the team's mailing list is not active."""

    def __init__(self, function):
        self._function = function

    def __get__(self, obj, type=None):
        """Called by the decorator machinery to return a decorated function.
        """

        def enable_if_active(*args, **kws):
            link = self._function(obj, *args, **kws)
            if not ITeam.providedBy(obj.context) or not obj.context.is_team:
                link.enabled = False
            mailing_list = getUtility(IMailingListSet).get(obj.context.name)
            if mailing_list is None or not mailing_list.is_usable:
                link.enabled = False
            return link
        return enable_if_active
