# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for linked branch implementations."""

__metaclass__ = type


import unittest

from zope.security.proxy import removeSecurityProxy

from lp.code.interfaces.linkedbranch import (
    CannotHaveLinkedBranch,
    get_linked_to_branch,
    ICanHasLinkedBranch,
    )
from lp.registry.errors import NoSuchDistroSeries
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.testing import (
    person_logged_in,
    run_with_login,
    TestCaseWithFactory,
    )
from lp.testing.factory import remove_security_proxy_and_shout_at_engineer
from lp.testing.layers import DatabaseFunctionalLayer


class TestProductSeriesLinkedBranch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_branch(self):
        # The linked branch of a product series is its branch attribute.
        product_series = self.factory.makeProductSeries()
        naked_product_series = remove_security_proxy_and_shout_at_engineer(
            product_series)
        naked_product_series.branch = self.factory.makeProductBranch(
            product=product_series.product)
        self.assertEqual(
            product_series.branch, ICanHasLinkedBranch(product_series).branch)

    def test_setBranch(self):
        # setBranch sets the linked branch of the product series.
        product_series = self.factory.makeProductSeries()
        naked_product_series = remove_security_proxy_and_shout_at_engineer(
            product_series)
        branch = self.factory.makeProductBranch(
            product=product_series.product)
        ICanHasLinkedBranch(naked_product_series).setBranch(branch)
        self.assertEqual(branch, product_series.branch)

    def test_bzr_path(self):
        # The bzr_path of a product series linked branch is
        # product/product_series.
        product_series = self.factory.makeProductSeries()
        bzr_path = '%s/%s' % (
            product_series.product.name, product_series.name)
        self.assertEqual(
            bzr_path, ICanHasLinkedBranch(product_series).bzr_path)


class TestProductLinkedBranch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_branch(self):
        # The linked branch of a product is the linked branch of its
        # development focus product series.
        branch = self.factory.makeProductBranch()
        product = branch.product
        removeSecurityProxy(product).development_focus.branch = branch
        self.assertEqual(branch, ICanHasLinkedBranch(product).branch)

    def test_setBranch(self):
        # setBranch sets the linked branch of the development focus product
        # series.
        branch = self.factory.makeProductBranch()
        product = removeSecurityProxy(branch.product)
        ICanHasLinkedBranch(product).setBranch(branch)
        self.assertEqual(branch, product.development_focus.branch)

    def test_get_linked_to_branch(self):
        branch = self.factory.makeProductBranch()
        product = removeSecurityProxy(branch.product)
        ICanHasLinkedBranch(product).setBranch(branch)
        got_linkable = get_linked_to_branch(product)
        self.assertEqual(got_linkable, ICanHasLinkedBranch(product))

    def test_bzr_path(self):
        # The bzr_path of a product linked branch is the product name.
        product = self.factory.makeProduct()
        self.assertEqual(
            product.name, ICanHasLinkedBranch(product).bzr_path)


class TestSuiteSourcePackageLinkedBranch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_branch(self):
        # The linked branch of a suite source package is the official branch
        # for the pocket of that source package.
        branch = self.factory.makeAnyBranch()
        suite_sourcepackage = self.factory.makeSuiteSourcePackage()
        registrant = suite_sourcepackage.distribution.owner
        with person_logged_in(registrant):
            suite_sourcepackage.sourcepackage.setBranch(
                suite_sourcepackage.pocket, branch, registrant)
        self.assertEqual(
            branch, ICanHasLinkedBranch(suite_sourcepackage).branch)

    def test_setBranch(self):
        # setBranch sets the official branch for the appropriate pocket of the
        # source package.
        branch = self.factory.makeAnyBranch()
        suite_sourcepackage = self.factory.makeSuiteSourcePackage()
        registrant = suite_sourcepackage.distribution.owner
        run_with_login(
            registrant,
            ICanHasLinkedBranch(suite_sourcepackage).setBranch,
            branch, registrant)
        self.assertEqual(
            branch,
            suite_sourcepackage.sourcepackage.getBranch(
                suite_sourcepackage.pocket))

    def test_bzr_path(self):
        # The bzr_path of a suite source package linked branch is the path
        # of that suite source package.
        suite_sourcepackage = self.factory.makeSuiteSourcePackage()
        self.assertEqual(
            suite_sourcepackage.path,
            ICanHasLinkedBranch(suite_sourcepackage).bzr_path)


class TestDistributionSourcePackageLinkedBranch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_branch(self):
        # The linked branch of a distribution source package is the official
        # branch for the release pocket of the development focus series for
        # that package. Phew.
        branch = self.factory.makeAnyBranch()
        sourcepackage = self.factory.makeSourcePackage()
        dev_sourcepackage = sourcepackage.development_version
        pocket = PackagePublishingPocket.RELEASE

        registrant = sourcepackage.distribution.owner
        with person_logged_in(registrant):
            dev_sourcepackage.setBranch(pocket, branch, registrant)

        distribution_sourcepackage = sourcepackage.distribution_sourcepackage
        self.assertEqual(
            branch, ICanHasLinkedBranch(distribution_sourcepackage).branch)

    def test_branch_when_no_series(self):
        # Our data model allows distributions that have no series. The linked
        # branch for a package in such a distribution is always None.
        distro_package = self.factory.makeDistributionSourcePackage()
        self.assertIs(None, ICanHasLinkedBranch(distro_package).branch)

    def test_setBranch(self):
        # Setting the linked branch for a distribution source package links
        # the branch to the release pocket of the development focus series for
        # that package.
        branch = self.factory.makeAnyBranch()
        sourcepackage = self.factory.makeSourcePackage()
        distribution_sourcepackage = sourcepackage.distribution_sourcepackage

        registrant = sourcepackage.distribution.owner
        run_with_login(
            registrant,
            ICanHasLinkedBranch(distribution_sourcepackage).setBranch,
            branch, registrant)

        dev_sourcepackage = sourcepackage.development_version
        pocket = PackagePublishingPocket.RELEASE
        self.assertEqual(branch, dev_sourcepackage.getBranch(pocket))

    def test_setBranch_with_no_series(self):
        distribution_sourcepackage = (
            self.factory.makeDistributionSourcePackage())
        linked_branch = ICanHasLinkedBranch(distribution_sourcepackage)
        registrant = distribution_sourcepackage.distribution.owner
        self.assertRaises(
            NoSuchDistroSeries,
            linked_branch.setBranch, self.factory.makeAnyBranch(), registrant)

    def test_bzr_path(self):
        # The bzr_path of a distribution source package linked branch is
        # distro/package.
        distribution_sourcepackage = (
            self.factory.makeDistributionSourcePackage())
        self.assertEqual(
            '%s/%s' % (
                distribution_sourcepackage.distribution.name,
                distribution_sourcepackage.sourcepackagename.name),
            ICanHasLinkedBranch(distribution_sourcepackage).bzr_path)


class TestProjectLinkedBranch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_cannot_have_linked_branch(self):
        # ProjectGroups cannot have linked branches.
        project = self.factory.makeProject()
        self.assertRaises(
            CannotHaveLinkedBranch, get_linked_to_branch, project)


class TestLinkedBranchSorting(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_sorting_different_types(self):
        # The different types can be sorted together, and sort so that the
        # results are ordered like:
        #   Product Link
        #   Distribution Source Package Link
        #   Product Series Link
        #   Package Link
        product_link = ICanHasLinkedBranch(self.factory.makeProduct())
        product_series_link = ICanHasLinkedBranch(
            self.factory.makeProductSeries())
        distro_sp_link = ICanHasLinkedBranch(
            self.factory.makeDistributionSourcePackage())
        package_link = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage())

        links = sorted(
            [package_link, product_series_link, distro_sp_link, product_link])
        self.assertIs(product_link, links[0])
        self.assertIs(distro_sp_link, links[1])
        self.assertIs(product_series_link, links[2])
        self.assertIs(package_link, links[3])

    def test_product_sort(self):
        # If in the extremely unlikely event we have one branch linked as the
        # trunk of two or more different products (you never know), then the
        # sorting reverts to the name of the product.
        aardvark_link = ICanHasLinkedBranch(
            self.factory.makeProduct(name='aardvark'))
        meerkat_link = ICanHasLinkedBranch(
            self.factory.makeProduct(name='meerkat'))
        zebra_link = ICanHasLinkedBranch(
            self.factory.makeProduct(name='zebra'))
        links = sorted(
            [zebra_link, aardvark_link, meerkat_link])
        self.assertIs(aardvark_link, links[0])
        self.assertIs(meerkat_link, links[1])
        self.assertIs(zebra_link, links[2])

    def test_product_series_sort(self):
        # Sorting by product series checks the product name first, then series
        # name.
        aardvark = self.factory.makeProduct(name='aardvark')
        zebra = self.factory.makeProduct(name='zebra')
        aardvark_devel = ICanHasLinkedBranch(
            self.factory.makeProductSeries(
                product=aardvark, name='devel'))
        aardvark_testing = ICanHasLinkedBranch(
            self.factory.makeProductSeries(
                product=aardvark, name='testing'))
        zebra_devel = ICanHasLinkedBranch(
            self.factory.makeProductSeries(
                product=zebra, name='devel'))
        zebra_mashup = ICanHasLinkedBranch(
            self.factory.makeProductSeries(
                product=zebra, name='mashup'))

        links = sorted(
            [zebra_mashup, aardvark_testing, zebra_devel, aardvark_devel])
        self.assertIs(aardvark_devel, links[0])
        self.assertIs(aardvark_testing, links[1])
        self.assertIs(zebra_devel, links[2])
        self.assertIs(zebra_mashup, links[3])

    def test_distribution_source_package_sort(self):
        # Sorting of distribution source packages sorts firstly on the
        # distribution name, then the package name.
        aardvark = self.factory.makeDistribution(name='aardvark')
        zebra = self.factory.makeDistribution(name='zebra')
        aardvark_devel = ICanHasLinkedBranch(
            self.factory.makeDistributionSourcePackage(
                distribution=aardvark, sourcepackagename='devel'))
        aardvark_testing = ICanHasLinkedBranch(
            self.factory.makeDistributionSourcePackage(
                distribution=aardvark, sourcepackagename='testing'))
        zebra_devel = ICanHasLinkedBranch(
            self.factory.makeDistributionSourcePackage(
                distribution=zebra, sourcepackagename='devel'))
        zebra_mashup = ICanHasLinkedBranch(
            self.factory.makeDistributionSourcePackage(
                distribution=zebra, sourcepackagename='mashup'))

        links = sorted(
            [zebra_mashup, aardvark_testing, zebra_devel, aardvark_devel])
        self.assertIs(aardvark_devel, links[0])
        self.assertIs(aardvark_testing, links[1])
        self.assertIs(zebra_devel, links[2])
        self.assertIs(zebra_mashup, links[3])

    def test_suite_source_package_sort(self):
        # The sorting of suite source packages checks the distribution first,
        # then the distroseries version, followed by the source package name,
        # and finally the pocket.
        aardvark = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                distroseries=self.factory.makeDistroSeries(
                    self.factory.makeDistribution(name='aardvark'))))
        zebra = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                distroseries=self.factory.makeDistroSeries(
                    self.factory.makeDistribution(name='zebra'))))
        meerkat = self.factory.makeDistribution(name='meerkat')
        meerkat_1 = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                self.factory.makeDistroSeries(meerkat, "1.0")))
        meerkat_2 = self.factory.makeDistroSeries(meerkat, "2.0")
        meerkat_3 = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                self.factory.makeDistroSeries(meerkat, "3.0")))
        meerkat_2_devel_release = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                meerkat_2, 'devel', PackagePublishingPocket.RELEASE))
        meerkat_2_devel_updates = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                meerkat_2, 'devel', PackagePublishingPocket.UPDATES))
        meerkat_2_devel_backports = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                meerkat_2, 'devel', PackagePublishingPocket.BACKPORTS))
        meerkat_2_apples = ICanHasLinkedBranch(
            self.factory.makeSuiteSourcePackage(
                meerkat_2, 'apples'))

        links = sorted(
            [meerkat_3,
             meerkat_2_devel_updates,
             zebra,
             meerkat_2_apples,
             aardvark,
             meerkat_2_devel_backports,
             meerkat_1,
             meerkat_2_devel_release])
        self.assertIs(aardvark, links[0])
        self.assertIs(meerkat_3, links[1])
        self.assertIs(meerkat_2_apples, links[2])
        self.assertIs(meerkat_2_devel_release, links[3])
        self.assertIs(meerkat_2_devel_updates, links[4])
        self.assertIs(meerkat_2_devel_backports, links[5])
        self.assertIs(meerkat_1, links[6])
        self.assertIs(zebra, links[7])


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
