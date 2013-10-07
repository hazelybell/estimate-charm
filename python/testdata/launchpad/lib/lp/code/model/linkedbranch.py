# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation of `ICanHasLinkedBranch`."""

__metaclass__ = type
# Don't export anything -- anything you need from this module you can get by
# adapting another object.
__all__ = []

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from zope.component import adapts
from zope.interface import implements

from lp.archivepublisher.debversion import Version
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.registry.errors import NoSuchDistroSeries
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.suitesourcepackage import ISuiteSourcePackage


class LinkedBranchOrder(EnumeratedType):
    """An enum used only for ordering."""

    PRODUCT = Item('Product')
    DISTRIBUTION_SOURCE_PACKAGE = Item('Distribution Source Package')
    PRODUCT_SERIES = Item('Product Series')
    SUITE_SOURCE_PACKAGE = Item('Suite Source Package')


class BaseLinkedBranch:
    """Provides the common sorting algorithm."""

    def __cmp__(self, other):
        if not ICanHasLinkedBranch.providedBy(other):
            raise AssertionError("Can't compare with: %r" % other)
        return cmp(self.sort_order, other.sort_order)


class ProductSeriesLinkedBranch(BaseLinkedBranch):
    """Implement a linked branch for a product series."""

    adapts(IProductSeries)
    implements(ICanHasLinkedBranch)

    sort_order = LinkedBranchOrder.PRODUCT_SERIES

    def __init__(self, product_series):
        self.context = product_series

    @property
    def product_series(self):
        return self.context

    def __cmp__(self, other):
        result = super(ProductSeriesLinkedBranch, self).__cmp__(other)
        if result != 0:
            return result
        else:
            # The sorting of the product series uses the same sorting the
            # product itself uses, which is alphabetically by name.
            my_parts = (
                self.product_series.product.name,
                self.product_series.name)
            other_parts = (
                other.product_series.product.name,
                other.product_series.name)
            return cmp(my_parts, other_parts)

    @property
    def branch(self):
        """See `ICanHasLinkedBranch`."""
        return self.product_series.branch

    @property
    def bzr_path(self):
        """See `ICanHasLinkedBranch`."""
        return '/'.join(
            [self.product_series.product.name, self.product_series.name])

    def setBranch(self, branch, registrant=None):
        """See `ICanHasLinkedBranch`."""
        self.product_series.branch = branch


class ProductLinkedBranch(BaseLinkedBranch):
    """Implement a linked branch for a product."""

    adapts(IProduct)
    implements(ICanHasLinkedBranch)

    sort_order = LinkedBranchOrder.PRODUCT

    def __init__(self, product):
        self.context = product

    @property
    def product(self):
        return self.context

    def __cmp__(self, other):
        result = super(ProductLinkedBranch, self).__cmp__(other)
        if result != 0:
            return result
        else:
            return cmp(self.product.name, other.product.name)

    @property
    def branch(self):
        """See `ICanHasLinkedBranch`."""
        return ICanHasLinkedBranch(self.product.development_focus).branch

    @property
    def bzr_path(self):
        """See `ICanHasLinkedBranch`."""
        return self.product.name

    def setBranch(self, branch, registrant=None):
        """See `ICanHasLinkedBranch`."""
        ICanHasLinkedBranch(self.product.development_focus).setBranch(
            branch, registrant)


class PackageLinkedBranch(BaseLinkedBranch):
    """Implement a linked branch for a source package pocket."""

    adapts(ISuiteSourcePackage)
    implements(ICanHasLinkedBranch)

    sort_order = LinkedBranchOrder.SUITE_SOURCE_PACKAGE

    def __init__(self, suite_sourcepackage):
        self.context = suite_sourcepackage

    @property
    def suite_sourcepackage(self):
        return self.context

    def __cmp__(self, other):
        result = super(PackageLinkedBranch, self).__cmp__(other)
        if result != 0:
            return result
        # The versions are reversed as we want the greater Version to sort
        # before the lesser one.  Hence self in the other tuple, and other in
        # the self tuple.  Next compare the distribution name.
        my_parts = (
            self.suite_sourcepackage.distribution.name,
            Version(other.suite_sourcepackage.distroseries.version),
            self.suite_sourcepackage.sourcepackagename.name,
            self.suite_sourcepackage.pocket)
        other_parts = (
            other.suite_sourcepackage.distribution.name,
            Version(self.suite_sourcepackage.distroseries.version),
            other.suite_sourcepackage.sourcepackagename.name,
            other.suite_sourcepackage.pocket)
        return cmp(my_parts, other_parts)

    @property
    def branch(self):
        """See `ICanHasLinkedBranch`."""
        package = self.suite_sourcepackage.sourcepackage
        pocket = self.suite_sourcepackage.pocket
        return package.getBranch(pocket)

    @property
    def bzr_path(self):
        """See `ICanHasLinkedBranch`."""
        return self.suite_sourcepackage.path

    def setBranch(self, branch, registrant):
        """See `ICanHasLinkedBranch`."""
        package = self.suite_sourcepackage.sourcepackage
        pocket = self.suite_sourcepackage.pocket
        package.setBranch(pocket, branch, registrant)


class DistributionPackageLinkedBranch(BaseLinkedBranch):
    """Implement a linked branch for an `IDistributionSourcePackage`."""

    adapts(IDistributionSourcePackage)
    implements(ICanHasLinkedBranch)

    sort_order = LinkedBranchOrder.DISTRIBUTION_SOURCE_PACKAGE

    def __init__(self, distribution_sourcepackage):
        self.context = distribution_sourcepackage

    @property
    def distribution_sourcepackage(self):
        return self.context

    def __cmp__(self, other):
        result = super(DistributionPackageLinkedBranch, self).__cmp__(other)
        if result != 0:
            return result
        else:
            my_names = (
                self.distribution_sourcepackage.distribution.name,
                self.distribution_sourcepackage.sourcepackagename.name)
            other_names = (
                other.distribution_sourcepackage.distribution.name,
                other.distribution_sourcepackage.sourcepackagename.name)
            return cmp(my_names, other_names)

    @property
    def branch(self):
        """See `ICanHasLinkedBranch`."""
        development_package = (
            self.distribution_sourcepackage.development_version)
        if development_package is None:
            return None
        suite_sourcepackage = development_package.getSuiteSourcePackage(
            PackagePublishingPocket.RELEASE)
        return ICanHasLinkedBranch(suite_sourcepackage).branch

    @property
    def bzr_path(self):
        """See `ICanHasLinkedBranch`."""
        return '/'.join(
            [self.distribution_sourcepackage.distribution.name,
             self.distribution_sourcepackage.sourcepackagename.name])

    def setBranch(self, branch, registrant):
        """See `ICanHasLinkedBranch`."""
        development_package = (
            self.distribution_sourcepackage.development_version)
        if development_package is None:
            raise NoSuchDistroSeries('no current series')
        suite_sourcepackage = development_package.getSuiteSourcePackage(
            PackagePublishingPocket.RELEASE)
        ICanHasLinkedBranch(suite_sourcepackage).setBranch(branch, registrant)
