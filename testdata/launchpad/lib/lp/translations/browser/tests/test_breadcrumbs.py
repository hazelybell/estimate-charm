# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lazr.restful.utils import smartquote
from zope.component import getUtility

from lp.app.enums import ServiceUsage
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing.breadcrumbs import BaseBreadcrumbTestCase
from lp.testing.factory import remove_security_proxy_and_shout_at_engineer
from lp.translations.interfaces.distroserieslanguage import (
    IDistroSeriesLanguageSet,
    )
from lp.translations.interfaces.productserieslanguage import (
    IProductSeriesLanguageSet,
    )
from lp.translations.interfaces.translationgroup import ITranslationGroupSet


class TestTranslationsVHostBreadcrumb(BaseBreadcrumbTestCase):

    def test_product(self):
        product = self.factory.makeProduct(
            name='crumb-tester', displayname="Crumb Tester")
        self.assertBreadcrumbs(
            [("Crumb Tester", 'http://launchpad.dev/crumb-tester'),
             ("Translations",
              'http://translations.launchpad.dev/crumb-tester')],
            product, rootsite='translations')

    def test_productseries(self):
        product = self.factory.makeProduct(
            name='crumb-tester', displayname="Crumb Tester")
        series = self.factory.makeProductSeries(name="test", product=product)
        self.assertBreadcrumbs(
            [("Crumb Tester", 'http://launchpad.dev/crumb-tester'),
             ("Series test", 'http://launchpad.dev/crumb-tester/test'),
             ("Translations",
              'http://translations.launchpad.dev/crumb-tester/test')],
            series, rootsite='translations')

    def test_distribution(self):
        distribution = self.factory.makeDistribution(
            name='crumb-tester', displayname="Crumb Tester")
        self.assertBreadcrumbs(
            [("Crumb Tester", 'http://launchpad.dev/crumb-tester'),
             ("Translations",
              'http://translations.launchpad.dev/crumb-tester')],
            distribution, rootsite='translations')

    def test_distroseries(self):
        distribution = self.factory.makeDistribution(
            name='crumb-tester', displayname="Crumb Tester")
        series = self.factory.makeDistroSeries(
            name="test", version="1.0", distribution=distribution)
        self.assertBreadcrumbs(
            [("Crumb Tester", 'http://launchpad.dev/crumb-tester'),
             ("Test (1.0)", 'http://launchpad.dev/crumb-tester/test'),
             ("Translations",
              'http://translations.launchpad.dev/crumb-tester/test')],
            series, rootsite='translations')

    def test_project(self):
        project = self.factory.makeProject(
            name='crumb-tester', displayname="Crumb Tester")
        self.assertBreadcrumbs(
            [("Crumb Tester", 'http://launchpad.dev/crumb-tester'),
             ("Translations",
              'http://translations.launchpad.dev/crumb-tester')],
            project, rootsite='translations')

    def test_person(self):
        person = self.factory.makePerson(
            name='crumb-tester', displayname="Crumb Tester")
        self.assertBreadcrumbs(
            [("Crumb Tester", 'http://launchpad.dev/~crumb-tester'),
             ("Translations",
              'http://translations.launchpad.dev/~crumb-tester')],
            person, rootsite='translations')


class TestTranslationGroupsBreadcrumbs(BaseBreadcrumbTestCase):

    def test_translationgroupset(self):
        group_set = getUtility(ITranslationGroupSet)
        self.assertBreadcrumbs(
            [("Translation groups",
              'http://translations.launchpad.dev/+groups')],
            group_set, rootsite='translations')

    def test_translationgroup(self):
        group = self.factory.makeTranslationGroup(
            name='test-translators', title='Test translators')
        self.assertBreadcrumbs(
            [("Translation groups",
              'http://translations.launchpad.dev/+groups'),
             ("Test translators",
              'http://translations.launchpad.dev/+groups/test-translators')],
            group, rootsite='translations')


class TestSeriesLanguageBreadcrumbs(BaseBreadcrumbTestCase):

    def setUp(self):
        super(TestSeriesLanguageBreadcrumbs, self).setUp()
        self.language = getUtility(ILanguageSet)['sr']

    def test_distroserieslanguage(self):
        distribution = self.factory.makeDistribution(
            name='crumb-tester', displayname="Crumb Tester")
        series = self.factory.makeDistroSeries(
            name="test", version="1.0", distribution=distribution)
        naked_series = remove_security_proxy_and_shout_at_engineer(series)
        naked_series.hide_all_translations = False
        serieslanguage = getUtility(IDistroSeriesLanguageSet).getDummy(
            series, self.language)

        self.assertBreadcrumbs(
            [("Crumb Tester", "http://launchpad.dev/crumb-tester"),
             ("Test (1.0)", "http://launchpad.dev/crumb-tester/test"),
             ("Translations",
              "http://translations.launchpad.dev/crumb-tester/test"),
             ("Serbian (sr)",
              "http://translations.launchpad.dev/"
              "crumb-tester/test/+lang/sr")],
            serieslanguage)

    def test_productserieslanguage(self):
        product = self.factory.makeProduct(
            name='crumb-tester', displayname="Crumb Tester")
        series = self.factory.makeProductSeries(
            name="test", product=product)
        psl_set = getUtility(IProductSeriesLanguageSet)
        serieslanguage = psl_set.getProductSeriesLanguage(
            series, self.language)

        self.assertBreadcrumbs(
            [("Crumb Tester", "http://launchpad.dev/crumb-tester"),
             ("Series test", "http://launchpad.dev/crumb-tester/test"),
             ("Translations",
              "http://translations.launchpad.dev/crumb-tester/test"),
             ("Serbian (sr)",
              "http://translations.launchpad.dev/"
              "crumb-tester/test/+lang/sr")],
            serieslanguage)


class TestPOTemplateBreadcrumbs(BaseBreadcrumbTestCase):
    """Test POTemplate breadcrumbs."""

    def test_potemplate(self):
        product = self.factory.makeProduct(
            name='crumb-tester', displayname="Crumb Tester",
            translations_usage=ServiceUsage.LAUNCHPAD)
        series = self.factory.makeProductSeries(
            name="test", product=product)
        potemplate = self.factory.makePOTemplate(
            name="template", productseries=series)
        self.assertBreadcrumbs(
            [("Crumb Tester", "http://launchpad.dev/crumb-tester"),
             ("Series test", "http://launchpad.dev/crumb-tester/test"),
             ("Translations",
              "http://translations.launchpad.dev/crumb-tester/test"),
             (smartquote('Template "template"'),
              "http://translations.launchpad.dev/"
              "crumb-tester/test/+pots/template")],
            potemplate)


class TestPOFileBreadcrumbs(BaseBreadcrumbTestCase):

    def setUp(self):
        super(TestPOFileBreadcrumbs, self).setUp()

    def test_pofiletranslate(self):
        product = self.factory.makeProduct(
            name='crumb-tester', displayname="Crumb Tester",
            translations_usage=ServiceUsage.LAUNCHPAD)
        series = self.factory.makeProductSeries(name="test", product=product)
        potemplate = self.factory.makePOTemplate(series, name="test-template")
        pofile = self.factory.makePOFile('eo', potemplate)

        self.assertBreadcrumbs(
            [("Crumb Tester", "http://launchpad.dev/crumb-tester"),
             ("Series test", "http://launchpad.dev/crumb-tester/test"),
             ("Translations",
              "http://translations.launchpad.dev/crumb-tester/test"),
             (smartquote('Template "test-template"'),
              "http://translations.launchpad.dev/crumb-tester/test"
              "/+pots/test-template"),
             ("Esperanto (eo)",
              "http://translations.launchpad.dev/crumb-tester/test"
              "/+pots/test-template/eo")],
            pofile)
