# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.identity.interfaces.account import AccountStatus
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.verification.browser.logintoken import (
    ClaimTeamView,
    ValidateEmailView,
    ValidateGPGKeyView,
    )
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import ILoginTokenSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.deprecated import LaunchpadFormHarness
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestCancelActionOnLoginTokenViews(TestCaseWithFactory):
    """Test the 'Cancel' action of LoginToken views.

    These views have an action instead of a link to cancel because we want the
    token to be consumed (so it can't be used again) when the user hits
    Cancel.
    """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.person = self.factory.makePerson(name='test-user')
        self.email = removeSecurityProxy(self.person).preferredemail.email
        self.expected_next_url = 'http://127.0.0.1/~test-user'

    def test_ClaimTeamView(self):
        token = getUtility(ILoginTokenSet).new(
            self.person, self.email, self.email, LoginTokenType.TEAMCLAIM)
        self._testCancelAction(ClaimTeamView, token)

    def test_ValidateGPGKeyView(self):
        self.gpg_key = self.factory.makeGPGKey(self.person)
        token = getUtility(ILoginTokenSet).new(
            self.person, self.email, self.email, LoginTokenType.VALIDATEGPG,
            fingerprint=self.gpg_key.fingerprint)
        self._testCancelAction(ValidateGPGKeyView, token)

    def test_ValidateEmailView(self):
        with person_logged_in(self.person):
            token = getUtility(ILoginTokenSet).new(
                self.person, self.email, 'foo@example.com',
                LoginTokenType.VALIDATEEMAIL)
            self._testCancelAction(ValidateEmailView, token)

    def _testCancelAction(self, view_class, token):
        """Test the 'Cancel' action of the given view, using the given token.

        To test that the action works, we just submit the form with that
        action, check that there are no errors and make sure that the view's
        next_url is what we expect.
        """
        harness = LaunchpadFormHarness(token, view_class)
        harness.submit('cancel', {})
        actions = harness.view.actions.byname
        self.assertIn('field.actions.cancel', actions)
        self.assertEquals(actions['field.actions.cancel'].submitted(), True)
        self.assertEquals(harness.view.errors, [])
        self.assertEquals(harness.view.next_url, self.expected_next_url)


class TestClaimTeamView(TestCaseWithFactory):
    """Test the claiming of a team via login token."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.claimer = self.factory.makePerson(name='claimer')
        self.claimee_email = 'claimee@example.com'
        self.claimee = self.factory.makePerson(
            name='claimee', email=self.claimee_email,
            email_address_status=EmailAddressStatus.NEW)

    def _claimToken(self, token):
        harness = LaunchpadFormHarness(token, ClaimTeamView)
        harness.submit('confirm', {})
        return [n.message for n in harness.request.notifications]

    def test_CannotClaimTwice(self):
        token1 = getUtility(ILoginTokenSet).new(
            requester=self.claimer, requesteremail=None,
            email=self.claimee_email, tokentype=LoginTokenType.TEAMCLAIM)
        token2 = getUtility(ILoginTokenSet).new(
            requester=self.claimer, requesteremail=None,
            email=self.claimee_email, tokentype=LoginTokenType.TEAMCLAIM)
        msgs = self._claimToken(token1)
        self.assertEquals([u'Team claimed successfully'], msgs)
        msgs = self._claimToken(token2)
        self.assertEquals(
            [u'claimee has already been converted to a team.'], msgs)


class MergePeopleViewTestCase(TestCaseWithFactory):
    """Test the view for confirming a merge via login token."""

    layer = DatabaseFunctionalLayer

    def assertWorkflow(self, claimer, dupe):
        token = getUtility(ILoginTokenSet).new(
            requester=claimer, requesteremail='me@example.com',
            email="him@example.com", tokentype=LoginTokenType.ACCOUNTMERGE)
        view = create_initialized_view(token, name="+accountmerge")
        self.assertIs(False, view.mergeCompleted)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*to merge the Launchpad account named.*claimer', view.render())
        view = create_initialized_view(
            token, name="+accountmerge", principal=claimer,
            form={'VALIDATE': 'Confirm'}, method='POST')
        with person_logged_in(claimer):
            view.render()
        self.assertIs(True, view.mergeCompleted)
        notifications = view.request.notifications
        self.assertEqual(2, len(notifications))
        text = notifications[0].message
        self.assertTextMatchesExpressionIgnoreWhitespace(
            "A merge is queued.*", text)

    def test_confirm_email_for_active_account(self):
        # Users can confirm they control an email address to merge a duplicate
        # profile.
        claimer = self.factory.makePerson(
            email='me@example.com', name='claimer')
        dupe = self.factory.makePerson(email='him@example.com', name='dupe')
        self.assertWorkflow(claimer, dupe)

    def test_confirm_email_for_non_active_account(self):
        # Users can confirm they control an email address to merge a
        # non-active duplicate profile.
        claimer = self.factory.makePerson(
            email='me@example.com', name='claimer')
        dupe = self.factory.makePerson(
            email='him@example.com', name='dupe',
            email_address_status=EmailAddressStatus.NEW,
            account_status=AccountStatus.NOACCOUNT)
        self.assertWorkflow(claimer, dupe)
