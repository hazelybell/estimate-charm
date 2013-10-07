# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for adapters."""

__metaclass__ = type

from lp.registry.adapters import (
    distroseries_to_distribution,
    information_type_from_product,
    package_to_sourcepackagename,
    productseries_to_product,
    sourcepackage_to_distribution,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.sourcepackagename import ISourcePackageName
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestAdapters(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_sourcepackage_to_distribution_dsp(self):
        # A distribution can be retrieved from a dsp.
        package = self.factory.makeDistributionSourcePackage()
        distribution = sourcepackage_to_distribution(package)
        self.assertTrue(IDistribution.providedBy(distribution))
        self.assertEqual(package.distribution, distribution)
        self.assertEqual(package.distribution, IDistribution(package))

    def test_sourcepackage_to_distribution_sp(self):
        # A distribution can be retrieved from a source package.
        package = self.factory.makeSourcePackage()
        distribution = sourcepackage_to_distribution(package)
        self.assertTrue(IDistribution.providedBy(distribution))
        self.assertEqual(package.distroseries.distribution, distribution)
        self.assertEqual(
            package.distroseries.distribution, IDistribution(package))

    def test_sourcepackage_to_sourcepackagename(self):
        # A sourcepackagename can be retrieved source package.
        package = self.factory.makeSourcePackage()
        spn = package_to_sourcepackagename(package)
        self.assertTrue(ISourcePackageName.providedBy(spn))
        self.assertEqual(
            package.sourcepackagename, ISourcePackageName(package))

    def test_distributionsourcepackage_to_sourcepackagename(self):
        # A sourcepackagename can be retrieved distribution source package.
        package = self.factory.makeDistributionSourcePackage()
        spn = package_to_sourcepackagename(package)
        self.assertTrue(ISourcePackageName.providedBy(spn))
        self.assertEqual(
            package.sourcepackagename, ISourcePackageName(package))

    def test_distroseries_to_distribution(self):
        # distroseries_to_distribution() returns an IDistribution given an
        # IDistroSeries.
        distro_series = self.factory.makeDistroSeries()
        distribution = distroseries_to_distribution(distro_series)
        self.assertTrue(IDistribution.providedBy(distribution))
        self.assertEqual(distro_series.distribution, distribution)
        self.assertEqual(
            distro_series.distribution, IDistribution(distro_series))

    def test_productseries_to_product(self):
        # productseries_to_product() returns an IProduct given an
        # IProductSeries.
        product_series = self.factory.makeProductSeries()
        product = productseries_to_product(product_series)
        self.assertTrue(IProduct.providedBy(product))
        self.assertEqual(product_series.product, product)
        self.assertEqual(product, IProduct(product_series))

    def test_information_type_from_product(self):
        # information_type_from_product() returns an IProduct given
        # an IMilestone.
        milestone = self.factory.makeMilestone()
        product = information_type_from_product(milestone)
        self.assertTrue(IProduct.providedBy(product))
        self.assertEqual(product, milestone.product)
