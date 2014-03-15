# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for BranchCollection adapters."""

__metaclass__ = type


from lp.code.interfaces.branchcollection import IBranchCollection
from lp.registry.model.personproduct import PersonProduct
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestPersonProduct(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_person_product(self):
        """A PersonProduct can be adapted to a collection.

        The collection will only find branches matching both the person and
        the product.
        """
        product = self.factory.makeProduct()
        person = self.factory.makePerson()
        person_product = PersonProduct(person, product)
        self.factory.makeBranch()
        self.factory.makeProductBranch(product=product)
        self.factory.makeBranch(owner=person)
        person_product_branch = self.factory.makeProductBranch(
            owner=person, product=product)
        branches = IBranchCollection(person_product).getBranches()
        self.assertEqual([person_product_branch], [b for b in branches])
