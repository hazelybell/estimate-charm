# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.services.webapp import canonical_url
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.browser.translationlinksaggregator import (
    TranslationLinksAggregator,
    )
from lp.translations.model.productserieslanguage import ProductSeriesLanguage


class DumbAggregator(TranslationLinksAggregator):
    """A very simple `TranslationLinksAggregator`.

    The `describe` method returns a tuple of its arguments.
    """

    def describe(self, target, link, covered_sheets):
        """See `TranslationLinksAggregator`."""
        return (target, link, covered_sheets)


def map_link(link_target, sheets=None, add_to=None):
    """Map a link the way _circumscribe does.

    :param link_target: The object to link to.  Its URL will be used.
    :param sheets: A list of POFiles and/or POTemplates.  The link will
        map to these.  If omitted, the list will consist of
        `link_target` itself.
    :param add_to: Optional existing dict to add the new entry to.
    :return: A dict mapping the URL for link_target to sheets.
    """
    if add_to is None:
        add_to = {}
    if sheets is None:
        sheets = [link_target]
    add_to[canonical_url(link_target)] = sheets
    return add_to


class TestTranslationLinksAggregator(TestCaseWithFactory):
    """Test `TranslationLinksAggregator`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationLinksAggregator, self).setUp()
        self.aggregator = DumbAggregator()

    def test_circumscribe_single_pofile(self):
        # If passed a single POFile, _circumscribe returns a list of
        # just that POFile.
        pofile = self.factory.makePOFile(language_code='lua')

        links = self.aggregator._circumscribe([pofile])

        self.assertEqual(map_link(pofile), links)

    def test_circumscribe_product_wild_mix(self):
        # A combination of wildly different POFiles in the same product
        # yields links to the individual POFiles.
        pofile1 = self.factory.makePOFile(language_code='sux')
        product = pofile1.potemplate.productseries.product
        series2 = self.factory.makeProductSeries(product)
        template2 = self.factory.makePOTemplate(productseries=series2)
        pofile2 = self.factory.makePOFile(
            potemplate=template2, language_code='la')

        links = self.aggregator._circumscribe([pofile1, pofile2])

        expected_links = map_link(pofile1)
        expected_links = map_link(pofile2, add_to=expected_links)
        self.assertEqual(expected_links, links)

    def test_circumscribe_different_templates(self):
        # A combination of POFiles in the same language but different
        # templates of the same productseries is represented as a link
        # to the ProductSeriesLanguage.
        pofile1 = self.factory.makePOFile(language_code='nl')
        series = pofile1.potemplate.productseries
        template2 = self.factory.makePOTemplate(productseries=series)
        pofile2 = self.factory.makePOFile(
            potemplate=template2, language_code='nl')

        links = self.aggregator._circumscribe([pofile1, pofile2])

        psl = ProductSeriesLanguage(series, pofile1.language)
        self.assertEqual(map_link(psl, [pofile1, pofile2]), links)

    def test_circumscribe_different_languages(self):
        # If the POFiles differ only in language, we get a link to the
        # overview for the template.
        pofile1 = self.factory.makePOFile(language_code='nl')
        template = pofile1.potemplate
        pofile2 = self.factory.makePOFile(
            potemplate=template, language_code='lo')

        pofiles = [pofile1, pofile2]
        links = self.aggregator._circumscribe(pofiles)

        self.assertEqual(map_link(template, pofiles), links)

    def test_circumscribe_sharing_pofiles(self):
        # In a Product, two POFiles may share their translations.  For
        # now, we link to each individually.  We may want to make this
        # more clever in the future.
        pofile1 = self.factory.makePOFile(language_code='nl')
        template1 = pofile1.potemplate
        series1 = template1.productseries
        series2 = self.factory.makeProductSeries(product=series1.product)
        template2 = self.factory.makePOTemplate(
            productseries=series2, name=template1.name,
            translation_domain=template1.translation_domain)
        pofile2 = template2.getPOFileByLang('nl')

        pofiles = [pofile1, pofile2]
        links = self.aggregator._circumscribe(pofiles)

        expected_links = map_link(pofile1)
        expected_links = map_link(pofile2, add_to=expected_links)
        self.assertEqual(expected_links, links)

    def test_circumscribe_package_different_languages(self):
        # For package POFiles in the same template but different
        # languages, we link to the template.
        package = self.factory.makeSourcePackage()
        package.distroseries.distribution.translations_usage = (
            ServiceUsage.LAUNCHPAD)
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        pofile1 = self.factory.makePOFile(
            potemplate=template, language_code='nl')
        pofile2 = self.factory.makePOFile(
            potemplate=template, language_code='ka')

        pofiles = [pofile1, pofile2]
        links = self.aggregator._circumscribe(pofiles)
        self.assertEqual(map_link(template, pofiles), links)

    def test_circumscribe_package_different_templates(self):
        # For package POFiles in different templates, we to the
        # package's template list.  There is no "source package series
        # language" page.
        package = self.factory.makeSourcePackage()
        package.distroseries.distribution.translations_usage = (
            ServiceUsage.LAUNCHPAD)
        template1 = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        template2 = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        pofile1 = self.factory.makePOFile(
            potemplate=template1, language_code='nl')
        pofile2 = self.factory.makePOFile(
            potemplate=template2, language_code='nl')

        pofiles = [pofile1, pofile2]
        links = self.aggregator._circumscribe(pofiles)

        self.assertEqual(map_link(package, pofiles), links)

    def test_circumscribe_pofile_plus_template(self):
        # A template circumscribes both itself and any of its
        # translations.
        pofile = self.factory.makePOFile(language_code='uga')
        template = pofile.potemplate

        sheets = [pofile, template]
        links = self.aggregator._circumscribe(sheets)

        self.assertEqual(map_link(template, sheets), links)

    def test_aggregate(self):
        # The aggregator represents a series of POFiles as a series of
        # target descriptions, aggregating where possible.

        # Trivial case: no POFiles means no targets.
        self.assertEqual([], self.aggregator.aggregate([]))

        # Basic case: one POFile yields its product or package.
        pofile = self.factory.makePOFile(language_code='ca')
        product = pofile.potemplate.productseries.product

        descriptions = self.aggregator.aggregate([pofile])

        expected = [(product, canonical_url(pofile), [pofile])]
        self.assertEqual(expected, descriptions)

    def test_aggregate_potemplate(self):
        # Besides POFiles, you can also feed an aggregator POTemplates.
        template = self.factory.makePOTemplate()
        product = template.productseries.product

        descriptions = self.aggregator.aggregate([template])

        expected = [(product, canonical_url(template), [template])]
        self.assertEqual(expected, descriptions)

    def test_aggregate_product_and_package(self):
        # The aggregator keeps a product and a package separate.
        product_pofile = self.factory.makePOFile(language_code='th')
        product = product_pofile.potemplate.productseries.product
        removeSecurityProxy(product_pofile).unreviewed_count = 1

        package = self.factory.makeSourcePackage()
        package.distroseries.distribution.translations_usage = (
            ServiceUsage.LAUNCHPAD)
        package_template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        package_pofile = self.factory.makePOFile(
            potemplate=package_template, language_code='th')
        removeSecurityProxy(package_pofile).unreviewed_count = 2

        descriptions = self.aggregator.aggregate(
            [product_pofile, package_pofile])

        expected = [
            (product, canonical_url(product_pofile), [product_pofile]),
            (package, canonical_url(package_pofile), [package_pofile]),
            ]
        self.assertContentEqual(expected, descriptions)

    def test_aggregate_bundles_productseries(self):
        # _aggregateTranslationTargets describes POFiles for the same
        # ProductSeries together.
        pofile1 = self.factory.makePOFile(language_code='es')
        series = pofile1.potemplate.productseries
        template2 = self.factory.makePOTemplate(productseries=series)
        pofile2 = self.factory.makePOFile(
            language_code='br', potemplate=template2)

        pofiles = [pofile1, pofile2]
        descriptions = self.aggregator.aggregate(pofiles)

        self.assertEqual(1, len(descriptions))
        self.assertEqual(
            [(series.product, canonical_url(series), pofiles)], descriptions)

    def test_aggregate_bundles_package(self):
        # _aggregateTranslationTargets describes POFiles for the same
        # ProductSeries together.
        package = self.factory.makeSourcePackage()
        package.distroseries.distribution.translations_usage = (
            ServiceUsage.LAUNCHPAD)
        template1 = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        pofile1 = self.factory.makePOFile(
            language_code='es', potemplate=template1)
        template2 = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        pofile2 = self.factory.makePOFile(
            language_code='br', potemplate=template2)

        pofiles = [pofile1, pofile2]
        descriptions = self.aggregator.aggregate(pofiles)

        expected = [(package, canonical_url(package), pofiles)]
        self.assertEqual(expected, descriptions)
