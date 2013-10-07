# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the `TranslationBuildApprover`."""

__metaclass__ = type

from zope.component import getUtility

from lp.services.config import config
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.model.approver import TranslationBuildApprover


class TestTranslationBuildApprover(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationBuildApprover, self).setUp()
        self.queue = getUtility(ITranslationImportQueue)
        self.uploader = self.factory.makePerson()

    def _makeApprovedEntries(self, series, approver, filenames):
        """Create a list of queue entries and approve them."""
        return [
            approver.approve(self.queue.addOrUpdateEntry(
                path, "#Dummy content.", False, self.uploader,
                productseries=series))
            for path in filenames]

    def _becomeBuilddMaster(self):
        """Switch db identity to the script that uses this approver."""
        switch_dbuser(config.builddmaster.dbuser)

    def test_approve_all_new(self):
        # A happy approval case, all new templates.
        filenames = [
            'po-domain1/domain1.pot',
            'po-domain2/domain2.pot',
            'po-domain3/domain3.pot',
            ]
        series = self.factory.makeProductSeries()

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(
            [RosettaImportStatus.APPROVED] * len(entries),
            [entry.status for entry in entries])
        self.assertEqual(
            ['domain1', 'domain2', 'domain3'],
            [entry.potemplate.name for entry in entries])

    def test_approve_only_pots(self):
        # Only template files will be approved.
        filenames = [
            'po/domain1.po',
            'po/eo.po',
            ]
        series = self.factory.makeProductSeries()

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(
            [RosettaImportStatus.NEEDS_REVIEW] * len(entries),
            [entry.status for entry in entries])

    def test_approve_all_existing(self):
        # A happy approval case, all existing templates.
        filenames = [
            'po-domain1/domain1.pot',
            'po-domain2/domain2.pot',
            'po-domain3/domain3.pot',
            ]
        series = self.factory.makeProductSeries()
        domain1_pot = self.factory.makePOTemplate(
            productseries=series, name='domain1')
        domain2_pot = self.factory.makePOTemplate(
            productseries=series, name='domain2')
        domain3_pot = self.factory.makePOTemplate(
            productseries=series, name='domain3')

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(
            [RosettaImportStatus.APPROVED] * len(entries),
            [entry.status for entry in entries])
        self.assertEqual(
            [domain1_pot, domain2_pot, domain3_pot],
            [entry.potemplate for entry in entries])

    def test_approve_some_existing(self):
        # A happy approval case, some existing templates.
        filenames = [
            'po-domain1/domain1.pot',
            'po-domain2/domain2.pot',
            'po-domain3/domain3.pot',
            'po-domain4/domain4.pot',
            ]
        series = self.factory.makeProductSeries()
        domain1_pot = self.factory.makePOTemplate(
            productseries=series, name='domain1')
        domain2_pot = self.factory.makePOTemplate(
            productseries=series, name='domain2')

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(
            [RosettaImportStatus.APPROVED] * len(entries),
            [entry.status for entry in entries])
        self.assertEqual(domain1_pot, entries[0].potemplate)
        self.assertEqual(domain2_pot, entries[1].potemplate)
        self.assertEqual('domain3', entries[2].potemplate.name)
        self.assertEqual('domain4', entries[3].potemplate.name)

    def test_approve_inactive_existing(self):
        # Inactive templates are approved, but they remain inactive.
        filenames = [
            'po-domain1/domain1.pot',
            ]
        series = self.factory.makeProductSeries()
        domain1_pot = self.factory.makePOTemplate(
            productseries=series, name='domain1', iscurrent=False)
        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)
        self.assertEqual(
            [RosettaImportStatus.APPROVED],
            [entry.status for entry in entries])
        self.assertEqual(
            [domain1_pot], [entry.potemplate for entry in entries])

    def test_approve_generic_name_one_new(self):
        # Generic names are OK, if there is only one.
        filenames = [
            'po/messages.pot',
            ]
        product = self.factory.makeProduct(name='fooproduct')
        series = product.getSeries('trunk')

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(RosettaImportStatus.APPROVED, entries[0].status)
        self.assertEqual('fooproduct', entries[0].potemplate.name)

    def test_approve_generic_name_one_existing(self):
        # Generic names are OK, if there is only one.
        filenames = [
            'po/messages.pot',
            ]
        series = self.factory.makeProductSeries()
        pot = self.factory.makePOTemplate(productseries=series)

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(RosettaImportStatus.APPROVED, entries[0].status)
        self.assertEqual(pot, entries[0].potemplate)

    def test_approve_generic_name_multiple_files(self):
        # Generic names in combination with others don't get approved.
        filenames = [
            'po/messages.pot',
            'mydomain/mydomain.pot',
            ]
        series = self.factory.makeProductSeries()

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(
            [RosettaImportStatus.NEEDS_REVIEW, RosettaImportStatus.APPROVED],
            [entry.status for entry in entries])
        self.assertEqual('mydomain', entries[1].potemplate.name)

    def test_approve_generic_name_multiple_templates(self):
        # Generic names don't get approved when more than one template exists.
        filenames = [
            'po/messages.pot',
            ]
        series = self.factory.makeProductSeries()
        self.factory.makePOTemplate(productseries=series)
        self.factory.makePOTemplate(productseries=series)

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entries[0].status)

    def test_approve_not_in_list(self):
        # A file that is not the list of filenames is not approved.
        filenames = [
            'po-domain1/domain1.pot',
            'po-domain2/domain2.pot',
            ]
        series = self.factory.makeProductSeries()

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(
            series, approver, filenames + ['po-domain3/domain3.pot'])

        self.assertEqual([
                RosettaImportStatus.APPROVED,
                RosettaImportStatus.APPROVED,
                RosettaImportStatus.NEEDS_REVIEW,
                ],
                [entry.status for entry in entries])

    def test_approve_by_path(self):
        # A file will be targeted to an existing template if the paths match.
        filenames = [
            'po-domain1/domain1.pot',
            'po-domain2/domain2.pot',
            ]
        series = self.factory.makeProductSeries()
        domain1_pot = self.factory.makePOTemplate(
            productseries=series, name='name1', path=filenames[0])
        domain2_pot = self.factory.makePOTemplate(
            productseries=series, name='name2', path=filenames[1])

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(
            [RosettaImportStatus.APPROVED] * len(entries),
            [entry.status for entry in entries])
        self.assertEqual(
            [domain1_pot, domain2_pot],
            [entry.potemplate for entry in entries])

    def test_approve_path_updated(self):
        # The path of an existing template will be updated with the path
        # from the entry..
        filenames = [
            'po-domain1/domain1.pot',
            ]
        series = self.factory.makeProductSeries()
        domain1_pot = self.factory.makePOTemplate(
            productseries=series, name='domain1', path='po/foo.pot')

        self._becomeBuilddMaster()
        approver = TranslationBuildApprover(filenames, productseries=series)
        entries = self._makeApprovedEntries(series, approver, filenames)

        self.assertEqual(RosettaImportStatus.APPROVED, entries[0].status)
        self.assertEqual(filenames[0], domain1_pot.path)
