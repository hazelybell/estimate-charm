# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Packaging content class."""

__metaclass__ = type

from unittest import TestLoader

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectDeletedEvent,
    )
from testtools.testcase import ExpectedException
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.registry.errors import CannotPackageProprietaryProduct
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.packaging import (
    IPackagingUtil,
    PackagingType,
    )
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.model.packaging import Packaging
from lp.testing import (
    EventRecorder,
    login,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class TestPackaging(TestCaseWithFactory):
    """Test Packaging object."""

    layer = LaunchpadFunctionalLayer

    def test_init_notifies(self):
        """Creating a Packaging should generate an event."""
        with EventRecorder() as recorder:
            packaging = Packaging()
        (event,) = recorder.events
        self.assertIsInstance(event, ObjectCreatedEvent)
        self.assertIs(packaging, event.object)

    def test_destroySelf_notifies(self):
        """destroySelf creates a notification."""
        packaging = self.factory.makePackagingLink()
        user = self.factory.makePerson(karma=200)
        with person_logged_in(user):
            with EventRecorder() as recorder:
                removeSecurityProxy(packaging).destroySelf()
        (event,) = recorder.events
        self.assertIsInstance(event, ObjectDeletedEvent)
        self.assertIs(removeSecurityProxy(packaging), event.object)

    def test_destroySelf__not_allowed_for_anonymous(self):
        """Anonymous cannot delete a packaging."""
        packaging = self.factory.makePackagingLink()
        packaging_util = getUtility(IPackagingUtil)
        self.assertRaises(
            Unauthorized, packaging_util.deletePackaging,
            packaging.productseries, packaging.sourcepackagename,
            packaging.distroseries)

    def test_destroySelf__not_allowed_for_probationary_user(self):
        """Arbitrary users cannot delete a packaging."""
        packaging = self.factory.makePackagingLink()
        packaging_util = getUtility(IPackagingUtil)
        with person_logged_in(self.factory.makePerson()):
            self.assertRaises(
                Unauthorized, packaging_util.deletePackaging,
                packaging.productseries, packaging.sourcepackagename,
                packaging.distroseries)

    def test_destroySelf__allowed_for_non_probationary_user(self):
        """An experienced user can delete a packaging."""
        packaging = self.factory.makePackagingLink()
        sourcepackagename = packaging.sourcepackagename
        distroseries = packaging.distroseries
        productseries = packaging.productseries
        packaging_util = getUtility(IPackagingUtil)
        user = self.factory.makePerson(karma=200)
        with person_logged_in(user):
            packaging_util.deletePackaging(
                packaging.productseries, packaging.sourcepackagename,
                packaging.distroseries)
        self.assertFalse(
            packaging_util.packagingEntryExists(
                sourcepackagename, distroseries, productseries))

    def test_destroySelf__allowed_for_uploader(self):
        """A person with upload rights for the sourcepackage can
        delete a packaging link.
        """
        packaging = self.factory.makePackagingLink()
        sourcepackagename = packaging.sourcepackagename
        sourcepackage = packaging.sourcepackage
        distroseries = packaging.distroseries
        productseries = packaging.productseries
        uploader = self.factory.makePerson()
        archive = sourcepackage.get_default_archive()
        with person_logged_in(distroseries.distribution.main_archive.owner):
            archive.newPackageUploader(uploader, sourcepackage.name)
        packaging_util = getUtility(IPackagingUtil)
        with person_logged_in(uploader):
            packaging_util.deletePackaging(
                productseries, sourcepackagename, distroseries)
        self.assertFalse(
            packaging_util.packagingEntryExists(
                sourcepackagename, distroseries, productseries))

    def test_destroySelf__allowed_for_admin(self):
        """A Launchpad admin can delete a packaging."""
        packaging = self.factory.makePackagingLink()
        sourcepackagename = packaging.sourcepackagename
        distroseries = packaging.distroseries
        productseries = packaging.productseries
        packaging_util = getUtility(IPackagingUtil)
        login('foo.bar@canonical.com')
        packaging_util.deletePackaging(
            packaging.productseries, packaging.sourcepackagename,
            packaging.distroseries)
        self.assertFalse(
            packaging_util.packagingEntryExists(
                sourcepackagename, distroseries, productseries))


class PackagingUtilMixin:
    """Common items for testing IPackagingUtil."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.packaging_util = getUtility(IPackagingUtil)
        self.sourcepackagename = self.factory.makeSourcePackageName('sparkle')
        self.distroseries = self.factory.makeDistroSeries(name='dazzle')
        self.productseries = self.factory.makeProductSeries(name='glitter')
        self.owner = self.productseries.product.owner


class TestCreatePackaging(PackagingUtilMixin, TestCaseWithFactory):
    """Test PackagingUtil.packagingEntryExists."""

    def test_CreatePackaging_unique(self):
        """Packaging is unique distroseries+sourcepackagename."""
        self.packaging_util.createPackaging(
            self.productseries, self.sourcepackagename, self.distroseries,
            PackagingType.PRIME, owner=self.owner)
        sourcepackage = self.distroseries.getSourcePackage('sparkle')
        packaging = sourcepackage.direct_packaging
        self.assertEqual(packaging.distroseries, self.distroseries)
        self.assertEqual(packaging.sourcepackagename, self.sourcepackagename)
        self.assertEqual(packaging.productseries, self.productseries)

    def test_CreatePackaging_assert_unique(self):
        """Assert unique distroseries+sourcepackagename."""
        self.packaging_util.createPackaging(
            self.productseries, self.sourcepackagename, self.distroseries,
            PackagingType.PRIME, owner=self.owner)
        self.assertRaises(
            AssertionError, self.packaging_util.createPackaging,
            self.productseries, self.sourcepackagename, self.distroseries,
            PackagingType.PRIME, self.owner)

    def test_createPackaging_refuses_PROPRIETARY(self):
        """Packaging cannot be created for PROPRIETARY productseries"""
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            information_type=InformationType.PROPRIETARY)
        series = self.factory.makeProductSeries(product=product)
        expected_message = (
            'Only Public project series can be packaged, not Proprietary.')
        with person_logged_in(owner):
            with ExpectedException(CannotPackageProprietaryProduct,
                                   expected_message):
                self.packaging_util.createPackaging(
                    series, self.sourcepackagename, self.distroseries,
                    PackagingType.PRIME, owner=self.owner)

    def test_createPackaging_refuses_EMBARGOED(self):
        """Packaging cannot be created for EMBARGOED productseries"""
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            information_type=InformationType.EMBARGOED)
        series = self.factory.makeProductSeries(product=product)
        with person_logged_in(owner):
            with ExpectedException(CannotPackageProprietaryProduct,
                'Only Public project series can be packaged, not Embargoed.'):
                self.packaging_util.createPackaging(
                    series, self.sourcepackagename, self.distroseries,
                    PackagingType.PRIME, owner=self.owner)


class TestPackagingEntryExists(PackagingUtilMixin, TestCaseWithFactory):
    """Test PackagingUtil.packagingEntryExists."""

    def setUpPackaging(self):
        self.packaging_util.createPackaging(
            self.productseries, self.sourcepackagename, self.distroseries,
            PackagingType.PRIME, owner=self.owner)

    def test_packagingEntryExists_false(self):
        """Verify that non-existent entries are false."""
        self.assertFalse(
            self.packaging_util.packagingEntryExists(
                sourcepackagename=self.sourcepackagename,
                distroseries=self.distroseries))

    def test_packagingEntryExists_unique(self):
        """Packaging entries are unique to distroseries+sourcepackagename."""
        self.setUpPackaging()
        self.assertTrue(
            self.packaging_util.packagingEntryExists(
                sourcepackagename=self.sourcepackagename,
                distroseries=self.distroseries))
        other_distroseries = self.factory.makeDistroSeries(name='shimmer')
        self.assertFalse(
            self.packaging_util.packagingEntryExists(
                sourcepackagename=self.sourcepackagename,
                distroseries=other_distroseries))

    def test_packagingEntryExists_specific(self):
        """Packaging entries are also specifc to both kinds of series."""
        self.setUpPackaging()
        self.assertTrue(
            self.packaging_util.packagingEntryExists(
                sourcepackagename=self.sourcepackagename,
                distroseries=self.distroseries,
                productseries=self.productseries))
        other_productseries = self.factory.makeProductSeries(name='flash')
        self.assertFalse(
            self.packaging_util.packagingEntryExists(
                sourcepackagename=self.sourcepackagename,
                distroseries=self.distroseries,
                productseries=other_productseries))


class TestDeletePackaging(TestCaseWithFactory):
    """Test PackagingUtil.deletePackaging.

    The essential functionality: deleting a Packaging record, is already
    covered in doctests.
    """

    layer = DatabaseFunctionalLayer

    def test_deleteNonExistentPackaging(self):
        """Deleting a non-existent Packaging fails.

        PackagingUtil.deletePackaging raises an Assertion error with a
        useful message if the specified Packaging record does not exist.
        """
        # Any authenticated user can delete a packaging entry.
        login('no-priv@canonical.com')

        # Get a SourcePackageName from the sample data.
        source_package_name_set = getUtility(ISourcePackageNameSet)
        firefox_name = source_package_name_set.queryByName('mozilla-firefox')

        # Get a DistroSeries from the sample data.
        distribution_set = getUtility(IDistributionSet)
        ubuntu_hoary = distribution_set.getByName('ubuntu').getSeries('hoary')

        # Get a ProductSeries from the sample data.
        product_set = getUtility(IProductSet)
        firefox_trunk = product_set.getByName('firefox').getSeries('trunk')

        # There must not be a packaging entry associating mozilla-firefox
        # ubunt/hoary to firefox/trunk.
        packaging_util = getUtility(IPackagingUtil)
        self.assertFalse(
            packaging_util.packagingEntryExists(
                productseries=firefox_trunk,
                sourcepackagename=firefox_name,
                distroseries=ubuntu_hoary),
            "This packaging entry should not exist in sample data.")

        # If we try to delete this non-existent entry, we get an
        # AssertionError with a helpful message.
        try:
            packaging_util.deletePackaging(
                productseries=firefox_trunk,
                sourcepackagename=firefox_name,
                distroseries=ubuntu_hoary)
        except AssertionError as exception:
            self.assertEqual(
                str(exception),
                "Tried to delete non-existent Packaging: "
                "productseries=trunk/firefox, "
                "sourcepackagename=mozilla-firefox, "
                "distroseries=ubuntu/hoary")
        else:
            self.fail("AssertionError was not raised.")

    def test_deletePackaging_notifies(self):
        """Deleting a Packaging creates a notification."""
        packaging_util = getUtility(IPackagingUtil)
        packaging = self.factory.makePackagingLink()
        user = self.factory.makePerson(karma=200)
        with person_logged_in(user):
            with EventRecorder() as recorder:
                packaging_util.deletePackaging(
                    packaging.productseries, packaging.sourcepackagename,
                    packaging.distroseries)
        (event,) = recorder.events
        self.assertIsInstance(event, ObjectDeletedEvent)
        self.assertIs(removeSecurityProxy(packaging), event.object)


def test_suite():
    return TestLoader().loadTestsFromName(__name__)
