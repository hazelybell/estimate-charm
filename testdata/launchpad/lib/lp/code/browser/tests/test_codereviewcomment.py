# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for CodeReviewComments."""

__metaclass__ = type

from soupmatchers import (
    HTMLContains,
    Tag,
    )
from testtools.matchers import Not

from lp.code.browser.codereviewcomment import (
    CodeReviewDisplayComment,
    ICodeReviewDisplayComment,
    )
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import IPrimaryContext
from lp.testing import (
    BrowserTestCase,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestCodeReviewComments(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def testPrimaryContext(self):
        # Tests the adaptation of a code review comment into a primary
        # context.
        # We need a person to make a comment.
        with person_logged_in(self.factory.makePerson()):
            # The primary context of a code review comment is the same
            # as the primary context for the branch merge proposal that
            # the comment is for.
            comment = self.factory.makeCodeReviewComment()

        self.assertEqual(
            IPrimaryContext(comment).context,
            IPrimaryContext(comment.branch_merge_proposal).context)

    def test_display_comment_provides_icodereviewdisplaycomment(self):
        # The CodeReviewDisplayComment class provides IComment.
        with person_logged_in(self.factory.makePerson()):
            comment = self.factory.makeCodeReviewComment()

        display_comment = CodeReviewDisplayComment(comment)

        verifyObject(ICodeReviewDisplayComment, display_comment)


class TestCodeReviewCommentHtml(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_comment_page_has_meta_description(self):
        # The CodeReviewDisplayComment class provides IComment.
        with person_logged_in(self.factory.makePerson()):
            comment = self.factory.makeCodeReviewComment()

        display_comment = CodeReviewDisplayComment(comment)
        browser = self.getViewBrowser(display_comment)
        self.assertThat(
            browser.contents,
            HTMLContains(Tag(
                'meta description', 'meta',
                dict(
                    name='description',
                    content=comment.message_body))))

    def test_long_comments_not_truncated(self):
        """Long comments displayed by themselves are not truncated."""
        comment = self.factory.makeCodeReviewComment(body='x y' * 2000)
        browser = self.getViewBrowser(comment)
        body = Tag('Body text', 'p', text='x y' * 2000)
        self.assertThat(browser.contents, HTMLContains(body))

    def test_excessive_comments_redirect_to_download(self):
        """View for excessive comments redirects to download page."""
        comment = self.factory.makeCodeReviewComment(body='x ' * 5001)
        view_url = canonical_url(comment)
        download_url = canonical_url(comment, view_name='+download')
        browser = self.getUserBrowser(view_url)
        self.assertNotEqual(view_url, browser.url)
        self.assertEqual(download_url, browser.url)
        self.assertEqual('x ' * 5001, browser.contents)

    def test_short_comment_no_download_link(self):
        """Long comments displayed by themselves are not truncated."""
        comment = self.factory.makeCodeReviewComment(body='x ' * 5000)
        download_url = canonical_url(comment, view_name='+download')
        browser = self.getViewBrowser(comment)
        body = Tag(
            'Download', 'a', {'href': download_url},
            text='Download full text')
        self.assertThat(browser.contents, Not(HTMLContains(body)))

    def test_download_view(self):
        """The download view has the expected contents and header."""
        comment = self.factory.makeCodeReviewComment(body=u'\u1234')
        browser = self.getViewBrowser(comment, view_name='+download')
        contents = u'\u1234'.encode('utf-8')
        self.assertEqual(contents, browser.contents)
        self.assertEqual(
            'text/plain;charset=utf-8', browser.headers['Content-type'])
        self.assertEqual(
            '%d' % len(contents), browser.headers['Content-length'])
        disposition = 'attachment; filename="comment-%d.txt"' % comment.id
        self.assertEqual(disposition, browser.headers['Content-disposition'])
