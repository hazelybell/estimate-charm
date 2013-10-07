# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Launchpad's 'view/macro:page' TALES adapter."""

__metaclass__ = type

import os

from zope.interface import implements
from zope.location.interfaces import LocationError
from zope.traversing.interfaces import IPathAdapter

from lp.app.interfaces.launchpad import IPrivacy
from lp.app.security import AuthorizationBase
from lp.testing import (
    FakeAdapterMixin,
    login_person,
    test_tales,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )
from lp.testing.views import create_view


class ITest(IPrivacy):
    """A mechanism for adaption."""


class TestObject:
    implements(ITest)

    def __init__(self):
        self.private = False


class TestView:

    def __init__(self, context, request):
        self.context = context
        self.request = request


class TestPageMacroDispatcherMixin(FakeAdapterMixin):

    def _setUpView(self):
        self.registerBrowserViewAdapter(TestView, ITest, '+index')
        self.view = create_view(TestObject(), name='+index')

    def _call_test_tales(self, path):
        test_tales(path, view=self.view)


class PageMacroDispatcherTestCase(TestPageMacroDispatcherMixin, TestCase):
    """Page macro tests for layouts.


    Templates should start by specifying the kind of pagetype they use.
    <html metal:use-macro="view/macro:page/main_side" />
    """
    layer = FunctionalLayer

    def setUp(self):
        super(PageMacroDispatcherTestCase, self).setUp()
        self._setUpView()

    def test_base_template(self):
        # Requests on the launchpad.dev vhost use the Launchpad base template.
        adapter = self.getAdapter([self.view], IPathAdapter, name='macro')
        template_path = os.path.normpath(adapter.base.filename)
        self.assertIn('lp/app/templates', template_path)
        # The base template defines a 'master' macro as the adapter expects.
        self.assertIn('master', adapter.base.macros.keys())

    def test_page(self):
        # A view can be adpated to a page macro object.
        page_macro = test_tales('view/macro:page/main_side', view=self.view)
        self.assertEqual('main_side', self.view.__pagetype__)
        self.assertEqual(('mode', 'html'), page_macro[1])
        source_file = page_macro[3]
        self.assertEqual('setSourceFile', source_file[0])
        self.assertEqual(
            '/templates/base-layout.pt', source_file[1].split('..')[1])

    def test_page_unknown_type(self):
        # An error is raised of the pagetype is not defined.
        self.assertRaisesWithContent(
            LocationError, "'unknown pagetype: not-defined'",
            self._call_test_tales, 'view/macro:page/not-defined')

    def test_pagetype(self):
        # The pagetype is 'unset', until macro:page is called.
        self.assertIs(None, getattr(self.view, '__pagetype__', None))
        self.assertEqual(
            'unset', test_tales('view/macro:pagetype', view=self.view))
        test_tales('view/macro:page/main_side', view=self.view)
        self.assertEqual('main_side', self.view.__pagetype__)
        self.assertEqual(
            'main_side', test_tales('view/macro:pagetype', view=self.view))

    def test_pagehas(self):
        # After the page type is set, the page macro can be queried
        # for what LayoutElements it supports supports.
        test_tales('view/macro:page/main_side', view=self.view)
        self.assertTrue(
            test_tales('view/macro:pagehas/portlets', view=self.view))

    def test_pagehas_unset_pagetype(self):
        # The page macro type must be set before the page macro can be
        # queried for what LayoutElements it supports.
        self.assertRaisesWithContent(
            KeyError, "'unset'",
            self._call_test_tales, 'view/macro:pagehas/fnord')

    def test_pagehas_unknown_attribute(self):
        # An error is raised if the LayoutElement does not exist.
        test_tales('view/macro:page/main_side', view=self.view)
        self.assertRaisesWithContent(
            KeyError, "'fnord'",
            self._call_test_tales, 'view/macro:pagehas/fnord')

    def test_has_watermark_default(self):
        # All pages have a watermark if the view does not provide the attr.
        has_watermark = test_tales('view/macro:has-watermark', view=self.view)
        self.assertIs(True, has_watermark)

    def test_has_watermark_false(self):
        # A view cand define has_watermark as False.
        class NoWatermarkView(TestView):
            has_watermark = False

        self.registerBrowserViewAdapter(NoWatermarkView, ITest, '+test')
        view = create_view(TestObject(), name='+test')
        has_watermark = test_tales('view/macro:has-watermark', view=view)
        self.assertIs(False, has_watermark)

    def test_has_watermark_true(self):
        # A view cand define has_watermark as True.
        class NoWatermarkView(TestView):
            has_watermark = True

        self.registerBrowserViewAdapter(NoWatermarkView, ITest, '+test')
        view = create_view(TestObject(), name='+test')
        has_watermark = test_tales('view/macro:has-watermark', view=view)
        self.assertIs(True, has_watermark)


class PageMacroDispatcherInteractionTestCase(TestPageMacroDispatcherMixin,
                                             TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(PageMacroDispatcherInteractionTestCase, self).setUp()
        self._setUpView()
        login_person(self.factory.makePerson())

    def _setUpPermissions(self, has_permission=True):
        # Setup a specific permission for the test object.
        class FakeSecurityChecker(AuthorizationBase):
            """A class to instrument a specific permission."""
            @classmethod
            def __call__(adaptee):
                return FakeSecurityChecker(adaptee)

            def __init__(self, adaptee=None):
                super(FakeSecurityChecker, self).__init__(adaptee)

            def checkUnauthenticated(self):
                return has_permission

            def checkAuthenticated(self, user):
                return has_permission

        self.registerAuthorizationAdapter(
            FakeSecurityChecker, ITest, 'launchpad.View')

    def test_is_page_contentless_public(self):
        # Public objects always have content to be shown.
        self.assertFalse(
            test_tales('view/macro:is-page-contentless', view=self.view))

    def test_is_page_contentless_private_with_view(self):
        # Private objects the user can view have content to be shown.
        self.view.context.private = True
        self._setUpPermissions(has_permission=True)
        result = test_tales('view/macro:is-page-contentless', view=self.view)
        self.assertFalse(result)

    def test_is_page_contentless_private_without_view(self):
        # Private objects the view cannot view cannot show content.
        self.view.context.private = True
        self._setUpPermissions(has_permission=False)
        result = test_tales('view/macro:is-page-contentless', view=self.view)
        self.assertTrue(result)
