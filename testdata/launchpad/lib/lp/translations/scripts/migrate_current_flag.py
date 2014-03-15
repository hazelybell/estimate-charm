# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Set 'is_imported' flag from 'is_current' for upstream projects."""

__metaclass__ = type
__all__ = ['MigrateCurrentFlagProcess']

import logging

from storm.expr import (
    And,
    Count,
    Or,
    Select,
    )
from storm.info import ClassAlias
from zope.interface import implements

from lp.registry.model.product import Product
from lp.registry.model.productseries import ProductSeries
from lp.services.database.interfaces import IMasterStore
from lp.services.looptuner import (
    DBLoopTuner,
    ITunableLoop,
    )
from lp.translations.model.potemplate import POTemplate
from lp.translations.model.translationmessage import TranslationMessage
from lp.translations.model.translationtemplateitem import (
    TranslationTemplateItem,
    )


class TranslationMessageImportedFlagUpdater:
    implements(ITunableLoop)
    """Populates is_imported flag from is_current flag on translations."""

    def __init__(self, transaction, logger, tm_ids):
        self.transaction = transaction
        self.logger = logger
        self.start_at = 0

        self.tm_ids = list(tm_ids)
        self.total = len(self.tm_ids)
        self.logger.info(
            "Fixing up a total of %d TranslationMessages." % (self.total))
        self.store = IMasterStore(Product)

    def isDone(self):
        """See `ITunableLoop`."""
        # When the main loop hits the end of the list of objects,
        # it sets start_at to None.
        return self.start_at is None

    def getNextBatch(self, chunk_size):
        """Return a batch of objects to work with."""
        end_at = self.start_at + int(chunk_size)
        self.logger.debug(
            "Getting translations[%d:%d]..." % (self.start_at, end_at))
        return self.tm_ids[self.start_at: end_at]

    def _updateTranslationMessages(self, tm_ids):
        # Unset imported messages that might be in the way.
        PreviousImported = ClassAlias(
            TranslationMessage, 'PreviousImported')
        CurrentTranslation = ClassAlias(
            TranslationMessage, 'CurrentTranslation')
        previous_imported_select = Select(
            PreviousImported.id,
            tables=[PreviousImported, CurrentTranslation],
            where=And(
                PreviousImported.is_current_upstream == True,
                (PreviousImported.potmsgsetID ==
                 CurrentTranslation.potmsgsetID),
                Or(And(PreviousImported.potemplateID == None,
                       CurrentTranslation.potemplateID == None),
                   (PreviousImported.potemplateID ==
                    CurrentTranslation.potemplateID)),
                PreviousImported.languageID == CurrentTranslation.languageID,
                CurrentTranslation.id.is_in(tm_ids)))

        previous_imported = self.store.find(
            TranslationMessage,
            TranslationMessage.id.is_in(previous_imported_select))
        previous_imported.set(is_current_upstream=False)
        translations = self.store.find(
            TranslationMessage,
            TranslationMessage.id.is_in(tm_ids))
        translations.set(is_current_upstream=True)

    def __call__(self, chunk_size):
        """See `ITunableLoop`.

        Retrieve a batch of TranslationMessages in ascending id order,
        and set is_imported flag to True on all of them.
        """
        tm_ids = self.getNextBatch(chunk_size)

        if len(tm_ids) == 0:
            self.start_at = None
        else:
            self._updateTranslationMessages(tm_ids)
            self.transaction.commit()
            self.transaction.begin()

            self.start_at += len(tm_ids)
            self.logger.info("Processed %d/%d TranslationMessages." % (
                self.start_at, self.total))


class MigrateCurrentFlagProcess:
    """Mark all translations as is_imported if they are is_current.

    Processes only translations for upstream projects, since Ubuntu
    source packages need no migration.
    """

    def __init__(self, transaction, logger=None):
        self.transaction = transaction
        self.logger = logger
        if logger is None:
            self.logger = logging.getLogger("migrate-current-flag")
        self.store = IMasterStore(Product)

    def getProductsWithTemplates(self):
        """Get Product.ids for projects with any translations templates."""
        return self.store.find(
            Product,
            POTemplate.productseriesID == ProductSeries.id,
            ProductSeries.productID == Product.id,
            ).group_by(Product).having(Count(POTemplate.id) > 0)

    def getCurrentNonimportedTranslations(self, product):
        """Get TranslationMessage.ids that need migration for a `product`."""
        return self.store.find(
            TranslationMessage.id,
            TranslationMessage.is_current_ubuntu == True,
            TranslationMessage.is_current_upstream == False,
            (TranslationMessage.potmsgsetID ==
             TranslationTemplateItem.potmsgsetID),
            TranslationTemplateItem.potemplateID == POTemplate.id,
            POTemplate.productseriesID == ProductSeries.id,
            ProductSeries.productID == product.id).config(distinct=True)

    def run(self):
        products_with_templates = list(self.getProductsWithTemplates())
        total_products = len(products_with_templates)
        if total_products == 0:
            self.logger.info("Nothing to do.")
        current_product = 0
        for product in products_with_templates:
            current_product += 1
            self.logger.info(
                "Migrating %s translations (%d of %d)..." % (
                    product.name, current_product, total_products))

            tm_ids = self.getCurrentNonimportedTranslations(product)
            tm_loop = TranslationMessageImportedFlagUpdater(
                self.transaction, self.logger, tm_ids)
            DBLoopTuner(tm_loop, 5, minimum_chunk_size=100).run()

        self.logger.info("Done.")
