# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Webservice unit tests related to Launchpad Bug messages."""

__metaclass__ = type

from lazr.restfulclient.errors import HTTPError
import transaction
from zope.component import getUtility
from zope.security.management import endInteraction
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugmessage import IBugMessageSet
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.registry.interfaces.person import IPersonSet
from lp.testing import (
    launchpadlib_for,
    login_celebrity,
    person_logged_in,
    TestCaseWithFactory,
    WebServiceTestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestMessageTraversal(WebServiceTestCase):
    """Tests safe traversal of bugs.

    See bug 607438."""

    def test_message_with_attachments(self):
        bugowner = self.factory.makePerson()
        bug = self.factory.makeBug(owner=bugowner)
        # Traversal over bug messages attachments has no errors.
        expected_messages = []
        with person_logged_in(bugowner):
            for i in range(3):
                att = self.factory.makeBugAttachment(bug)
                expected_messages.append(att.message.subject)

        lp_user = self.factory.makePerson()
        lp_bug = self.wsObject(bug, lp_user)

        attachments = lp_bug.attachments
        messages = [a.message.subject for a in attachments
            if a.message is not None]
        self.assertContentEqual(
            messages,
            expected_messages)

    def test_message_with_parent(self):
        # The API exposes the parent attribute IMessage that is hidden by
        # IIndexedMessage. The representation cannot make a link to the
        # parent message because it might switch to another context
        # object that is not exposed or the user may not have access to.
        message_1 = self.factory.makeMessage()
        message_2 = self.factory.makeMessage()
        message_2.parent = message_1
        bug = self.factory.makeBug()
        bug.linkMessage(message_2)
        user = self.factory.makePerson()
        lp_bug = self.wsObject(bug, user)
        for lp_message in lp_bug.messages:
            # An IIndexedMessage's representation.
            self.assertIs(None, lp_message.parent)
        # An IMessage's representation.
        lp_message = self.wsObject(message_2, user)
        self.assertIs(None, lp_message.parent)


class TestSetCommentVisibility(TestCaseWithFactory):
    """Tests who can successfully set comment visibility."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSetCommentVisibility, self).setUp()
        self.person_set = getUtility(IPersonSet)
        admins = self.person_set.getByName('admins')
        self.admin = admins.teamowner
        with person_logged_in(self.admin):
            self.bug = self.factory.makeBug()
            self.message = self.factory.makeBugComment(
                bug=self.bug,
                subject='foo',
                body='bar')
        transaction.commit()

    def _get_bug_for_user(self, user=None):
        """Convenience function to get the api bug reference."""
        endInteraction()
        if user is not None:
            lp = launchpadlib_for("test", user)
        else:
            lp = launchpadlib_for("test")

        bug_entry = lp.load('/bugs/%s/' % self.bug.id)
        return bug_entry

    def _set_visibility(self, bug):
        """Method to set visibility; needed for assertRaises."""
        bug.setCommentVisibility(
            comment_number=1,
            visible=False)

    def _check_comment_hidden(self):
        bug_msg_set = getUtility(IBugMessageSet)
        with person_logged_in(self.admin):
            bug_message = bug_msg_set.getByBugAndMessage(
                self.bug, self.message)
            self.assertFalse(bug_message.message.visible)

    def _test_hide_comment(self, person, should_fail=False):
        bug = self._get_bug_for_user(person)
        if should_fail:
            self.assertRaises(
                HTTPError,
                self._set_visibility,
                bug)
        else:
            self._set_visibility(bug)
            self._check_comment_hidden()

    def test_random_user_cannot_set_visible(self):
        # Logged in users without privs can't set bug comment
        # visibility.
        nopriv = self.person_set.getByName('no-priv')
        self._test_hide_comment(person=nopriv, should_fail=True)

    def test_anon_cannot_set_visible(self):
        # Anonymous users can't set bug comment
        # visibility.
        self._test_hide_comment(person=None, should_fail=True)

    def test_registry_admin_can_set_visible(self):
        # Members of registry experts can set bug comment
        # visibility.
        person = login_celebrity('registry_experts')
        self._test_hide_comment(person)

    def test_admin_can_set_visible(self):
        # Admins can set bug comment
        # visibility.
        person = login_celebrity('admin')
        self._test_hide_comment(person)

    def test_userdata_grantee_can_set_visible(self):
        person = self.factory.makePerson()
        pillar = removeSecurityProxy(self.bug.default_bugtask).pillar
        policy = getUtility(IAccessPolicySource).find(
            [(pillar, InformationType.USERDATA)]).one()
        self.factory.makeAccessPolicyGrant(
            policy=policy, grantor=pillar.owner, grantee=person)
        self._test_hide_comment(person)
