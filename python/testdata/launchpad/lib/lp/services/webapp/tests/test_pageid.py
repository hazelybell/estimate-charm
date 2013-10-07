# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test page ID generation."""

__metaclass__ = type


from lazr.restful.interfaces import ICollectionResource
from zope.interface import implements

from lp.services.webapp.publication import LaunchpadBrowserPublication
from lp.services.webapp.servers import WebServicePublication
from lp.testing import TestCase


class FakeContext:
    """A context object that doesn't do anything."""


class FakeRequest:
    """A request that has just enough request-ness for page ID generation."""

    def __init__(self):
        self.query_string_params = {}
        self.form_values = {}

    def get(self, key):
        return self.form_values.get(key)


class FakeView:
    """A view object that just has a fake context and request."""

    def __init__(self):
        self.context = FakeContext()
        self.request = FakeRequest()

    def __call__(self):
        return 'result'


class FakeCollectionResourceView(FakeView):
    """A view object that provides ICollectionResource."""
    implements(ICollectionResource)

    def __init__(self):
        super(FakeCollectionResourceView, self).__init__()
        self.type_url = (
            u'https://launchpad.dev/api/devel/#milestone-page-resource')


class LaunchpadBrowserPublicationPageIDTestCase(TestCase):
    """Ensure that the web service enhances the page ID correctly."""

    def setUp(self):
        super(LaunchpadBrowserPublicationPageIDTestCase, self).setUp()
        self.publication = LaunchpadBrowserPublication(db=None)
        self.view = FakeView()
        self.context = FakeContext()

    def test_pageid_without_context(self):
        # The pageid is an empty string if there is no context.
        self.assertEqual('', self.publication.constructPageID(self.view, None))

    def test_pageid_view_without_name(self):
        # The view. __class__.__name__ is used if the view does not have a
        # __name__ attribute.
        self.assertEqual(
            'FakeContext:FakeView',
            self.publication.constructPageID(self.view, self.context))

    def test_pageid_view_with_name(self):
        # The view.__name__ is used when it exists.
        self.view.__name__ = '+snarf'
        self.assertEqual(
            'FakeContext:+snarf',
            self.publication.constructPageID(self.view, self.context))

    def test_pageid_context_is_view_from_template(self):
        # When the context is a dynamic view class of a page template,
        # such as adapting a form view to ++model++, the method recurses
        # the views to locate the true context.
        class FakeView2(FakeView):
            pass

        class FakeViewView(FakeView):
            __name__ = '++model++'

            def __init__(self):
                self.request = FakeRequest()
                self.context = FakeView2()

        self.view = FakeViewView()
        self.context = self.view.context
        self.context.__name__ = '+bugs'
        self.context.__class__.__name__ = 'SimpleViewClass from template.pt'
        self.assertEqual(
            'FakeContext:+bugs:++model++',
            self.publication.constructPageID(self.view, self.context))


class TestWebServicePageIDs(TestCase):
    """Ensure that the web service enhances the page ID correctly."""

    def setUp(self):
        super(TestWebServicePageIDs, self).setUp()
        self.publication = WebServicePublication(db=None)
        self.view = FakeView()
        self.context = FakeContext()

    def makePageID(self):
        return self.publication.constructPageID(self.view, self.context)

    def test_pageid_without_op(self):
        # When the HTTP request does not have a named operation (ws.op) field
        # (either in the body or query string), the operation is included in
        # the page ID.
        self.assertEqual(
            self.makePageID(), 'FakeContext:FakeView')

    def test_pageid_without_op_in_form(self):
        # When the HTTP request does not have a named operation (ws.op) field
        # (either in the body or query string), the operation is included in
        # the page ID.
        self.view.request.form_values['ws.op'] = 'operation-name-1'
        self.assertEqual(
            self.makePageID(), 'FakeContext:FakeView:operation-name-1')

    def test_pageid_without_op_in_query_string(self):
        # When the HTTP request does not have a named operation (ws.op) field
        # (either in the body or query string), the operation is included in
        # the page ID.
        self.view.request.query_string_params['ws.op'] = 'operation-name-2'
        self.assertEqual(
            self.makePageID(), 'FakeContext:FakeView:operation-name-2')


class TestCollectionResourcePageIDs(TestCase):
    """Ensure page ids for collections display the origin page resource."""

    def setUp(self):
        super(TestCollectionResourcePageIDs, self).setUp()
        self.publication = WebServicePublication(db=None)
        self.view = FakeCollectionResourceView()
        self.context = FakeContext()

    def makePageID(self):
        return self.publication.constructPageID(self.view, self.context)

    def test_origin_pageid_for_collection(self):
        # When the view provides a ICollectionResource, make sure the origin
        # page resource is included in the page ID.
        self.assertEqual(
            self.makePageID(),
            'FakeContext:FakeCollectionResourceView:#milestone-page-resource')


class TestPageIdCorners(TestCase):
    """Ensure that the page ID generation handles corner cases well."""

    def setUp(self):
        super(TestPageIdCorners, self).setUp()
        self.publication = WebServicePublication(db=None)
        self.view = FakeView()
        self.context = FakeContext()

    def makePageID(self):
        return self.publication.constructPageID(self.view, self.context)

    def test_pageid_with_multiple_op_fields(self):
        # The publisher will combine multiple form values with the same name
        # into a list.  If those values are for "ws.op", the page ID mechanism
        # should just ignore the op altogether.  (It used to generate an
        # error, see bug 810113).
        self.view.request.form_values['ws.op'] = ['one', 'another']
        self.assertEqual(self.makePageID(), 'FakeContext:FakeView')
