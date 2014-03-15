# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for classes that implement IHasRecipes."""

__metaclass__ = type

from lp.code.interfaces.hasrecipes import IHasRecipes
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestIHasRecipes(TestCaseWithFactory):
    """Test that the correct objects implement the interface."""

    layer = DatabaseFunctionalLayer

    def test_branch_implements_hasrecipes(self):
        # Branches should implement IHasRecipes.
        branch = self.factory.makeBranch()
        self.assertProvides(branch, IHasRecipes)

    def test_branch_recipes(self):
        # IBranch.recipes should provide all the SourcePackageRecipes attached
        # to that branch.
        base_branch = self.factory.makeBranch()
        recipe1 = self.factory.makeSourcePackageRecipe(branches=[base_branch])
        recipe2 = self.factory.makeSourcePackageRecipe(branches=[base_branch])
        recipe_ignored = self.factory.makeSourcePackageRecipe()
        self.assertEqual(2, base_branch.recipes.count())

    def test_branch_recipes_nonbase(self):
        # IBranch.recipes should provide all the SourcePackageRecipes
        # that refer to the branch, even as a non-base branch.
        base_branch = self.factory.makeBranch()
        nonbase_branch = self.factory.makeBranch()
        recipe = self.factory.makeSourcePackageRecipe(
            branches=[base_branch, nonbase_branch])
        recipe_ignored = self.factory.makeSourcePackageRecipe()
        self.assertEqual(recipe, nonbase_branch.recipes.one())

    def test_person_implements_hasrecipes(self):
        # Person should implement IHasRecipes.
        person = self.factory.makeBranch()
        self.assertProvides(person, IHasRecipes)

    def test_person_recipes(self):
        # IPerson.recipes should provide all the SourcePackageRecipes
        # owned by that person.
        person = self.factory.makePerson()
        recipe1 = self.factory.makeSourcePackageRecipe(owner=person)
        recipe2 = self.factory.makeSourcePackageRecipe(owner=person)
        recipe_ignored = self.factory.makeSourcePackageRecipe()
        self.assertEqual(2, person.recipes.count())

    def test_product_implements_hasrecipes(self):
        # Product should implement IHasRecipes.
        product = self.factory.makeProduct()
        self.assertProvides(product, IHasRecipes)

    def test_product_recipes(self):
        # IProduct.recipes should provide all the SourcePackageRecipes
        # attached to that product's branches.
        product = self.factory.makeProduct()
        branch = self.factory.makeBranch(product=product)
        recipe1 = self.factory.makeSourcePackageRecipe(branches=[branch])
        recipe2 = self.factory.makeSourcePackageRecipe(branches=[branch])
        recipe_ignored = self.factory.makeSourcePackageRecipe()
        self.assertEqual(2, product.recipes.count())
