# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import transaction
from zope.security.interfaces import Unauthorized

from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class TestBugAttachmentEditView(TestCaseWithFactory):
    """Tests of traversal to and access of files of bug attachments."""

    layer = LaunchpadFunctionalLayer

    CHANGE_FORM_DATA = {
        'field.title': 'new description',
        'field.patch': 'on',
        'field.contenttype': 'application/whatever',
        'field.actions.change': 'Change',
        }

    def setUp(self):
        super(TestBugAttachmentEditView, self).setUp()
        self.bug_owner = self.factory.makePerson()
        login_person(self.bug_owner)
        self.bug = self.factory.makeBug(owner=self.bug_owner)
        self.bugattachment = self.factory.makeBugAttachment(
            bug=self.bug, filename='foo.diff', data='file content',
            description='attachment description', content_type='text/plain',
            is_patch=False)
        # The Librarian server should know about the new file before
        # we start the tests.
        transaction.commit()

    def test_change_action_public_bug(self):
        # Properties of attachments for public bugs can be
        # changed by every user.
        user = self.factory.makePerson()
        login_person(user)
        create_initialized_view(
            self.bugattachment, name='+edit', form=self.CHANGE_FORM_DATA)
        self.assertEqual('new description', self.bugattachment.title)
        self.assertTrue(self.bugattachment.is_patch)
        self.assertEqual(
            'application/whatever', self.bugattachment.libraryfile.mimetype)

    def test_change_action_private_bug(self):
        # Subscribers of a private bug can edit attachments.
        user = self.factory.makePerson()
        self.bug.setPrivate(True, self.bug_owner)
        with person_logged_in(self.bug_owner):
            self.bug.subscribe(user, self.bug_owner)
        transaction.commit()
        login_person(user)
        create_initialized_view(
            self.bugattachment, name='+edit', form=self.CHANGE_FORM_DATA)
        self.assertEqual('new description', self.bugattachment.title)
        self.assertTrue(self.bugattachment.is_patch)
        self.assertEqual(
            'application/whatever', self.bugattachment.libraryfile.mimetype)

    def test_change_action_private_bug_unauthorized(self):
        # Other users cannot edit attachments of private bugs.
        user = self.factory.makePerson()
        self.bug.setPrivate(True, self.bug_owner)
        transaction.commit()
        login_person(user)
        self.assertRaises(
            Unauthorized, create_initialized_view, self.bugattachment,
            name='+edit', form=self.CHANGE_FORM_DATA)

    DELETE_FORM_DATA = {
        'field.actions.delete': 'Delete Attachment',
        }

    def test_delete_action_public_bug(self):
        # Bug attachments can be removed from a bug.
        user = self.factory.makePerson()
        login_person(user)
        create_initialized_view(
            self.bugattachment, name='+edit', form=self.DELETE_FORM_DATA)
        self.assertEqual(0, self.bug.attachments.count())

    def test_delete_action_private_bug(self):
        # Subscribers of a private bug can delete attachments.
        user = self.factory.makePerson()
        self.bug.setPrivate(True, self.bug_owner)
        with person_logged_in(self.bug_owner):
            self.bug.subscribe(user, self.bug_owner)
        login_person(user)
        create_initialized_view(
            self.bugattachment, name='+edit', form=self.DELETE_FORM_DATA)
        self.assertEqual(0, self.bug.attachments.count())

    def test_delete_action_private_bug_unautorized(self):
        # Other users cannot delete private bug attachments.
        user = self.factory.makePerson()
        self.bug.setPrivate(True, self.bug_owner)
        login_person(user)
        self.assertRaises(
            Unauthorized, create_initialized_view, self.bugattachment,
            name='+edit', form=self.DELETE_FORM_DATA)
