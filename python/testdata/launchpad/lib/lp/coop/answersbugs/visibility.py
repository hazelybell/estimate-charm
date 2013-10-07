# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Provides mixins for visibility tests in messages."""

__metaclass__ = type

__all__ = [
    'TestHideMessageControlMixin',
    'TestMessageVisibilityMixin',
    ]


from lp.services.webapp.escaping import html_escape
from lp.testing.pages import find_tag_by_id


class TestMessageVisibilityMixin:

    comment_text = "You can't see me."
    html_comment_text = html_escape(comment_text).encode('utf-8')

    def makeHiddenMessage(self):
        """To be overwridden by subclasses.

        This method must create and return a message bearing object
        (e.g. bug or question) with a hidden message/comment.
        """
        raise NotImplementedError

    def getView(self, context, user=None, no_login=False):
        """To be overwridden by subclasses.

        This method returns a view object rendered on the context
        obtained from makeHiddenMessage.
        """
        raise NotImplementedError

    def test_admin_can_see_comments(self):
        context = self.makeHiddenMessage()
        admin = self.factory.makeAdministrator()
        view = self.getView(context=context, user=admin)
        self.assertIn(self.html_comment_text, view.contents)

    def test_registry_can_see_comments(self):
        context = self.makeHiddenMessage()
        registry_expert = self.factory.makeRegistryExpert()
        view = self.getView(context=context, user=registry_expert)
        self.assertIn(self.html_comment_text, view.contents)

    def test_anon_cannot_see_comments(self):
        context = self.makeHiddenMessage()
        view = self.getView(context=context, no_login=True)
        self.assertNotIn(self.html_comment_text, view.contents)

    def test_random_cannot_see_comments(self):
        context = self.makeHiddenMessage()
        view = self.getView(context=context)
        self.assertNotIn(self.html_comment_text, view.contents)


class TestHideMessageControlMixin:

    control_text = 'mark-spam-1'

    def getContext(self, comment_owner=None):
        """To be overwridden by subclasses.

        This method must create and return a message bearing object
        (e.g. bug or question) with a hidden message/comment.
        """
        raise NotImplementedError

    def getView(self, context, user=None, no_login=False):
        """To be overwridden by subclasses.

        This method returns a view object rendered on the context
        obtained from makeHiddenMessage.
        """
        raise NotImplementedError

    def test_admin_sees_hide_control(self):
        context = self.getContext()
        administrator = self.factory.makeAdministrator()
        view = self.getView(context=context, user=administrator)
        hide_link = find_tag_by_id(view.contents, self.control_text)
        self.assertIsNot(None, hide_link)

    def test_registry_sees_hide_control(self):
        context = self.getContext()
        registry_expert = self.factory.makeRegistryExpert()
        view = self.getView(context=context, user=registry_expert)
        hide_link = find_tag_by_id(view.contents, self.control_text)
        self.assertIsNot(None, hide_link)

    def test_anon_doesnt_see_hide_control(self):
        context = self.getContext()
        view = self.getView(context=context, no_login=True)
        hide_link = find_tag_by_id(view.contents, self.control_text)
        self.assertIs(None, hide_link)

    def test_random_doesnt_see_hide_control(self):
        context = self.getContext()
        view = self.getView(context=context)
        hide_link = find_tag_by_id(view.contents, self.control_text)
        self.assertIs(None, hide_link)
