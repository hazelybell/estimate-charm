# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views, menus and traversal related to PersonProducts."""

__metaclass__ = type
__all__ = [
    'PersonProductBreadcrumb',
    'PersonProductFacets',
    'PersonProductNavigation',
    ]


from zope.component import queryAdapter
from zope.traversing.interfaces import IPathAdapter

from lp.app.errors import NotFoundError
from lp.code.interfaces.branchnamespace import get_branch_namespace
from lp.registry.interfaces.personproduct import IPersonProduct
from lp.services.webapp import (
    canonical_url,
    Link,
    Navigation,
    StandardLaunchpadFacets,
    )
from lp.services.webapp.breadcrumb import Breadcrumb


class PersonProductNavigation(Navigation):
    """Navigation to branches for this person/product."""
    usedfor = IPersonProduct

    def traverse(self, branch_name):
        """Look for a branch in the person/product namespace."""
        namespace = get_branch_namespace(
            person=self.context.person, product=self.context.product)
        branch = namespace.getByName(branch_name)
        if branch is None:
            raise NotFoundError
        else:
            return branch


class PersonProductBreadcrumb(Breadcrumb):
    """Breadcrumb for an `IPersonProduct`."""

    @property
    def text(self):
        return self.context.product.displayname

    @property
    def url(self):
        if self._url is None:
            return canonical_url(self.context.product, rootsite=self.rootsite)
        else:
            return self._url

    @property
    def icon(self):
        return queryAdapter(
            self.context.product, IPathAdapter, name='image').icon()


class PersonProductFacets(StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an IPerson."""

    usedfor = IPersonProduct

    enable_only = ['branches']

    def branches(self):
        text = 'Code'
        summary = ('Bazaar Branches of %s owned by %s' %
                   (self.context.product.displayname,
                    self.context.person.displayname))
        return Link('', text, summary)
