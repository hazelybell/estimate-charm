# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for Launchpad-specific widgets."""

__metaclass__ = type

import unittest

from lazr.uri import URI
from zope.component import (
    getUtility,
    provideUtility,
    )
from zope.formlib.interfaces import ConversionError
from zope.interface import implements
from zope.schema import Choice

from lp import _
from lp.code.browser.widgets.branch import (
    BranchPopupWidget,
    NoProductError,
    )
from lp.code.enums import BranchType
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.vocabularies.branch import (
    BranchRestrictedOnProductVocabulary,
    BranchVocabulary,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class DummyLaunchBag:
    """Dummy LaunchBag that we can easily control in our tests."""

    implements(ILaunchBag)

    def __init__(self, user=None, product=None):
        self.user = user
        self.product = product


class TestBranchPopupWidget(unittest.TestCase):
    """Tests for the branch popup widget."""

    layer = LaunchpadFunctionalLayer

    def assertIs(self, first, second):
        """Assert `first` is `second`."""
        self.assertTrue(first is second, "%r is not %r" % (first, second))

    def installLaunchBag(self, user=None, product=None):
        bag = DummyLaunchBag(user, product)
        provideUtility(bag, ILaunchBag)
        return bag

    def makeBranchPopup(self, vocabulary=None):
        # Pick a random, semi-appropriate context.
        context = self.factory.makeProduct()
        if vocabulary is None:
            vocabulary = BranchVocabulary(context)
        request = self.makeRequest()
        return BranchPopupWidget(
            self.makeField(context, vocabulary), vocabulary, request)

    def makeField(self, context, vocabulary):
        field = Choice(
            title=_('Branch'), vocabulary=vocabulary, required=False,
            description=_("The Bazaar branch."))
        field.context = context
        return field

    def makeRequest(self):
        return LaunchpadTestRequest()

    def setUp(self):
        login(ANONYMOUS)
        self._original_launch_bag = getUtility(ILaunchBag)
        self.factory = LaunchpadObjectFactory()
        self.launch_bag = self.installLaunchBag(
            user=self.factory.makePerson(),
            product=self.factory.makeProduct())
        self.popup = self.makeBranchPopup()

    def tearDown(self):
        provideUtility(self._original_launch_bag, ILaunchBag)
        logout()

    def test_getProduct(self):
        """getProduct() returns the product in the LaunchBag."""
        self.assertEqual(self.launch_bag.product, self.popup.getProduct())

    def test_getPerson(self):
        """getPerson() returns the logged-in user."""
        self.assertEqual(self.launch_bag.user, self.popup.getPerson())

    def test_getBranchNameFromURL(self):
        """getBranchNameFromURL() gets a branch name from a url.

        In general, the name is the last path segment of the URL.
        """
        url = self.factory.getUniqueURL()
        name = self.popup.getBranchNameFromURL(url)
        self.assertEqual(URI(url).path.split('/')[-1], name)

    def test_makeBranchFromURL(self):
        """makeBranchFromURL(url) creates a mirrored branch at `url`.

        The owner and registrant are the currently logged-in user, as given by
        getPerson(), and the product is the product in the LaunchBag.
        """
        url = self.factory.getUniqueURL()
        expected_name = self.popup.getBranchNameFromURL(url)
        branch = self.popup.makeBranchFromURL(url)
        self.assertEqual(BranchType.MIRRORED, branch.branch_type)
        self.assertEqual(url, branch.url)
        self.assertEqual(self.popup.getPerson(), branch.owner)
        self.assertEqual(self.popup.getPerson(), branch.registrant)
        self.assertEqual(self.popup.getProduct(), branch.product)
        self.assertEqual(expected_name, branch.name)

    def test_makeBranch_used(self):
        # makeBranch makes up the branch name if the inferred one is already
        # used.
        url = self.factory.getUniqueURL()
        expected_name = self.popup.getBranchNameFromURL(url)
        self.factory.makeProductBranch(
            name=expected_name, product=self.popup.getProduct(),
            owner=self.popup.getPerson())
        branch = self.popup.makeBranchFromURL(url)
        self.assertEqual(expected_name + '-1', branch.name)

    def test_makeBranchRequestsMirror(self):
        """makeBranch requests a mirror on the branch it creates."""
        url = self.factory.getUniqueURL()
        branch = self.popup.makeBranchFromURL(url)
        self.assertNotEqual('None', str(branch.next_mirror_time))

    def test_makeBranchNoProduct(self):
        """makeBranchFromURL(url) returns None if there's no product.

        Not all contexts for branch registration have products. In particular,
        a bug can be on a source package. When we link a branch to that bug,
        there's no clear product to choose, so we don't choose any.
        """
        self.installLaunchBag(product=None, user=self.factory.makePerson())
        url = self.factory.getUniqueURL()
        self.assertRaises(NoProductError, self.popup.makeBranchFromURL, url)

    def test_makeBranchTrailingSlash(self):
        """makeBranch creates a mirrored branch even if the URL ends with /.
        """
        uri = URI(self.factory.getUniqueURL())
        expected_name = self.popup.getBranchNameFromURL(
            str(uri.ensureNoSlash()))
        branch = self.popup.makeBranchFromURL(str(uri.ensureSlash()))
        self.assertEqual(str(uri.ensureNoSlash()), branch.url)
        self.assertEqual(expected_name, branch.name)

    def test_toFieldValueFallsBackToMakingBranch(self):
        """_toFieldValue falls back to making a branch if it's given a URL."""
        url = self.factory.getUniqueURL()
        # Check that there's no branch with this URL.
        self.assertIs(None, getUtility(IBranchLookup).getByUrl(url))

        branch = self.popup._toFieldValue(url)
        self.assertEqual(url, branch.url)

    def test_toFieldValueFetchesTheExistingBranch(self):
        """_toFieldValue returns the existing branch that has that URL."""
        expected_branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED)
        branch = self.popup._toFieldValue(expected_branch.url)
        self.assertEqual(expected_branch, branch)

    def test_toFieldValueNonURL(self):
        """When the input isn't a URL, fall back to the original error."""
        empty_search = 'doesntexist'
        self.assertRaises(
            ConversionError, self.popup._toFieldValue, empty_search)

    def test_toFieldValueNoProduct(self):
        """When there's no product, fall back to the original error."""
        self.installLaunchBag(product=None, user=self.factory.makePerson())
        self.assertRaises(
            ConversionError, self.popup._toFieldValue,
            self.factory.getUniqueURL())

    def test_toFieldBadURL(self):
        """When the input is a bad URL, fall back to the original error.

        There are many valid URLs that are inappropriate for a mirrored
        branch. We don't want to register a mirrored branch when someone
        enters such a URL.
        """
        bad_url = 'svn://svn.example.com/repo/trunk'
        self.assertRaises(ConversionError, self.popup._toFieldValue, bad_url)

    def test_branchInRestrictedProduct(self):
        # There are two reasons for a URL not being in the vocabulary. One
        # reason is that it's there's no registered branch with that URL. The
        # other is that the vocabulary on this form is restricted to one
        # product, and there *is* a branch with that URL, but it's registered
        # on a different product.

        # Make a popup restricted to a particular product.
        vocab = BranchRestrictedOnProductVocabulary(self.launch_bag.product)
        self.assertEqual(vocab.product, self.launch_bag.product)
        popup = self.makeBranchPopup(vocab)

        # Make a branch on a different product.
        branch = self.factory.makeProductBranch(
            branch_type=BranchType.MIRRORED)
        self.assertNotEqual(self.launch_bag.product, branch.product)

        # Trying to make a branch with that URL will fail.
        self.assertRaises(ConversionError, popup._toFieldValue, branch.url)

    # XXX: JonathanLange 2008-04-17 bug=219019: Not sure how to test what
    # happens when this widget has a good value but other fields have bad
    # values. The correct behavior is to *not* create the branch.
