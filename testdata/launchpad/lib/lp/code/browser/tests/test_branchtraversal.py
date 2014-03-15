# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for branch traversal."""

from zope.component import getUtility
from zope.publisher.interfaces import NotFound
from zope.security.proxy import removeSecurityProxy

from lp.registry.browser.person import PersonNavigation
from lp.registry.browser.personproduct import PersonProductNavigation
from lp.registry.interfaces.personproduct import (
    IPersonProduct,
    IPersonProductFactory,
    )
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    FakeLaunchpadRequest,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestPersonBranchTraversal(TestCaseWithFactory):
    """Branches are traversed to from IPersons. Test we can reach them.

    This class tests the `PersonNavigation` class to see that we can traverse
    to branches from such objects.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.person = self.factory.makePerson()

    def assertRedirects(self, segments, url):
        redirection = self.traverse(segments)
        self.assertEqual(url, redirection.target)

    def traverse(self, segments):
        """Traverse to 'segments' using a 'PersonNavigation' object.

        Using the Zope traversal machinery, traverse to the path given by
        'segments', starting at a `PersonNavigation` object wrapped around the
        'person' attribute.

        :param segments: A list of path segments.
        :return: The object found.
        """
        stack = list(reversed(segments))
        name = stack.pop()
        request = FakeLaunchpadRequest(['~' + self.person.name], stack)
        traverser = PersonNavigation(self.person, request)
        return traverser.publishTraverse(request, name)

    def test_redirect_product_branch(self):
        branch = self.factory.makeProductBranch(owner=self.person)
        segments = ['+branch', branch.product.name, branch.name]
        self.assertRedirects(segments, canonical_url(branch))

    def test_redirect_junk_branch(self):
        branch = self.factory.makePersonalBranch(owner=self.person)
        segments = ['+branch', '+junk', branch.name]
        self.assertRedirects(segments, canonical_url(branch))

    def test_redirect_branch_not_found(self):
        self.assertRaises(
            NotFound, self.traverse, ['+branch', 'no-product', 'no-branch'])

    def test_redirect_on_package_branch_aliases(self):
        branch = self.factory.makePackageBranch(owner=self.person)
        distro = removeSecurityProxy(branch.distribution)
        distro.setAliases(['foo'])
        self.assertRedirects(
            ['foo', branch.distroseries.name, branch.sourcepackagename.name,
             branch.name],
            canonical_url(branch))

    def test_junk_branch(self):
        branch = self.factory.makePersonalBranch(owner=self.person)
        segments = ['+junk', branch.name]
        self.assertEqual(branch, self.traverse(segments))

    def test_junk_branch_no_such_branch(self):
        branch_name = self.factory.getUniqueString()
        self.assertRaises(NotFound, self.traverse, ['+junk', branch_name])

    def test_product_only(self):
        # Traversal to the product returns an IPersonProduct.
        product = self.factory.makeProduct()
        target = self.traverse([product.name])
        self.assertTrue(IPersonProduct.providedBy(target))

    def test_product_branch_no_such_product(self):
        product_name = self.factory.getUniqueString()
        branch_name = self.factory.getUniqueString()
        self.assertRaises(
            NotFound, self.traverse, [product_name, branch_name])

    def test_package_branch(self):
        branch = self.factory.makePackageBranch(owner=self.person)
        segments = [
            branch.distribution.name,
            branch.distroseries.name,
            branch.sourcepackagename.name,
            branch.name]
        self.assertEqual(branch, self.traverse(segments))


class TestPersonProductBranchTraversal(TestCaseWithFactory):
    """Test the traversal from a `PersonProuct`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.person = self.factory.makePerson()
        self.product = self.factory.makeProduct()
        self.person_product = getUtility(IPersonProductFactory).create(
                self.person, self.product)

    def traverse(self, segments):
        """Traverse to 'segments' using a 'PersonNavigation' object.

        Using the Zope traversal machinery, traverse to the path given by
        'segments', starting at a `PersonNavigation` object wrapped around the
        'person' attribute.

        :param segments: A list of path segments.
        :return: The object found.
        """
        stack = list(reversed(segments))
        name = stack.pop()
        request = FakeLaunchpadRequest(
            ['~' + self.person.name, self.product.name], stack)
        traverser = PersonProductNavigation(self.person_product, request)
        return traverser.publishTraverse(request, name)

    def test_product_branch(self):
        # The branch is returned if the branch does exist.
        branch = self.factory.makeProductBranch(
            owner=self.person, product=self.product)
        segments = [branch.name]
        self.assertEqual(branch, self.traverse(segments))

    def test_product_branch_no_such_branch(self):
        # NotFound is raised if the branch name doesn't exist.
        branch_name = self.factory.getUniqueString()
        self.assertRaises(NotFound, self.traverse, [branch_name])
