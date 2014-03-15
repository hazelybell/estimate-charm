# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import logging
import re

import transaction
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.mail import stub
from lp.services.webapp import errorlog
from lp.testing import TestCaseWithFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import LaunchpadScriptLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.model.translationimportqueue import (
    TranslationImportQueue,
    )
from lp.translations.scripts.po_import import TranslationsImport


class UnexpectedException(Exception):
    """An exception type nobody was expecting."""


class OutrageousSystemError(SystemError):
    """Very serious system error."""


class TestTranslationsImport(TestCaseWithFactory):

    layer = LaunchpadScriptLayer

    def setUp(self):
        super(TestTranslationsImport, self).setUp()
        self.queue = TranslationImportQueue()
        self.script = TranslationsImport('poimport', test_args=[])
        self.script.logger.setLevel(logging.FATAL)
        self.owner = self.factory.makePerson()

    def _makeProductSeries(self):
        """Make a product series called 'trunk'."""
        return self.factory.makeProduct(owner=self.owner).getSeries('trunk')

    def _makeEntry(self, path, **kwargs):
        """Produce a queue entry."""
        uploader = kwargs.pop('uploader', self.owner)
        return self.queue.addOrUpdateEntry(
            path, '# Nothing here', False, uploader, **kwargs)

    def _makeApprovedEntry(self, uploader):
        """Produce an approved queue entry."""
        path = '%s.pot' % self.factory.getUniqueString()
        series = self.factory.makeProductSeries()
        template = self.factory.makePOTemplate(series)
        entry = self._makeEntry(
            path, uploader=uploader, potemplate=template,
            productseries=template.productseries)
        entry.status = RosettaImportStatus.APPROVED
        return entry

    def _getEmailRecipients(self):
        """List the recipients of all pending outgoing emails."""
        return sum([
            recipients
            for sender, recipients, text in stub.test_emails], [])

    def test_describeEntry_without_target(self):
        productseries = self._makeProductSeries()
        entry = self._makeEntry('foo.po', productseries=productseries)
        description = self.script._describeEntry(entry)
        pattern = "'foo.po' \(id [0-9]+\) in [A-Za-z0-9_-]+ trunk series$"
        self.assertNotEqual(None, re.match(pattern, description))

    def test_describeEntry_for_pofile(self):
        productseries = self._makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        pofile = template.newPOFile('nl')
        entry = self._makeEntry(
            'foo.po', productseries=productseries, potemplate=template,
            pofile=pofile)
        description = self.script._describeEntry(entry)
        pattern = "Dutch \(nl\) translation of .* in .* trunk \(id [0-9]+\)$"
        self.assertNotEqual(None, re.match(pattern, description))

    def test_describeEntry_for_template(self):
        productseries = self._makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        entry = self._makeEntry(
            'foo.pot', productseries=productseries, potemplate=template)
        description = self.script._describeEntry(entry)
        pattern = 'Template "[^"]+" in [A-Za-z0-9_-]+ trunk \(id [0-9]+\)$'
        self.assertNotEqual(None, re.match(pattern, description))

    def test_checkEntry(self):
        productseries = self._makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        entry = self._makeEntry(
            'foo.pot', productseries=productseries, potemplate=template)
        self.assertTrue(self.script._checkEntry(entry))

    def test_checkEntry_without_target(self):
        productseries = self._makeProductSeries()
        entry = self._makeEntry('foo.pot', productseries=productseries)
        self.assertFalse(self.script._checkEntry(entry))
        self.assertIn(
            "Entry is approved but has no place to import to.",
            self.script.failures.keys())

    def test_checkEntry_misapproved_product(self):
        productseries = self._makeProductSeries()
        template = self.factory.makePOTemplate()
        entry = self._makeEntry(
            'foo.pot', productseries=productseries, potemplate=template)
        self.assertNotEqual(None, entry.import_into)

        self.assertFalse(self.script._checkEntry(entry))
        self.assertIn(
            "Entry was approved for the wrong productseries.",
            self.script.failures.keys())

    def test_checkEntry_misapproved_package(self):
        package = self.factory.makeSourcePackage()
        other_series = self.factory.makeDistroSeries(
            distribution=package.distroseries.distribution)
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        entry = self._makeEntry(
            'foo.pot', sourcepackagename=package.sourcepackagename,
            distroseries=other_series, potemplate=template)
        self.assertNotEqual(None, entry.import_into)

        self.assertFalse(self.script._checkEntry(entry))
        self.assertIn(
            "Entry was approved for the wrong distroseries.",
            self.script.failures.keys())

    def test_handle_serious_error(self):
        productseries = self._makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        entry = self._makeEntry(
            'snaf.pot', productseries=productseries, potemplate=template)
        entry.potemplate = template
        entry.status = RosettaImportStatus.APPROVED
        self.assertNotEqual(None, entry.import_into)

        message = "The system has exploded."
        self.script._importEntry = FakeMethod(
            failure=OutrageousSystemError(message))
        self.assertRaises(OutrageousSystemError, self.script.main)

        self.assertEqual(RosettaImportStatus.FAILED, entry.status)
        self.assertEqual(message, entry.error_output)

    def test_handle_unexpected_exception(self):
        # Unexpected exceptions during import are caught and reported.
        productseries = self._makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        entry = self._makeEntry(
            'foo.pot', productseries=productseries, potemplate=template)
        entry.potemplate = template
        entry.status = RosettaImportStatus.APPROVED
        self.assertNotEqual(None, entry.import_into)

        message = "Nobody expects the Spanish Inquisition!"
        self.script._importEntry = FakeMethod(
            failure=UnexpectedException(message))
        self.script.main()

        self.assertEqual(RosettaImportStatus.FAILED, entry.status)
        self.assertEqual(message, entry.error_output)

    def test_main_leaves_oops_handling_alone(self):
        """Ensure that script.main is not altering oops reporting."""
        self.script.main()
        default_reporting = errorlog.ErrorReportingUtility()
        default_reporting.configure('error_reports')
        self.assertEqual(default_reporting.oops_prefix,
                         errorlog.globalErrorUtility.oops_prefix)

    def test_notifies_uploader(self):
        entry = self._makeApprovedEntry(self.owner)
        transaction.commit()
        self.script._importEntry(entry)
        transaction.commit()
        self.assertEqual(
            [self.owner.preferredemail.email], self._getEmailRecipients())

    def test_does_not_notify_vcs_imports(self):
        vcs_imports = getUtility(ILaunchpadCelebrities).vcs_imports
        entry = self._makeApprovedEntry(vcs_imports)
        transaction.commit()
        self.script._importEntry(entry)
        transaction.commit()
        self.assertEqual([], self._getEmailRecipients())
