# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for translation import queue auto-approval.

This test overlaps with the one in doc/translationimportqueue.txt.
Documentation-style tests go in there, ones that go systematically
through the possibilities should go here.
"""

from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
    )

from pytz import UTC
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.distribution import Distribution
from lp.registry.model.sourcepackagename import (
    SourcePackageName,
    SourcePackageNameSet,
    )
from lp.services.database.interfaces import IMasterStore
from lp.services.worlddata.model.language import (
    Language,
    LanguageSet,
    )
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.customlanguagecode import ICustomLanguageCode
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    translation_import_queue_entry_age,
    )
from lp.translations.model.customlanguagecode import CustomLanguageCode
from lp.translations.model.pofile import POFile
from lp.translations.model.potemplate import (
    POTemplateSet,
    POTemplateSubset,
    )
from lp.translations.model.translationimportqueue import (
    TranslationImportQueue,
    TranslationImportQueueEntry,
    )


class GardenerDbUserMixin(object):
    """Switch to the translations import queue gardener database role.

    Admittedly, this might be a little over-engineered but it looks good. ;)
    """

    def becomeTheGardener(self):
        """One-way method to avoid unnecessary switch back."""
        self.becomeDbUser('translations_import_queue_gardener')

    @contextmanager
    def beingTheGardener(self):
        """Context manager to restore the launchpad user."""
        self.becomeTheGardener()
        yield
        self.becomeDbUser('launchpad')


class TestCustomLanguageCode(TestCaseWithFactory):
    """Unit tests for `CustomLanguageCode`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestCustomLanguageCode, self).setUp()
        self.product_codes = {}
        self.package_codes = {}

        self.product = self.factory.makeProduct()

        # Map "es_ES" to "no language."
        self.product_codes['es_ES'] = CustomLanguageCode(
            product=self.product, language_code='es_ES')

        # Map "pt_PT" to "pt."
        self.product_codes['pt_PT'] = CustomLanguageCode(
            product=self.product, language_code='pt_PT',
            language=Language.byCode('pt'))

        self.distro = Distribution.byName('ubuntu')
        self.sourcepackagename = SourcePackageName.byName('evolution')
        self.package_codes['Brazilian'] = CustomLanguageCode(
            distribution=self.distro,
            sourcepackagename=self.sourcepackagename,
            language_code='Brazilian',
            language=Language.byCode('pt_BR'))

    def test_ICustomLanguageCode(self):
        # Does CustomLanguageCode conform to ICustomLanguageCode?
        custom_language_code = CustomLanguageCode(
            language_code='sux', product=self.product)
        verifyObject(ICustomLanguageCode, custom_language_code)

    def test_NoCustomLanguageCode(self):
        # Look up custom language code for context that has none.
        # The "fresh" items here are ones that have no custom language codes
        # associated with them.
        fresh_product = self.factory.makeProduct()
        self.assertEqual(fresh_product.getCustomLanguageCode('nocode'), None)
        self.assertEqual(fresh_product.getCustomLanguageCode('pt_PT'), None)

        fresh_distro = Distribution.byName('gentoo')
        gentoo_package = fresh_distro.getSourcePackage(self.sourcepackagename)
        nocode = gentoo_package.getCustomLanguageCode('nocode')
        self.assertEqual(nocode, None)
        brazilian = gentoo_package.getCustomLanguageCode('Brazilian')
        self.assertEqual(brazilian, None)

        cnews = SourcePackageName.byName('cnews')
        cnews_package = self.distro.getSourcePackage(cnews)
        self.assertEqual(cnews_package.getCustomLanguageCode('nocode'), None)
        self.assertEqual(
            cnews_package.getCustomLanguageCode('Brazilian'), None)

    def test_UnsuccessfulCustomLanguageCodeLookup(self):
        # Look up nonexistent custom language code for product.
        self.assertEqual(self.product.getCustomLanguageCode('nocode'), None)
        package = self.distro.getSourcePackage(self.sourcepackagename)
        self.assertEqual(package.getCustomLanguageCode('nocode'), None)

    def test_SuccessfulProductCustomLanguageCodeLookup(self):
        # Look up custom language code.
        es_ES_code = self.product.getCustomLanguageCode('es_ES')
        self.assertEqual(es_ES_code, self.product_codes['es_ES'])
        self.assertEqual(es_ES_code.product, self.product)
        self.assertEqual(es_ES_code.distribution, None)
        self.assertEqual(es_ES_code.sourcepackagename, None)
        self.assertEqual(es_ES_code.language_code, 'es_ES')
        self.assertEqual(es_ES_code.language, None)

    def test_SuccessfulPackageCustomLanguageCodeLookup(self):
        # Look up custom language code.
        package = self.distro.getSourcePackage(self.sourcepackagename)
        Brazilian_code = package.getCustomLanguageCode('Brazilian')
        self.assertEqual(Brazilian_code, self.package_codes['Brazilian'])
        self.assertEqual(Brazilian_code.product, None)
        self.assertEqual(Brazilian_code.distribution, self.distro)
        self.assertEqual(
            Brazilian_code.sourcepackagename, self.sourcepackagename)
        self.assertEqual(Brazilian_code.language_code, 'Brazilian')
        self.assertEqual(Brazilian_code.language, Language.byCode('pt_BR'))


class TestGuessPOFileCustomLanguageCode(TestCaseWithFactory,
                                        GardenerDbUserMixin):
    """Test interaction with `TranslationImportQueueEntry.getGuessedPOFile`.

    Auto-approval of translation files, i.e. figuring out which existing
    translation file a new upload might match, is a complex process.
    One of the factors that influence it is the existence of custom
    language codes that may redirect translations from a wrong language
    code to a right one, or to none at all.
    """

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestGuessPOFileCustomLanguageCode, self).setUp()
        self.product = self.factory.makeProduct()
        self.series = self.factory.makeProductSeries(product=self.product)
        self.queue = TranslationImportQueue()
        self.template = POTemplateSubset(productseries=self.series).new(
            'test', 'test', 'test.pot', self.product.owner)

    def _makePOFile(self, language_code):
        """Create a translation file."""
        file = self.template.newPOFile(language_code)
        file.syncUpdate()
        return file

    def _makeQueueEntry(self, language_code):
        """Create translation import queue entry."""
        return self.queue.addOrUpdateEntry(
            "%s.po" % language_code, 'contents', True, self.product.owner,
            productseries=self.series)

    def _setCustomLanguageCode(self, language_code, target_language_code):
        """Create custom language code."""
        if target_language_code is None:
            language = None
        else:
            language = Language.byCode(target_language_code)
        customcode = CustomLanguageCode(
            product=self.product, language_code=language_code,
            language=language)
        customcode.syncUpdate()

    def test_MatchWithoutCustomLanguageCode(self):
        # Of course matching will work without custom language codes.
        tr_file = self._makePOFile('tr')
        entry = self._makeQueueEntry('tr')
        self.becomeTheGardener()
        self.assertEqual(entry.getGuessedPOFile(), tr_file)

    def test_CustomLanguageCodeEnablesMatch(self):
        # Custom language codes may enable matches that wouldn't have been
        # found otherwise.
        fy_file = self._makePOFile('fy')
        entry = self._makeQueueEntry('fy_NL')
        self.assertEqual(entry.getGuessedPOFile(), None)

        self._setCustomLanguageCode('fy_NL', 'fy')

        self.becomeTheGardener()
        self.assertEqual(entry.getGuessedPOFile(), fy_file)

    def test_CustomLanguageCodeParsesBogusLanguage(self):
        # A custom language code can tell the importer how to deal with a
        # completely nonstandard language code.
        entry = self._makeQueueEntry('flemish')
        self.assertEqual(entry.getGuessedPOFile(), None)

        self._setCustomLanguageCode('flemish', 'nl')

        self.becomeTheGardener()
        nl_file = entry.getGuessedPOFile()
        self.assertEqual(nl_file.language.code, 'nl')

    def test_CustomLanguageCodePreventsMatch(self):
        # A custom language code that disables a language code may hide an
        # existing translation file from the matching process.
        sv_file = self._makePOFile('sv')
        entry = self._makeQueueEntry('sv')
        self.assertEqual(entry.getGuessedPOFile(), sv_file)

        self._setCustomLanguageCode('sv', None)

        self.becomeTheGardener()
        self.assertEqual(entry.getGuessedPOFile(), None)
        self.assertEqual(entry.status, RosettaImportStatus.DELETED)

    def test_CustomLanguageCodeHidesPOFile(self):
        # A custom language code may redirect the search away from an existing
        # translation file, even if it points to an existing language.
        elx_file = self._makePOFile('elx')
        entry = self._makeQueueEntry('elx')
        self.assertEqual(entry.getGuessedPOFile(), elx_file)

        self._setCustomLanguageCode('elx', 'el')

        self.becomeTheGardener()
        el_file = entry.getGuessedPOFile()
        self.failIfEqual(el_file, elx_file)
        self.assertEqual(el_file.language.code, 'el')

    def test_CustomLanguageCodeRedirectsMatch(self):
        # A custom language code may cause one match to be replaced by another
        # one.
        nn_file = self._makePOFile('nn')
        nb_file = self._makePOFile('nb')
        entry = self._makeQueueEntry('nb')
        self.assertEqual(entry.getGuessedPOFile(), nb_file)

        self._setCustomLanguageCode('nb', 'nn')

        self.becomeTheGardener()
        self.assertEqual(entry.getGuessedPOFile(), nn_file)

    def test_CustomLanguageCodeReplacesMatch(self):
        # One custom language code can block uploads for language code pt
        # while another redirects the uploads for pt_PT into their place.
        pt_file = self._makePOFile('pt')
        pt_entry = self._makeQueueEntry('pt')
        pt_PT_entry = self._makeQueueEntry('pt_PT')

        self._setCustomLanguageCode('pt', None)
        self._setCustomLanguageCode('pt_PT', 'pt')

        self.becomeTheGardener()
        self.assertEqual(pt_entry.getGuessedPOFile(), None)
        self.assertEqual(pt_PT_entry.getGuessedPOFile(), pt_file)

    def test_CustomLanguageCodesSwitchLanguages(self):
        # Two CustomLanguageCodes may switch two languages around.
        zh_CN_file = self._makePOFile('zh_CN')
        zh_TW_file = self._makePOFile('zh_TW')
        zh_CN_entry = self._makeQueueEntry('zh_CN')
        zh_TW_entry = self._makeQueueEntry('zh_TW')

        self._setCustomLanguageCode('zh_CN', 'zh_TW')
        self._setCustomLanguageCode('zh_TW', 'zh_CN')

        self.becomeTheGardener()
        self.assertEqual(zh_CN_entry.getGuessedPOFile(), zh_TW_file)
        self.assertEqual(zh_TW_entry.getGuessedPOFile(), zh_CN_file)


class TestTemplateGuess(TestCaseWithFactory, GardenerDbUserMixin):
    """Test auto-approval's attempts to find the right template."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTemplateGuess, self).setUp()
        self.templateset = POTemplateSet()

    def _setUpProduct(self):
        """Set up a `Product` with release series and two templates."""
        self.product = self.factory.makeProduct()
        self.productseries = self.factory.makeProductSeries(
            product=self.product)
        product_subset = POTemplateSubset(productseries=self.productseries)
        self.producttemplate1 = product_subset.new(
            'test1', 'test1', 'test.pot', self.product.owner)
        self.producttemplate2 = product_subset.new(
            'test2', 'test2', 'test.pot', self.product.owner)

    def _makeTemplateForDistroSeries(self, distroseries, name):
        """Create a template in the given `DistroSeries`."""
        distro_subset = POTemplateSubset(
            distroseries=distroseries, sourcepackagename=self.packagename)
        return distro_subset.new(name, name, 'test.pot', self.distro.owner)

    def _setUpDistro(self):
        """Set up a `Distribution` with two templates."""
        self.distro = self.factory.makeDistribution()
        self.distroseries = self.factory.makeDistroSeries(
            distribution=self.distro)
        self.packagename = SourcePackageNameSet().new('package')
        self.from_packagename = SourcePackageNameSet().new('from')
        self.distrotemplate1 = self._makeTemplateForDistroSeries(
            self.distroseries, 'test1')
        self.distrotemplate2 = self._makeTemplateForDistroSeries(
            self.distroseries, 'test2')

    def test_ByPathAndOrigin_product_duplicate(self):
        # When multiple templates match for a product series,
        # getPOTemplateByPathAndOrigin returns none.
        self._setUpProduct()
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', productseries=self.productseries)
        self.assertEqual(None, guessed_template)

    def test_ByPathAndOrigin_package_duplicate(self):
        # When multiple templates match on sourcepackagename,
        # getPOTemplateByPathAndOrigin returns none.
        self._setUpDistro()
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', sourcepackagename=self.packagename)
        self.assertEqual(None, guessed_template)

    def test_ByPathAndOrigin_from_package_duplicate(self):
        # When multiple templates match on from_sourcepackagename,
        # getPOTemplateByPathAndOrigin returns none.
        self._setUpDistro()
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', sourcepackagename=self.from_packagename)
        self.assertEqual(None, guessed_template)

    def test_ByPathAndOrigin_similar_between_distroseries(self):
        # getPOTemplateByPathAndOrigin disregards templates from other
        # distroseries.
        self._setUpDistro()
        other_series = self.factory.makeDistroSeries(
            distribution=self.distro)
        self._makeTemplateForDistroSeries(other_series, 'test1')
        self.distrotemplate1.iscurrent = False
        self.distrotemplate2.iscurrent = True
        self.distrotemplate1.from_sourcepackagename = None
        self.distrotemplate2.from_sourcepackagename = None
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', distroseries=self.distroseries,
            sourcepackagename=self.packagename)
        self.assertEqual(self.distrotemplate2, guessed_template)

    def test_ByPathAndOrigin_preferred_match(self):
        # getPOTemplateByPathAndOrigin prefers from_sourcepackagename
        # matches over sourcepackagename matches.
        self._setUpDistro()
        # Use unique name for this package, since the search does not
        # pass a distroseries and so might pick one of the same name up
        # from elsewhere.
        match_package = SourcePackageNameSet().new(
            self.factory.getUniqueString())
        self.distrotemplate1.sourcepackagename = match_package
        self.distrotemplate2.from_sourcepackagename = match_package

        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', sourcepackagename=match_package)
        self.assertEqual(self.distrotemplate2, guessed_template)

    def test_ByPathAndOriginProductNonCurrentDuplicate(self):
        # If two templates for the same product series have the same
        # path, but only one is current, that one is returned.
        self._setUpProduct()
        self.producttemplate1.iscurrent = False
        self.producttemplate2.iscurrent = True
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', productseries=self.productseries)
        self.assertEqual(guessed_template, self.producttemplate2)

    def test_ByPathAndOriginProductNoCurrentTemplate(self):
        # Non-current templates in product series are ignored.
        self._setUpProduct()
        self.producttemplate1.iscurrent = False
        self.producttemplate2.iscurrent = False
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', productseries=self.productseries)
        self.assertEqual(guessed_template, None)

    def test_ByPathAndOriginDistroNonCurrentDuplicate(self):
        # If two templates for the same distroseries and source package
        # have the same  path, but only one is current, the current one
        # is returned.
        self._setUpDistro()
        self.distrotemplate1.iscurrent = False
        self.distrotemplate2.iscurrent = True
        self.distrotemplate1.from_sourcepackagename = None
        self.distrotemplate2.from_sourcepackagename = None
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', distroseries=self.distroseries,
            sourcepackagename=self.packagename)
        self.assertEqual(guessed_template, self.distrotemplate2)

    def test_ByPathAndOriginDistroNoCurrentTemplate(self):
        # Non-current templates in distroseries are ignored.
        self._setUpDistro()
        self.distrotemplate1.iscurrent = False
        self.distrotemplate2.iscurrent = False
        self.distrotemplate1.from_sourcepackagename = None
        self.distrotemplate2.from_sourcepackagename = None
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', distroseries=self.distroseries,
            sourcepackagename=self.packagename)
        self.assertEqual(guessed_template, None)

    def test_ByPathAndOriginDistroFromSourcePackageNonCurrentDuplicate(self):
        # If two templates for the same distroseries and original source
        # package have the same path, but only one is current, that one is
        # returned.
        self._setUpDistro()
        self.distrotemplate1.iscurrent = False
        self.distrotemplate2.iscurrent = True
        self.distrotemplate1.from_sourcepackagename = self.from_packagename
        self.distrotemplate2.from_sourcepackagename = self.from_packagename
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', distroseries=self.distroseries,
            sourcepackagename=self.from_packagename)
        self.assertEqual(guessed_template, self.distrotemplate2)

    def test_ByPathAndOriginDistroFromSourcePackageNoCurrentTemplate(self):
        # Non-current templates in distroseries are ignored by the
        # "from_sourcepackagename" match.
        self._setUpDistro()
        self.distrotemplate1.iscurrent = False
        self.distrotemplate2.iscurrent = False
        self.distrotemplate1.from_sourcepackagename = self.from_packagename
        self.distrotemplate2.from_sourcepackagename = self.from_packagename
        self.becomeTheGardener()
        guessed_template = self.templateset.getPOTemplateByPathAndOrigin(
            'test.pot', distroseries=self.distroseries,
            sourcepackagename=self.from_packagename)
        self.assertEqual(guessed_template, None)

    def test_ByDomain_finds_by_domain(self):
        # matchPOTemplateByDomain looks for a template of a given domain
        # in the entry's context.  It ignores other domains.
        series = self.factory.makeProductSeries()
        templates = [
            self.factory.makePOTemplate(productseries=series)
            for counter in xrange(2)]
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=series)
        self.assertEqual(
            templates[0],
            removeSecurityProxy(entry).matchPOTemplateByDomain(
                templates[0].translation_domain))

    def test_byDomain_finds_in_productseries(self):
        # matchPOTemplateByDomain for a productseries upload looks only
        # in that productseries.
        domain = self.factory.getUniqueString()
        templates = [
            self.factory.makePOTemplate(
                translation_domain=domain,
                productseries=self.factory.makeProductSeries())
            for counter in xrange(2)]
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=templates[0].productseries)
        self.assertEqual(
            templates[0],
            removeSecurityProxy(entry).matchPOTemplateByDomain(domain))

    def test_byDomain_finds_in_source_package(self):
        # matchPOTemplateByDomain for a distro upload, if given a source
        # package, looks only in that source package.  It doesn't matter
        # if the entry itself is for the same source package or not.
        domain = self.factory.getUniqueString()
        distroseries = self.factory.makeDistroSeries()
        templates = [
            self.factory.makePOTemplate(
                translation_domain=domain, distroseries=distroseries,
                sourcepackagename=self.factory.makeSourcePackageName())
            for counter in xrange(2)]
        entry = self.factory.makeTranslationImportQueueEntry(
            distroseries=distroseries,
            sourcepackagename=templates[1].sourcepackagename)
        self.assertEqual(
            templates[0],
            removeSecurityProxy(entry).matchPOTemplateByDomain(
                domain, templates[0].sourcepackagename))

    def test_byDomain_ignores_sourcepackagename_by_default(self):
        # If no sourcepackagename is given, matchPOTemplateByDomain
        # on a distroseries searches all packages in the series.
        distroseries = self.factory.makeDistroSeries()
        template = self.factory.makePOTemplate(
            distroseries=distroseries,
            sourcepackagename=self.factory.makeSourcePackageName())
        entry = self.factory.makeTranslationImportQueueEntry(
            distroseries=distroseries,
            sourcepackagename=self.factory.makeSourcePackageName())
        self.assertEqual(
            template,
            removeSecurityProxy(entry).matchPOTemplateByDomain(
                template.translation_domain))

    def test_ByDomain_may_return_None(self):
        # If no templates match, matchPOTemplateByDomain returns None.
        entry = self.factory.makeTranslationImportQueueEntry()
        self.assertEqual(
            None,
            removeSecurityProxy(entry).matchPOTemplateByDomain("domain"))

    def test_ByDomain_reports_conflicts(self):
        # If multiple templates match, matchPOTemplateByDomain registers
        # an error in the entry's error_output, and returns None.
        domain = self.factory.getUniqueString()
        series = self.factory.makeProductSeries()
        templates = [
            self.factory.makePOTemplate(
                translation_domain=domain, productseries=series)
            for counter in xrange(2)]
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=series)

        with self.beingTheGardener():
            result = removeSecurityProxy(entry).matchPOTemplateByDomain(
                domain)

        self.assertIs(None, result)
        self.assertIn(templates[0].displayname, entry.error_output)

    def test_ByDomain_ignores_inactive_templates(self):
        series = self.factory.makeProductSeries()
        template = self.factory.makePOTemplate(
            productseries=series, iscurrent=False)
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=series)
        self.assertIs(
            None,
            removeSecurityProxy(entry).matchPOTemplateByDomain(
                template.translation_domain))

    def test_approval_clears_error_output(self):
        # If a previous approval attempt set an error notice on the
        # entry, successful approval clears it away.
        template = self.factory.makePOTemplate(path='messages.pot')
        pofile = self.factory.makePOFile(potemplate=template)
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=pofile.potemplate.productseries,
            potemplate=pofile.potemplate, pofile=pofile)
        entry.setErrorOutput("Entry can't be approved for whatever reason.")
        TranslationImportQueue()._attemptToApprove(entry)
        self.assertIs(None, entry.error_output)

    def test_ClashingEntries(self):
        # Very rarely two entries may have the same uploader, path, and
        # target package/productseries.  They would be approved for the
        # same template, except there's a uniqueness condition on that
        # set of properties.
        # To tickle this condition, the user first has to upload a file
        # that's not attached to a template; then upload another one
        # that is, before the first one goes into auto-approval.
        self._setUpProduct()
        queue = TranslationImportQueue()
        template = self.producttemplate1

        template.path = 'program/program.pot'
        self.producttemplate2.path = 'errors/errors.pot'
        entry1 = queue.addOrUpdateEntry(
            'program/nl.po', 'contents', False, template.owner,
            productseries=template.productseries)

        # The clashing entry goes through approval unsuccessfully, but
        # without causing breakage.
        queue.addOrUpdateEntry(
            'program/nl.po', 'other contents', False, template.owner,
            productseries=template.productseries, potemplate=template)

        self.becomeTheGardener()
        entry1.getGuessedPOFile()

        self.assertEqual(entry1.potemplate, None)

    def test_getGuessedPOFile_ignores_obsolete_POFiles(self):
        pofile = self.factory.makePOFile()
        template = pofile.potemplate
        template.iscurrent = False
        queue = getUtility(ITranslationImportQueue)
        entry = queue.addOrUpdateEntry(
            pofile.path, 'contents', False, self.factory.makePerson(),
            productseries=template.productseries)

        self.assertEqual(None, entry.getGuessedPOFile())

    def test_getGuessedPOFile_survives_clashing_obsolete_POFile_path(self):
        series = self.factory.makeProductSeries()
        current_template = self.factory.makePOTemplate(productseries=series)
        current_template.iscurrent = True
        current_pofile = self.factory.makePOFile(
            'nl', potemplate=current_template)
        obsolete_template = self.factory.makePOTemplate(productseries=series)
        obsolete_template.iscurrent = False
        obsolete_pofile = self.factory.makePOFile(
            'nl', potemplate=obsolete_template)
        obsolete_pofile.path = current_pofile.path

        queue = getUtility(ITranslationImportQueue)
        entry = queue.addOrUpdateEntry(
            current_pofile.path, 'contents', False, self.factory.makePerson(),
            productseries=series)

        self.assertEqual(current_pofile, entry.getGuessedPOFile())

    def test_pathless_template_match(self):
        # If an uploaded template has no directory component in its
        # path, and no matching template is found in the database, the
        # approver also tries if there might be exactly 1 template with
        # the same base filename.  If so, that's a match.
        self._setUpProduct()
        template = self.producttemplate1
        template.path = 'po/test.pot'
        self.producttemplate2.path = 'different.pot'

        queue = TranslationImportQueue()
        entry = queue.addOrUpdateEntry(
            'test.pot', 'contents', False, template.owner,
            productseries=template.productseries)

        self.assertEqual(template, entry.guessed_potemplate)

    def test_pathless_template_no_match(self):
        # The search for a matching filename will still ignore
        # templates with non-matching paths.
        self._setUpProduct()
        template = self.producttemplate1

        queue = TranslationImportQueue()
        entry = queue.addOrUpdateEntry(
            'other.pot', 'contents', False, template.owner,
            productseries=template.productseries)

        self.assertEqual(None, entry.guessed_potemplate)

    def test_pathless_template_multiple_matches(self):
        # If multiple active templates have matching filenames
        # (regardless of whether they're in subdirectories or in the
        # project root directory) then there is no unique match.
        self._setUpProduct()
        template = self.producttemplate1
        template.path = 'here/test.pot'
        self.producttemplate2.path = 'there/test.pot'

        queue = TranslationImportQueue()
        entry = queue.addOrUpdateEntry(
            'test.pot', 'contents', False, template.owner,
            productseries=template.productseries)

        self.assertEqual(None, entry.guessed_potemplate)

    def test_pathless_template_one_current_match(self):
        # Deactivated templates are not considered in the match; if one
        # active and one non-active template both match on filename, the
        # active one is returned as a unique match.
        self._setUpProduct()
        template = self.producttemplate1
        template.iscurrent = True
        template.path = 'here/test.pot'
        self.producttemplate2.iscurrent = False
        self.producttemplate2.path = 'there/test.pot'

        queue = TranslationImportQueue()
        entry = queue.addOrUpdateEntry(
            'test.pot', 'contents', False, template.owner,
            productseries=template.productseries)

        self.assertEqual(template, entry.guessed_potemplate)

    def test_avoid_clash_with_existing_entry(self):
        # When trying to approve a template upload that didn't have its
        # potemplate field set during upload or an earlier approval run,
        # the approver will fill out the field if it can.  But if by
        # then there's already another entry from the same person and
        # for the same target that does have the field set, then filling
        # out the field would make the two entries clash.
        queue = TranslationImportQueue()
        template = self.factory.makePOTemplate()
        old_entry = queue.addOrUpdateEntry(
            template.path, '# Content here', False, template.owner,
            productseries=template.productseries)
        new_entry = queue.addOrUpdateEntry(
            template.path, '# Content here', False, template.owner,
            productseries=template.productseries, potemplate=template)

        # Before approval, the two entries differ in that the new one
        # has a potemplate.
        self.assertNotEqual(old_entry, new_entry)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, old_entry.status)
        self.assertIs(None, old_entry.potemplate)
        self.assertEqual(template, new_entry.potemplate)
        IMasterStore(old_entry).flush()

        # The approver deals with the problem by skipping the entry.
        queue._attemptToApprove(old_entry)

        # So nothing changes.
        self.assertIs(None, old_entry.potemplate)
        self.assertEqual(template, new_entry.potemplate)


class TestKdePOFileGuess(TestCaseWithFactory, GardenerDbUserMixin):
    """Test auto-approval's `POFile` guessing for KDE uploads.

    KDE has an unusual setup that the approver recognizes as a special
    case: translation uploads are done in a package that represents a
    KDE language pack, following a naming convention that differs
    between KDE3 and KDE4.  The approver then attaches entries to the
    real software packages they belong to, which it finds by looking
    for a matching translation domain.
    """
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestKdePOFileGuess, self).setUp()
        self.queue = TranslationImportQueue()

        self.distroseries = self.factory.makeDistroSeries()

        # For each of KDE3 and KDE4, set up:
        #  a translation package following that KDE's naming pattern,
        #  another package that the translations really belong in,
        #  a template for that other package, and
        #  a translation file into a language we'll test in.
        self.kde_i18n_ca = SourcePackageNameSet().new('kde-i18n-ca')
        kde3_package = SourcePackageNameSet().new('kde3')
        ca_template = self.factory.makePOTemplate(
            distroseries=self.distroseries,
            sourcepackagename=kde3_package, name='kde3',
            translation_domain='kde3')
        self.pofile_ca = ca_template.newPOFile('ca')

        self.kde_l10n_nl = SourcePackageNameSet().new('kde-l10n-nl')
        kde4_package = SourcePackageNameSet().new('kde4')
        nl_template = self.factory.makePOTemplate(
            distroseries=self.distroseries,
            sourcepackagename=kde4_package, name='kde4',
            translation_domain='kde4')
        self.pofile_nl = nl_template.newPOFile('nl')

        self.pocontents = """
            msgid "foo"
            msgstr ""
            """

    def test_kde3(self):
        # KDE3 translations are in packages named kde-i10n-** (where **
        # is the language code).
        poname = self.pofile_ca.potemplate.name + '.po'
        entry = self.queue.addOrUpdateEntry(
            poname, self.pocontents, False, self.distroseries.owner,
            sourcepackagename=self.kde_i18n_ca,
            distroseries=self.distroseries)
        self.becomeTheGardener()
        pofile = entry.getGuessedPOFile()
        self.assertEqual(pofile, self.pofile_ca)

    def test_kde4(self):
        # KDE4 translations are in packages named kde-l10n-** (where **
        # is the language code).
        poname = self.pofile_nl.potemplate.name + '.po'
        entry = self.queue.addOrUpdateEntry(
            poname, self.pocontents, False, self.distroseries.owner,
            sourcepackagename=self.kde_l10n_nl,
            distroseries=self.distroseries)
        self.becomeTheGardener()
        pofile = entry.getGuessedPOFile()
        self.assertEqual(pofile, self.pofile_nl)


class TestGetPOFileFromLanguage(TestCaseWithFactory, GardenerDbUserMixin):
    """Test `TranslationImportQueueEntry._get_pofile_from_language`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestGetPOFileFromLanguage, self).setUp()
        self.queue = TranslationImportQueue()

    def test_get_pofile_from_language_feeds_enabled_template(self):
        # _get_pofile_from_language will find an enabled template, and
        # return either an existing POFile for the given language, or a
        # newly created one.
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        trunk = product.getSeries('trunk')
        template = self.factory.makePOTemplate(
            productseries=trunk, translation_domain='domain')
        template.iscurrent = True

        entry = self.queue.addOrUpdateEntry(
            'nl.po', '# ...', False, template.owner, productseries=trunk)

        self.becomeTheGardener()
        pofile = entry._get_pofile_from_language('nl', 'domain')
        self.assertNotEqual(None, pofile)

    def test_get_pofile_from_language_starves_disabled_template(self):
        # _get_pofile_from_language will not consider a disabled
        # template as an auto-approval target, and so will not return a
        # POFile for it.
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        trunk = product.getSeries('trunk')
        template = self.factory.makePOTemplate(
            productseries=trunk, translation_domain='domain')
        template.iscurrent = False

        entry = self.queue.addOrUpdateEntry(
            'nl.po', '# ...', False, template.owner, productseries=trunk)

        self.becomeTheGardener()
        pofile = entry._get_pofile_from_language('nl', 'domain')
        self.assertEqual(None, pofile)

    def test_get_pofile_from_language_works_with_translation_credits(self):
        # When the template has translation credits, a new dummy translation
        # is created in the new POFile. Since this is running with gardener
        # privileges, we need to check that this works, too.
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        trunk = product.getSeries('trunk')
        template = self.factory.makePOTemplate(
            productseries=trunk, translation_domain='domain')
        template.iscurrent = True
        self.factory.makePOTMsgSet(template, "translator-credits")

        entry = self.queue.addOrUpdateEntry(
            'nl.po', '# ...', False, template.owner, productseries=trunk)

        self.becomeTheGardener()
        pofile = entry._get_pofile_from_language('nl', 'domain')
        self.assertNotEqual(None, pofile)


class TestCleanup(TestCaseWithFactory, GardenerDbUserMixin):
    """Test `TranslationImportQueueEntry` garbage collection."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestCleanup, self).setUp()
        self.queue = TranslationImportQueue()
        self.store = IMasterStore(TranslationImportQueueEntry)

    def _makeProductEntry(self, path='foo.pot', status=None):
        """Simulate upload for a product."""
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        trunk = product.getSeries('trunk')
        entry = self.queue.addOrUpdateEntry(
            path, '# contents', False, product.owner, productseries=trunk)
        if status is not None:
            entry.status = status
        return entry

    def _makeDistroEntry(self, path='bar.pot', status=None):
        """Simulate upload for a distribution package."""
        package = self.factory.makeSourcePackage()
        owner = package.distroseries.owner
        entry = self.queue.addOrUpdateEntry(
            path, '# contents', False, owner,
            sourcepackagename=package.sourcepackagename,
            distroseries=package.distroseries)
        if status is not None:
            entry.status = status
        return entry

    def _ageEntry(self, entry, interval):
        """Make an entry's timestamps older by a given interval."""
        entry.dateimported -= interval
        entry.date_status_changed -= interval
        entry.syncUpdate()

    def _exists(self, entry_id):
        """Is the entry with the given id still on the queue?"""
        entry = self.store.find(
            TranslationImportQueueEntry,
            TranslationImportQueueEntry.id == entry_id).any()
        return entry is not None

    def _setStatus(self, entry, status, when=None):
        """Simulate status on queue entry having been set at a given time."""
        entry.setStatus(status,
                        getUtility(ILaunchpadCelebrities).rosetta_experts)
        if when is not None:
            entry.date_status_changed = when
        entry.syncUpdate()

    def test_cleanUpObsoleteEntries_unaffected_statuses(self):
        # _cleanUpObsoleteEntries leaves entries in states without
        # expiry age (currently only Blocked) alone no matter how old
        # they are.
        unaffected_statuses = (
            set(RosettaImportStatus.items) -
                set(translation_import_queue_entry_age.keys()))
        self.assertNotEqual(
            0, len(unaffected_statuses),
            "This test is no longer needed; "
            "there are no statuses without expiry ages.")

        years_ago = datetime.now(UTC) - timedelta(days=2000)
        entry = self._makeProductEntry()
        entry.potemplate = self.factory.makePOTemplate(
                productseries=entry.productseries)
        entry_id = entry.id
        for status in unaffected_statuses:
            self._setStatus(entry, status, years_ago)
            self.queue._cleanUpObsoleteEntries(self.store)
            self.assertTrue(self._exists(entry_id))

    def test_cleanUpObsoleteEntries_affected_statuses(self):
        # _cleanUpObsoleteEntries deletes entries in terminal states
        # (Imported, Failed, Deleted) after a few days.  The exact
        # period depends on the state.  Entries in certain other states
        # get cleaned up after longer periods.
        for status in translation_import_queue_entry_age.keys():
            entry = self._makeProductEntry()
            entry.potemplate = self.factory.makePOTemplate()
            maximum_age = translation_import_queue_entry_age[status]
            self._setStatus(entry, status)

            # A day before the cleanup age for this status, the
            # entry is left intact.
            self._ageEntry(entry, maximum_age - timedelta(days=1))
            entry_id = entry.id

            # No write or delete action expected, so no reason to switch the
            # database user.  If it writes or deletes, the test has failed
            # anyway.
            self.queue._cleanUpObsoleteEntries(self.store)
            self.assertTrue(self._exists(entry_id))

            # Two days later, the entry is past its cleanup age and will
            # be removed.
            self._ageEntry(entry, timedelta(days=2))
            with self.beingTheGardener():
                self.queue._cleanUpObsoleteEntries(self.store)
                self.assertFalse(
                    self._exists(entry_id),
                    "Queue entry in state '%s' was not removed." % status)

    def test_cleanUpObsoleteEntries_blocked_ubuntu_po(self):
        # _cleanUpObsoleteEntries deletes Ubuntu entries for gettext
        # translations that are Blocked if they haven't been touched in
        # a year.  These entries once made up about half the queue.  As
        # far as we can tell all these PO files have been auto-blocked
        # after their template uploads were blocked, so even if they
        # were ever re-uploaded, they'd just get blocked again.
        entry = self._makeDistroEntry(
            path='fo.po', status=RosettaImportStatus.BLOCKED)
        self._ageEntry(entry, timedelta(days=300))
        entry_id = entry.id

        # It hasn't been a year yet since the last status change; the
        # entry stays in place.
        with self.beingTheGardener():
            self.queue._cleanUpObsoleteEntries(self.store)
        self.assertTrue(self._exists(entry_id))

        # Months later, a year has passed; the entry gets cleaned up.
        self._ageEntry(entry, timedelta(days=100))
        with self.beingTheGardener():
            self.queue._cleanUpObsoleteEntries(self.store)
        self.assertFalse(self._exists(entry_id))

    def test_cleanUpObsoleteEntries_ignores_entry_age(self):
        # _cleanUpObsoleteEntries looks at date of an entry's last
        # status change; the upload date does not matter.
        entry = self._makeDistroEntry(
            path='fo.po', status=RosettaImportStatus.BLOCKED)
        entry.dateimported -= timedelta(days=9000)
        entry_id = entry.id

        with self.beingTheGardener():
            self.queue._cleanUpObsoleteEntries(self.store)
        self.assertTrue(self._exists(entry_id))

        entry.date_status_changed -= timedelta(days=400)
        with self.beingTheGardener():
            self.queue._cleanUpObsoleteEntries(self.store)
        self.assertFalse(self._exists(entry_id))

    def test_cleanUpObsoleteEntries_blocked_product_po(self):
        # _cleanUpObsoleteEntries leaves blocked project uploads in
        # place.
        entry = self._makeProductEntry(
            path='fo.po', status=RosettaImportStatus.BLOCKED)
        self._ageEntry(entry, timedelta(days=400))
        entry_id = entry.id

        with self.beingTheGardener():
            self.queue._cleanUpObsoleteEntries(self.store)

        self.assertTrue(self._exists(entry_id))

    def test_cleanUpObsoleteEntries_blocked_ubuntu_pot(self):
        # _cleanUpObsoleteEntries leaves blocked Ubuntu templates in
        # place.
        entry = self._makeDistroEntry(
            path='foo.pot', status=RosettaImportStatus.BLOCKED)
        self._ageEntry(entry, timedelta(days=400))
        entry_id = entry.id

        with self.beingTheGardener():
            self.queue._cleanUpObsoleteEntries(self.store)

        self.assertTrue(self._exists(entry_id))

    def test_cleanUpInactiveProductEntries(self):
        # After a product is deactivated, _cleanUpInactiveProductEntries
        # will clean up any entries it may have on the queue.
        entry = self._makeProductEntry()
        entry_id = entry.id

        self.queue._cleanUpInactiveProductEntries(self.store)
        self.assertTrue(self._exists(entry_id))

        entry.productseries.product.active = False
        entry.productseries.product.syncUpdate()

        self.becomeTheGardener()
        self.queue._cleanUpInactiveProductEntries(self.store)
        self.assertFalse(self._exists(entry_id))

    def test_cleanUpObsoleteDistroEntries(self):
        # _cleanUpObsoleteDistroEntries cleans up entries for
        # distroseries that are in the Obsolete state.
        entry = self._makeDistroEntry()
        entry_id = entry.id

        self.queue._cleanUpObsoleteDistroEntries(self.store)
        self.assertTrue(self._exists(entry_id))

        entry.distroseries.status = SeriesStatus.OBSOLETE
        entry.distroseries.syncUpdate()

        self.becomeTheGardener()
        self.queue._cleanUpObsoleteDistroEntries(self.store)
        self.assertFalse(self._exists(entry_id))


class TestAutoApprovalNewPOFile(TestCaseWithFactory, GardenerDbUserMixin):
    """Test creation of new `POFile`s in approval."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestAutoApprovalNewPOFile, self).setUp()
        self.product = self.factory.makeProduct()
        self.queue = TranslationImportQueue()
        self.language = LanguageSet().getLanguageByCode('nl')

    def _makeTemplate(self, series):
        """Create a template."""
        return POTemplateSubset(productseries=series).new(
            'test', 'test', 'test.pot', self.product.owner)

    def _makeQueueEntry(self, series):
        """Create translation import queue entry."""
        return self.queue.addOrUpdateEntry(
            "%s.po" % self.language.code, 'contents', True,
            self.product.owner, productseries=series)

    def test_getGuessedPOFile_creates_POFile(self):
        # Auto-approval may involve creating POFiles.  The queue
        # gardener has permissions to do this.  The POFile's owner is
        # the rosetta_experts team.
        trunk = self.product.getSeries('trunk')
        self._makeTemplate(trunk)
        entry = self._makeQueueEntry(trunk)
        rosetta_experts = getUtility(ILaunchpadCelebrities).rosetta_experts

        self.becomeTheGardener()

        pofile = entry.getGuessedPOFile()

        self.assertIsInstance(pofile, POFile)
        self.assertNotEqual(rosetta_experts, pofile.owner)

    def test_getGuessedPOFile_creates_POFile_with_credits(self):
        # When the approver creates a POFile for a template that
        # has a translation credits message, it also includes a
        # "translation" for the credits message.
        trunk = self.product.getSeries('trunk')
        template = self._makeTemplate(trunk)
        credits = self.factory.makePOTMsgSet(
            template, singular='translation-credits')

        entry = self._makeQueueEntry(trunk)

        self.becomeTheGardener()

        entry.getGuessedPOFile()

        credits.getCurrentTranslation(
            template, self.language, template.translation_side)
        self.assertNotEqual(None, credits)


class TestAutoBlocking(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestAutoBlocking, self).setUp()
        self.queue = TranslationImportQueue()
        # Our test queue operates on the master store instead of the
        # slave store so we don't have to synchronize stores.
        master_store = IMasterStore(TranslationImportQueueEntry)
        self.queue._getSlaveStore = FakeMethod(result=master_store)

    def _copyTargetFromEntry(self, entry):
        """Return a dict representing `entry`'s translation target.

        :param entry: An existing `TranslationImportQueueEntry`, or None.
        """
        if entry is None:
            return {}
        else:
            return {
                'distroseries': entry.distroseries,
                'sourcepackagename': entry.sourcepackagename,
                'productseries': entry.productseries,
            }

    def _makeTemplateEntry(self, suffix='.pot', directory=None, status=None,
                           same_target_as=None):
        """Create an import queue entry for a template.

        If `same_target_as` is given, creates an entry for the same
        translation target as `same_target_as`.  This lets you create an
        entry for the same translation target as another one.
        """
        if suffix == '.xpi':
            basename = 'en-US'
        else:
            basename = self.factory.getUniqueString()

        filename = basename + suffix
        if directory is None:
            path = filename
        else:
            path = '/'.join([directory, filename])

        target = self._copyTargetFromEntry(same_target_as)

        return removeSecurityProxy(
            self.factory.makeTranslationImportQueueEntry(
                path=path, status=status, **target))

    def _makeTranslationEntry(self, path, status=None, same_target_as=None):
        """Create an import queue entry for a translation file.

        If `same_target_as` is given, creates an entry for the same
        translation target as `same_target_as`.  This lets you create an
        entry that may have to be blocked depending on same_target_as.
        """
        target = self._copyTargetFromEntry(same_target_as)
        return removeSecurityProxy(
            self.factory.makeTranslationImportQueueEntry(
                path=path, status=status, **target))

    def test_getBlockableDirectories_checks_templates(self):
        old_blocklist = self.queue._getBlockableDirectories()

        self._makeTemplateEntry(status=RosettaImportStatus.BLOCKED)

        new_blocklist = self.queue._getBlockableDirectories()

        self.assertEqual(len(old_blocklist) + 1, len(new_blocklist))

    def test_getBlockableDirectories_ignores_translations(self):
        old_blocklist = self.queue._getBlockableDirectories()

        self._makeTranslationEntry(
            'gl.po', status=RosettaImportStatus.BLOCKED)

        new_blocklist = self.queue._getBlockableDirectories()

        self.assertEqual(len(old_blocklist), len(new_blocklist))

    def test_getBlockableDirectories_checks_xpi_templates(self):
        old_blocklist = self.queue._getBlockableDirectories()

        self._makeTemplateEntry(
            suffix='.xpi', status=RosettaImportStatus.BLOCKED)

        new_blocklist = self.queue._getBlockableDirectories()

        self.assertEqual(len(old_blocklist) + 1, len(new_blocklist))

    def test_getBlockableDirectories_ignores_xpi_translations(self):
        old_blocklist = self.queue._getBlockableDirectories()

        self._makeTranslationEntry(
            'lt.xpi', status=RosettaImportStatus.BLOCKED)

        new_blocklist = self.queue._getBlockableDirectories()

        self.assertEqual(len(old_blocklist), len(new_blocklist))

    def test_isBlockable_none(self):
        blocklist = self.queue._getBlockableDirectories()
        entry = self._makeTranslationEntry('nl.po')
        self.assertFalse(self.queue._isBlockable(entry, blocklist))

    def test_isBlockable_one_blocked(self):
        blocked_template = self._makeTemplateEntry(
            status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()

        translations = self._makeTranslationEntry(
            'de.po', same_target_as=blocked_template)
        self.assertTrue(self.queue._isBlockable(translations, blocklist))

    def test_isBlockable_multiple_blocked(self):
        blocked1 = self._makeTemplateEntry(status=RosettaImportStatus.BLOCKED)
        self._makeTemplateEntry(
            status=RosettaImportStatus.BLOCKED, same_target_as=blocked1)
        blocklist = self.queue._getBlockableDirectories()

        translations = self._makeTranslationEntry(
            'lo.po', same_target_as=blocked1)

        self.assertTrue(self.queue._isBlockable(translations, blocklist))

    def test_isBlockable_one_unblocked(self):
        unblocked = self._makeTemplateEntry()
        blocklist = self.queue._getBlockableDirectories()

        translations = self._makeTranslationEntry(
            'xh.po', same_target_as=unblocked)

        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_isBlockable_mixed(self):
        # When there are both blocked and unblocked template entries in
        # a directory, translation uploads for that directory are not
        # blocked.
        blocked = self._makeTemplateEntry(status=RosettaImportStatus.BLOCKED)
        self._makeTemplateEntry(same_target_as=blocked)
        blocklist = self.queue._getBlockableDirectories()

        translations = self._makeTranslationEntry(
            'fr.po', same_target_as=blocked)

        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_rootdir_match(self):
        # _getBlockableDirectories matches sees a template and
        # translations file in the root directory as being in the same
        # directory.
        blocked = self._makeTemplateEntry(
            directory=None, status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'es.po', same_target_as=blocked)
        self.assertTrue(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_rootdir_nonmatch(self):
        # _getBlockableDirectories matches sees a template in the root
        # directory (i.e. without a directory component in its path) as
        # being in a different directory from a translations upload in a
        # subdirectory.
        blocked = self._makeTemplateEntry(
            directory=None, status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'po/es.po', same_target_as=blocked)
        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_subdir_match(self):
        # _getBlockableDirectories matches sees a template and
        # translations file in the same directory as being in the same
        # directory.
        blocked = self._makeTemplateEntry(
            directory='po/module', status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'po/module/es.po', same_target_as=blocked)
        self.assertTrue(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_subdir_nonmatch(self):
        # _getBlockableDirectories matches sees a template in a
        # subdirectory as being in a different directory from a
        # translations upload in the root directory.
        blocked = self._makeTemplateEntry(
            directory='po', status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'es.po', same_target_as=blocked)
        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_nested_translations(self):
        # _getBlockableDirectories sees a translations upload in a
        # subdirectory of that on the template upload as being in a
        # different directory.
        blocked = self._makeTemplateEntry(
            directory='po', status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'po/module/es.po', same_target_as=blocked)
        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_nested_template(self):
        # _getBlockableDirectories sees a translations upload in one
        # directory and a template upload in a subdirectory of that
        # directory as being in different directories.
        blocked = self._makeTemplateEntry(
            directory='po/module', status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'po/es.po', same_target_as=blocked)
        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_substring_translations(self):
        # _getBlockableDirectories sees the difference between a
        # template's directory and a translation upload's directory even
        # if the latter is a substring of the former.
        blocked = self._makeTemplateEntry(
            directory='po/moduleX', status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'po/module/es.po', same_target_as=blocked)
        self.assertFalse(self.queue._isBlockable(translations, blocklist))

    def test_getBlockableDirectories_path_substring_template(self):
        # _getBlockableDirectories sees the difference between a
        # template's directory and a translation upload's directory even
        # if the former is a substring of the latter.
        blocked = self._makeTemplateEntry(
            directory='po/module', status=RosettaImportStatus.BLOCKED)
        blocklist = self.queue._getBlockableDirectories()
        translations = self._makeTranslationEntry(
            'po/moduleX/es.po', same_target_as=blocked)
        self.assertFalse(self.queue._isBlockable(translations, blocklist))
