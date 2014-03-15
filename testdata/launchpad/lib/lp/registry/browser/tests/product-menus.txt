========================
The product menu classes
========================

Each link specified by menu classes for products should be accessible.
In most cases, the context for links will be the product itself, which
makes it possible to test most of the links simply with getMultiAdapter().

The check_menu_links() function is defined here to make it simple to
test all the product menu classes below.

    >>> from lp.testing.menu import check_menu_links
    >>> from lp.registry.browser.product import (
    ...     ProductBugsMenu, ProductNavigationMenu,
    ...     ProductOverviewMenu, ProductSpecificationsMenu)

    >>> product = factory.makeProduct()

    >>> check_menu_links(ProductOverviewMenu(product))
    True

    >>> check_menu_links(ProductBugsMenu(product))
    True

    >>> check_menu_links(ProductSpecificationsMenu(product))
    True

    >>> check_menu_links(ProductNavigationMenu(product))
    True


ProductBranchesMenu and ProductTranslationsMenu
===============================================

We are not testing ProductBranchesMenu.code_import because it
points to a view (/+code-imports/+new), which is not easily tested.

Most of the links in ProductTranslationsMenu do not
work with check_menu_links(). This might be because the
facet is not applied correctly before using getMultiAdapter().

# XXX: EdwinGrubbs 2008-11-11 bug=296927
# A method for testing the links in the above menus should be added.
