# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the lp.testing.yuixhr."""

__metaclass__ = type


import os
import re
from shutil import rmtree
import sys
import tempfile
import types

import simplejson
from storm.exceptions import DisconnectionError
from testtools.testcase import ExpectedException
import transaction
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.publisher.interfaces import NotFound
from zope.publisher.interfaces.browser import IBrowserPublisher
from zope.publisher.interfaces.http import IResult
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.osutils import override_environ
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.testing import (
    ANONYMOUS,
    login,
    TestCase,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.matchers import Contains
from lp.testing.publication import test_traverse
from lp.testing.tests import test_yuixhr_fixture
from lp.testing.views import create_view
from lp.testing.yuixhr import setup


TEST_MODULE_NAME = '_lp_.tests'


def create_traversed_view(*args, **kwargs):
    login(ANONYMOUS)
    root = getUtility(ILaunchpadRoot)
    view = create_view(root, '+yuitest', *args, **kwargs)
    view.names = kwargs['path_info'].split('/')[2:]
    return view


class TestYUITestFixtureController(TestCase):
    layer = LaunchpadFunctionalLayer

    def test_provides_browserpublisher(self):
        root = getUtility(ILaunchpadRoot)
        view = create_view(root, '+yuitest')
        self.assertTrue(view, verifyObject(IBrowserPublisher, view))

    def test_traverse_stores_the_path(self):
        login(ANONYMOUS)
        object, view, request = test_traverse(
            'http://launchpad.dev/+yuitest/'
            'lib/lp/testing/tests/test_yuixhr_fixture.js')
        self.assertEquals(
            'lib/lp/testing/tests/test_yuixhr_fixture.js',
            removeSecurityProxy(view).traversed_path)

    def test_request_is_js(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/test_yuixhr_fixture.js')
        view.initialize()
        self.assertEquals(view.JAVASCRIPT, view.action)

    def test_request_is_html(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/test_yuixhr_fixture')
        view.initialize()
        self.assertEquals(view.HTML, view.action)

    def test_request_is_setup(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'base_line'},
            method='POST')
        view.initialize()
        self.assertEquals(view.SETUP, view.action)
        self.assertEquals(['base_line'], view.fixtures)

    def test_request_is_teardown(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/test_yuixhr_fixture',
            form={'action': 'teardown', 'fixtures': 'base_line'},
            method='POST')
        view.initialize()
        self.assertEquals(view.TEARDOWN, view.action)
        self.assertEquals(['base_line'], view.fixtures)

    def test_page(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/test_yuixhr_fixture')
        view.initialize()
        content = view.renderHTML()
        self.assertTrue(content.startswith('<!DOCTYPE html>'))
        self.assertTextMatchesExpressionIgnoreWhitespace(
            re.escape(
                'src="/+yuitest/lp/testing/tests/test_yuixhr_fixture.js"'),
            content)

    def test_render_javascript(self):
        top_dir = tempfile.mkdtemp()
        js_dir = os.path.join(top_dir, 'lib')
        os.mkdir(js_dir)
        true_root = config.root
        self.addCleanup(setattr, config, 'root', true_root)
        self.addCleanup(rmtree, top_dir)
        open(os.path.join(js_dir, 'foo.py'), 'w').close()
        js_file = open(os.path.join(js_dir, 'foo.js'), 'w')
        js_file.write('// javascript')
        js_file.close()
        config.root = top_dir
        view = create_traversed_view(path_info='/+yuitest/foo.js')
        content = view()
        self.assertEqual('// javascript', content.read())
        self.assertEqual(
            'text/javascript',
            view.request.response.getHeader('Content-Type'))
        self.assertEqual(
            'no-cache',
            view.request.response.getHeader('Cache-Control'))

    def test_javascript_must_have_a_py_fixture(self):
        js_dir = tempfile.mkdtemp()
        true_root = config.root
        self.addCleanup(setattr, config, 'root', true_root)
        self.addCleanup(rmtree, js_dir)
        open(os.path.join(js_dir, 'foo.js'), 'w').close()
        config.root = js_dir
        view = create_traversed_view(path_info='/+yuitest/foo.js')
        with ExpectedException(NotFound, '.*'):
            view()

    def test_missing_javascript_raises_NotFound(self):
        js_dir = tempfile.mkdtemp()
        true_root = config.root
        self.addCleanup(setattr, config, 'root', true_root)
        self.addCleanup(rmtree, js_dir)
        open(os.path.join(js_dir, 'foo.py'), 'w').close()
        config.root = js_dir
        view = create_traversed_view(path_info='/+yuitest/foo')
        with ExpectedException(NotFound, '.*'):
            view()

    def test_render_html(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/test_yuixhr_fixture')
        content = view()
        self.assertTrue(content.startswith('<!DOCTYPE html>'))
        self.assertEqual(
            'text/html',
            view.request.response.getHeader('Content-Type'))
        self.assertEqual(
            'no-cache',
            view.request.response.getHeader('Cache-Control'))

    def test_get_fixtures(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'baseline'},
            method='POST')
        view.initialize()
        self.assertEquals(
            test_yuixhr_fixture._fixtures_, view.get_fixtures())

    def make_example_setup_function_module(self):
        module = types.ModuleType(TEST_MODULE_NAME)
        sys.modules[TEST_MODULE_NAME] = module
        self.addCleanup(lambda: sys.modules.pop(TEST_MODULE_NAME))

        def baseline(request, data):
            data['hi'] = 'world'
            data['called'] = ['baseline']
        baseline.__module__ = TEST_MODULE_NAME
        module.baseline = baseline
        return module

    def test_setup_decorator(self):
        module = self.make_example_setup_function_module()
        fixture = setup(module.baseline)
        self.assertTrue('_fixtures_' in module.__dict__)
        self.assertTrue('baseline' in module._fixtures_)
        self.assertEquals(fixture, module._fixtures_['baseline'])
        self.assertTrue(getattr(fixture, 'add_cleanup', None) is not None)
        self.assertTrue(getattr(fixture, 'teardown', None) is not None)
        self.assertTrue(getattr(fixture, 'extend', None) is not None)

    def test_do_setup(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'baseline'},
            method='POST')
        content = view()
        self.assertEqual({'hello': 'world'}, simplejson.loads(content))
        self.assertEqual(
            'application/json',
            view.request.response.getHeader('Content-Type'))

    def test_do_setup_data_returns_object_summaries(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'make_product'},
            method='POST')
        data = simplejson.loads(view())
        # The licenses is just an example.
        self.assertEqual(['GNU GPL v2'], data['product']['licenses'])

    def test_do_setup_data_object_summaries_are_redacted_if_necessary(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'make_product'},
            method='POST')
        data = simplejson.loads(view())
        self.assertEqual(
            'tag:launchpad.net:2008:redacted',
            data['product']['project_reviewed'])

    def test_do_setup_unproxied_data_object_summaries_are_redacted(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'naughty_make_product'},
            method='POST')
        data = simplejson.loads(view())
        self.assertEqual(
            'tag:launchpad.net:2008:redacted',
            data['product']['project_reviewed'])

    def test_do_setup_data_object_summaries_not_redacted_if_possible(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'make_product_loggedin'},
            method='POST')
        data = simplejson.loads(view())
        self.assertEqual(
            False,
            data['product']['project_reviewed'])

    def test_add_cleanup_decorator(self):
        fixture = setup(self.make_example_setup_function_module().baseline)
        result = []

        def my_teardown(request, data):
            result.append('foo')
        self.assertEquals(fixture, fixture.add_cleanup(my_teardown))
        fixture.teardown(None, None)
        self.assertEquals(['foo'], result)

    def test_add_cleanup_decorator_twice(self):
        fixture = setup(self.make_example_setup_function_module().baseline)
        result = []

        def my_teardown(request, data):
            result.append('foo')

        def my_other_teardown(request, data):
            result.append('bar')
        self.assertEquals(fixture, fixture.add_cleanup(my_teardown))
        self.assertEquals(fixture, fixture.add_cleanup(my_other_teardown))
        fixture.teardown(None, None)
        self.assertEquals(['bar', 'foo'], result)

    def test_do_teardown(self):
        del test_yuixhr_fixture._received[:]
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'teardown', 'fixtures': 'baseline',
                  'data': simplejson.dumps({'bonjour': 'monde'})},
            method='POST')
        view.request.response.setResult(view())
        # The teardowns are called *before* the result is iterated.
        self.assertEqual(1, len(test_yuixhr_fixture._received))
        self.assertEqual(
            ('baseline', view.request, {'bonjour': 'monde'}),
            test_yuixhr_fixture._received[0])
        result = view.request.response.consumeBodyIter()
        self.assertProvides(result, IResult)
        self.assertEqual('\n', ''.join(result))
        self.assertEqual(
            '1',
            view.request.response.getHeader('Content-Length'))
        del test_yuixhr_fixture._received[:]  # Cleanup

    def test_do_teardown_resets_database_only_after_request_completes(self):
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'setup', 'fixtures': 'make_product'},
            method='POST')
        data = view()
        # Committing the transaction makes sure that we are not just seeing
        # the effect of an abort, below.
        transaction.commit()
        name = simplejson.loads(data)['product']['name']
        products = getUtility(IProductSet)
        # The new product exists after the setup.
        self.assertFalse(products.getByName(name) is None)
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'teardown', 'fixtures': 'make_product',
                  'data': data},
            method='POST')
        view.request.response.setResult(view())
        # The product still exists after the teardown has been called.
        self.assertFalse(products.getByName(name) is None)
        # Iterating over the result causes the database to be reset.
        ''.join(view.request.response.consumeBodyIter())
        # The database is disconnected now.
        self.assertRaises(
            DisconnectionError,
            products.getByName, name)
        # If we abort the transaction...
        transaction.abort()
        # ...we see that the product is gone: the database has been reset.
        self.assertTrue(products.getByName(name) is None)

    def test_do_teardown_multiple(self):
        # Teardown should call fixtures in reverse order.
        del test_yuixhr_fixture._received[:]
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture',
            form={'action': 'teardown', 'fixtures': 'baseline,second',
                  'data': simplejson.dumps({'bonjour': 'monde'})},
            method='POST')
        view()
        self.assertEqual(
            'second', test_yuixhr_fixture._received[0][0])
        self.assertEqual(
            'baseline', test_yuixhr_fixture._received[1][0])
        del test_yuixhr_fixture._received[:]

    def test_extend_decorator_setup(self):
        module = self.make_example_setup_function_module()
        original_fixture = setup(module.baseline)
        second_fixture = self.make_extend_fixture(
            original_fixture, 'second')
        data = {}
        second_fixture(None, data)
        self.assertEqual(['baseline', 'second'], data['called'])
        data = {}
        original_fixture(None, data)
        self.assertEqual(['baseline'], data['called'])

    def test_extend_decorator_can_be_composed(self):
        module = self.make_example_setup_function_module()
        original_fixture = setup(module.baseline)
        second_fixture = self.make_extend_fixture(
            original_fixture, 'second')
        third_fixture = self.make_extend_fixture(
            second_fixture, 'third')
        data = {}
        third_fixture(None, data)
        self.assertEqual(['baseline', 'second', 'third'], data['called'])

    def make_extend_fixture(self, original_fixture, name):
        f = lambda request, data: data['called'].append(name)
        f.__module__ == TEST_MODULE_NAME
        return original_fixture.extend(f)

    def test_extend_calls_teardown_in_reverse_order(self):
        module = self.make_example_setup_function_module()
        original_fixture = setup(module.baseline)
        second_fixture = self.make_extend_fixture(
            original_fixture, 'second')
        third_fixture = self.make_extend_fixture(
            second_fixture, 'third')
        called = []
        original_fixture.add_cleanup(
            lambda request, data: called.append('original'))
        second_fixture.add_cleanup(
            lambda request, data: called.append('second'))
        third_fixture.add_cleanup(
            lambda request, data: called.append('third'))
        third_fixture.teardown(None, dict())
        self.assertEquals(['third', 'second', 'original'], called)

        del called[:]
        original_fixture.teardown(None, dict())
        self.assertEquals(['original'], called)

    def test_python_fixture_does_not_reload_by_default(self):
        # Even though the dangers of Python's "reload" are subtle and
        # real, using it can be very nice, particularly with
        # Launchpad's slow start-up time.  By default, though, it is
        # not used.  We will show this by scribbling on one of the
        # fixtures and showing that the scribble is still there when
        # we load the page.
        test_yuixhr_fixture._fixtures_['baseline'].scribble = 'hello'
        self.addCleanup(
            delattr, test_yuixhr_fixture._fixtures_['baseline'], 'scribble')
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture')
        view.initialize()
        view.render()
        self.assertEquals(
            'hello', test_yuixhr_fixture._fixtures_['baseline'].scribble)

    def test_python_fixture_does_not_reload_without_environ_var(self):
        # As a bit of extra paranoia, we only allow a reload if
        # 'INTERACTIVE_TESTS' is in the environ.  make run-testapp
        # sets this environmental variable.  However, if we don't set
        # the environment, even if we request a reload it will not
        # happen.
        test_yuixhr_fixture._fixtures_['baseline'].scribble = 'hello'
        self.addCleanup(
            delattr, test_yuixhr_fixture._fixtures_['baseline'], 'scribble')
        view = create_traversed_view(
            path_info='/+yuitest/lp/testing/tests/'
                      'test_yuixhr_fixture', form=dict(reload='1'))
        view.initialize()
        view.render()
        self.assertEquals(
            'hello', test_yuixhr_fixture._fixtures_['baseline'].scribble)

    def test_python_fixture_can_reload(self):
        # Now we will turn reloading fully on, with the environmental
        # variable and the query string..
        test_yuixhr_fixture._fixtures_['baseline'].scribble = 'hello'
        with override_environ(INTERACTIVE_TESTS='1'):
            view = create_traversed_view(
                path_info='/+yuitest/lp/testing/tests/'
                'test_yuixhr_fixture', form=dict(reload='1'))
            # reloading only happens at render time, so the scribble is
            # still there for now.
            view.initialize()
            self.assertEquals(
                'hello', test_yuixhr_fixture._fixtures_['baseline'].scribble)
            # After a render of the html view, the module is reloaded.
            view.render()
            self.assertEquals(
                None,
                getattr(test_yuixhr_fixture._fixtures_['baseline'],
                        'scribble',
                        None))

    def test_python_fixture_resets_fixtures(self):
        # When we reload, we also clear out _fixtures_.  This means
        # that if you rename or delete something, it won't be hanging
        # around confusing you into thinking everything is fine after
        # the reload.
        test_yuixhr_fixture._fixtures_['extra_scribble'] = 42
        with override_environ(INTERACTIVE_TESTS='1'):
            view = create_traversed_view(
                path_info='/+yuitest/lp/testing/tests/'
                'test_yuixhr_fixture', form=dict(reload='1'))
            view.initialize()
            # After a render of the html view, the module is reloaded.
            view.render()
            self.assertEquals(
                None,
                test_yuixhr_fixture._fixtures_.get('extra_scribble'))

    def test_python_fixture_reload_in_html(self):
        # The reload is specifically when we load HTML pages only.
        test_yuixhr_fixture._fixtures_['extra_scribble'] = 42
        with override_environ(INTERACTIVE_TESTS='1'):
            view = create_traversed_view(
                path_info='/+yuitest/lp/testing/tests/'
                'test_yuixhr_fixture', form=dict(reload='1'))
            view.initialize()
            # After a render of the html view, the module is reloaded.
            view.renderHTML()
            self.assertEquals(
                None,
                test_yuixhr_fixture._fixtures_.get('extra_scribble'))

    def test_index_page(self):
        view = create_traversed_view(path_info='/+yuitest')
        view.initialize()
        output = view.render()
        self.assertThat(
            output,
            Contains(
                'href="/+yuitest/lp/testing/tests/test_yuixhr_fixture'))
