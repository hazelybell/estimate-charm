# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Webservice unit tests related to Launchpad Bugs."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.enums import InformationType
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.testing import (
    login,
    login_celebrity,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugIndexedMessages(TestCaseWithFactory):
    """Test the workings of IBug.indexed_messages."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugIndexedMessages, self).setUp()
        login('foo.bar@canonical.com')

        bug_1 = self.factory.makeBug()
        self.bug_2 = self.factory.makeBug()

        message_1 = self.factory.makeMessage()
        message_2 = self.factory.makeMessage()
        message_2.parent = message_1

        bug_1.linkMessage(message_1)
        self.bug_2.linkMessage(message_2)

    def test_indexed_message_null_parents(self):
        # Accessing the parent of an IIndexedMessage will return None if
        # the parent isn't linked to the same bug as the
        # IIndexedMessage.
        for indexed_message in self.bug_2.indexed_messages:
            self.failUnlessEqual(None, indexed_message.parent)


class TestUserCanSetCommentVisibility(TestCaseWithFactory):

    """Test whether expected users can toggle bug comment visibility."""

    layer = DatabaseFunctionalLayer

    def test_random_user_cannot_toggle_comment_visibility(self):
        # A random user cannot set bug comment visibility.
        person = self.factory.makePerson()
        bug = self.factory.makeBug()
        self.assertFalse(bug.userCanSetCommentVisibility(person))

    def test_registry_admin_can_toggle_comment_visibility(self):
        # Members of registry experts can set bug comment visibility.
        person = login_celebrity('registry_experts')
        bug = self.factory.makeBug()
        self.assertTrue(bug.userCanSetCommentVisibility(person))

    def test_admin_can_toggle_comment_visibility(self):
        # Admins can set bug comment visibility.
        person = login_celebrity('admin')
        bug = self.factory.makeBug()
        self.assertTrue(bug.userCanSetCommentVisibility(person))

    def test_userdata_grant_can_toggle_comment_visibility(self):
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        policy = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)]).one()
        self.factory.makeAccessPolicyGrant(
            policy=policy, grantor=product.owner, grantee=person)
        self.assertTrue(bug.userCanSetCommentVisibility(person))
