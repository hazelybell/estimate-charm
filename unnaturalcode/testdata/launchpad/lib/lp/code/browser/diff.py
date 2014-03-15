# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Display classes relating to diff objects of one sort or another."""

__metaclass__ = type
__all__ = [
    'PreviewDiffFormatterAPI',
    ]


from lp import _
from lp.app.browser.tales import ObjectFormatterAPI
from lp.code.interfaces.diff import IPreviewDiff
from lp.services.browser_helpers import get_plural_text
from lp.services.librarian.browser import FileNavigationMixin
from lp.services.webapp import Navigation
from lp.services.webapp.publisher import canonical_url


class PreviewDiffNavigation(Navigation, FileNavigationMixin):

    usedfor = IPreviewDiff


class DiffFormatterAPI(ObjectFormatterAPI):

    def _get_url(self, librarian_alias):
        return librarian_alias.getURL()

    def url(self, view_name=None, rootsite=None):
        """Use the url of the librarian file containing the diff.
        """
        librarian_alias = self._context.diff_text
        if librarian_alias is None:
            return None
        return self._get_url(librarian_alias)

    def link(self, view_name):
        """The link to the diff should show the line count.

        Stale diffs will have a stale-diff css class.
        Diffs with conflicts will have a conflict-diff css class.
        Diffs with neither will have clean-diff css class.

        The title of the diff will show the number of lines added or removed
        if available.

        :param view_name: If not None, the link will point to the page with
            that name on this object.
        """
        diff = self._context
        conflict_text = ''
        if diff.has_conflicts:
            conflict_text = _(' (has conflicts)')

        count_text = ''
        added = diff.added_lines_count
        removed = diff.removed_lines_count
        if (added is not None and removed is not None):
            count_text = ' (+%d/-%d)' % (added, removed)

        file_text = ''
        diffstat = diff.diffstat
        if diffstat is not None:
            file_count = len(diffstat)
            file_text = get_plural_text(
                file_count, _(' %d file modified'), _(' %d files modified'))
            file_text = file_text % file_count

        args = {
            'line_count': _('%s lines') % diff.diff_lines_count,
            'file_text': file_text,
            'conflict_text': conflict_text,
            'count_text': count_text,
            'url': self.url(view_name),
            }
        # Under normal circumstances, there will be an associated file,
        # however if the diff is empty, then there is no alias to link to.
        if args['url'] is None:
            return (
                '<span class="empty-diff">'
                '%(line_count)s</span>' % args)
        else:
            return (
                '<a href="%(url)s" class="diff-link">'
                '%(line_count)s%(count_text)s%(file_text)s%(conflict_text)s'
                '</a>' % args)


class PreviewDiffFormatterAPI(DiffFormatterAPI):
    """Formatter for preview diffs."""

    def _get_url(self, library_):
        return canonical_url(self._context) + '/+files/preview.diff'
