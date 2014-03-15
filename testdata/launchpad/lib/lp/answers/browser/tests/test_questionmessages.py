# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the various rules around question comment visibility."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.coop.answersbugs.visibility import (
    TestHideMessageControlMixin,
    TestMessageVisibilityMixin,
    )
from lp.testing import (
    BrowserTestCase,
    person_logged_in,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import find_tag_by_id


class TestQuestionMessageVisibility(
        BrowserTestCase, TestMessageVisibilityMixin):

    layer = DatabaseFunctionalLayer

    def makeHiddenMessage(self):
        """Required by the mixin."""
        administrator = getUtility(ILaunchpadCelebrities).admin.teamowner
        self.commenter = self.factory.makePerson()
        with person_logged_in(administrator):
            question = self.factory.makeQuestion()
            comment = question.addComment(self.commenter, self.comment_text)
            removeSecurityProxy(comment).message.visible = False
        return question

    def getView(self, context, user=None, no_login=False):
        """Required by the mixin."""
        view = self.getViewBrowser(
            context=context,
            user=user,
            no_login=no_login)
        return view

    def test_commenter_can_see_comments(self):
        # The author of the comment can see the hidden comment.
        context = self.makeHiddenMessage()
        view = self.getView(context=context, user=self.commenter)
        self.assertIn(self.html_comment_text, view.contents)


class TestHideQuestionMessageControls(
        BrowserTestCase, TestHideMessageControlMixin):

    layer = DatabaseFunctionalLayer

    control_text = 'mark-spam-0'

    def getContext(self, comment_owner=None):
        """Required by the mixin."""
        administrator = getUtility(ILaunchpadCelebrities).admin.teamowner
        user = comment_owner or administrator
        question = self.factory.makeQuestion()
        body = self.factory.getUniqueString()
        with person_logged_in(user):
            question.addComment(user, body)
        return question

    def getView(self, context, user=None, no_login=False):
        """Required by the mixin."""
        view = self.getViewBrowser(
            context=context,
            user=user,
            no_login=no_login)
        return view

    def test_comment_owner_sees_hide_control(self):
        # The comment owner sees the hide control.
        user = self.factory.makePerson()
        context = self.getContext(comment_owner=user)
        view = self.getView(context=context, user=user)
        hide_link = find_tag_by_id(view.contents, self.control_text)
        self.assertIsNot(None, hide_link)
