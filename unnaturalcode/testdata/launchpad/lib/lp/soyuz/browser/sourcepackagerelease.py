# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser view for a sourcepackagerelease"""

__metaclass__ = type

__all__ = [
    'linkify_changelog',
    'SourcePackageReleaseView',
    ]

import re

from lp.app.browser.stringformatter import (
    FormattersAPI,
    linkify_bug_numbers,
    )
from lp.services.webapp import LaunchpadView
from lp.services.webapp.escaping import html_escape


def obfuscate_email(user, text):
    """Obfuscate email addresses if the user is not logged in."""
    if not text:
        # If there is nothing to obfuscate, the FormattersAPI
        # will blow up, so just return.
        return text
    formatter = FormattersAPI(text)
    if user:
        return text
    else:
        return formatter.obfuscate_email()


def linkify_email(text, preloaded_person_data):
    """Email addresses are linkified to point to the person's profile."""
    formatter = FormattersAPI(text)
    return formatter.linkify_email(preloaded_person_data)


def linkify_changelog(user, changelog, preloaded_person_data=None):
    """Linkify the changelog.

    This obfuscates email addresses to anonymous users, linkifies
    them for non-anonymous and links to the bug page for any bug
    numbers mentioned.
    """
    if changelog is None:
        return ''

    # Remove any email addresses if the user is not logged in.
    changelog = obfuscate_email(user, changelog)

    # CGI Escape the changelog here before further replacements
    # insert HTML. Email obfuscation does not insert HTML but can insert
    # characters that must be escaped.
    changelog = html_escape(changelog)

    # Any email addresses remaining in the changelog were not obfuscated,
    # so we linkify them here.
    changelog = linkify_email(changelog, preloaded_person_data)

    # Ensure any bug numbers are linkified to the bug page.
    changelog = linkify_bug_numbers(changelog)

    return changelog


class SourcePackageReleaseView(LaunchpadView):

    @property
    def changelog_entry(self):
        """Return a linkified changelog entry."""
        return linkify_changelog(self.user, self.context.changelog_entry)

    @property
    def change_summary(self):
        """Return a linkified change summary."""
        return linkify_changelog(self.user, self.context.change_summary)

    @property
    def highlighted_copyright(self):
        """Return the copyright with markup that highlights paths and URLs."""
        if not self.context.copyright:
            return ''
        # Match any string with 2 or more non-consecutive slashes in it.
        pattern = re.compile(r'([\S]+/[\S]+/[\S]+)')
        highlight = r'<span class="highlight">\1</span>'
        return pattern.sub(highlight, self.context.copyright)
