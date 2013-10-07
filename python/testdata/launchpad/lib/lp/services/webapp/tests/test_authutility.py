# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import base64

import testtools
from zope.app.testing import ztapi
from zope.app.testing.placelesssetup import PlacelessSetup
from zope.authentication.interfaces import ILoginPassword
from zope.component import (
    getUtility,
    provideAdapter,
    provideUtility,
    )
from zope.interface import implements
from zope.principalregistry.principalregistry import UnauthenticatedPrincipal
from zope.publisher.browser import TestRequest
from zope.publisher.http import BasicAuthAdapter
from zope.publisher.interfaces.http import IHTTPCredentials

from lp.registry.interfaces.person import IPerson
from lp.services.config import config
from lp.services.identity.interfaces.account import IAccount
from lp.services.webapp.authentication import (
    LaunchpadPrincipal,
    PlacelessAuthUtility,
    )
from lp.services.webapp.interfaces import (
    IPlacelessAuthUtility,
    IPlacelessLoginSource,
    )


class DummyPerson(object):
    implements(IPerson)
    is_valid_person = True


class DummyAccount(object):
    implements(IAccount)
    person = DummyPerson()


Bruce = LaunchpadPrincipal(42, 'bruce', 'Bruce', DummyAccount())
Bruce.person = Bruce.account.person


class DummyPlacelessLoginSource(object):
    implements(IPlacelessLoginSource)

    def getPrincipalByLogin(self, id):
        return Bruce

    getPrincipal = getPrincipalByLogin

    def getPrincipals(self, name):
        return [Bruce]


class TestPlacelessAuth(PlacelessSetup, testtools.TestCase):

    def setUp(self):
        testtools.TestCase.setUp(self)
        PlacelessSetup.setUp(self)
        provideUtility(DummyPlacelessLoginSource(), IPlacelessLoginSource)
        provideUtility(PlacelessAuthUtility(), IPlacelessAuthUtility)
        provideAdapter(BasicAuthAdapter, (IHTTPCredentials,), ILoginPassword)

    def tearDown(self):
        ztapi.unprovideUtility(IPlacelessLoginSource)
        ztapi.unprovideUtility(IPlacelessAuthUtility)
        PlacelessSetup.tearDown(self)
        testtools.TestCase.tearDown(self)

    def _make(self, login, pwd):
        dict = {
            'HTTP_AUTHORIZATION':
            'Basic %s' % base64.encodestring('%s:%s' % (login, pwd))}
        request = TestRequest(**dict)
        return getUtility(IPlacelessAuthUtility), request

    def test_authenticate_ok(self):
        authsvc, request = self._make('bruce', 'test')
        self.assertEqual(authsvc.authenticate(request), Bruce)

    def test_authenticate_notok(self):
        authsvc, request = self._make('bruce', 'nottest')
        self.assertEqual(authsvc.authenticate(request), None)

    def test_unauthenticatedPrincipal(self):
        authsvc, request = self._make(None, None)
        self.assert_(isinstance(authsvc.unauthenticatedPrincipal(),
                                UnauthenticatedPrincipal))

    def test_unauthorized(self):
        authsvc, request = self._make('bruce', 'test')
        self.assertEqual(authsvc.unauthorized('bruce', request), None)
        self.assertEqual(request._response._status, 401)

    def test_basic_auth_disabled(self):
        # Basic auth uses a single password for every user, so it must
        # never be used on production. authenticate() will skip basic
        # auth unless it's enabled.
        authsvc, request = self._make('bruce', 'test')
        self.assertEqual(authsvc.authenticate(request), Bruce)
        try:
            config.push(
                "no-basic", "[launchpad]\nbasic_auth_password: none")
            self.assertEqual(authsvc.authenticate(request), None)
        finally:
            config.pop("no-basic")

    def test_direct_basic_call_fails_when_disabled(self):
        # Basic auth uses a single password for every user, so it must
        # never be used on production. authenticate() won't call the
        # underlying method unless it's enabled, but even if it somehow
        # does it will fail.
        authsvc, request = self._make('bruce', 'test')
        credentials = ILoginPassword(request, None)
        self.assertEqual(
            authsvc._authenticateUsingBasicAuth(credentials, request), Bruce)
        try:
            config.push(
                "no-basic", "[launchpad]\nbasic_auth_password: none")
            exception = self.assertRaises(
                AssertionError, authsvc._authenticateUsingBasicAuth,
                credentials, request)
            self.assertEquals(
                "Attempted to use basic auth when it is disabled",
                str(exception))
        finally:
            config.pop("no-basic")

    def test_getPrincipal(self):
        authsvc, request = self._make('bruce', 'test')
        self.assertEqual(authsvc.getPrincipal('bruce'), Bruce)

    def test_getPrincipals(self):
        authsvc, request = self._make('bruce', 'test')
        self.assertEqual(authsvc.getPrincipals('bruce'), [Bruce])

    def test_getPrincipalByLogin(self):
        authsvc, request = self._make('bruce', 'test')
        self.assertEqual(authsvc.getPrincipalByLogin('bruce'), Bruce)
