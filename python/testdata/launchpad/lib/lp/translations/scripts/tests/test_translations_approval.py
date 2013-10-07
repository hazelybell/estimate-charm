# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import logging

import transaction

from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadScriptLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.model.translationimportqueue import (
    TranslationImportQueue,
    )
from lp.translations.scripts.import_queue_gardener import ImportQueueGardener


class TestTranslationsImportApproval(TestCaseWithFactory):

    layer = LaunchpadScriptLayer

    def setUp(self):
        super(TestTranslationsImportApproval, self).setUp()
        self.queue = TranslationImportQueue()
        self.script = ImportQueueGardener(
            'translations-import-queue-gardener',
            dbuser='translations_import_queue_gardener',
            test_args=[])
        self.script.logger.setLevel(logging.FATAL)
        self.owner = self.factory.makePerson()
        self.productseries = self.factory.makeProductSeries()

    def test_templates_with_unique_directories_are_approved(self):
        # If there are multiple templates with unique directories then the
        # approval is ok.

        # Make two valid templates with different directories.
        self.factory.makePOTemplate(
            path='po/evolution-3.2.pot',
            productseries=self.productseries)
        self.factory.makePOTemplate(
            path='other-po/evolution-3.0.pot',
            productseries=self.productseries)
        tiqe = self.factory.makeTranslationImportQueueEntry(
            path='po/fr.po', productseries=self.productseries)
        transaction.commit()
        self.assertIsNone(tiqe.import_into)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, tiqe.status)
        self.script.main()
        self.assertIsNotNone(tiqe.import_into)
        self.assertEqual(RosettaImportStatus.APPROVED, tiqe.status)

    def test_inactive_templates_do_not_block_approval(self):
        # If all but one of the templates with the same path directory are
        # marked as obsolete, the approval proceeds.
        # See bug 867411 for more details.

        # Make a valid template.
        self.factory.makePOTemplate(
            path='po/evolution-3.2.pot',
            productseries=self.productseries)
        # Make a obsolete template with the same directory.
        self.factory.makePOTemplate(
            path='po/evolution-3.0.pot',
            productseries=self.productseries,
            iscurrent=False)
        tiqe = self.factory.makeTranslationImportQueueEntry(
            path='po/fr.po', productseries=self.productseries)
        transaction.commit()
        self.assertIsNone(tiqe.import_into)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, tiqe.status)
        self.script.main()
        self.assertIsNotNone(tiqe.import_into)
        self.assertEqual(RosettaImportStatus.APPROVED, tiqe.status)
