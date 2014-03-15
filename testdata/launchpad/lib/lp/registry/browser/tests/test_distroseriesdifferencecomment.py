# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `lp.registry.browser.distroseriesdifferencecomment`."""

__metaclass__ = type

from lxml import html
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class TestDistroSeriesDifferenceCommentFragment(TestCaseWithFactory):
    """`IDistroSeriesDifferenceComment` +latest-comment-fragment view."""

    layer = LaunchpadFunctionalLayer

    def test_render(self):
        comment_text = "_123456789" * 10
        comment = self.factory.makeDistroSeriesDifferenceComment(
            comment=comment_text)
        view = create_initialized_view(comment, '+latest-comment-fragment')
        root = html.fromstring(view())
        self.assertEqual("span", root.tag)
        self.assertEqual("%s..." % comment_text[:47], root.text.strip())
        self.assertEqual(
            "/~%s" % comment.comment_author.name,
            root.find("span").find("a").get("href"))

    def test_error_icon_does_not_appear_if_not_is_error(self):
        comment = self.factory.makeDistroSeriesDifferenceComment()
        view = create_initialized_view(comment, '+latest-comment-fragment')
        view.is_error = False
        root = html.fromstring(view())
        self.assertNotIn("error", root.find("span").get("class"))

    def test_error_icon_appears_if_is_error(self):
        comment = self.factory.makeDistroSeriesDifferenceComment()
        view = create_initialized_view(comment, '+latest-comment-fragment')
        view.is_error = True
        root = html.fromstring(view())
        self.assertIn("error", root.find("span").get("class"))

    def test_is_error_is_normally_False(self):
        comment = self.factory.makeDistroSeriesDifferenceComment(
            comment=self.factory.getUniqueString())
        view = create_initialized_view(comment, '+latest-comment-fragment')
        self.assertFalse(view.is_error)

    def test_is_error_is_True_if_comment_comes_from_janitor(self):
        comment = self.factory.makeDistroSeriesDifferenceComment(
            owner=getUtility(ILaunchpadCelebrities).janitor)
        view = create_initialized_view(comment, '+latest-comment-fragment')
        self.assertTrue(view.is_error)
