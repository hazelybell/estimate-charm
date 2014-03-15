# Copyright 2009, 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for ISourcePackage implementations."""

__metaclass__ = type

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectDeletedEvent,
    )
from storm.locals import Store
from testtools.testcase import ExpectedException
import transaction
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.checker import canAccess
from zope.security.management import checkPermission
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.model.seriessourcepackagebranch import (
    SeriesSourcePackageBranchSet,
    )
from lp.registry.errors import CannotPackageProprietaryProduct
from lp.registry.interfaces.distribution import NoPartnerArchive
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.distributionsourcepackage import (
    DistributionSourcePackage,
    )
from lp.registry.model.packaging import Packaging
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.component import IComponentSet
from lp.testing import (
    EventRecorder,
    person_logged_in,
    TestCaseWithFactory,
    WebServiceTestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestSourcePackage(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_interface_consistency(self):
        package = self.factory.makeSourcePackage()
        verifyObject(ISourcePackage, removeSecurityProxy(package))

    def test_path(self):
        sourcepackage = self.factory.makeSourcePackage()
        self.assertEqual(
            '%s/%s/%s' % (
                sourcepackage.distribution.name,
                sourcepackage.distroseries.name,
                sourcepackage.sourcepackagename.name),
            sourcepackage.path)

    def test_getBranch_no_branch(self):
        # If there's no official branch for that pocket of a source package,
        # getBranch returns None.
        sourcepackage = self.factory.makeSourcePackage()
        branch = sourcepackage.getBranch(PackagePublishingPocket.RELEASE)
        self.assertIs(None, branch)

    def test_getBranch_exists(self):
        # If there is a SeriesSourcePackageBranch entry for that source
        # package and pocket, then return the branch.
        sourcepackage = self.factory.makeSourcePackage()
        registrant = self.factory.makePerson()
        branch = self.factory.makePackageBranch(sourcepackage=sourcepackage)
        SeriesSourcePackageBranchSet.new(
            sourcepackage.distroseries, PackagePublishingPocket.RELEASE,
            sourcepackage.sourcepackagename, branch, registrant)
        official_branch = sourcepackage.getBranch(
            PackagePublishingPocket.RELEASE)
        self.assertEqual(branch, official_branch)

    def test_setBranch(self):
        # We can set the official branch for a pocket of a source package.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        registrant = self.factory.makePerson()
        branch = self.factory.makePackageBranch(sourcepackage=sourcepackage)
        with person_logged_in(sourcepackage.distribution.owner):
            sourcepackage.setBranch(pocket, branch, registrant)
        self.assertEqual(branch, sourcepackage.getBranch(pocket))
        # A DSP was created for the official branch.
        new_dsp = DistributionSourcePackage._get(
            sourcepackage.distribution, sourcepackage.sourcepackagename)
        self.assertIsNot(None, new_dsp)

    def test_change_branch_once_set(self):
        # We can change the official branch for a a pocket of a source package
        # even after it has already been set.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        registrant = self.factory.makePerson()
        branch = self.factory.makePackageBranch(sourcepackage=sourcepackage)
        new_branch = self.factory.makePackageBranch(
            sourcepackage=sourcepackage)
        with person_logged_in(sourcepackage.distribution.owner):
            sourcepackage.setBranch(pocket, branch, registrant)
            sourcepackage.setBranch(pocket, new_branch, registrant)
        self.assertEqual(new_branch, sourcepackage.getBranch(pocket))

    def test_unsetBranch(self):
        # Setting the official branch for a pocket to 'None' breaks the link
        # between the branch and pocket.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        registrant = self.factory.makePerson()
        branch = self.factory.makePackageBranch(sourcepackage=sourcepackage)
        with person_logged_in(sourcepackage.distribution.owner):
            sourcepackage.setBranch(pocket, branch, registrant)
            sourcepackage.setBranch(pocket, None, registrant)
        self.assertIs(None, sourcepackage.getBranch(pocket))

    def test_unsetBranch_delete_unpublished_dsp(self):
        # Setting the official branch for a pocket to 'None' deletes the
        # official DSP record if there is no SPPH.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        registrant = self.factory.makePerson()
        branch = self.factory.makePackageBranch(sourcepackage=sourcepackage)
        with person_logged_in(sourcepackage.distribution.owner):
            sourcepackage.setBranch(pocket, branch, registrant)
            sourcepackage.setBranch(pocket, None, registrant)
        new_dsp = DistributionSourcePackage._get(
            sourcepackage.distribution, sourcepackage.sourcepackagename)
        self.assertIs(None, new_dsp)

    def test_linked_branches(self):
        # ISourcePackage.linked_branches is a mapping of pockets to branches.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        registrant = self.factory.makePerson()
        branch = self.factory.makePackageBranch(sourcepackage=sourcepackage)
        with person_logged_in(sourcepackage.distribution.owner):
            sourcepackage.setBranch(pocket, branch, registrant)
        self.assertEqual(
            [(pocket, branch)], list(sourcepackage.linked_branches))

    def test_getSuiteSourcePackage(self):
        # ISourcePackage.getSuiteSourcePackage returns the suite source
        # package object for the given pocket.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        ssp = sourcepackage.getSuiteSourcePackage(pocket)
        self.assertEqual(sourcepackage, ssp.sourcepackage)
        self.assertEqual(pocket, ssp.pocket)

    def test_path_to_release_pocket(self):
        # ISourcePackage.getPocketPath returns the path to a pocket. For the
        # RELEASE pocket, it's the same as the package path.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.RELEASE
        self.assertEqual(
            sourcepackage.path, sourcepackage.getPocketPath(pocket))

    def test_path_to_non_release_pocket(self):
        # ISourcePackage.getPocketPath returns the path to a pocket. For a
        # non-RELEASE pocket, it's the same as the package path, except with
        # series-pocket for the middle component.
        sourcepackage = self.factory.makeSourcePackage()
        pocket = PackagePublishingPocket.SECURITY
        path = '%s/%s-%s/%s' % (
            sourcepackage.distribution.name,
            sourcepackage.distroseries.name,
            pocket.name.lower(),
            sourcepackage.name)
        self.assertEqual(path, sourcepackage.getPocketPath(pocket))

    def test_development_version(self):
        # ISourcePackage.development_version gets the development version of
        # the source package.
        distribution = self.factory.makeDistribution()
        dev_series = self.factory.makeDistroSeries(
            distribution=distribution, status=SeriesStatus.DEVELOPMENT)
        other_series = self.factory.makeDistroSeries(
            distribution=distribution, status=SeriesStatus.OBSOLETE)
        self.assertEqual(dev_series, distribution.currentseries)
        dev_sourcepackage = self.factory.makeSourcePackage(
            distroseries=dev_series)
        other_sourcepackage = self.factory.makeSourcePackage(
            distroseries=other_series,
            sourcepackagename=dev_sourcepackage.sourcepackagename)
        self.assertEqual(
            dev_sourcepackage, other_sourcepackage.development_version)
        self.assertEqual(
            dev_sourcepackage, dev_sourcepackage.development_version)

    def test_distribution_sourcepackage(self):
        # ISourcePackage.distribution_sourcepackage is the distribution source
        # package for the ISourcePackage.
        sourcepackage = self.factory.makeSourcePackage()
        distribution = sourcepackage.distribution
        distribution_sourcepackage = distribution.getSourcePackage(
            sourcepackage.sourcepackagename)
        self.assertEqual(
            distribution_sourcepackage,
            sourcepackage.distribution_sourcepackage)

    def test_default_archive(self):
        # The default archive of a source package is the primary archive of
        # its distribution.
        sourcepackage = self.factory.makeSourcePackage()
        distribution = sourcepackage.distribution
        self.assertEqual(
            distribution.main_archive, sourcepackage.get_default_archive())

    def test_default_archive_partner(self):
        # If the source package was most recently uploaded to a partner
        # component, then its default archive is the partner archive for the
        # distribution.
        sourcepackage = self.factory.makeSourcePackage()
        partner = getUtility(IComponentSet)['partner']
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackage.sourcepackagename,
            distroseries=sourcepackage.distroseries,
            component=partner,
            status=PackagePublishingStatus.PUBLISHED)
        distribution = sourcepackage.distribution
        expected_archive = self.factory.makeArchive(
            distribution=distribution,
            purpose=ArchivePurpose.PARTNER)
        self.assertEqual(
            expected_archive, sourcepackage.get_default_archive())

    def test_default_archive_specified_component(self):
        # If the component is explicitly specified as partner, then we return
        # the partner archive.
        sourcepackage = self.factory.makeSourcePackage()
        partner = getUtility(IComponentSet)['partner']
        distribution = sourcepackage.distribution
        expected_archive = self.factory.makeArchive(
            distribution=distribution,
            purpose=ArchivePurpose.PARTNER)
        self.assertEqual(
            expected_archive,
            sourcepackage.get_default_archive(component=partner))

    def test_default_archive_partner_doesnt_exist(self):
        # If the default archive ought to be the partner archive (because the
        # last published upload was to a partner component) then
        # default_archive will raise an exception.
        sourcepackage = self.factory.makeSourcePackage()
        partner = getUtility(IComponentSet)['partner']
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackage.sourcepackagename,
            distroseries=sourcepackage.distroseries,
            component=partner,
            status=PackagePublishingStatus.PUBLISHED)
        self.assertRaises(
            NoPartnerArchive, sourcepackage.get_default_archive)

    def test_source_package_summary_no_releases_returns_None(self):
        sourcepackage = self.factory.makeSourcePackage()
        self.assertEqual(sourcepackage.summary, None)

    def test_source_package_summary_with_releases_returns_None(self):
        sourcepackage = self.factory.makeSourcePackage()
        self.factory.makeSourcePackageRelease(
            sourcepackagename=sourcepackage.sourcepackagename)
        self.assertEqual(sourcepackage.summary, None)

    def test_source_package_summary_with_binaries_returns_list(self):
        sp = getUtility(
            ILaunchpadCelebrities).ubuntu['warty'].getSourcePackage(
            'mozilla-firefox')

        expected_summary = (
            u'mozilla-firefox: Mozilla Firefox Web Browser\n'
            u'mozilla-firefox-data: No summary available for '
            u'mozilla-firefox-data in ubuntu warty.')
        self.assertEqual(''.join(expected_summary), sp.summary)

    def test_deletePackaging(self):
        """Ensure deletePackaging completely removes packaging."""
        user = self.factory.makePerson(karma=200)
        packaging = self.factory.makePackagingLink()
        packaging_id = packaging.id
        store = Store.of(packaging)
        with person_logged_in(user):
            packaging.sourcepackage.deletePackaging()
        result = store.find(Packaging, Packaging.id == packaging_id)
        self.assertIs(None, result.one())

    def test_setPackaging__new(self):
        """setPackaging() creates a Packaging link."""
        sourcepackage = self.factory.makeSourcePackage()
        productseries = self.factory.makeProductSeries()
        sourcepackage.setPackaging(
            productseries, owner=self.factory.makePerson())
        packaging = sourcepackage.direct_packaging
        self.assertEqual(packaging.productseries, productseries)

    def test_setPackaging__change_existing_entry(self):
        """setPackaging() changes existing Packaging links."""
        sourcepackage = self.factory.makeSourcePackage()
        productseries = self.factory.makeProductSeries()
        other_series = self.factory.makeProductSeries()
        user = self.factory.makePerson(karma=200)
        registrant = self.factory.makePerson()
        with EventRecorder() as recorder:
            with person_logged_in(user):
                sourcepackage.setPackaging(productseries, owner=registrant)
                sourcepackage.setPackaging(other_series, owner=registrant)
                packaging = sourcepackage.direct_packaging
                self.assertEqual(packaging.productseries, other_series)
        # The first call of setPackaging() created an ObjectCreatedEvent;
        # the second call created an ObjectDeletedEvent for the deletion
        # of the old packaging link, and another ObjectCreatedEvent
        # for the new Packaging.
        event1, event2, event3 = recorder.events
        self.assertIsInstance(event1, ObjectCreatedEvent)
        self.assertIsInstance(event2, ObjectDeletedEvent)
        self.assertIsInstance(event3, ObjectCreatedEvent)

    def test_refuses_PROPRIETARY(self):
        """Packaging cannot be created for PROPRIETARY productseries"""
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            information_type=InformationType.PROPRIETARY)
        series = self.factory.makeProductSeries(product=product)
        ubuntu_series = self.factory.makeUbuntuDistroSeries()
        sp = self.factory.makeSourcePackage(distroseries=ubuntu_series)
        with person_logged_in(owner):
            with ExpectedException(
                CannotPackageProprietaryProduct,
                'Only Public project series can be packaged, not '
                'Proprietary.'):
                sp.setPackaging(series, owner)

    def test_setPackagingReturnSharingDetailPermissions__ordinary_user(self):
        """An ordinary user can create a packaging link but he cannot
        set the series' branch or translation syncronisation settings,
        or the translation usage settings of the product.
        """
        sourcepackage = self.factory.makeSourcePackage()
        productseries = self.factory.makeProductSeries()
        packaging_owner = self.factory.makePerson(karma=100)
        with person_logged_in(packaging_owner):
            permissions = (
                sourcepackage.setPackagingReturnSharingDetailPermissions(
                    productseries, packaging_owner))
            self.assertEqual(productseries, sourcepackage.productseries)
            self.assertFalse(
                packaging_owner.canWrite(productseries, 'branch'))
            self.assertFalse(
                packaging_owner.canWrite(
                    productseries, 'translations_autoimport_mode'))
            self.assertFalse(
                packaging_owner.canWrite(
                    productseries.product, 'translations_usage'))
            expected = {
                'user_can_change_product_series': True,
                'user_can_change_branch': False,
                'user_can_change_translation_usage': False,
                'user_can_change_translations_autoimport_mode': False,
                }
            self.assertEqual(expected, permissions)

    def test_getSharingDetailPermissions__ordinary_user(self):
        """An ordinary user cannot set the series' branch or translation
        synchronisation settings, or the translation usage settings of the
        product.
        """
        user = self.factory.makePerson(karma=100)
        packaging = self.factory.makePackagingLink()
        sourcepackage = packaging.sourcepackage
        productseries = packaging.productseries
        with person_logged_in(user):
            permissions = sourcepackage.getSharingDetailPermissions()
            self.assertEqual(productseries, sourcepackage.productseries)
            self.assertFalse(
                user.canWrite(productseries, 'branch'))
            self.assertFalse(
                user.canWrite(
                    productseries, 'translations_autoimport_mode'))
            self.assertFalse(
                user.canWrite(
                    productseries.product, 'translations_usage'))
            expected = {
                'user_can_change_product_series': True,
                'user_can_change_branch': False,
                'user_can_change_translation_usage': False,
                'user_can_change_translations_autoimport_mode': False,
                }
            self.assertEqual(expected, permissions)

    def makeDistinctOwnerProductSeries(self):
        # Ensure productseries owner is distinct from product owner.
        return self.factory.makeProductSeries(
            owner=self.factory.makePerson())

    def test_getSharingDetailPermissions__product_owner(self):
        """A product owner can create a packaging link, and he can set the
        series' branch and the translation syncronisation settings, and the
        translation usage settings of the product.
        """
        productseries = self.makeDistinctOwnerProductSeries()
        product = productseries.product
        with person_logged_in(product.owner):
            packaging = self.factory.makePackagingLink(
                productseries=productseries, owner=product.owner)
            sourcepackage = packaging.sourcepackage
            permissions = sourcepackage.getSharingDetailPermissions()
            self.assertEqual(productseries, sourcepackage.productseries)
            self.assertTrue(product.owner.canWrite(productseries, 'branch'))
            self.assertTrue(
                product.owner.canWrite(
                    productseries, 'translations_autoimport_mode'))
            self.assertTrue(
                product.owner.canWrite(
                    productseries.product, 'translations_usage'))
            expected = {
                'user_can_change_product_series': True,
                'user_can_change_branch': True,
                'user_can_change_translation_usage': True,
                'user_can_change_translations_autoimport_mode': True,
                }
            self.assertEqual(expected, permissions)

    def test_getSharingDetailPermissions_change_product(self):
        """Test user_can_change_product_series.

        Until a Packaging is created, anyone can change product series.
        Afterward, random people cannot change product series.
        """
        sourcepackage = self.factory.makeSourcePackage()
        person1 = self.factory.makePerson(karma=100)
        person2 = self.factory.makePerson()

        def can_change_product_series():
            return sourcepackage.getSharingDetailPermissions()[
                    'user_can_change_product_series']
        with person_logged_in(person1):
            self.assertTrue(can_change_product_series())
        with person_logged_in(person2):
            self.assertTrue(can_change_product_series())
        self.factory.makePackagingLink(
            sourcepackage=sourcepackage, owner=person1)
        with person_logged_in(person1):
            self.assertTrue(can_change_product_series())
        with person_logged_in(person2):
            self.assertFalse(can_change_product_series())

    def test_getSharingDetailPermissions_no_product_series(self):
        sourcepackage = self.factory.makeSourcePackage()
        expected = {
            'user_can_change_product_series': True,
            'user_can_change_branch': False,
            'user_can_change_translation_usage': False,
            'user_can_change_translations_autoimport_mode': False}
        with person_logged_in(self.factory.makePerson()):
            self.assertEqual(
                expected, sourcepackage.getSharingDetailPermissions())

    def test_getSharingDetailPermissions_no_user(self):
        sourcepackage = self.factory.makeSourcePackage()
        expected = {
            'user_can_change_product_series': False,
            'user_can_change_branch': False,
            'user_can_change_translation_usage': False,
            'user_can_change_translations_autoimport_mode': False}
        self.assertEqual(
            expected, sourcepackage.getSharingDetailPermissions())

    def test_drivers_are_distroseries(self):
        # SP.drivers returns the drivers for the distroseries.
        distroseries = self.factory.makeDistroSeries()
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        self.assertNotEqual([], distroseries.drivers)
        self.assertEqual(sourcepackage.drivers, distroseries.drivers)

    def test_personHasDriverRights_true(self):
        # A distroseries driver has driver permissions on source packages.
        distroseries = self.factory.makeDistroSeries()
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        driver = distroseries.drivers[0]
        self.assertTrue(sourcepackage.personHasDriverRights(driver))

    def test_personHasDriverRights_false(self):
        # A non-owner/driver/admin does not have driver rights.
        distroseries = self.factory.makeDistroSeries()
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        non_priv_user = self.factory.makePerson()
        self.assertFalse(sourcepackage.personHasDriverRights(non_priv_user))

    def test_owner_is_distroseries_owner(self):
        # The source package owner differs to the ditroseries owner.
        distroseries = self.factory.makeDistroSeries()
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        self.assertIsNot(None, sourcepackage.owner)
        self.assertEqual(distroseries.owner, sourcepackage.owner)
        self.assertTrue(
            sourcepackage.personHasDriverRights(distroseries.owner))


class TestSourcePackageWebService(WebServiceTestCase):

    def test_setPackaging(self):
        """setPackaging is accessible and works."""
        sourcepackage = self.factory.makeSourcePackage()
        self.assertIs(None, sourcepackage.direct_packaging)
        productseries = self.factory.makeProductSeries()
        transaction.commit()
        ws_sourcepackage = self.wsObject(sourcepackage)
        ws_productseries = self.wsObject(productseries)
        ws_sourcepackage.setPackaging(productseries=ws_productseries)
        transaction.commit()
        self.assertEqual(
            productseries, sourcepackage.direct_packaging.productseries)

    def test_deletePackaging(self):
        """Deleting a packaging should work."""
        user = self.factory.makePerson(karma=200)
        packaging = self.factory.makePackagingLink()
        sourcepackage = packaging.sourcepackage
        transaction.commit()
        self.wsObject(sourcepackage, user=user).deletePackaging()
        transaction.commit()
        self.assertIs(None, sourcepackage.direct_packaging)

    def test_deletePackaging_with_no_packaging(self):
        """Deleting when there's no packaging should be a no-op."""
        sourcepackage = self.factory.makeSourcePackage()
        transaction.commit()
        self.wsObject(sourcepackage).deletePackaging()
        transaction.commit()
        self.assertIs(None, sourcepackage.direct_packaging)


class TestSourcePackageSecurity(TestCaseWithFactory):
    """Tests for source package security."""

    layer = DatabaseFunctionalLayer

    def test_admins_have_launchpad_Edit(self):
        admin = self.factory.makeAdministrator()
        sourcepackage = self.factory.makeSourcePackage()
        with person_logged_in(admin):
            self.assertTrue(
                checkPermission('launchpad.Edit', sourcepackage),
                "Administrators should have launchpad.Edit on source "
                "packages.")

    def test_distro_owner_have_launchpad_Edit(self):
        sourcepackage = self.factory.makeSourcePackage()
        with person_logged_in(sourcepackage.distribution.owner):
            self.assertTrue(
                checkPermission('launchpad.Edit', sourcepackage),
                "Distribution owner should have launchpad.Edit on source "
                "packages.")

    def test_uploader_has_launchpad_edit(self):
        sourcepackage = self.factory.makeSourcePackage()
        uploader = self.factory.makePerson()
        archive = sourcepackage.get_default_archive()
        with person_logged_in(sourcepackage.distribution.main_archive.owner):
            archive.newPackageUploader(uploader, sourcepackage.name)
        with person_logged_in(uploader):
            self.assertTrue(
                checkPermission('launchpad.Edit', sourcepackage),
                "Uploader to the package should have launchpad.Edit on "
                "source packages.")

    def test_uploader_has_launchpad_edit_on_obsolete_series(self):
        obsolete_series = self.factory.makeDistroSeries(
            status=SeriesStatus.OBSOLETE)
        archive = obsolete_series.distribution.main_archive
        removeSecurityProxy(archive).permit_obsolete_series_uploads = True
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=obsolete_series)
        uploader = self.factory.makePerson()
        archive = sourcepackage.get_default_archive()
        with person_logged_in(sourcepackage.distribution.main_archive.owner):
            archive.newPackageUploader(uploader, sourcepackage.name)
        with person_logged_in(uploader):
            self.assertTrue(
                checkPermission('launchpad.Edit', sourcepackage),
                "Uploader to the package should have launchpad.Edit on "
                "source packages in an OBSOLETE series.")

    def test_uploader_have_launchpad_edit_on_current_series(self):
        current_series = self.factory.makeDistroSeries(
            status=SeriesStatus.CURRENT)
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=current_series)
        uploader = self.factory.makePerson()
        archive = sourcepackage.get_default_archive()
        with person_logged_in(sourcepackage.distribution.main_archive.owner):
            archive.newPackageUploader(uploader, sourcepackage.name)
        with person_logged_in(uploader):
            self.assertTrue(
                checkPermission('launchpad.Edit', sourcepackage),
                "Uploader to the package should have launchpad.Edit on "
                "source packages in a CURRENT series.")

    def test_uploader_have_launchpad_edit_on_supported_series(self):
        supported_series = self.factory.makeDistroSeries(
            status=SeriesStatus.SUPPORTED)
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=supported_series)
        uploader = self.factory.makePerson()
        archive = sourcepackage.get_default_archive()
        with person_logged_in(sourcepackage.distribution.main_archive.owner):
            archive.newPackageUploader(uploader, sourcepackage.name)
        with person_logged_in(uploader):
            self.assertTrue(
                checkPermission('launchpad.Edit', sourcepackage),
                "Uploader to the package should have launchpad.Edit on "
                "source packages in a SUPPORTED series.")

    def test_john_doe_cannot_edit(self):
        sourcepackage = self.factory.makeSourcePackage()
        john_doe = self.factory.makePerson()
        with person_logged_in(john_doe):
            self.failIf(
                checkPermission('launchpad.Edit', sourcepackage),
                "Random user shouldn't have launchpad.Edit on source "
                "packages.")

    def test_cannot_setBranch(self):
        sourcepackage = self.factory.makeSourcePackage()
        self.failIf(
            canAccess(sourcepackage, 'setBranch'),
            "setBranch should only be available to admins and uploaders")


class TestSourcePackageViews(TestCaseWithFactory):
    """Tests for source package view classes."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.owner = self.factory.makePerson()
        self.product = self.factory.makeProduct(
            name='bonkers', displayname='Bonkers', owner=self.owner)

        self.obsolete_productseries = self.factory.makeProductSeries(
            name='obsolete', product=self.product)
        with person_logged_in(self.product.owner):
            self.obsolete_productseries.status = SeriesStatus.OBSOLETE

        self.dev_productseries = self.factory.makeProductSeries(
            name='current', product=self.product)
        with person_logged_in(self.product.owner):
            self.dev_productseries.status = SeriesStatus.DEVELOPMENT

        self.distribution = self.factory.makeDistribution(
            name='youbuntu', displayname='Youbuntu', owner=self.owner)
        self.distroseries = self.factory.makeDistroSeries(
            name='busy', distribution=self.distribution)
        self.sourcepackagename = self.factory.makeSourcePackageName(
            name='bonkers')
        self.package = self.factory.makeSourcePackage(
            sourcepackagename=self.sourcepackagename,
            distroseries=self.distroseries)

    def test_editpackaging_obsolete_series_in_vocabulary(self):
        # The sourcepackage's current product series is included in
        # the vocabulary even if it is obsolete.
        self.package.setPackaging(self.obsolete_productseries, self.owner)
        form = {
            'field.product': 'bonkers',
            'field.actions.continue': 'Continue',
            'field.__visited_steps__': 'sourcepackage_change_upstream_step1',
            }
        view = create_initialized_view(
            self.package, name='+edit-packaging', form=form,
            principal=self.owner)
        self.assertEqual([], view.view.errors)
        self.assertEqual(
            self.obsolete_productseries,
            view.view.form_fields['productseries'].field.default,
            "The form's default productseries must be the current one.")
        options = [term.token
                   for term in view.view.widgets['productseries'].vocabulary]
        self.assertEqual(
            ['trunk', 'current', 'obsolete'], options,
            "The obsolete series must be in the vocabulary.")

    def test_editpackaging_obsolete_series_not_in_vocabulary(self):
        # Obsolete productseries are normally not in the vocabulary.
        form = {
            'field.product': 'bonkers',
            'field.actions.continue': 'Continue',
            'field.__visited_steps__': 'sourcepackage_change_upstream_step1',
            }
        view = create_initialized_view(
            self.package, name='+edit-packaging', form=form,
            principal=self.owner)
        self.assertEqual([], view.view.errors)
        self.assertEqual(
            None,
            view.view.form_fields['productseries'].field.default,
            "The form's default productseries must be None.")
        options = [term.token
                   for term in view.view.widgets['productseries'].vocabulary]
        self.assertEqual(
            ['trunk', 'current'], options,
            "The obsolete series must NOT be in the vocabulary.")
