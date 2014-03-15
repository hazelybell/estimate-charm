# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `TranslationTemplatesCollection`."""

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.model.pofile import POFile
from lp.translations.model.potemplate import (
    POTemplate,
    TranslationTemplatesCollection,
    )


class TestSomething(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_baseline(self):
        # A collection constructed with no arguments selects all
        # templates.
        template = self.factory.makePOTemplate()

        collection = TranslationTemplatesCollection()
        self.assertIn(template, collection.select())

    def test_none_found(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)

        self.assertContentEqual([], by_series.select())

    def test_restrictProductSeries(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        template = self.factory.makePOTemplate(productseries=trunk)

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)

        self.assertContentEqual([template], by_series.select())

    def test_restrictProductSeries_restricts(self):
        # restrictProductSeries makes the collection ignore templates
        # from other productseries and source packages.
        product = self.factory.makeProduct()
        trunk = product.getSeries('trunk')

        nontrunk = removeSecurityProxy(product).newSeries(
            product.owner, 'nontrunk', 'foo')
        sourcepackage = self.factory.makeSourcePackage()

        self.factory.makePOTemplate(productseries=nontrunk)
        self.factory.makePOTemplate(
            distroseries=sourcepackage.distroseries,
            sourcepackagename=sourcepackage.sourcepackagename)

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)

        self.assertContentEqual([], by_series.select())

    def test_restrictDistroSeries(self):
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictDistroSeries(package.distroseries)

        self.assertContentEqual([template], by_series.select())

    def test_restrictDistroSeries_restricts(self):
        # restrictProductSeries makes the collection ignore templates
        # from other productseries and distroseries.
        distribution = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distribution)
        other_series = self.factory.makeDistroSeries(
            distribution=distribution)
        productseries = self.factory.makeProductSeries()
        package = self.factory.makeSourcePackageName()

        self.factory.makePOTemplate(
            distroseries=other_series, sourcepackagename=package)
        self.factory.makePOTemplate(productseries=productseries)

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictDistroSeries(series)

        self.assertContentEqual([], by_series.select())

    def test_restrictSourcePackageName(self):
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

        assert package.sourcepackagename
        collection = TranslationTemplatesCollection()
        by_packagename = collection.restrictSourcePackageName(
            package.sourcepackagename)

        self.assertContentEqual([template], by_packagename.select())

    def test_restrictSourcePackageName_restricts(self):
        # restrictSourcePackageName makes the collection ignore
        # templates from other source package names and productseries.
        package = self.factory.makeSourcePackage()
        distroseries = package.distroseries
        other_package = self.factory.makeSourcePackage(
            distroseries=distroseries)
        productseries = self.factory.makeProductSeries()

        self.factory.makePOTemplate(
            distroseries=distroseries,
            sourcepackagename=other_package.sourcepackagename)
        self.factory.makePOTemplate(productseries=productseries)

        collection = TranslationTemplatesCollection()
        by_packagename = collection.restrictSourcePackageName(
            package.sourcepackagename)

        self.assertContentEqual([], by_packagename.select())

    def test_restrict_SourcePackage(self):
        # You can restrict to a source package by restricting both to a
        # DistroSeries and to a SourcePackageName.
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictDistroSeries(package.distroseries)
        by_package = by_series.restrictSourcePackageName(
            package.sourcepackagename)

        self.assertContentEqual([template], by_package.select())

    def test_restrictCurrent_current(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        template = self.factory.makePOTemplate(productseries=trunk)
        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)

        current_templates = by_series.restrictCurrent(True)

        removeSecurityProxy(template).iscurrent = True
        self.assertContentEqual(
            [template], current_templates.select())

        removeSecurityProxy(template).iscurrent = False
        self.assertContentEqual([], current_templates.select())

    def test_restrictCurrent_obsolete(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        template = self.factory.makePOTemplate(productseries=trunk)
        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)

        obsolete_templates = by_series.restrictCurrent(False)

        removeSecurityProxy(template).iscurrent = True
        self.assertContentEqual([], obsolete_templates.select())

        removeSecurityProxy(template).iscurrent = False
        self.assertContentEqual(
            [template], obsolete_templates.select())

    def test_restrictName(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        template = self.factory.makePOTemplate(productseries=trunk)
        template_name = template.name
        # Other template that will not be returned.
        self.factory.makePOTemplate(productseries=trunk)
        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)

        same_name_templates = by_series.restrictName(template_name)
        self.assertContentEqual(
            [template], same_name_templates.select())

    def test_joinPOFile(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        translated_template = self.factory.makePOTemplate(productseries=trunk)
        untranslated_template = self.factory.makePOTemplate(
            productseries=trunk)
        nl = translated_template.newPOFile('nl')
        de = translated_template.newPOFile('de')

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)
        joined = by_series.joinPOFile()

        self.assertContentEqual(
            [(translated_template, nl), (translated_template, de)],
            joined.select(POTemplate, POFile))

    def test_joinOuterPOFile(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        translated_template = self.factory.makePOTemplate(productseries=trunk)
        untranslated_template = self.factory.makePOTemplate(
            productseries=trunk)
        nl = translated_template.newPOFile('nl')
        de = translated_template.newPOFile('de')

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)
        joined = by_series.joinOuterPOFile()

        expected_outcome = [
            (translated_template, nl),
            (translated_template, de),
            (untranslated_template, None),
            ]
        self.assertContentEqual(
            expected_outcome, joined.select(POTemplate, POFile))

    def test_joinOuterPOFile_language(self):
        trunk = self.factory.makeProduct().getSeries('trunk')
        translated_template = self.factory.makePOTemplate(productseries=trunk)
        untranslated_template = self.factory.makePOTemplate(
            productseries=trunk)
        nl = translated_template.newPOFile('nl')
        de = translated_template.newPOFile('de')

        collection = TranslationTemplatesCollection()
        by_series = collection.restrictProductSeries(trunk)
        joined = by_series.joinOuterPOFile(language=nl.language)

        expected_outcome = [
            (translated_template, nl),
            (untranslated_template, None),
            ]
        self.assertContentEqual(
            expected_outcome, joined.select(POTemplate, POFile))
