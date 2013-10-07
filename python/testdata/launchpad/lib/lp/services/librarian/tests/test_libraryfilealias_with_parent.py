# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = []

from zope.component import getMultiAdapter
from zope.security.interfaces import Unauthorized

from lp.app.enums import InformationType
from lp.services.librarian.interfaces import ILibraryFileAliasWithParent
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestLibraryFileAliasForBugAttachment(TestCaseWithFactory):
    """Tests for ILibraryFileAliasWithParent."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestLibraryFileAliasForBugAttachment, self).setUp()
        self.bug_owner = self.factory.makePerson()
        login_person(self.bug_owner)
        self.bug = self.factory.makeBug(
            owner=self.bug_owner, information_type=InformationType.USERDATA)
        self.bug_attachment = self.factory.makeBugAttachment(bug=self.bug)
        self.lfa_with_parent = getMultiAdapter(
            (self.bug_attachment.libraryfile, self.bug_attachment),
            ILibraryFileAliasWithParent)

    def test_setRestricted_authorized_user(self):
        # A LibraryFileAlias instance can be adapted to an editable
        # variant, by adapting it, together with a parent object to
        # ILibraryFileAliasWithParent.
        #
        # People who can edit the parent object can also edit
        # LibraryFilasAlias instance.
        login_person(self.bug_owner)
        self.assertTrue(self.lfa_with_parent.restricted)
        self.bug_attachment.title = 'foo'
        self.lfa_with_parent.restricted = False
        self.assertFalse(self.lfa_with_parent.restricted)

    def test_setRestricted_unauthorized_user(self):
        # If a user cannot change properties of a bug attachment...
        other_person = self.factory.makePerson()
        login_person(other_person)
        self.assertRaises(
            Unauthorized, setattr, self.bug_attachment, 'title', 'whatever')
        # ...he also can't change the LibraryFileAlias for this bug.
        self.assertRaises(
            Unauthorized, setattr, self.lfa_with_parent, 'restricted', True)

    def test_createToken_authorized_user(self):
        # Persons having access to a parent object of a restricted
        # Librarian file can call the method
        # ILibraryFileAliasWithParent.createToken()
        login_person(self.bug_owner)
        self.lfa_with_parent.createToken()

    def test_createToken_unauthorized_user(self):
        # Users without access to a parent object cannot call
        # ILibraryFileAliasWithParent.createToken()
        other_person = self.factory.makePerson()
        login_person(other_person)
        self.assertRaises(
            Unauthorized, getattr, self.lfa_with_parent, 'createToken')
