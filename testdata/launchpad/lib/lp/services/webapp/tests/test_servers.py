# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import (
    DocTestSuite,
    ELLIPSIS,
    NORMALIZE_WHITESPACE,
    )
import StringIO
import unittest

from lazr.restful.interfaces import (
    IServiceRootResource,
    IWebServiceConfiguration,
    )
from lazr.restful.simple import RootResource
from lazr.restful.testing.webservice import (
    IGenericCollection,
    IGenericEntry,
    WebServiceTestCase,
    )
from zope.component import (
    getGlobalSiteManager,
    getUtility,
    )
from zope.interface import (
    implements,
    Interface,
    )

from lp.services.webapp.interfaces import IFinishReadOnlyRequestEvent
from lp.services.webapp.publication import LaunchpadBrowserPublication
from lp.services.webapp.servers import (
    ApplicationServerSettingRequestFactory,
    FeedsBrowserRequest,
    LaunchpadBrowserRequest,
    LaunchpadTestRequest,
    PrivateXMLRPCRequest,
    VHostWebServiceRequestPublicationFactory,
    VirtualHostRequestPublicationFactory,
    web_service_request_to_browser_request,
    WebServiceClientRequest,
    WebServicePublication,
    WebServiceRequestPublicationFactory,
    WebServiceTestRequest,
    )
from lp.testing import (
    EventRecorder,
    TestCase,
    )
from lp.testing.layers import FunctionalLayer


class SetInWSGIEnvironmentTestCase(TestCase):

    def test_set(self):
        # Test that setInWSGIEnvironment() can set keys in the WSGI
        # environment.
        data = StringIO.StringIO('foo')
        env = {}
        request = LaunchpadBrowserRequest(data, env)
        request.setInWSGIEnvironment('key', 'value')
        self.assertEqual(request._orig_env['key'], 'value')

    def test_set_fails_for_existing_key(self):
        # Test that setInWSGIEnvironment() fails if the user tries to
        # set a key that existed in the WSGI environment.
        data = StringIO.StringIO('foo')
        env = {'key': 'old value'}
        request = LaunchpadBrowserRequest(data, env)
        self.assertRaises(KeyError,
                          request.setInWSGIEnvironment, 'key', 'new value')
        self.assertEqual(request._orig_env['key'], 'old value')

    def test_set_twice(self):
        # Test that setInWSGIEnvironment() can change the value of
        # keys in the WSGI environment that it had previously set.
        data = StringIO.StringIO('foo')
        env = {}
        request = LaunchpadBrowserRequest(data, env)
        request.setInWSGIEnvironment('key', 'first value')
        request.setInWSGIEnvironment('key', 'second value')
        self.assertEqual(request._orig_env['key'], 'second value')

    def test_set_after_retry(self):
        # Test that setInWSGIEnvironment() a key in the environment
        # can be set twice over a request retry.
        data = StringIO.StringIO('foo')
        env = {}
        request = LaunchpadBrowserRequest(data, env)
        request.setInWSGIEnvironment('key', 'first value')
        new_request = request.retry()
        new_request.setInWSGIEnvironment('key', 'second value')
        self.assertEqual(new_request._orig_env['key'], 'second value')


class TestApplicationServerSettingRequestFactory(TestCase):
    """Tests for the ApplicationServerSettingRequestFactory."""

    def test___call___should_set_HTTPS_env_on(self):
        # Ensure that the factory sets the HTTPS variable in the request
        # when the protocol is https.
        factory = ApplicationServerSettingRequestFactory(
            LaunchpadBrowserRequest, 'launchpad.dev', 'https', 443)
        request = factory(StringIO.StringIO(), {'HTTP_HOST': 'launchpad.dev'})
        self.assertEquals(
            request.get('HTTPS'), 'on', "factory didn't set the HTTPS env")
        # This is a sanity check ensuring that effect of this works as
        # expected with the Zope request implementation.
        self.assertEquals(request.getURL(), 'https://launchpad.dev')

    def test___call___should_not_set_HTTPS(self):
        # Ensure that the factory doesn't put an HTTPS variable in the
        # request when the protocol is http.
        factory = ApplicationServerSettingRequestFactory(
            LaunchpadBrowserRequest, 'launchpad.dev', 'http', 80)
        request = factory(StringIO.StringIO(), {})
        self.assertEquals(
            request.get('HTTPS'), None,
            "factory should not have set HTTPS env")


class TestVhostWebserviceFactory(WebServiceTestCase):

    class VHostTestBrowserRequest(LaunchpadBrowserRequest):
        pass

    class VHostTestPublication(LaunchpadBrowserRequest):
        pass

    def setUp(self):
        super(TestVhostWebserviceFactory, self).setUp()
        # XXX We have to use a real hostname.
        self.factory = VHostWebServiceRequestPublicationFactory(
            'bugs', self.VHostTestBrowserRequest, self.VHostTestPublication)

    def wsgi_env(self, path, method='GET'):
        """Simulate a WSGI application environment."""
        return {
            'PATH_INFO': path,
            'HTTP_HOST': 'bugs.launchpad.dev',
            'REQUEST_METHOD': method,
            }

    @property
    def api_path(self):
        """Requests to this path should be treated as webservice requests."""
        return '/' + getUtility(IWebServiceConfiguration).path_override

    @property
    def non_api_path(self):
        """Requests to this path should not be treated as webservice requests.
        """
        return '/foo'

    def test_factory_produces_webservice_objects(self):
        """The factory should produce WebService request and publication
        objects for requests to the /api root URL.
        """
        env = self.wsgi_env(self.api_path)

        # Necessary preamble and sanity check.  We need to call
        # the factory's canHandle() method with an appropriate
        # WSGI environment before it can produce a request object for us.
        self.assert_(self.factory.canHandle(env),
            "Sanity check: The factory should be able to handle requests.")

        wrapped_factory, publication_factory = self.factory()

        # We need to unwrap the real request factory.
        request_factory = wrapped_factory.requestfactory

        self.assertEqual(request_factory, WebServiceClientRequest,
            "Requests to the /api path should return a WebService "
            "request object.")
        self.assertEqual(
            publication_factory, WebServicePublication,
            "Requests to the /api path should return a WebService "
            "publication object.")

    def test_factory_produces_normal_request_objects(self):
        """The factory should return the request and publication factories
        specified in it's constructor if the request is not bound for the
        web service.
        """
        env = self.wsgi_env(self.non_api_path)
        self.assert_(self.factory.canHandle(env),
            "Sanity check: The factory should be able to handle requests.")

        wrapped_factory, publication_factory = self.factory()

        # We need to unwrap the real request factory.
        request_factory = wrapped_factory.requestfactory

        self.assertEqual(request_factory, self.VHostTestBrowserRequest,
            "Requests to normal paths should return a VHostTest "
            "request object.")
        self.assertEqual(
            publication_factory, self.VHostTestPublication,
            "Requests to normal paths should return a VHostTest "
            "publication object.")

    def test_factory_processes_webservice_http_methods(self):
        """The factory should accept the HTTP methods for requests that
        should be processed by the web service.
        """
        allowed_methods = WebServiceRequestPublicationFactory.default_methods

        for method in allowed_methods:
            env = self.wsgi_env(self.api_path, method)
            self.assert_(self.factory.canHandle(env),
                "Sanity check")
            # Returns a tuple of (request_factory, publication_factory).
            rfactory, pfactory = self.factory.checkRequest(env)
            self.assert_(rfactory is None,
                "The '%s' HTTP method should be handled by the factory."
                % method)

    def test_factory_rejects_normal_http_methods(self):
        """The factory should reject some HTTP methods for requests that
        are *not* bound for the web service.

        This includes methods like 'PUT' and 'PATCH'.
        """
        vhost_methods = VirtualHostRequestPublicationFactory.default_methods
        ws_methods = WebServiceRequestPublicationFactory.default_methods

        denied_methods = set(ws_methods) - set(vhost_methods)

        for method in denied_methods:
            env = self.wsgi_env(self.non_api_path, method)
            self.assert_(self.factory.canHandle(env), "Sanity check")
            # Returns a tuple of (request_factory, publication_factory).
            rfactory, pfactory = self.factory.checkRequest(env)
            self.assert_(rfactory is not None,
                "The '%s' HTTP method should be rejected by the factory."
                % method)

    def test_factory_understands_webservice_paths(self):
        """The factory should know if a path is directed at a web service
        resource path.
        """
        # This is a sanity check, so I can write '/api/foo' instead
        # of PATH_OVERRIDE + '/foo' in my tests.  The former's
        # intention is clearer.
        self.assertEqual(
            getUtility(IWebServiceConfiguration).path_override, 'api',
            "Sanity check: The web service path override should be 'api'.")

        self.assert_(
            self.factory.isWebServicePath('/api'),
            "The factory should handle URLs that start with /api.")

        self.assert_(
            self.factory.isWebServicePath('/api/foo'),
            "The factory should handle URLs that start with /api.")

        self.failIf(
            self.factory.isWebServicePath('/foo'),
            "The factory should not handle URLs that do not start with "
            "/api.")

        self.failIf(
            self.factory.isWebServicePath('/'),
            "The factory should not handle URLs that do not start with "
            "/api.")

        self.failIf(
            self.factory.isWebServicePath('/apifoo'),
            "The factory should not handle URLs that do not start with "
            "/api.")

        self.failIf(
            self.factory.isWebServicePath('/foo/api'),
            "The factory should not handle URLs that do not start with "
            "/api.")


class TestWebServiceRequestTraversal(WebServiceTestCase):

    testmodule_objects = [IGenericEntry, IGenericCollection]

    def setUp(self):
        super(TestWebServiceRequestTraversal, self).setUp()

        # For this test we need to make the URL "/foo" resolve to a
        # resource.  To this end, we'll define a top-level collection
        # named 'foo'.
        class GenericCollection:
            implements(IGenericCollection)

        class MyRootResource(RootResource):

            def _build_top_level_objects(self):
                return ({'foo': (IGenericEntry, GenericCollection())}, {})

        getGlobalSiteManager().registerUtility(
            MyRootResource(), IServiceRootResource)

    def test_traversal_of_api_path_urls(self):
        """Requests that have /api at the root of their path should trim
        the 'api' name from the traversal stack.
        """
        # First, we need to forge a request to the API.
        data = ''
        config = getUtility(IWebServiceConfiguration)
        api_url = ('/' + config.path_override +
                   '/' + '1.0' + '/' + 'foo')
        env = {'PATH_INFO': api_url}
        request = config.createRequest(data, env)

        stack = request.getTraversalStack()
        self.assert_(config.path_override in stack,
            "Sanity check: the API path should show up in the request's "
            "traversal stack: %r" % stack)

        request.traverse(None)

        stack = request.getTraversalStack()
        self.failIf(config.path_override in stack,
            "Web service paths should be dropped from the webservice "
            "request traversal stack: %r" % stack)


class TestWebServiceRequest(WebServiceTestCase):

    def test_application_url(self):
        """Requests to the /api path should return the original request's
        host, not api.launchpad.net.
        """
        # Simulate a request to bugs.launchpad.net/api
        server_url = 'http://bugs.launchpad.dev'
        env = {
            'PATH_INFO': '/api/devel',
            'SERVER_URL': server_url,
            'HTTP_HOST': 'bugs.launchpad.dev',
            }

        # WebServiceTestRequest will suffice, as it too should conform to
        # the Same Origin web browser policy.
        request = WebServiceTestRequest(environ=env, version="1.0")
        self.assertEqual(request.getApplicationURL(), server_url)

    def test_response_should_vary_based_on_content_type(self):
        request = WebServiceClientRequest(StringIO.StringIO(''), {})
        self.assertEquals(
            request.response.getHeader('Vary'), 'Accept')


class TestBasicLaunchpadRequest(TestCase):
    """Tests for the base request class"""

    layer = FunctionalLayer

    def test_baserequest_response_should_vary(self):
        """Test that our base response has a proper vary header."""
        request = LaunchpadBrowserRequest(StringIO.StringIO(''), {})
        self.assertEquals(
            request.response.getHeader('Vary'), 'Cookie, Authorization')

    def test_baserequest_response_should_vary_after_retry(self):
        """Test that our base response has a proper vary header."""
        request = LaunchpadBrowserRequest(StringIO.StringIO(''), {})
        retried_request = request.retry()
        self.assertEquals(
            retried_request.response.getHeader('Vary'),
            'Cookie, Authorization')

    def test_baserequest_security_headers(self):
        response = LaunchpadBrowserRequest(StringIO.StringIO(''), {}).response
        self.assertEquals(
            response.getHeader('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEquals(
            response.getHeader('X-Content-Type-Options'), 'nosniff')
        self.assertEquals(
            response.getHeader('X-XSS-Protection'), '1; mode=block')
        self.assertEquals(
            response.getHeader(
                'Strict-Transport-Security'), 'max-age=2592000')

    def test_baserequest_recovers_from_bad_path_info_encoding(self):
        # The request object recodes PATH_INFO to ensure sane_environment
        # does not raise a UnicodeDecodeError when LaunchpadBrowserRequest
        # is instantiated.
        bad_path = 'fnord/trunk\xE4'
        env = {'PATH_INFO': bad_path}
        request = LaunchpadBrowserRequest(StringIO.StringIO(''), env)
        self.assertEquals(u'fnord/trunk\ufffd', request.getHeader('PATH_INFO'))

    def test_request_with_invalid_query_string_recovers(self):
        # When the query string has invalid utf-8, it is decoded with
        # replacement.
        env = {'QUERY_STRING': 'field.title=subproc\xe9s '}
        request = LaunchpadBrowserRequest(StringIO.StringIO(''), env)
        # XXX: Python 2.6 and 2.7 handle unicode replacement differently.
        self.assertIn(
            request.query_string_params['field.title'],
            ([u'subproc\ufffd'], [u'subproc\ufffds ']))


class TestFeedsBrowserRequest(TestCase):
    """Tests for `FeedsBrowserRequest`."""

    def test_not_strict_transport_security(self):
        # Feeds are served over HTTP, so no Strict-Transport-Security
        # header is sent.
        response = FeedsBrowserRequest(StringIO.StringIO(''), {}).response
        self.assertIs(None, response.getHeader('Strict-Transport-Security'))


class TestPrivateXMLRPCRequest(TestCase):
    """Tests for `PrivateXMLRPCRequest`."""

    def test_not_strict_transport_security(self):
        # Private XML-RPC is served over HTTP, so no Strict-Transport-Security
        # header is sent.
        response = PrivateXMLRPCRequest(StringIO.StringIO(''), {}).response
        self.assertIs(None, response.getHeader('Strict-Transport-Security'))


class TestLaunchpadBrowserRequestMixin:
    """Tests for `LaunchpadBrowserRequestMixin`.

    As `LaunchpadBrowserRequestMixin` is a mixin, it needs to be tested when
    mixed into another class, hence why this does not inherit from `TestCase`.
    """

    request_factory = None  # Specify in subclasses.

    def test_is_ajax_false(self):
        """Normal requests do not define HTTP_X_REQUESTED_WITH."""
        request = self.request_factory(StringIO.StringIO(''), {})

        self.assertFalse(request.is_ajax)

    def test_is_ajax_true(self):
        """Requests with HTTP_X_REQUESTED_WITH set are ajax requests."""
        request = self.request_factory(StringIO.StringIO(''), {
            'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
            })

        self.assertTrue(request.is_ajax)

    def test_getURL(self):
        """
        getURL() overrides HTTPRequest.getURL(), but behaves identically by
        default.
        """
        environ = {
            "SERVER_URL": "http://geturl.example.com",
            "SCRIPT_NAME": "/sabbra/cadabra",
            "QUERY_STRING": "tuesday=gone",
            }
        request = self.request_factory(StringIO.StringIO(''), environ)
        self.assertEqual(
            "http://geturl.example.com/sabbra/cadabra",
            request.getURL())
        self.assertEqual(
            "http://geturl.example.com/sabbra",
            request.getURL(level=1))
        self.assertEqual(
            "/sabbra/cadabra",
            request.getURL(path_only=True))

    def test_getURL_include_query(self):
        """
        getURL() overrides HTTPRequest.getURL(), but appends the query string
        if include_query=True.
        """
        environ = {
            "SERVER_URL": "http://geturl.example.com",
            "SCRIPT_NAME": "/sabbra/cadabra",
            "QUERY_STRING": "tuesday=gone",
            }
        request = self.request_factory(StringIO.StringIO(''), environ)
        self.assertEqual(
            "http://geturl.example.com/sabbra/cadabra?tuesday=gone",
            request.getURL(include_query=True))
        self.assertEqual(
            "http://geturl.example.com/sabbra?tuesday=gone",
            request.getURL(include_query=True, level=1))
        self.assertEqual(
            "/sabbra/cadabra?tuesday=gone",
            request.getURL(include_query=True, path_only=True))


class TestLaunchpadBrowserRequestMixinWithLaunchpadBrowserRequest(
    TestLaunchpadBrowserRequestMixin, TestCase):
    """
    Tests for `LaunchpadBrowserRequestMixin` as found in
    `LaunchpadBrowserRequest`.
    """
    request_factory = LaunchpadBrowserRequest


class TestLaunchpadBrowserRequestMixinWithLaunchpadTestRequest(
    TestLaunchpadBrowserRequestMixin, TestCase):
    """
    Tests for `LaunchpadBrowserRequestMixin` as found in
    `LaunchpadTestRequest`.
    """
    request_factory = LaunchpadTestRequest


class IThingSet(Interface):
    """Marker interface for a set of things."""


class IThing(Interface):
    """Marker interface for a thing."""


class Thing:
    implements(IThing)


class ThingSet:
    implements(IThingSet)


class TestLaunchpadBrowserRequest_getNearest(TestCase):

    def setUp(self):
        super(TestLaunchpadBrowserRequest_getNearest, self).setUp()
        self.request = LaunchpadBrowserRequest('', {})
        self.thing_set = ThingSet()
        self.thing = Thing()

    def test_return_value(self):
        # .getNearest() returns a two-tuple with the object and the interface
        # that matched. The second item in the tuple is useful when multiple
        # interfaces are passed to getNearest().
        request = self.request
        request.traversed_objects.extend([self.thing_set, self.thing])
        self.assertEquals(request.getNearest(IThing), (self.thing, IThing))
        self.assertEquals(
            request.getNearest(IThingSet), (self.thing_set, IThingSet))

    def test_multiple_traversed_objects_with_common_interface(self):
        # If more than one object of a particular interface type has been
        # traversed, the most recently traversed one is returned.
        thing2 = Thing()
        self.request.traversed_objects.extend(
            [self.thing_set, self.thing, thing2])
        self.assertEquals(self.request.getNearest(IThing), (thing2, IThing))

    def test_interface_not_traversed(self):
        # If a particular interface has not been traversed, the tuple
        # (None, None) is returned.
        self.request.traversed_objects.extend([self.thing_set])
        self.assertEquals(self.request.getNearest(IThing), (None, None))


class TestLaunchpadBrowserRequest(TestCase):

    def prepareRequest(self, form):
        """Return a `LaunchpadBrowserRequest` with the given form.

        Also set the accepted charset to 'utf-8'.
        """
        request = LaunchpadBrowserRequest('', form)
        request.charsets = ['utf-8']
        return request

    def test_query_string_params_on_get(self):
        """query_string_params is populated from the QUERY_STRING during
        GET requests."""
        request = self.prepareRequest({'QUERY_STRING': "a=1&b=2&c=3"})
        self.assertEqual(
            {'a': ['1'], 'b': ['2'], 'c': ['3']},
            request.query_string_params,
            "The query_string_params dict is populated from the "
            "QUERY_STRING during GET requests.")

    def test_query_string_params_on_post(self):
        """query_string_params is populated from the QUERY_STRING during
        POST requests."""
        request = self.prepareRequest(
            {'QUERY_STRING': "a=1&b=2&c=3", 'REQUEST_METHOD': 'POST'})
        self.assertEqual(request.method, 'POST')
        self.assertEqual(
            {'a': ['1'], 'b': ['2'], 'c': ['3']},
            request.query_string_params,
            "The query_string_params dict is populated from the "
            "QUERY_STRING during POST requests.")

    def test_query_string_params_empty(self):
        """The query_string_params dict is always empty when QUERY_STRING
        is empty, None or undefined.
        """
        request = self.prepareRequest({'QUERY_STRING': ''})
        self.assertEqual({}, request.query_string_params)
        request = self.prepareRequest({'QUERY_STRING': None})
        self.assertEqual({}, request.query_string_params)
        request = self.prepareRequest({})
        self.assertEqual({}, request.query_string_params)

    def test_query_string_params_multi_value(self):
        """The query_string_params dict can include multiple values
        for a parameter."""
        request = self.prepareRequest({'QUERY_STRING': "a=1&a=2&b=3"})
        self.assertEqual(
            {'a': ['1', '2'], 'b': ['3']},
            request.query_string_params,
            "The query_string_params dict correctly interprets multiple "
            "values for the same key in a query string.")

    def test_query_string_params_unicode(self):
        # Encoded query string parameters are properly decoded.
        request = self.prepareRequest({'QUERY_STRING': "a=%C3%A7"})
        self.assertEqual(
            {'a': [u'\xe7']},
            request.query_string_params,
            "The query_string_params dict correctly interprets encoded "
            "parameters.")


class TestWebServiceRequestToBrowserRequest(WebServiceTestCase):

    def test_unicode_path_info(self):
        web_service_request = WebServiceTestRequest(
            PATH_INFO=u'/api/devel\u1234'.encode('utf-8'))
        browser_request = web_service_request_to_browser_request(
            web_service_request)
        self.assertEqual(
            web_service_request.get('PATH_INFO'),
            browser_request.get('PATH_INFO'))


class LoggingTransaction:

    def __init__(self):
        self.log = []

    def commit(self):
        self.log.append("COMMIT")

    def abort(self):
        self.log.append("ABORT")


class TestFinishReadOnlyRequest(TestCase):
    # Publications that have a finishReadOnlyRequest() method are obliged to
    # fire an IFinishReadOnlyRequestEvent.

    def _test_publication(self, publication, expected_transaction_log):
        # publication.finishReadOnlyRequest() issues an
        # IFinishReadOnlyRequestEvent and alters the transaction.
        fake_request = object()
        fake_object = object()
        fake_transaction = LoggingTransaction()

        with EventRecorder() as event_recorder:
            publication.finishReadOnlyRequest(
                fake_request, fake_object, fake_transaction)

        self.assertEqual(
            expected_transaction_log,
            fake_transaction.log)

        finish_events = [
            event for event in event_recorder.events
            if IFinishReadOnlyRequestEvent.providedBy(event)]
        self.assertEqual(
            1, len(finish_events), (
                "Expected only one IFinishReadOnlyRequestEvent, but "
                "got: %r" % finish_events))

        [finish_event] = finish_events
        self.assertIs(fake_request, finish_event.request)
        self.assertIs(fake_object, finish_event.object)

    def test_WebServicePub_fires_FinishReadOnlyRequestEvent(self):
        # WebServicePublication.finishReadOnlyRequest() issues an
        # IFinishReadOnlyRequestEvent and commits the transaction.
        publication = WebServicePublication(None)
        self._test_publication(publication, ["COMMIT"])

    def test_LaunchpadBrowserPub_fires_FinishReadOnlyRequestEvent(self):
        # LaunchpadBrowserPublication.finishReadOnlyRequest() issues an
        # IFinishReadOnlyRequestEvent and aborts the transaction.
        publication = LaunchpadBrowserPublication(None)
        self._test_publication(publication, ["ABORT"])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(DocTestSuite(
        'lp.services.webapp.servers',
        optionflags=NORMALIZE_WHITESPACE | ELLIPSIS))
    suite.addTest(unittest.TestLoader().loadTestsFromName(__name__))
    return suite
