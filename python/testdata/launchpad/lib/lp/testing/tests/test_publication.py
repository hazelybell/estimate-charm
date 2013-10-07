# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the helpers in `lp.testing.publication`."""

__metaclass__ = type

from lazr.restful import EntryResource
from lazr.restful.utils import get_current_browser_request
from zope.browserpage.simpleviewclass import simple
from zope.component import (
    getSiteManager,
    getUtility,
    )
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope.security.checker import (
    Checker,
    CheckerPublic,
    defineChecker,
    )

from lp.services.webapp.interfaces import (
    ILaunchBag,
    ILaunchpadRoot,
    )
from lp.services.webapp.publisher import (
    Navigation,
    stepthrough,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    ANONYMOUS,
    FakeLaunchpadRequest,
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )
from lp.testing.publication import test_traverse


class TestTestTraverse(TestCaseWithFactory):
    # Tests for `test_traverse`

    layer = DatabaseFunctionalLayer

    def registerViewCallable(self, view_callable):
        """Return a URL traversing to which will call `view_callable`.

        :param view_callable: Will be called with no arguments during
            traversal.
        """
        # This method is completely out of control.  Thanks, Zope.
        name = '+' + self.factory.getUniqueString()

        class new_class(simple):
            def __init__(self, context, request):
                self.context = context
                view_callable()
        required = {}
        for n in ('browserDefault', '__call__', 'publishTraverse'):
            required[n] = CheckerPublic
        defineChecker(new_class, Checker(required))
        getSiteManager().registerAdapter(
            new_class, (ILaunchpadRoot, IDefaultBrowserLayer), Interface,
            name)
        self.addCleanup(
            getSiteManager().unregisterAdapter, new_class,
            (ILaunchpadRoot, IDefaultBrowserLayer), Interface, name)
        return 'https://launchpad.dev/' + name

    def test_traverse_simple(self):
        # test_traverse called with a product URL returns the product
        # as the traversed object.
        login(ANONYMOUS)
        product = self.factory.makeProduct()
        context, view, request = test_traverse(
            'https://launchpad.dev/' + product.name)
        self.assertEqual(product, context)

    def test_request_is_current_during_traversal(self):
        # The request that test_traverse creates is current during
        # traversal in the sense of get_current_browser_request.
        login(ANONYMOUS)
        requests = []

        def record_current_request():
            requests.append(get_current_browser_request())
        context, view, request = test_traverse(
            self.registerViewCallable(record_current_request))
        self.assertEqual(1, len(requests))
        self.assertIs(request, requests[0])

    def test_participation_restored(self):
        # test_traverse restores the interaction (and hence
        # participation) that was present before it was called.
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        product = self.factory.makeProduct()
        test_traverse('https://launchpad.dev/' + product.name)
        self.assertIs(request, get_current_browser_request())

    def test_uses_current_user(self):
        # test_traverse performs the traversal as the currently logged
        # in user.
        person = self.factory.makePerson()
        login_person(person)
        users = []

        def record_user():
            users.append(getUtility(ILaunchBag).user)
        context, view, request = test_traverse(
            self.registerViewCallable(record_user))
        self.assertEqual(1, len(users))
        self.assertEqual(person, users[0])

    def test_webservice_traverse(self):
        login(ANONYMOUS)
        product = self.factory.makeProduct()
        context, view, request = test_traverse(
            'http://api.launchpad.dev/devel/' + product.name)
        self.assertEqual(product, context)
        self.assertIsInstance(view, EntryResource)


class DummyNavigation(Navigation):
    """A simple navigation class to test traversal."""
    def traverse(self, name):
        return name

    @stepthrough('+step')
    def traverse_stepthrough(self, name):
        return 'stepthrough-' + name


class TestStepThrough(TestCaseWithFactory):
    """Test some stepthrough traversal scenarios."""

    layer = FunctionalLayer

    def traverse(self, request, name):
        """Traverse to 'segments' using a 'DummyNavigation' object.

        Using the Zope traversal machinery, traverse to the path given by
        'segments'.
        """
        traverser = DummyNavigation(object(), request)
        return traverser.publishTraverse(request, name)

    def test_normal_stepthrough(self):
        # The stepthrough is processed normally.
        request = FakeLaunchpadRequest(['~dummy'], ['fred'])
        self.assertEqual('stepthrough-fred', self.traverse(request, '+step'))

    def test_ignored_stepthrough(self):
        # The stepthrough is ignored since the next path item is a zope
        # namespace.
        request = FakeLaunchpadRequest(['~dummy'], ['++model++'])
        self.assertEqual('+step', self.traverse(request, '+step'))
        self.assertEqual('++model++', request.stepstogo.peek())
