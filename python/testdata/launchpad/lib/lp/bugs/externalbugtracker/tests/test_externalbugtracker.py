# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the externalbugtracker package."""

__metaclass__ = type

from StringIO import StringIO
import urllib2

from zope.interface import implements

from lp.bugs.externalbugtracker.base import (
    BugTrackerConnectError,
    ExternalBugTracker,
    LP_USER_AGENT,
    )
from lp.bugs.externalbugtracker.debbugs import DebBugs
from lp.bugs.interfaces.externalbugtracker import (
    ISupportsBackLinking,
    ISupportsCommentImport,
    ISupportsCommentPushing,
    )
from lp.testing import (
    monkey_patch,
    TestCase,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessLayer


class BackLinkingExternalBugTracker(ExternalBugTracker):
    implements(ISupportsBackLinking)


class CommentImportingExternalBugTracker(ExternalBugTracker):
    implements(ISupportsCommentImport)


class CommentPushingExternalBugTracker(ExternalBugTracker):
    implements(ISupportsCommentPushing)


class TestCheckwatchesConfig(TestCase):

    base_url = "http://www.example.com/"

    def test_sync_comments_enabled(self):
        # If the global config checkwatches.sync_comments is True,
        # external bug trackers will set their sync_comments attribute
        # according to their support of comment syncing.
        self.pushConfig('checkwatches', sync_comments=True)
        # A plain tracker will never support syncing comments.
        tracker = ExternalBugTracker(self.base_url)
        self.assertFalse(tracker.sync_comments)
        # Trackers that support comment pushing, comment pulling or
        # back-linking will have sync_comments set to True.
        tracker = BackLinkingExternalBugTracker(self.base_url)
        self.assertTrue(tracker.sync_comments)
        tracker = CommentImportingExternalBugTracker(self.base_url)
        self.assertTrue(tracker.sync_comments)
        tracker = CommentPushingExternalBugTracker(self.base_url)
        self.assertTrue(tracker.sync_comments)

    def test_sync_comments_disabled(self):
        # If the global config checkwatches.sync_comments is False,
        # external bug trackers will always set their sync_comments
        # attribute to False.
        self.pushConfig('checkwatches', sync_comments=False)
        tracker = ExternalBugTracker(self.base_url)
        self.assertFalse(tracker.sync_comments)
        tracker = BackLinkingExternalBugTracker(self.base_url)
        self.assertFalse(tracker.sync_comments)
        tracker = CommentImportingExternalBugTracker(self.base_url)
        self.assertFalse(tracker.sync_comments)
        tracker = CommentPushingExternalBugTracker(self.base_url)
        self.assertFalse(tracker.sync_comments)

    def test_sync_debbugs_comments_enabled(self):
        # Debian Bugs syncing can also be switched on and off using a
        # separate config variable, sync_debbugs_comments. DebBugs
        # supports comment pushing and import.
        self.pushConfig(
            'checkwatches', sync_comments=True, sync_debbugs_comments=True)
        tracker = DebBugs(self.base_url)
        self.assertTrue(tracker.sync_comments)
        # When either sync_comments or sync_debbugs_comments is False
        # (or both), the Debian Bugs external bug tracker will claim
        # to not support any form of comment syncing.
        for state in ((True, False), (False, True), (False, False)):
            self.pushConfig(
                'checkwatches', sync_comments=state[0],
                sync_debbugs_comments=state[1])
            tracker = DebBugs(self.base_url)
            self.assertFalse(tracker.sync_comments)

    def _makeFakePostForm(self, base_url, page=None):
        """Create a fake `urllib2.urlopen` result."""
        content = "<bugzilla>%s</bugzilla>" % self.factory.getUniqueString()
        fake_form = StringIO(content)
        if page is None:
            page = self.factory.getUniqueString()
        fake_form.url = base_url + page
        return fake_form

    def _fakeExternalBugTracker(self, base_url, fake_form):
        """Create an `ExternalBugTracker` with a fake `_post` method."""
        bugtracker = ExternalBugTracker(base_url)
        bugtracker._post = FakeMethod(result=fake_form)
        return bugtracker

    def test_postPage_returns_response_page(self):
        # _postPage posts, then returns the page text it gets back from
        # the server.
        base_url = "http://example.com/"
        form = self.factory.getUniqueString()
        fake_form = self._makeFakePostForm(base_url, page=form)
        bugtracker = self._fakeExternalBugTracker(base_url, fake_form)
        self.assertEqual(fake_form.getvalue(), bugtracker._postPage(form, {}))

    def test_postPage_does_not_repost_on_redirect(self):
        # By default, if the POST redirects, _postPage leaves urllib2 to
        # handle it in the normal, RFC-compliant way.
        base_url = "http://example.com/"
        form = self.factory.getUniqueString()
        fake_form = self._makeFakePostForm(base_url)
        bugtracker = self._fakeExternalBugTracker(base_url, fake_form)

        bugtracker._postPage(form, {})

        self.assertEqual(1, bugtracker._post.call_count)
        args, kwargs = bugtracker._post.calls[0]
        self.assertEqual((base_url + form, ), args)

    def test_postPage_can_repost_on_redirect(self):
        # Some pages (that means you, BugZilla bug-search page!) can
        # redirect on POST, but without honouring the POST.  Standard
        # urllib2 behaviour is to redirect to a GET, but if the caller
        # says it's safe, _postPage can re-do the POST at the new URL.
        base_url = "http://example.com/"
        form = self.factory.getUniqueString()
        fake_form = self._makeFakePostForm(base_url)
        bugtracker = self._fakeExternalBugTracker(base_url, fake_form)

        bugtracker._postPage(form, form={}, repost_on_redirect=True)

        self.assertEqual(2, bugtracker._post.call_count)
        last_args, last_kwargs = bugtracker._post.calls[-1]
        self.assertEqual((fake_form.url, ), last_args)


class TestExternalBugTracker(TestCase):
    """Tests for various methods of the ExternalBugTracker."""

    layer = ZopelessLayer

    def test_post_raises_on_404(self):
        # When posting, a 404 is converted to a BugTrackerConnectError.
        base_url = "http://example.com/"
        bugtracker = ExternalBugTracker(base_url)
        def raise404(request, data, timeout=None):
            raise urllib2.HTTPError('url', 404, 'Not Found', None, None)
        with monkey_patch(urllib2, urlopen=raise404):
            self.assertRaises(
                BugTrackerConnectError,
                bugtracker._post, 'some-url', {'post-data': 'here'})

    def test_post_sends_host(self):
        # When posting, a Host header is sent.
        base_host = 'example.com'
        base_url = 'http://%s/' % base_host
        bugtracker = ExternalBugTracker(base_url)
        def assert_headers(request, data, timeout=None):
            self.assertContentEqual(
                [('User-agent', LP_USER_AGENT), ('Host', base_host)],
                request.header_items())
        with monkey_patch(urllib2, urlopen=assert_headers):
            bugtracker._post('some-url', {'post-data': 'here'})
