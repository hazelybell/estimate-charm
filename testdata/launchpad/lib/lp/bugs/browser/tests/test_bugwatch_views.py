# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BugWatch views."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import (
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class TestBugWatchEditView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBugWatchEditView, self).setUp()
        self.person = self.factory.makePerson()

        login_person(self.person)
        self.bug_task = self.factory.makeBug(
            owner=self.person).default_bugtask
        self.bug_watch = self.factory.makeBugWatch(
            bug=self.bug_task.bug)

    def test_can_delete_watch(self):
        # An unlinked bugwatch can be deleted.
        bwid = self.bug_watch.id
        form = {'field.actions.delete': 'Delete Bug Watch'}
        getUtility(ILaunchBag).add(self.bug_task.bug)
        view = create_initialized_view(self.bug_watch, '+edit', form=form)
        self.assertContentEqual([], view.errors)
        self.assertRaises(NotFoundError, getUtility(IBugWatchSet).get, bwid)

    def test_can_not_delete_unlinked_watch_with_unsynched_comments(self):
        # If a bugwatch is unlinked, but has imported comments that are
        # awaiting synch, it can not be deleted.
        self.factory.makeBugComment(
            bug=self.bug_task.bug.id, bug_watch=self.bug_watch)
        view = create_initialized_view(self.bug_watch, '+edit')
        self.assertFalse(view.bugWatchIsUnlinked(None))

    def test_cannot_delete_watch_if_linked_to_task(self):
        # It isn't possible to delete a bug watch that's linked to a bug
        # task.
        self.bug_task.bugwatch = self.bug_watch
        view = create_initialized_view(self.bug_watch, '+edit')
        self.assertFalse(view.bugWatchIsUnlinked(None))

    def test_cannot_delete_watch_if_linked_to_comment(self):
        # It isn't possible to delete a bug watch that's linked to a bug
        # comment.
        message = getUtility(IMessageSet).fromText(
            "Example message", "With some example content to read.",
            owner=self.person)
        # We need to log in as an admin here as only admins can link a
        # watch to a comment.
        login(ADMIN_EMAIL)
        removeSecurityProxy(self.bug_watch).addComment('comment-id', message)
        login_person(self.person)
        view = create_initialized_view(self.bug_watch, '+edit')
        self.assertFalse(view.bugWatchIsUnlinked(None))
