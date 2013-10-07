# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests related to ILaunchpadRoot."""

__metaclass__ = type


from BeautifulSoup import (
    BeautifulSoup,
    SoupStrainer,
    )
from fixtures import FakeLogger
from zope.component import getUtility
from zope.security.checker import selectChecker

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.memcache.interfaces import IMemcacheClient
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.testing import (
    anonymous_logged_in,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.publication import test_traverse
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class LaunchpadRootPermissionTest(TestCaseWithFactory):
    """Test for the ILaunchpadRoot permission"""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.root = getUtility(ILaunchpadRoot)
        self.admin = getUtility(IPersonSet).getByEmail(
            'foo.bar@canonical.com')
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def setUpRegistryExpert(self):
        """Create a registry expert and logs in as them."""
        login_person(self.admin)
        self.expert = self.factory.makePerson()
        getUtility(ILaunchpadCelebrities).registry_experts.addMember(
            self.expert, self.admin)
        login_person(self.expert)

    def test_anonymous_cannot_edit(self):
        self.failIf(check_permission('launchpad.Edit', self.root),
            "Anonymous user shouldn't have launchpad.Edit on ILaunchpadRoot")

    def test_regular_user_cannot_edit(self):
        login_person(self.factory.makePerson())
        self.failIf(check_permission('launchpad.Edit', self.root),
            "Regular users shouldn't have launchpad.Edit on ILaunchpadRoot")

    def test_registry_expert_can_edit(self):
        self.setUpRegistryExpert()
        self.failUnless(check_permission('launchpad.Edit', self.root),
            "Registry experts should have launchpad.Edit on ILaunchpadRoot")

    def test_admins_can_edit(self):
        login_person(self.admin)
        self.failUnless(check_permission('launchpad.Edit', self.root),
            "Admins should have launchpad.Edit on ILaunchpadRoot")

    def test_featured_projects_view_requires_edit(self):
        view = create_view(self.root, '+featuredprojects')
        checker = selectChecker(view)
        self.assertEquals('launchpad.Edit', checker.permission_id('__call__'))

    def test_featured_projects_manage_link_requires_edit(self):
        self.setUpRegistryExpert()
        view = create_initialized_view(
            self.root, 'index.html', principal=self.expert)
        # Stub out the getRecentBlogPosts which fetches a blog feed using
        # urlfetch.
        view.getRecentBlogPosts = lambda: []
        content = BeautifulSoup(view(), parseOnlyThese=SoupStrainer('a'))
        self.failUnless(
            content.find('a', href='+featuredprojects'),
            "Cannot find the +featuredprojects link on the first page")


class TestLaunchpadRootNavigation(TestCaseWithFactory):
    """Test for the LaunchpadRootNavigation."""

    layer = DatabaseFunctionalLayer

    def test_support(self):
        # The /support link redirects to answers.
        context, view, request = test_traverse(
            'http://launchpad.dev/support')
        view()
        self.assertEqual(301, request.response.getStatus())
        self.assertEqual(
            'http://answers.launchpad.dev/launchpad',
            request.response.getHeader('location'))

    def test_feedback(self):
        # The /feedback link redirects to the help site.
        context, view, request = test_traverse(
            'http://launchpad.dev/feedback')
        view()
        self.assertEqual(301, request.response.getStatus())
        self.assertEqual(
            'https://help.launchpad.net/Feedback',
            request.response.getHeader('location'))


class LaunchpadRootIndexViewTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(LaunchpadRootIndexViewTestCase, self).setUp()
        # Use a FakeLogger fixture to prevent Memcached warnings to be
        # printed to stdout while browsing pages.
        self.useFixture(FakeLogger())

    def test_has_logo_without_watermark(self):
        root = getUtility(ILaunchpadRoot)
        user = self.factory.makePerson()
        login_person(user)
        view = create_initialized_view(root, 'index.html', principal=user)
        # Replace the blog posts so the view does not make a network request.
        view.getRecentBlogPosts = lambda: []
        markup = BeautifulSoup(
            view(), parseOnlyThese=SoupStrainer(id='document'))
        self.assertIs(False, view.has_watermark)
        self.assertIs(None, markup.find(True, id='watermark'))
        logo = markup.find(True, id='launchpad-logo-and-name')
        self.assertIsNot(None, logo)
        self.assertEqual('/@@/launchpad-logo-and-name.png', logo['src'])

    @staticmethod
    def _make_blog_post(linkid, title, body, date):
        return {
            'title': title,
            'description': body,
            'link': "http://blog.invalid/%s" % (linkid,),
            'date': date,
            }

    def test_blog_posts(self):
        """Posts from the launchpad blog are shown when feature is enabled"""
        self.useFixture(FeatureFixture({'app.root_blog.enabled': True}))
        posts = [
            self._make_blog_post(1, "A post", "Post contents.", "2002"),
            self._make_blog_post(2, "Another post", "More contents.", "2003"),
            ]
        calls = []

        def _get_blog_posts():
            calls.append('called')
            return posts

        root = getUtility(ILaunchpadRoot)
        with anonymous_logged_in():
            view = create_initialized_view(root, 'index.html')
            view.getRecentBlogPosts = _get_blog_posts
            result = view()
        markup = BeautifulSoup(result,
            parseOnlyThese=SoupStrainer(id='homepage-blogposts'))
        self.assertEqual(['called'], calls)
        items = markup.findAll('li', 'news')
        # Notice about launchpad being opened is always added at the end
        self.assertEqual(3, len(items))
        a = items[-1].find("a")
        self.assertEqual("Launchpad now open source", a.string.strip())
        for post, item in zip(posts, items):
            a = item.find("a")
            self.assertEqual(post['link'], a["href"])
            self.assertEqual(post['title'], a.string)

    def test_blog_disabled(self):
        """Launchpad blog not queried for display without feature"""
        calls = []

        def _get_blog_posts():
            calls.append('called')
            return []

        root = getUtility(ILaunchpadRoot)
        user = self.factory.makePerson()
        login_person(user)
        view = create_initialized_view(root, 'index.html', principal=user)
        view.getRecentBlogPosts = _get_blog_posts
        markup = BeautifulSoup(
            view(), parseOnlyThese=SoupStrainer(id='homepage'))
        self.assertEqual([], calls)
        self.assertIs(None, markup.find(True, id='homepage-blogposts'))
        # Even logged in users should get the launchpad intro text in the left
        # column rather than blank space when the blog is not being displayed.
        self.assertTrue(view.show_whatslaunchpad)
        self.assertTrue(markup.find(True, 'homepage-whatslaunchpad'))

    def test_blog_posts_with_memcache(self):
        self.useFixture(FeatureFixture({'app.root_blog.enabled': True}))
        posts = [
            self._make_blog_post(1, "A post", "Post contents.", "2002"),
            self._make_blog_post(2, "Another post", "More contents.", "2003"),
            ]
        key = '%s:homepage-blog-posts' % config.instance_name
        getUtility(IMemcacheClient).set(key, posts)

        root = getUtility(ILaunchpadRoot)
        with anonymous_logged_in():
            view = create_initialized_view(root, 'index.html')
            result = view()
        markup = BeautifulSoup(result,
            parseOnlyThese=SoupStrainer(id='homepage-blogposts'))
        items = markup.findAll('li', 'news')
        self.assertEqual(3, len(items))
