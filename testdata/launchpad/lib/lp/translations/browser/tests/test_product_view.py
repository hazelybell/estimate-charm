# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from soupmatchers import (
    HTMLContains,
    Tag,
    )
from testtools.matchers import Not

from lp.app.enums import (
    InformationType,
    PUBLIC_PROPRIETARY_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.services.webapp import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    celebrity_logged_in,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )
from lp.translations.browser.product import ProductView
from lp.translations.publisher import TranslationsLayer


class TestProduct(TestCaseWithFactory):
    """Test Product view in translations facet."""

    layer = LaunchpadZopelessLayer

    def test_primary_translatable_with_package_link(self):
        # Create a product that uses translations.
        product = self.factory.makeProduct()
        series = product.development_focus
        product.translations_usage = ServiceUsage.LAUNCHPAD
        view = ProductView(product, LaunchpadTestRequest())

        # If development focus series is linked to
        # a distribution package with translations,
        # we do not try to show translation statistics
        # for the package.
        sourcepackage = self.factory.makeSourcePackage()
        sourcepackage.setPackaging(series, None)
        sourcepackage.distroseries.distribution.translations_usage = (
            ServiceUsage.LAUNCHPAD)
        self.factory.makePOTemplate(
            distroseries=sourcepackage.distroseries,
            sourcepackagename=sourcepackage.sourcepackagename)
        self.assertEquals(None, view.primary_translatable)

    def test_untranslatable_series(self):
        # Create a product that uses translations.
        product = self.factory.makeProduct()
        product.translations_usage = ServiceUsage.LAUNCHPAD
        view = ProductView(product, LaunchpadTestRequest())

        # New series are added, one for each type of status
        series_experimental = self.factory.makeProductSeries(
            product=product, name='evo-experimental')
        series_experimental.status = SeriesStatus.EXPERIMENTAL

        series_development = self.factory.makeProductSeries(
            product=product, name='evo-development')
        series_development.status = SeriesStatus.DEVELOPMENT

        series_frozen = self.factory.makeProductSeries(
            product=product, name='evo-frozen')
        series_frozen.status = SeriesStatus.FROZEN

        series_current = self.factory.makeProductSeries(
            product=product, name='evo-current')
        series_current.status = SeriesStatus.CURRENT

        series_supported = self.factory.makeProductSeries(
            product=product, name='evo-supported')
        series_supported.status = SeriesStatus.SUPPORTED

        series_obsolete = self.factory.makeProductSeries(
            product=product, name='evo-obsolete')
        series_obsolete.status = SeriesStatus.OBSOLETE

        series_future = self.factory.makeProductSeries(
            product=product, name='evo-future')
        series_future.status = SeriesStatus.FUTURE

        # The series are returned in alphabetical order and do not
        # include obsolete series.
        series_names = [series.name for series in view.untranslatable_series]
        self.assertEqual([
            u'evo-current',
            u'evo-development',
            u'evo-experimental',
            u'evo-frozen',
            u'evo-future',
            u'evo-supported',
            u'trunk'], series_names)


class TestCanConfigureTranslations(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_cannot_configure_translations_product_no_edit_permission(self):
        product = self.factory.makeProduct()
        view = create_view(product, '+translations', layer=TranslationsLayer)
        self.assertEqual(False, view.can_configure_translations())

    def test_can_configure_translations_product_with_edit_permission(self):
        product = self.factory.makeProduct()
        login_person(product.owner)
        view = create_view(product, '+translations', layer=TranslationsLayer)
        self.assertEqual(True, view.can_configure_translations())

    def test_rosetta_expert_can_configure_translations(self):
        product = self.factory.makeProduct()
        with celebrity_logged_in('rosetta_experts'):
            view = create_view(product, '+translations',
                               layer=TranslationsLayer)
            self.assertEqual(True, view.can_configure_translations())

    def test_launchpad_not_listed_for_proprietary(self):
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            for info_type in PUBLIC_PROPRIETARY_INFORMATION_TYPES:
                product.information_type = info_type
                view = create_initialized_view(
                    product, '+configure-translations',
                    layer=TranslationsLayer)
                if product.private:
                    self.assertNotIn(
                        ServiceUsage.LAUNCHPAD,
                        view.widgets['translations_usage'].vocabulary)
                else:
                    self.assertIn(
                        ServiceUsage.LAUNCHPAD,
                        view.widgets['translations_usage'].vocabulary)

    @staticmethod
    def getViewContent(view):
        with person_logged_in(view.request.principal):
            return view()

    @staticmethod
    def hasLink(url):
        return HTMLContains(Tag('link', 'a', attrs={'href': url}))

    @classmethod
    def getTranslationsContent(cls, product):
        view = create_initialized_view(product, '+translations',
                                       layer=TranslationsLayer,
                                       principal=product.owner)
        return cls.getViewContent(view)

    def test_no_sync_links_for_proprietary(self):
        # Proprietary products don't have links for synchronizing
        # productseries.
        product = self.factory.makeProduct()
        content = self.getTranslationsContent(product)
        series_url = canonical_url(
            product.development_focus, view_name='+translations',
            rootsite='translations')
        manual_url = canonical_url(
            product.development_focus, view_name='+translations-upload',
            rootsite='translations')
        automatic_url = canonical_url(
            product.development_focus, view_name='+translations-settings',
            rootsite='translations')
        self.assertThat(content, self.hasLink(series_url))
        self.assertThat(content, self.hasLink(manual_url))
        self.assertThat(content, self.hasLink(automatic_url))
        with person_logged_in(product.owner):
            product.information_type = InformationType.PROPRIETARY
        content = self.getTranslationsContent(product)
        self.assertThat(content, Not(self.hasLink(series_url)))
        self.assertThat(content, Not(self.hasLink(manual_url)))
        self.assertThat(content, Not(self.hasLink(automatic_url)))
