# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import cgi
from datetime import datetime

import lazr.uri
from zope.component import getUtility
from zope.event import notify
from zope.session.interfaces import ISession

from lp.services.config import config
from lp.services.identity.interfaces.account import (
    AccountCreationRationale,
    IAccountSet,
    )
from lp.services.webapp.authentication import LaunchpadPrincipal
from lp.services.webapp.interfaces import (
    CookieAuthLoggedInEvent,
    IPlacelessAuthUtility,
    )
from lp.services.webapp.login import (
    CookieLogoutPage,
    logInPrincipal,
    logoutPerson,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestLoginAndLogout(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.request = LaunchpadTestRequest()
        # We create an account without a Person here just to make sure the
        # person and account created later don't end up with the same IDs,
        # which could happen since they're both sequential.
        # We need them to be different for one of our tests here.
        getUtility(IAccountSet).new(
            AccountCreationRationale.UNKNOWN, 'Dummy name')
        person = self.factory.makePerson('foo.bar@example.com')
        self.failIfEqual(person.id, person.account.id)
        self.principal = LaunchpadPrincipal(
            person.account.id, person.displayname,
            person.displayname, person)

    def test_logging_in_and_logging_out(self):
        # A test showing that we can authenticate the request after
        # logInPrincipal() is called, and after logoutPerson() we can no
        # longer authenticate it.

        # This is to setup an interaction so that we can call logInPrincipal
        # below.
        login('foo.bar@example.com')

        logInPrincipal(self.request, self.principal, 'foo.bar@example.com')
        session = ISession(self.request)
        # logInPrincipal() stores the account ID in a variable named
        # 'accountid'.
        self.failUnlessEqual(
            session['launchpad.authenticateduser']['accountid'],
            int(self.principal.id))

        # Ensure we are using cookie auth.
        self.assertIsNotNone(
            self.request.response.getCookie(config.launchpad_session.cookie)
            )

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnlessEqual(self.principal.id, principal.id)

        logoutPerson(self.request)

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnless(principal is None)

    def test_CookieLogoutPage(self):
        # This test shows that the CookieLogoutPage redirects as we expect:
        # first to loggerhead for it to log out (see bug 574493) and then
        # to our OpenId provider for it to log out (see bug 568106).  This
        # will need to be readdressed when we want to accept other OpenId
        # providers, unfortunately.

        # This is to setup an interaction so that we can call logInPrincipal
        # below.
        login('foo.bar@example.com')

        logInPrincipal(self.request, self.principal, 'foo.bar@example.com')

        # Normally CookieLogoutPage is magically mixed in with a base class
        # that accepts context and request and sets up other things.  We're
        # just going to put the request on the base class ourselves for this
        # test.

        view = CookieLogoutPage()
        view.request = self.request

        # We need to set the session cookie so it can be expired.
        self.request.response.setCookie(
            config.launchpad_session.cookie, 'xxx')

        # Now we logout.

        result = view.logout()

        # We should, in fact, be logged out (this calls logoutPerson).

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnless(principal is None)

        # The view should have redirected us, with no actual response body.

        self.assertEquals(self.request.response.getStatus(), 302)
        self.assertEquals(result, '')

        # We are redirecting to Loggerhead, to ask it to logout.

        location = lazr.uri.URI(self.request.response.getHeader('location'))
        self.assertEquals(location.host, 'bazaar.launchpad.dev')
        self.assertEquals(location.scheme, 'https')
        self.assertEquals(location.path, '/+logout')

        # That page should then redirect to our OpenId provider to logout,
        # which we provide in our query string.  See
        # launchpad_loggerhead.tests.TestLogout for the pertinent tests.

        query = cgi.parse_qs(location.query)
        self.assertEquals(
            query['next_to'][0], 'http://testopenid.dev/+logout')

    def test_logging_in_and_logging_out_the_old_way(self):
        # A test showing that we can authenticate a request that had the
        # person/account ID stored in the 'personid' session variable instead
        # of 'accountid' -- where it's stored by logInPrincipal(). Also shows
        # that after logoutPerson() we can no longer authenticate it.
        # This is just for backwards compatibility.

        # This is to setup an interaction so that we can do the same thing
        # that's done by logInPrincipal() below.
        login('foo.bar@example.com')

        session = ISession(self.request)
        authdata = session['launchpad.authenticateduser']
        self.request.setPrincipal(self.principal)
        authdata['personid'] = self.principal.person.id
        authdata['logintime'] = datetime.utcnow()
        authdata['login'] = 'foo.bar@example.com'
        notify(CookieAuthLoggedInEvent(self.request, 'foo.bar@example.com'))

        # This is so that the authenticate() call below uses cookie auth.
        self.request.response.setCookie(
            config.launchpad_session.cookie, 'xxx')

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnlessEqual(self.principal.id, principal.id)
        self.failUnlessEqual(self.principal.person, principal.person)

        logoutPerson(self.request)

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnless(principal is None)
