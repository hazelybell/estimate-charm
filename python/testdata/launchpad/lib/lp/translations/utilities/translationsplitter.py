# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


import logging

from storm.expr import (
    And,
    Join,
    LeftJoin,
    Not,
    Or,
    )
from storm.locals import (
    ClassAlias,
    Store,
    )
import transaction

from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.packaging import Packaging
from lp.registry.model.productseries import ProductSeries
from lp.translations.model.potemplate import POTemplate
from lp.translations.model.translationtemplateitem import (
    TranslationTemplateItem,
    )


class TranslationSplitterBase:
    """Base class for translation splitting jobs."""

    @staticmethod
    def splitPOTMsgSet(ubuntu_item):
        """Split the POTMsgSet for TranslationTemplateItem.

        The specified `TranslationTemplateItem` will have a new `POTMsgSet`
        that is a clone of the old one.  All other TranslationTemplateItems
        will continue to use the old POTMsgSet.

        :param ubuntu_item: The `TranslationTemplateItem` to use.
        """
        new_potmsgset = ubuntu_item.potmsgset.clone()
        ubuntu_item.potmsgset = new_potmsgset
        return new_potmsgset

    @staticmethod
    def migrateTranslations(upstream_msgset, ubuntu_item):
        """Migrate the translations between potemplates.

        :param upstream_msgset: The `POTMsgSet` to copy or move translations
            from.
        :param ubuntu_item: The target `TranslationTemplateItem`.
            ubuntu_item.potmsgset is the msgset to attach translations to and
            ubuntu_item.potemplate is used to determine whether to move a
            diverged translation.
        """
        for message in upstream_msgset.getAllTranslationMessages():
            if message.potemplate == ubuntu_item.potemplate:
                message.potmsgset = ubuntu_item.potmsgset
            elif not message.is_diverged:
                message.clone(ubuntu_item.potmsgset)

    def split(self):
        """Split the translations for the ProductSeries and SourcePackage."""
        logger = logging.getLogger()
        shared = enumerate(self.findShared(), 1)
        total = 0
        for num, (upstream_item, ubuntu_item) in shared:
            self.splitPOTMsgSet(ubuntu_item)
            self.migrateTranslations(upstream_item.potmsgset, ubuntu_item)
            if num % 100 == 0:
                logger.info('%d entries split.  Committing...', num)
                transaction.commit()
            total = num

        if total % 100 != 0 or total == 0:
            transaction.commit()
            logger.info('%d entries split.', total)


class TranslationSplitter(TranslationSplitterBase):
    """Split translations for a productseries, sourcepackage pair.

    If a productseries and sourcepackage were linked in error, and then
    unlinked, they may still share some translations.  This class breaks those
    associations.
    """

    def __init__(self, productseries, sourcepackage):
        """Constructor.

        :param productseries: The `ProductSeries` to split from.
        :param sourcepackage: The `SourcePackage` to split from.
        """
        self.productseries = productseries
        self.sourcepackage = sourcepackage

    def findShared(self):
        """Provide tuples of upstream, ubuntu for each shared POTMsgSet."""
        store = Store.of(self.productseries)
        UpstreamItem = ClassAlias(TranslationTemplateItem, 'UpstreamItem')
        UpstreamTemplate = ClassAlias(POTemplate, 'UpstreamTemplate')
        UbuntuItem = ClassAlias(TranslationTemplateItem, 'UbuntuItem')
        UbuntuTemplate = ClassAlias(POTemplate, 'UbuntuTemplate')
        return store.find(
            (UpstreamItem, UbuntuItem),
            UpstreamItem.potmsgsetID == UbuntuItem.potmsgsetID,
            UbuntuItem.potemplateID == UbuntuTemplate.id,
            UbuntuTemplate.sourcepackagenameID ==
                self.sourcepackage.sourcepackagename.id,
            UbuntuTemplate.distroseriesID ==
                self.sourcepackage.distroseries.id,
            UpstreamItem.potemplateID == UpstreamTemplate.id,
            UpstreamTemplate.productseriesID == self.productseries.id,
        )


class TranslationTemplateSplitter(TranslationSplitterBase):
    """Split translations for an extracted potemplate.

    When a POTemplate is removed from a set of sharing templates,
    it keeps sharing POTMsgSets with other templates.  This class
    removes those associations.
    """

    def __init__(self, potemplate):
        """Constructor.

        :param potemplate: The `POTemplate` to sanitize.
        """
        self.potemplate = potemplate

    def findShared(self):
        """Provide tuples of (other, this) items for each shared POTMsgSet.

        Only return those that are shared but shouldn't be because they
        are now in non-sharing templates.
        """
        store = Store.of(self.potemplate)
        ThisItem = ClassAlias(TranslationTemplateItem, 'ThisItem')
        OtherItem = ClassAlias(TranslationTemplateItem, 'OtherItem')
        OtherTemplate = ClassAlias(POTemplate, 'OtherTemplate')

        tables = [
            OtherTemplate,
            Join(OtherItem, OtherItem.potemplateID == OtherTemplate.id),
            Join(ThisItem,
                 And(ThisItem.potmsgsetID == OtherItem.potmsgsetID,
                     ThisItem.potemplateID == self.potemplate.id)),
            ]

        if self.potemplate.productseries is not None:
            # If the template is now in a product, we look for all
            # effectively sharing templates that are in *different*
            # products, or that are in a sourcepackage which is not
            # linked (through Packaging table) with this product.
            ps = self.potemplate.productseries
            productseries_join = LeftJoin(
                ProductSeries,
                ProductSeries.id == OtherTemplate.productseriesID)
            packaging_join = LeftJoin(
                Packaging,
                And(Packaging.productseriesID == ps.id,
                    (Packaging.sourcepackagenameID ==
                     OtherTemplate.sourcepackagenameID),
                    Packaging.distroseriesID == OtherTemplate.distroseriesID
                    ))
            tables.extend([productseries_join, packaging_join])
            # Template should not be sharing if...
            other_clauses = Or(
                # The name is different, or...
                OtherTemplate.name != self.potemplate.name,
                # It's in a different product, or...
                And(Not(ProductSeries.id == None),
                    ProductSeries.productID != ps.productID),
                # There is no link between this product series and
                # a source package the template is in.
                And(Not(OtherTemplate.distroseriesID == None),
                    Packaging.id == None))
        else:
            # If the template is now in a source package, we look for all
            # effectively sharing templates that are in *different*
            # distributions or source packages, or that are in a product
            # which is not linked with this source package.
            ds = self.potemplate.distroseries
            spn = self.potemplate.sourcepackagename
            distroseries_join = LeftJoin(
                DistroSeries,
                DistroSeries.id == OtherTemplate.distroseriesID)
            packaging_join = LeftJoin(
                Packaging,
                And(Packaging.distroseriesID == ds.id,
                    Packaging.sourcepackagenameID == spn.id,
                    Packaging.productseriesID == OtherTemplate.productseriesID
                    ))
            tables.extend([distroseries_join, packaging_join])
            # Template should not be sharing if...
            other_clauses = Or(
                # The name is different, or...
                OtherTemplate.name != self.potemplate.name,
                # It's in a different distribution or source package, or...
                And(Not(DistroSeries.id == None),
                    Or(DistroSeries.distributionID != ds.distributionID,
                       OtherTemplate.sourcepackagenameID != spn.id)),
                # There is no link between this source package and
                # a product the template is in.
                And(Not(OtherTemplate.productseriesID == None),
                    Packaging.id == None))

        return store.using(*tables).find(
            (OtherItem, ThisItem),
            OtherTemplate.id != self.potemplate.id,
            other_clauses,
            )
