# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base class view for sourcepackagerecipe listings."""

__metaclass__ = type

__all__ = [
    'BranchRecipeListingView',
    'HasRecipesMenuMixin',
    'PersonRecipeListingView',
    'ProductRecipeListingView',
    ]


from lp.services.feeds.browser import FeedsMixin
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    Link,
    )


class HasRecipesMenuMixin:
    """A mixin for context menus for objects that implement IHasRecipes."""

    def view_recipes(self):
        text = 'View source package recipes'
        enabled = False
        if self.context.recipes.count():
            enabled = True
        return Link(
            '+recipes', text, icon='info', enabled=enabled, site='code')


class RecipeListingView(LaunchpadView, FeedsMixin):

    feed_types = ()

    branch_enabled = True
    owner_enabled = True

    @property
    def page_title(self):
        return 'Source Package Recipes for %(displayname)s' % {
            'displayname': self.context.displayname}

    def initialize(self):
        super(RecipeListingView, self).initialize()
        recipes = self.context.recipes
        if recipes.count() == 1:
            recipe = recipes.one()
            self.request.response.redirect(canonical_url(recipe))


class BranchRecipeListingView(RecipeListingView):

    branch_enabled = False


class PersonRecipeListingView(RecipeListingView):

    owner_enabled = False


class ProductRecipeListingView(RecipeListingView):
    pass
