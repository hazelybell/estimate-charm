# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser tests for Packaging actions."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.packaging import (
    IPackagingUtil,
    PackagingType,
    )
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.testing import (
    login,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    PageTestLayer,
    )
from lp.testing.pages import setupBrowser
from lp.testing.views import create_initialized_view


class TestProductSeriesUbuntuPackagingView(TestCaseWithFactory):
    """Browser tests for deletion of Packaging objects."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductSeriesUbuntuPackagingView, self).setUp()
        self.ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.hoary = self.ubuntu.getSeries('hoary')
        self.sourcepackagename = self.factory.makeSourcePackageName('hot')
        self.sourcepackage = self.factory.makeSourcePackage(
            sourcepackagename=self.sourcepackagename, distroseries=self.hoary)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.sourcepackagename, distroseries=self.hoary)
        self.product = self.factory.makeProduct(name="hot", displayname='Hot')
        self.productseries = self.factory.makeProductSeries(
            product=self.product, name='hotter')
        self.packaging_util = getUtility(IPackagingUtil)

    def test_no_error_when_trying_to_readd_same_package(self):
        # There is no reason to display an error when the user's action
        # wouldn't cause a state change.
        self.packaging_util.createPackaging(
            productseries=self.productseries,
            sourcepackagename=self.sourcepackagename,
            distroseries=self.hoary, packaging=PackagingType.PRIME,
            owner=self.product.owner)

        form = {
            'field.distroseries': self.hoary.name,
            'field.sourcepackagename': self.sourcepackagename.name,
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.productseries, '+ubuntupkg', form=form)
        self.assertEqual([], view.errors)

    def test_cannot_link_to_linked_package(self):
        # Once a distro series sourcepackage is linked to a product series,
        # no other product series can link to it.
        form = {
            'field.distroseries': 'hoary',
            'field.sourcepackagename': 'hot',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.productseries, '+ubuntupkg', form=form)
        self.assertEqual([], view.errors)
        other_productseries = self.factory.makeProductSeries(
            product=self.product, name='hottest')
        form = {
            'field.distroseries': 'hoary',
            'field.sourcepackagename': 'hot',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            other_productseries, '+ubuntupkg', form=form)
        view_errors = [
            'The <a href="http://launchpad.dev/ubuntu/hoary/+source/hot">'
             'hot</a> package in Hoary is already linked to another series.']
        self.assertEqual(view_errors, view.errors)

    def test_sourcepackgename_required(self):
        # A source package name must be provided.
        form = {
            'field.distroseries': 'hoary',
            'field.sourcepackagename': '',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.productseries, '+ubuntupkg', form=form)
        self.assertEqual(1, len(view.errors))
        self.assertEqual('sourcepackagename', view.errors[0].field_name)
        self.assertEqual('Required input is missing.', view.errors[0].doc())

    def test_cannot_link_to_nonexistant_ubuntu_package(self):
        # In the case of full functionality distributions like Ubuntu, the
        # source package must be published in the distro series.
        self.factory.makeSourcePackageName('vapor')
        form = {
            'field.distroseries': 'hoary',
            'field.sourcepackagename': 'vapor',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.productseries, '+ubuntupkg', form=form)
        view_errors = ['The source package is not published in Hoary.']
        self.assertEqual(view_errors, view.errors)

    def test_link_older_distroseries(self):
        # The view allows users to link to older Ubuntu series.
        warty = self.ubuntu.getSeries('warty')
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=self.sourcepackagename, distroseries=warty)
        form = {
            'field.distroseries': 'warty',
            'field.sourcepackagename': 'hot',
            'field.actions.continue': 'Continue',
            }
        view = create_initialized_view(
            self.productseries, '+ubuntupkg', form=form)
        self.assertEqual([], view.errors)
        has_packaging = self.packaging_util.packagingEntryExists(
            self.sourcepackagename, warty, self.productseries)
        self.assertTrue(has_packaging)


class TestBrowserDeletePackaging(TestCaseWithFactory):
    """Browser tests for deletion of Packaging objects."""

    layer = PageTestLayer

    def setUp(self):
        super(TestBrowserDeletePackaging, self).setUp()
        # Only the person which created the packaging, admins
        # and other people with certain privileges can delete a
        # packaging. Since the sample data record we'll use for
        # deletion testing does not have any owner set, we'll
        # log in as an admin.
        self.user_browser = setupBrowser(
            auth="Basic foo.bar@canonical.com:test")

    def test_deletionIsPersistent(self):
        # Test that deleting a Packaging entry is persistent.
        #
        # When developing the initial Packaging deletion feature, we hit a bug
        # where submitting the Packaging deletion form apparently worked, and
        # rendered a page where the deleted Packaging was not present, but a
        # silent error occurred while rendering the page, which caused the
        # transaction to abort. As a consequence, the Packaging deletion was
        # not recorded, and reloading the page would make the deleted
        # Packaging data reappear on the page.
        # Check sampledata expectations
        login('no-priv@canonical.com')
        source_package_name_set = getUtility(ISourcePackageNameSet)
        package_name = source_package_name_set.queryByName('alsa-utils')
        distribution_set = getUtility(IDistributionSet)
        distroseries = distribution_set.getByName('ubuntu').getSeries('warty')
        product_set = getUtility(IProductSet)
        product = product_set.getByName('alsa-utils')
        productseries = product.getSeries('trunk')
        packaging_util = getUtility(IPackagingUtil)
        self.assertTrue(packaging_util.packagingEntryExists(
            productseries=productseries,
            sourcepackagename=package_name,
            distroseries=distroseries))
        logout()
        # Delete the packaging
        user_browser = self.user_browser
        user_browser.open('http://launchpad.dev/ubuntu/+source/alsa-utils')
        link = user_browser.getLink(
            url='/ubuntu/warty/+source/alsa-utils/+remove-packaging')
        link.click()
        user_browser.getControl('Unlink').click()
        # Check that the change was committed.
        login('no-priv@canonical.com')
        self.assertFalse(packaging_util.packagingEntryExists(
            productseries=productseries,
            sourcepackagename=package_name,
            distroseries=distroseries))
