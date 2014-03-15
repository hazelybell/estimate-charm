# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests post-zcml application initialization.

As found in lp.services.webapp.initialization.py."""

from zope.component import getSiteManager
from zope.interface import Interface
from zope.publisher.interfaces.browser import IBrowserRequest
from zope.traversing.interfaces import ITraversable

from lp.services.webapp.errorlog import OopsNamespace
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer


class AnyObject:
    pass


class TestURLNamespace(TestCase):

    layer = FunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        self.sm = getSiteManager()
        self.context = AnyObject()
        self.request = LaunchpadTestRequest()

    def test_oops_namespace_not_view(self):
        # The ++oops++ namespace should not be available as a "oops" view.
        # First, we will verify that it is available as a namespace.
        namespace = self.sm.getMultiAdapter(
            (self.context, self.request), ITraversable, 'oops')
        self.failUnless(isinstance(namespace, OopsNamespace))
        # However, it is not available as a view.
        not_a_namespace = self.sm.queryMultiAdapter(
            (self.context, self.request), Interface, 'oops')
        self.failIf(isinstance(not_a_namespace, OopsNamespace))

    def test_no_namespaces_are_views(self):
        # This tests an abstract superset of test_oops_namespace_not_view.
        # At the time of writing, namespaces were 'resource', 'oops', 'form',
        # and 'view'.
        namespace_info = self.sm.adapters.lookupAll(
            (Interface, IBrowserRequest), ITraversable)
        for name, factory in namespace_info:
            try:
                not_the_namespace_factory = self.sm.adapters.lookup(
                    (Interface, IBrowserRequest), Interface, name)
            except LookupError:
                pass
            else:
                self.assertNotEqual(factory, not_the_namespace_factory)
