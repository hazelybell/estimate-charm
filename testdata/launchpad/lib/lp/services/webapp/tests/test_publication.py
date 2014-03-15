# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests publication.py"""

__metaclass__ = type

import sys

from contrib.oauth import (
    OAuthRequest,
    OAuthSignatureMethod_PLAINTEXT,
    )
from storm.database import (
    STATE_DISCONNECTED,
    STATE_RECONNECT,
    )
from storm.exceptions import DisconnectionError
from zope.component import getUtility
from zope.interface import directlyProvides
from zope.publisher.interfaces import (
    NotFound,
    Retry,
    )

from lp.services.database.interfaces import IMasterStore
from lp.services.identity.model.emailaddress import EmailAddress
from lp.services.oauth.interfaces import (
    IOAuthConsumerSet,
    IOAuthSignedRequest,
    )
import lp.services.webapp.adapter as dbadapter
from lp.services.webapp.interfaces import (
    NoReferrerError,
    OAuthPermission,
    OffsiteFormPostError,
    )
from lp.services.webapp.publication import (
    is_browser,
    LaunchpadBrowserPublication,
    maybe_block_offsite_form_post,
    OFFSITE_POST_WHITELIST,
    )
from lp.services.webapp.servers import (
    LaunchpadTestRequest,
    WebServicePublication,
    )
from lp.services.webapp.vhosts import allvhosts
from lp.testing import (
    ANONYMOUS,
    login,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestLaunchpadBrowserPublication(TestCase):

    def test_callTraversalHooks_appends_to_traversed_objects(self):
        # Traversed objects are appended to request.traversed_objects in the
        # order they're traversed.
        obj1 = object()
        obj2 = object()
        request = LaunchpadTestRequest()
        publication = LaunchpadBrowserPublication(None)
        publication.callTraversalHooks(request, obj1)
        publication.callTraversalHooks(request, obj2)
        self.assertEquals(request.traversed_objects, [obj1, obj2])

    def test_callTraversalHooks_appends_only_once_to_traversed_objects(self):
        # callTraversalHooks() may be called more than once for a given
        # traversed object, but if that's the case we won't add the same
        # object twice to traversed_objects.
        obj1 = obj2 = object()
        request = LaunchpadTestRequest()
        publication = LaunchpadBrowserPublication(None)
        publication.callTraversalHooks(request, obj1)
        publication.callTraversalHooks(request, obj2)
        self.assertEquals(request.traversed_objects, [obj1])


class TestWebServicePublication(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        login(ANONYMOUS)

    def _getRequestForPersonAndAccountWithDifferentIDs(self):
        """Return a LaunchpadTestRequest with the correct OAuth parameters in
        its form.
        """
        # Create a lone account followed by an account-with-person just to
        # make sure in the second one the ID of the account and the person are
        # different.
        self.factory.makeAccount('Personless account')
        person = self.factory.makePerson()
        self.failIfEqual(person.id, person.account.id)

        # Create an access token for our new person.
        consumer = getUtility(IOAuthConsumerSet).new('test-consumer')
        request_token = consumer.newRequestToken()
        request_token.review(
            person, permission=OAuthPermission.READ_PUBLIC, context=None)
        access_token = request_token.createAccessToken()

        # Use oauth.OAuthRequest just to generate a dictionary containing all
        # the parameters we need to use in a valid OAuth request, using the
        # access token we just created for our new person.
        oauth_request = OAuthRequest.from_consumer_and_token(
            consumer, access_token)
        oauth_request.sign_request(
            OAuthSignatureMethod_PLAINTEXT(), consumer, access_token)
        return LaunchpadTestRequest(form=oauth_request.parameters)

    def test_getPrincipal_for_person_and_account_with_different_ids(self):
        # WebServicePublication.getPrincipal() does not rely on accounts
        # having the same IDs as their associated person entries to work.
        request = self._getRequestForPersonAndAccountWithDifferentIDs()
        principal = WebServicePublication(None).getPrincipal(request)
        self.failIf(principal is None)

    def test_disconnect_logs_oops(self):
        # Ensure that OOPS reports are generated for database
        # disconnections, as per Bug #373837.
        request = LaunchpadTestRequest()
        publication = WebServicePublication(None)
        dbadapter.set_request_started()
        try:
            raise DisconnectionError('Fake')
        except DisconnectionError:
            self.assertRaises(
                Retry,
                publication.handleException,
                None, request, sys.exc_info(), True)
        dbadapter.clear_request_started()
        self.assertEqual(1, len(self.oopses))
        oops = self.oopses[0]

        # Ensure the OOPS mentions the correct exception
        self.assertEqual(oops['type'], "DisconnectionError")

    def test_store_disconnected_after_request_handled_logs_oops(self):
        # Bug #504291 was that a Store was being left in a disconnected
        # state after a request, causing subsequent requests handled by that
        # thread to fail. We detect this state in endRequest and log an
        # OOPS to help track down the trigger.
        request = LaunchpadTestRequest()
        publication = WebServicePublication(None)
        dbadapter.set_request_started()

        # Disconnect a store
        store = IMasterStore(EmailAddress)
        store._connection._state = STATE_DISCONNECTED

        # Invoke the endRequest hook.
        publication.endRequest(request, None)

        self.assertEqual(1, len(self.oopses))
        oops = self.oopses[0]

        # Ensure the OOPS mentions the correct exception
        self.assertStartsWith(oops['value'], "Bug #504291")

        # Ensure the store has been rolled back and in a usable state.
        self.assertEqual(store._connection._state, STATE_RECONNECT)
        store.find(EmailAddress).first()  # Confirms Store is working.

    def test_is_browser(self):
        # No User-Agent: header.
        request = LaunchpadTestRequest()
        self.assertFalse(is_browser(request))

        # Browser User-Agent: header.
        request = LaunchpadTestRequest(environ={
            'USER_AGENT': 'Mozilla/42 Extreme Edition'})
        self.assertTrue(is_browser(request))

        # Robot User-Agent: header.
        request = LaunchpadTestRequest(environ={'USER_AGENT': 'BottyBot'})
        self.assertFalse(is_browser(request))


class TestBlockingOffsitePosts(TestCase):
    """We are very particular about what form POSTs we will accept."""

    def test_NoReferrerError(self):
        # If this request is a POST and there is no referrer, an exception is
        # raised.
        request = LaunchpadTestRequest(
            method='POST', environ=dict(PATH_INFO='/'))
        self.assertRaises(
            NoReferrerError, maybe_block_offsite_form_post, request)

    def test_nonPOST_requests(self):
        # If the request isn't a POST it is always allowed.
        request = LaunchpadTestRequest(method='SOMETHING')
        maybe_block_offsite_form_post(request)

    def test_localhost_is_ok(self):
        # we accept "localhost" and "localhost:9000" as valid referrers.  See
        # comments in the code as to why and for a related bug report.
        request = LaunchpadTestRequest(
            method='POST', environ=dict(PATH_INFO='/', REFERER='localhost'))
        # this doesn't raise an exception
        maybe_block_offsite_form_post(request)

    def test_whitelisted_paths(self):
        # There are a few whitelisted POST targets that don't require the
        # referrer be LP.  See comments in the code as to why and for related
        # bug reports.
        for path in OFFSITE_POST_WHITELIST:
            request = LaunchpadTestRequest(
                method='POST', environ=dict(PATH_INFO=path))
            # this call shouldn't raise an exception
            maybe_block_offsite_form_post(request)

    def test_OAuth_signed_requests(self):
        # Requests that are OAuth signed are allowed.
        request = LaunchpadTestRequest(
            method='POST', environ=dict(PATH_INFO='/'))
        directlyProvides(request, IOAuthSignedRequest)
        # this call shouldn't raise an exception
        maybe_block_offsite_form_post(request)

    def test_nonbrowser_requests(self):
        # Requests that are from non-browsers are allowed.
        class FakeNonBrowserRequest:
            method = 'SOMETHING'

        # this call shouldn't raise an exception
        maybe_block_offsite_form_post(FakeNonBrowserRequest)

    def test_onsite_posts(self):
        # Other than the explicit exceptions, all POSTs have to come from a
        # known LP virtual host.
        for hostname in allvhosts.hostnames:
            referer = 'http://' + hostname + '/foo'
            request = LaunchpadTestRequest(
                method='POST', environ=dict(PATH_INFO='/', REFERER=referer))
            # this call shouldn't raise an exception
            maybe_block_offsite_form_post(request)

    def test_offsite_posts(self):
        # If a post comes from an unknown host an exception is raised.
        disallowed_hosts = ['example.com', 'not-subdomain.launchpad.net']
        for hostname in disallowed_hosts:
            referer = 'http://' + hostname + '/foo'
            request = LaunchpadTestRequest(
                method='POST', environ=dict(PATH_INFO='/', REFERER=referer))
            self.assertRaises(
                OffsiteFormPostError, maybe_block_offsite_form_post, request)

    def test_unparsable_referer(self):
        # If a post has a referer that is unparsable as a URI an exception is
        # raised.
        referer = 'this is not a URI'
        request = LaunchpadTestRequest(
            method='POST', environ=dict(PATH_INFO='/', REFERER=referer))
        self.assertRaises(
            OffsiteFormPostError, maybe_block_offsite_form_post, request)

    def test_openid_callback_with_query_string(self):
        # An OpenId provider (OP) may post to the +openid-callback URL with a
        # query string and without a referer.  These posts need to be allowed.
        path_info = u'/+openid-callback?starting_url=...'
        request = LaunchpadTestRequest(
            method='POST', environ=dict(PATH_INFO=path_info))
        # this call shouldn't raise an exception
        maybe_block_offsite_form_post(request)


class TestEncodedReferer(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_not_found(self):
        # No oopses are reported when accessing the referer while rendering
        # the page.
        browser = self.getUserBrowser()
        browser.addHeader('Referer', '/whut\xe7foo')
        self.assertRaises(
            NotFound,
            browser.open,
            'http://launchpad.dev/missing')
        self.assertEqual(0, len(self.oopses))


class TestUnicodePath(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_non_ascii_url(self):
        # No oopses are reported when accessing the URL while rendering the
        # page.
        browser = self.getUserBrowser()
        self.assertRaises(
            NotFound,
            browser.open,
            'http://launchpad.dev/%ED%B4%B5')
        self.assertEqual(0, len(self.oopses))
