# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for sourcepackagerecipe listings."""

__metaclass__ = type


from lp.testing import BrowserTestCase
from lp.testing.layers import DatabaseFunctionalLayer


class TestSourcePackageRecipeListing(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_project_branch_recipe_listing(self):
        # We can see recipes for the product. We need to create two, since
        # only one will redirect to that recipe.
        branch = self.factory.makeProductBranch()
        recipe = self.factory.makeSourcePackageRecipe(branches=[branch])
        recipe2 = self.factory.makeSourcePackageRecipe(branches=[branch])
        text = self.getMainText(recipe.base_branch, '+recipes')
        self.assertTextMatchesExpressionIgnoreWhitespace("""
            Source Package Recipes for lp:.*
            Name              Owner       Registered
            spr-name.*        Person-name""", text)

    def test_package_branch_recipe_listing(self):
        # We can see recipes for the package. We need to create two, since
        # only one will redirect to that recipe.
        branch = self.factory.makePackageBranch()
        recipe = self.factory.makeSourcePackageRecipe(branches=[branch])
        recipe2 = self.factory.makeSourcePackageRecipe(branches=[branch])
        text = self.getMainText(recipe.base_branch, '+recipes')
        self.assertTextMatchesExpressionIgnoreWhitespace("""
            Source Package Recipes for lp:.*
            Name             Owner       Registered
            spr-name.*       Person-name""", text)
