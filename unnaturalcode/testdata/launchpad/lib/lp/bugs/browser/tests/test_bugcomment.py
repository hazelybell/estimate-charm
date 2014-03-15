# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the bugcomment module."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from itertools import count

from pytz import utc
from soupmatchers import (
    HTMLContains,
    Tag,
    )
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.browser.bugcomment import (
    BugComment,
    group_comments_with_activity,
    )
from lp.bugs.interfaces.bugmessage import IBugComment
from lp.coop.answersbugs.visibility import (
    TestHideMessageControlMixin,
    TestMessageVisibilityMixin,
    )
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    BrowserTestCase,
    celebrity_logged_in,
    login_person,
    TestCase,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import find_tag_by_id


class BugActivityStub:

    def __init__(self, datechanged, owner=None):
        self.datechanged = datechanged
        if owner is None:
            owner = PersonStub()
        self.person = owner

    def __repr__(self):
        return "BugActivityStub(%r, %r)" % (
            self.datechanged.strftime('%Y-%m-%d--%H%M'), self.person)


class BugCommentStub:

    def __init__(self, datecreated, index, owner=None):
        self.datecreated = datecreated
        if owner is None:
            owner = PersonStub()
        self.owner = owner
        self.activity = []
        self.index = index

    def __repr__(self):
        return "BugCommentStub(%r, %d, %r)" % (
            self.datecreated.strftime('%Y-%m-%d--%H%M'),
            self.index, self.owner)


class PersonStub:

    ids = count(1)

    def __init__(self):
        self.id = next(self.ids)

    def __repr__(self):
        return "PersonStub#%d" % self.id


class TestGroupCommentsWithActivities(TestCase):
    """Tests for `group_comments_with_activities`."""

    def setUp(self):
        super(TestGroupCommentsWithActivities, self).setUp()
        self.now = datetime.now(utc)
        self.time_index = (
            (self.now + timedelta(minutes=counter), counter)
            for counter in count(1))

    def group(self, comments, activities):
        return list(
            group_comments_with_activity(
                comments=comments, activities=activities))

    def test_empty(self):
        # Given no comments or activities the result is also empty.
        self.assertEqual(
            [], self.group(comments=[], activities=[]))

    def test_activity_empty_no_common_actor(self):
        # When no activities are passed in, and the comments passed in don't
        # have any common actors, no grouping is possible.
        comments = [
            BugCommentStub(*next(self.time_index))
            for number in xrange(5)]
        self.assertEqual(
            comments, self.group(comments=comments, activities=[]))

    def test_comments_empty_no_common_actor(self):
        # When no comments are passed in, and the activities passed in don't
        # have any common actors, no grouping is possible.
        activities = [
            BugActivityStub(next(self.time_index)[0])
            for number in xrange(5)]
        self.assertEqual(
            [[activity] for activity in activities], self.group(
                comments=[], activities=activities))

    def test_no_common_actor(self):
        # When each activities and comment given has a different actor then no
        # grouping is possible.
        activity1 = BugActivityStub(next(self.time_index)[0])
        comment1 = BugCommentStub(*next(self.time_index))
        activity2 = BugActivityStub(next(self.time_index)[0])
        comment2 = BugCommentStub(*next(self.time_index))

        activities = set([activity1, activity2])
        comments = list([comment1, comment2])

        self.assertEqual(
            [[activity1], comment1, [activity2], comment2],
            self.group(comments=comments, activities=activities))

    def test_comment_then_activity_close_by_common_actor(self):
        # An activity shortly after a comment by the same person is grouped
        # into the comment.
        actor = PersonStub()
        comment = BugCommentStub(*next(self.time_index), owner=actor)
        activity = BugActivityStub(next(self.time_index)[0], owner=actor)
        grouped = self.group(comments=[comment], activities=[activity])
        self.assertEqual([comment], grouped)
        self.assertEqual([activity], comment.activity)

    def test_activity_then_comment_close_by_common_actor(self):
        # An activity shortly before a comment by the same person is grouped
        # into the comment.
        actor = PersonStub()
        activity = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment = BugCommentStub(*next(self.time_index), owner=actor)
        grouped = self.group(comments=[comment], activities=[activity])
        self.assertEqual([comment], grouped)
        self.assertEqual([activity], comment.activity)

    def test_interleaved_activity_with_comment_by_common_actor(self):
        # Activities shortly before and after a comment are grouped into the
        # comment's activity.
        actor = PersonStub()
        activity1 = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment = BugCommentStub(*next(self.time_index), owner=actor)
        activity2 = BugActivityStub(next(self.time_index)[0], owner=actor)
        grouped = self.group(
            comments=[comment], activities=[activity1, activity2])
        self.assertEqual([comment], grouped)
        self.assertEqual([activity1, activity2], comment.activity)

    def test_common_actor_over_a_prolonged_time(self):
        # There is a timeframe for grouping events, 5 minutes by default.
        # Anything outside of that window is considered separate.
        actor = PersonStub()
        activities = [
            BugActivityStub(next(self.time_index)[0], owner=actor)
            for count in xrange(8)]
        grouped = self.group(comments=[], activities=activities)
        self.assertEqual(2, len(grouped))
        self.assertEqual(activities[:5], grouped[0])
        self.assertEqual(activities[5:], grouped[1])

    def test_two_comments_by_common_actor(self):
        # Only one comment will ever appear in a group.
        actor = PersonStub()
        comment1 = BugCommentStub(*next(self.time_index), owner=actor)
        comment2 = BugCommentStub(*next(self.time_index), owner=actor)
        grouped = self.group(comments=[comment1, comment2], activities=[])
        self.assertEqual([comment1, comment2], grouped)

    def test_two_comments_with_activity_by_common_actor(self):
        # Activity gets associated with earlier comment when all other factors
        # are unchanging.
        actor = PersonStub()
        activity1 = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment1 = BugCommentStub(*next(self.time_index), owner=actor)
        activity2 = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment2 = BugCommentStub(*next(self.time_index), owner=actor)
        activity3 = BugActivityStub(next(self.time_index)[0], owner=actor)
        grouped = self.group(
            comments=[comment1, comment2],
            activities=[activity1, activity2, activity3])
        self.assertEqual([comment1, comment2], grouped)
        self.assertEqual([activity1, activity2], comment1.activity)
        self.assertEqual([activity3], comment2.activity)


class TestBugCommentVisibility(
        BrowserTestCase, TestMessageVisibilityMixin):

    layer = DatabaseFunctionalLayer

    def makeHiddenMessage(self):
        """Required by the mixin."""
        with celebrity_logged_in('admin'):
            bug = self.factory.makeBug()
            comment = self.factory.makeBugComment(
                    bug=bug, body=self.comment_text)
            comment.visible = False
        return bug

    def getView(self, context, user=None, no_login=False):
        """Required by the mixin."""
        view = self.getViewBrowser(
            context=context.default_bugtask,
            user=user,
            no_login=no_login)
        return view


class TestBugHideCommentControls(
        BrowserTestCase, TestHideMessageControlMixin):

    layer = DatabaseFunctionalLayer

    def getContext(self, comment_owner=None):
        """Required by the mixin."""
        bug = self.factory.makeBug()
        with celebrity_logged_in('admin'):
            self.factory.makeBugComment(bug=bug, owner=comment_owner)
        return bug

    def getView(self, context, user=None, no_login=False):
        """Required by the mixin."""
        task = removeSecurityProxy(context).default_bugtask
        return self.getViewBrowser(
            context=task, user=user, no_login=no_login)

    def _test_hide_link_visible(self, context, user):
        view = self.getView(context=context, user=user)
        hide_link = find_tag_by_id(view.contents, self.control_text)
        self.assertIsNot(None, hide_link)

    def test_comment_owner_sees_hide_control(self):
        # The comment owner sees the hide control.
        owner = self.factory.makePerson()
        context = self.getContext(comment_owner=owner)
        self._test_hide_link_visible(context, owner)

    def test_userdata_grant_sees_hide_control(self):
        # The pillar owner sees the hide control.
        person = self.factory.makePerson()
        context = self.getContext()
        pillar = context.default_bugtask.product
        policy = getUtility(IAccessPolicySource).find(
            [(pillar, InformationType.USERDATA)]).one()
        self.factory.makeAccessPolicyGrant(
            policy=policy, grantor=pillar.owner, grantee=person)
        self._test_hide_link_visible(context, person)


class TestBugCommentMicroformats(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_bug_comment_metadata(self):
        owner = self.factory.makePerson()
        login_person(owner)
        bug_comment = self.factory.makeBugComment()
        browser = self.getViewBrowser(bug_comment)
        iso_date = bug_comment.datecreated.isoformat()
        self.assertThat(
            browser.contents,
            HTMLContains(Tag(
                'comment time tag',
                'time',
                attrs=dict(
                    itemprop='commentTime',
                    title=True,
                    datetime=iso_date))))


class TestBugCommentImplementsInterface(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_bug_comment_implements_interface(self):
        """Ensure BugComment implements IBugComment"""
        bug_message = self.factory.makeBugComment()
        bugtask = bug_message.bugs[0].bugtasks[0]
        bug_comment = BugComment(1, bug_message, bugtask)
        verifyObject(IBugComment, bug_comment)

    def test_download_url(self):
        """download_url is provided and works as expected."""
        bug_comment = make_bug_comment(self.factory)
        url = canonical_url(bug_comment, view_name='+download')
        self.assertEqual(url, bug_comment.download_url)

    def test_bug_comment_canonical_url(self):
        """The bug comment url should use the default bugtastk."""
        bug_message = self.factory.makeBugComment()
        bugtask = bug_message.bugs[0].default_bugtask
        product = removeSecurityProxy(bugtask).target
        url = 'http://bugs.launchpad.dev/%s/+bug/%s/comments/%s' % (
           product.name, bugtask.bug.id, 1)
        self.assertEqual(url, canonical_url(bug_message))


def make_bug_comment(factory, *args, **kwargs):
    bug_message = factory.makeBugComment(*args, **kwargs)
    bugtask = bug_message.bugs[0].bugtasks[0]
    return BugComment(1, bug_message, bugtask)


class TestBugCommentInBrowser(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_excessive_comments_redirect_to_download(self):
        """View for excessive comments redirects to download page."""
        comment = make_bug_comment(self.factory, body='x ' * 5001)
        view_url = canonical_url(comment)
        download_url = canonical_url(comment, view_name='+download')
        browser = self.getUserBrowser(view_url)
        self.assertNotEqual(view_url, browser.url)
        self.assertEqual(download_url, browser.url)
        self.assertEqual('x ' * 5001, browser.contents)
