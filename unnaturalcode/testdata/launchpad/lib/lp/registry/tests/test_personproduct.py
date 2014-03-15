# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the Person/Product non-database class."""

__metaclass__ = type

from lp.registry.model.personproduct import PersonProduct
from lp.services.webapp.interfaces import IBreadcrumb
from lp.services.webapp.publisher import canonical_url
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestPersonProduct(TestCaseWithFactory):
    """Tests for `IPersonProduct`s."""

    layer = DatabaseFunctionalLayer

    def _makePersonProduct(self):
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        return PersonProduct(person, product)

    def test_canonical_url(self):
        # The canonical_url of a person product is ~person/product.
        pp = self._makePersonProduct()
        expected = 'http://launchpad.dev/~%s/%s' % (
            pp.person.name, pp.product.name)
        self.assertEqual(expected, canonical_url(pp))

    def test_breadcrumb(self):
        # Person products give the product as their breadcrumb url.
        pp = self._makePersonProduct()
        breadcrumb = IBreadcrumb(pp, None)
        self.assertEqual(canonical_url(pp.product), breadcrumb.url)
