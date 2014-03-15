# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for `ProductWithLicenses`."""

__metaclass__ = type

from operator import attrgetter

from storm.store import Store
from zope.interface.verify import verifyObject

from lp.registry.interfaces.product import (
    IProduct,
    License,
    LicenseStatus,
    )
from lp.registry.model.product import (
    Product,
    ProductWithLicenses,
    )
from lp.testing import (
    ANONYMOUS,
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestProductWithLicenses(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_baseline(self):
        product = self.factory.makeProduct()
        product_with_licenses = ProductWithLicenses(product, [])
        # Log in--a full verification takes Edit privileges.
        login('foo.bar@canonical.com')
        self.assertTrue(verifyObject(IProduct, product_with_licenses))

    def test_uses_cached_licenses(self):
        # The ProductWithLicenses' licensing information is based purely
        # on the cached licenses list.  The database is not queried to
        # determine licensing status.
        product = self.factory.makeProduct(licenses=[License.BSD])
        product_with_licenses = ProductWithLicenses(
            product, [License.OTHER_PROPRIETARY.value])
        license_status = product_with_licenses.license_status
        self.assertEqual(LicenseStatus.PROPRIETARY, license_status)

    def test_sorts_licenses(self):
        # The ProductWithLicenses constructor sorts the Licenses by
        # numeric value.
        product = self.factory.makeProduct()
        licenses = [License.AFFERO, License.BSD, License.MIT]

        # Feed the constructor a list of ids in the wrong order.
        product_with_licenses = ProductWithLicenses(
            product,
            sorted([license.value for license in licenses], reverse=True))

        expected = sorted(licenses, key=attrgetter('value'))
        self.assertEqual(tuple(expected), product_with_licenses.licenses)

    def test_licenses_column_contains_licensing_info(self):
        # Feeding the licenses column into the ProductWithLicenses
        # constructor seeds it with the appropriate licenses.
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        column = ProductWithLicenses.composeLicensesColumn()
        store = Store.of(product)
        row = store.find((Product, column), Product.id == product.id).one()

        product_with_licenses = ProductWithLicenses(*row)
        licenses = product_with_licenses.licenses
        license_status = product_with_licenses.license_status
        self.assertEqual((License.OTHER_PROPRIETARY, ), licenses)
        self.assertEqual(LicenseStatus.PROPRIETARY, license_status)

    def test_licenses_column_aggregates(self):
        # Adding a licensing column for a product with multiple licenses
        # still finds a single product, not one per licence.
        licenses = [License.AFFERO, License.GNU_GPL_V3]
        product = self.factory.makeProduct(licenses=licenses)
        column = ProductWithLicenses.composeLicensesColumn()
        store = Store.of(product)
        result = list(store.find((Product, column), Product.id == product.id))

        self.assertEqual(1, len(result))
        found_product, found_licenses = result[0]
        self.assertEqual(product, found_product)
        self.assertEqual(len(licenses), len(found_licenses))

    def test_license_status_is_public(self):
        # The license_status attribute can be read by anyone, on
        # ProductWithLicenses as on Product.
        product = self.factory.makeProduct(licenses=[License.BSD])
        product_with_licenses = ProductWithLicenses(
            product, [License.BSD.value])
        login(ANONYMOUS)
        self.assertEqual(
            LicenseStatus.OPEN_SOURCE, product.license_status)
        self.assertEqual(
            LicenseStatus.OPEN_SOURCE, product_with_licenses.license_status)
