# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.browser.productseries import ProductSeriesView
from lp.translations.browser.serieslanguage import ProductSeriesLanguageView
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )


class TestProductSeriesView(TestCaseWithFactory):
    """Test ProductSeries view in translations facet."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a productseries that uses translations.
        super(TestProductSeriesView, self).setUp()
        self.productseries = self.factory.makeProductSeries()
        self.product = self.productseries.product

    def _createView(self):
        return ProductSeriesView(self.productseries, LaunchpadTestRequest())

    def test_single_potemplate_no_template(self):
        view = self._createView()
        self.assertFalse(view.single_potemplate)

    def test_single_potemplate_one_template(self):
        self.factory.makePOTemplate(productseries=self.productseries)
        view = self._createView()
        self.assertTrue(view.single_potemplate)

    def test_single_potemplate_multiple_templates(self):
        self.factory.makePOTemplate(productseries=self.productseries)
        self.factory.makePOTemplate(productseries=self.productseries)
        view = self._createView()
        self.assertFalse(view.single_potemplate)

    def test_has_translation_documentation_no_group(self):
        # Without a translation group, there is no documentation either.
        view = self._createView()
        self.assertFalse(view.has_translation_documentation)

    def test_has_translation_documentation_group_without_url(self):
        # Adding a translation group with no documentation keeps
        # `has_translation_documentation` at False.
        self.product.translationgroup = self.factory.makeTranslationGroup(
            self.productseries.product.owner, url=None)
        view = self._createView()
        self.assertFalse(view.has_translation_documentation)

    def test_has_translation_documentation_group_with_url(self):
        # After adding a translation group with a documentation URL lets
        # `has_translation_documentation` be True.
        self.product.translationgroup = self.factory.makeTranslationGroup(
            self.productseries.product.owner, url=u'http://something')
        view = self._createView()
        self.assertTrue(view.has_translation_documentation)

    def test_productserieslanguages_no_template(self):
        # With no POTemplates, no languages can be seen, either.
        view = self._createView()
        self.assertEquals(None, view.productserieslanguages)

    def _getProductserieslanguages(self, view):
        return [psl.language for psl in view.productserieslanguages]

    def test_productserieslanguages_without_pofile(self):
        # With a single POTemplate, but no actual translations, the list
        # of languages is empty.
        self.factory.makePOTemplate(productseries=self.productseries)
        view = self._createView()
        self.assertEquals([], self._getProductserieslanguages(view))

    def test_productserieslanguages_with_pofile(self):
        # The `productserieslanguages` properperty has a list of the
        # languages of the po files for the templates in this seris.
        potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        pofile = self.factory.makePOFile(potemplate=potemplate)
        view = self._createView()
        self.assertEquals(
            [pofile.language], self._getProductserieslanguages(view))

    def _makePersonWithLanguage(self):
        user = self.factory.makePerson()
        language = self.factory.makeLanguage()
        user.addLanguage(language)
        return user, language

    def test_productserieslanguages_preferred_language_without_pofile(self):
        # If the user has a preferred language, that language always in
        # the list.
        self.factory.makePOTemplate(
            productseries=self.productseries)
        user, language = self._makePersonWithLanguage()
        login_person(user)
        view = self._createView()
        self.assertEquals([language], self._getProductserieslanguages(view))

    def test_productserieslanguages_preferred_language_with_pofile(self):
        # If the user has a preferred language, that language always in
        # the list.
        potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        pofile = self.factory.makePOFile(potemplate=potemplate)
        user, language = self._makePersonWithLanguage()
        login_person(user)
        view = self._createView()
        self.assertContentEqual(
            [pofile.language, language],
            self._getProductserieslanguages(view))

    def test_productserieslanguages_ordered_by_englishname(self):
        # Returned languages are ordered by their name in English.
        language1 = self.factory.makeLanguage(
            language_code='lang-aa', name='Zz')
        language2 = self.factory.makeLanguage(
            language_code='lang-zz', name='Aa')
        potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        self.factory.makePOFile(language=language1, potemplate=potemplate)
        self.factory.makePOFile(language=language2, potemplate=potemplate)
        view = self._createView()
        self.assertEquals(
            [language2, language1], self._getProductserieslanguages(view))

    def test_productserieslanguages_english(self):
        # English is not listed among translated languages, even if there's
        # an English POFile
        potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        self.factory.makePOFile('en', potemplate)
        view = self._createView()
        self.assertEquals([], self._getProductserieslanguages(view))

        # It's not shown even with more than one POTemplate
        # (different code paths).
        self.factory.makePOTemplate(productseries=self.productseries)
        self.assertEquals([], self._getProductserieslanguages(view))


class TestProductSeriesViewBzrUsage(TestCaseWithFactory):
    """Test ProductSeries view in translations facet."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Create a productseries that uses translations.
        # Strip off the security proxy to allow customization.
        super(TestProductSeriesViewBzrUsage, self).setUp()
        self.secured_productseries = self.factory.makeProductSeries()
        self.productseries = removeSecurityProxy(self.secured_productseries)

    def _createView(self):
        # The view operates on the secured product series!
        view = ProductSeriesView(
            self.secured_productseries, LaunchpadTestRequest())
        view.initialize()
        return view

    def test_has_imports_enabled_no_branch(self):
        view = self._createView()
        self.assertFalse(view.has_imports_enabled)

    def test_has_exports_enabled_no_branch(self):
        view = self._createView()
        self.assertFalse(view.has_exports_enabled)

    def test_has_imports_enabled_with_branch_imports_disabled(self):
        self.productseries.branch = self.factory.makeBranch()
        self.productseries.translations_autoimport_mode = (
                TranslationsBranchImportMode.NO_IMPORT)
        view = self._createView()
        self.assertFalse(view.has_imports_enabled)

    def test_has_imports_enabled_with_branch_template_imports_enabled(self):
        self.productseries.branch = self.factory.makeBranch()
        self.productseries.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        view = self._createView()
        self.assertTrue(view.has_imports_enabled)

    def test_has_imports_enabled_with_branch_trans_imports_enabled(self):
        self.productseries.branch = self.factory.makeBranch()
        self.productseries.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS)
        view = self._createView()
        self.assertTrue(view.has_imports_enabled)

    def test_has_imports_enabled_private_branch_non_privileged(self):
        # Private branches are hidden from non-privileged users. The view
        # pretends that it is not used for imports.
        self.productseries.branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        self.productseries.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS)
        view = self._createView()
        self.assertFalse(view.has_imports_enabled)

    def test_has_imports_enabled_private_branch_privileged(self):
        # Private branches are visible for privileged users.
        self.productseries.branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        self.productseries.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS)
        with person_logged_in(self.productseries.branch.owner):
            view = self._createView()
            self.assertTrue(view.has_imports_enabled)

    def test_has_exports_enabled_with_branch(self):
        self.productseries.translations_branch = self.factory.makeBranch()
        view = self._createView()
        self.assertTrue(view.has_exports_enabled)

    def test_has_exports_enabled_private_branch_non_privileged(self):
        # Private branches are hidden from non-privileged users. The view
        # pretends that it is not used for exports.
        self.productseries.translations_branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        view = self._createView()
        self.assertFalse(view.has_exports_enabled)

    def test_has_exports_enabled_private_branch_privileged(self):
        # Private branches are visible for privileged users.
        self.productseries.translations_branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        with person_logged_in(self.productseries.translations_branch.owner):
            view = self._createView()
            self.assertTrue(view.has_exports_enabled)


class TestProductSeriesLanguageView(TestCaseWithFactory):
    """Test ProductSeriesLanguage view."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a productseries that uses translations.
        super(TestProductSeriesLanguageView, self).setUp()
        self.productseries = self.factory.makeProductSeries()
        self.language = self.factory.makeLanguage()
        potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        self.factory.makePOFile(language=self.language, potemplate=potemplate)
        self.psl = self.productseries.productserieslanguages[0]

    def _createView(self):
        view = ProductSeriesLanguageView(self.psl, LaunchpadTestRequest())
        view.initialize()
        return view

    def test_translation_group_no_group(self):
        view = self._createView()
        self.assertEquals(None, view.translation_group)

    def test_translation_team_no_group_no_team(self):
        view = self._createView()
        self.assertEquals(None, view.translation_team)

    def _makeTranslationGroup(self):
        group = self.factory.makeTranslationGroup(
            self.productseries.product.owner, url=None)
        self.productseries.product.translationgroup = group
        return group

    def test_translation_group(self):
        group = self._makeTranslationGroup()
        view = self._createView()
        self.assertEquals(group, view.translation_group)

    def test_translation_team_no_translator(self):
        # Just having a group doesn't mean there's a translation
        # team as well.
        self._makeTranslationGroup()
        view = self._createView()
        self.assertEquals(None, view.translation_team)

    def test_translation_team(self):
        # Setting a translator for this languages makes it
        # appear as the translation_team.
        group = self._makeTranslationGroup()
        translator = self.factory.makeTranslator(
            group=group, language=self.language)
        view = self._createView()
        self.assertEquals(translator, view.translation_team)
