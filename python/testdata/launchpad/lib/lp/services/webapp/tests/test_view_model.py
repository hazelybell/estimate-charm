# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the user requested oops using ++oops++ traversal."""

__metaclass__ = type


from lazr.restful.interfaces import IJSONRequestCache
from lazr.restful.utils import get_current_browser_request
from simplejson import loads
from testtools.matchers import KeysEqual
from zope.configuration import xmlconfig

from lp.app.browser.launchpadform import LaunchpadFormView
from lp.services.webapp import LaunchpadView
from lp.services.webapp.namespace import JsonModelNamespaceView
from lp.services.webapp.publisher import canonical_url
import lp.services.webapp.tests
from lp.testing import (
    ANONYMOUS,
    BrowserTestCase,
    login,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class FakeView:
    """A view object that just has a fake context and request."""
    def __init__(self):
        self.context = object()
        self.request = object()


class TestJsonModelNamespace(TestCaseWithFactory):
    """Test that traversal to ++model++ returns a namespace."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        login(ANONYMOUS)

    def tearDown(self):
        logout()
        TestCaseWithFactory.tearDown(self)

    def test_JsonModelNamespace_traverse_non_LPview(self):
        # Test traversal for JSON model namespace,
        # ++model++ for a non-LaunchpadView context.
        request = get_current_browser_request()
        context = object()
        view = FakeView()
        namespace = JsonModelNamespaceView(context, request)
        result = namespace.traverse(view, None)
        self.assertEqual(result, namespace)

    def test_JsonModelNamespace_traverse_LPView(self):
        # Test traversal for JSON model namespace,
        # ++model++ for a non-LaunchpadView context.
        request = get_current_browser_request()
        context = object()
        view = LaunchpadView(context, request)
        namespace = JsonModelNamespaceView(view, request)
        result = namespace.traverse(view, None)
        self.assertEqual(result, namespace)

    def test_JsonModelNamespace_traverse_LPFormView(self):
        # Test traversal for JSON model namespace,
        # ++model++ for a non-LaunchpadView context.
        request = get_current_browser_request()
        context = object()
        view = LaunchpadFormView(context, request)
        namespace = JsonModelNamespaceView(view, request)
        result = namespace.traverse(view, None)
        self.assertEqual(result, namespace)


class BaseProductModelTestView(LaunchpadView):
    def initialize(self):
        # Ensure initialize does not put anything in the cache.
        pass


class TestJsonModelView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        login(ANONYMOUS)
        self.product = self.factory.makeProduct(name="test-product")
        self.url = canonical_url(self.product) + '/+modeltest/++model++'

    def tearDown(self):
        logout()
        TestCaseWithFactory.tearDown(self)

    def configZCML(self):
        # Register the ZCML for our test view.  Note the view class must be
        # registered first.
        xmlconfig.string("""
          <configure
              xmlns:browser="http://namespaces.zope.org/browser">
              <include package="zope.browserpage" file="meta.zcml" />
              <include package="lp.services.webapp" file="meta.zcml" />
              <browser:page
                name="+modeltest"
                for="lp.registry.interfaces.product.IProduct"
                class="lp.services.webapp.tests.ProductModelTestView"
                permission="zope.Public"
                />
          </configure>""")

    def test_JsonModel_default_cache(self):
        # If nothing is added to the class by the view, the cache will only
        # have the context.
        class ProductModelTestView(BaseProductModelTestView):
            pass
        lp.services.webapp.tests.ProductModelTestView = \
            ProductModelTestView
        self.configZCML()
        browser = self.getUserBrowser(self.url)
        cache = loads(browser.contents)
        self.assertEqual(['related_features', 'context'], cache.keys())

    def test_JsonModel_custom_cache(self):
        # Adding an item to the cache in the initialize method results in it
        # being in the cache.
        class ProductModelTestView(BaseProductModelTestView):
            def initialize(self):
                request = get_current_browser_request()
                target_info = {}
                target_info['title'] = "The Title"
                cache = IJSONRequestCache(request).objects
                cache['target_info'] = target_info
        lp.services.webapp.tests.ProductModelTestView = \
            ProductModelTestView
        self.configZCML()
        browser = self.getUserBrowser(self.url)
        cache = loads(browser.contents)
        self.assertThat(
            cache, KeysEqual('related_features', 'context', 'target_info'))

    def test_JsonModel_custom_cache_wrong_method(self):
        # Adding an item to the cache in some other method is not recognized,
        # even if it called as part of normal rendering.
        class ProductModelTestView(BaseProductModelTestView):
            def initialize(self):
                request = get_current_browser_request()
                target_info = {}
                target_info['title'] = "The Title"
                cache = IJSONRequestCache(request).objects
                cache['target_info'] = target_info

            def render(self):
                request = get_current_browser_request()
                other_info = {}
                other_info['spaz'] = "Stuff"
                IJSONRequestCache(request).objects['other_info'] = other_info

        lp.services.webapp.tests.ProductModelTestView = \
            ProductModelTestView
        self.configZCML()
        browser = self.getUserBrowser(self.url)
        cache = loads(browser.contents)
        self.assertThat(
            cache, KeysEqual('related_features', 'context', 'target_info'))
