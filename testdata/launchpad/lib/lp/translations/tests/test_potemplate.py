# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from operator import methodcaller

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.interfaces.side import TranslationSide
from lp.translations.model.potemplate import get_pofiles_for


class TestPOTemplate(TestCaseWithFactory):
    """Test POTemplate functions not covered by doctests."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.potemplate = removeSecurityProxy(self.factory.makePOTemplate(
            translation_domain="testdomain"))

    def assertIsDummy(self, pofile):
        """Assert that `pofile` is actually a `DummyPOFile`."""
        # Avoid circular imports.
        from lp.translations.model.pofile import DummyPOFile

        self.assertEquals(DummyPOFile, type(pofile))

    def test_composePOFilePath(self):
        esperanto = getUtility(ILanguageSet).getLanguageByCode('eo')
        self.potemplate.path = "testdir/messages.pot"
        expected = "testdir/testdomain-eo.po"
        result = self.potemplate._composePOFilePath(esperanto)
        self.failUnlessEqual(expected, result,
            "_composePOFilePath does not create a correct file name with "
            "directory and language code. "
            "(Expected: '%s' Got: '%s')" % (expected, result))

        self.potemplate.path = "testdir/messages.pot"
        expected = "testdir/testdomain-eo@variant.po"
        esperanto_variant = self.factory.makeLanguage(
            'eo@variant', 'Esperanto Variant')
        result = self.potemplate._composePOFilePath(esperanto_variant)
        self.failUnlessEqual(expected, result,
            "_composePOFilePath does not create a correct file name with "
            "directory, language code and variant. "
            "(Expected: '%s' Got: '%s')" % (expected, result))

        self.potemplate.path = "/messages.pot"
        expected = "/testdomain-eo.po"
        result = self.potemplate._composePOFilePath(esperanto)
        self.failUnlessEqual(expected, result,
            "_composePOFilePath does not create a correct file name with "
            "leading slash and language code. "
            "(Expected: '%s' Got: '%s')" % (expected, result))

        self.potemplate.path = "messages.pot"
        expected = "testdomain-eo.po"
        result = self.potemplate._composePOFilePath(esperanto)
        self.failUnlessEqual(expected, result,
            "_composePOFilePath does not create a correct file name with "
            "missing directory and language code. "
            "(Expected: '%s' Got: '%s')" % (expected, result))

    def test_getDummyPOFile_no_existing_pofile(self):
        # Test basic behaviour of getDummyPOFile.
        language = self.factory.makeLanguage('sr@test')
        dummy = self.potemplate.getDummyPOFile(language)
        self.assertIsDummy(dummy)

    def test_getDummyPOFile_with_existing_pofile(self):
        # Test that getDummyPOFile fails when trying to get a DummyPOFile
        # where a POFile already exists for that language.
        language = self.factory.makeLanguage('sr@test')
        self.potemplate.newPOFile(language.code)
        self.assertRaises(
            AssertionError, self.potemplate.getDummyPOFile, language)

    def test_getDummyPOFile_with_existing_pofile_no_check(self):
        # Test that getDummyPOFile succeeds when trying to get a DummyPOFile
        # where a POFile already exists for that language when
        # check_for_existing=False is passed in.
        language = self.factory.makeLanguage('sr@test')
        self.potemplate.newPOFile(language.code)
        # This is just "assertNotRaises".
        dummy = self.potemplate.getDummyPOFile(language,
                                               check_for_existing=False)
        self.assertIsDummy(dummy)

    def test_newPOFile_owner(self):
        # The intended owner of a new POFile can be passed to newPOFile.
        language = self.factory.makeLanguage('nl@test')
        person = self.factory.makePerson()
        pofile = self.potemplate.newPOFile(language.code, owner=person)
        self.assertEqual(person, pofile.owner)

    def test_getDummyPOFile_owner(self):
        # The intended owner of a new DummyPOFile can be passed to
        # getDummyPOFile.
        language = self.factory.makeLanguage('nl@test')
        person = self.factory.makePerson()
        pofile = self.potemplate.getDummyPOFile(language, requester=person)
        self.assertEqual(person, pofile.owner)

    def test_getTranslationCredits(self):
        # getTranslationCredits returns only translation credits.
        self.factory.makePOTMsgSet(self.potemplate, sequence=1)
        gnome_credits = self.factory.makePOTMsgSet(
            self.potemplate, sequence=2, singular=u"translator-credits")
        kde_credits = self.factory.makePOTMsgSet(
            self.potemplate, sequence=3,
            singular=u"Your emails", context=u"EMAIL OF TRANSLATORS")
        self.factory.makePOTMsgSet(self.potemplate, sequence=4)

        self.assertContentEqual([gnome_credits, kde_credits],
                                self.potemplate.getTranslationCredits())

    def test_awardKarma(self):
        person = self.factory.makePerson()
        template = self.factory.makePOTemplate()
        karma_listener = self.installKarmaRecorder(
            person=person, product=template.product)
        action = 'translationsuggestionadded'

        # This is not something that browser code or scripts should do,
        # so we go behind the proxy.
        removeSecurityProxy(template).awardKarma(person, action)

        karma_events = karma_listener.karma_events
        self.assertEqual(1, len(karma_events))
        self.assertEqual(action, karma_events[0].action.name)

    def test_translationtarget_can_be_productseries(self):
        productseries = self.factory.makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        self.assertEqual(productseries, template.translationtarget)

    def test_translationtarget_can_be_sourcepackage(self):
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        self.assertEqual(package, template.translationtarget)

    def _toggleIsCurrent(self, states):
        """Toggle iscurrent according to states and report call count.

        :param states: An array of Boolean values to set iscurrent to.
        :returns: An array of integers representing the call count for
            removeFromSuggestivePOTemplatesCache after each toggle.
        """
        patched_method = FakeMethod(result=True)
        self.potemplate._removeFromSuggestivePOTemplatesCache = patched_method
        call_counts = []
        for state in states:
            self.potemplate.setActive(state)
            call_counts.append(patched_method.call_count)
        return call_counts

    def test_setActive_detects_negative_edge(self):
        # SetActive will only trigger suggestive cache removal if the flag
        # changes from true to false.
        # Start with a current template.
        self.assertTrue(self.potemplate.iscurrent)
        # The toggle sequence, contains two negative edges.
        self.assertEqual(
            [0, 1, 1, 1, 2],
            self._toggleIsCurrent([True, False, False, True, False]))


class EquivalenceClassTestMixin:
    """Helper for POTemplate equivalence class tests."""

    def _compareResult(self, expected, actual):
        """Compare equivalence-classes set to expectations.

        This ignores the ordering of templates in an equivalence class.
        A separate test looks at ordering.
        """
        self.assertEqual(set(actual.iterkeys()), set(expected.iterkeys()))
        for key, value in actual.iteritems():
            self.assertEqual(set(value), set(expected[key]))


class TestProductTemplateEquivalenceClasses(TestCaseWithFactory,
                                            EquivalenceClassTestMixin):
    """Which templates in Products will and will not share messages."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestProductTemplateEquivalenceClasses, self).setUp()
        self.product = self.factory.makeProduct()
        self.trunk = self.product.getSeries('trunk')
        self.stable = self.factory.makeProductSeries(
            product=self.product)
        self.subset = getUtility(IPOTemplateSet).getSharingSubset(
            product=self.product)

    def test_ProductTemplateEquivalence(self):
        # Within a product, two identically named templates form an
        # equivalence class.
        trunk_template = self.factory.makePOTemplate(
            productseries=self.trunk, name='foo')
        stable_template = self.factory.makePOTemplate(
            productseries=self.stable, name='foo')

        classes = self.subset.groupEquivalentPOTemplates()
        expected = {('foo', None): [trunk_template, stable_template]}
        self._compareResult(expected, classes)

    def test_DifferentlyNamedProductTemplatesAreNotEquivalent(self):
        # Two differently-named templates in a product do not form an
        # equivalence class.
        trunk_template = self.factory.makePOTemplate(
            productseries=self.trunk, name='foo')
        stable_template = self.factory.makePOTemplate(
            productseries=self.stable, name='bar')

        classes = self.subset.groupEquivalentPOTemplates()
        expected = {
            ('foo', None): [trunk_template],
            ('bar', None): [stable_template],
        }
        self._compareResult(expected, classes)

    def test_NoEquivalenceAcrossProducts(self):
        # Two identically-named templates in different products do not
        # form an equivalence class.
        external_series = self.factory.makeProductSeries()
        template1 = self.factory.makePOTemplate(
            productseries=self.trunk, name='foo')
        template2 = self.factory.makePOTemplate(
            productseries=external_series, name='foo')

        classes = self.subset.groupEquivalentPOTemplates()
        expected = {('foo', None): [template1]}
        self._compareResult(expected, classes)

        external_subset = getUtility(IPOTemplateSet).getSharingSubset(
            product=external_series.product)
        classes = external_subset.groupEquivalentPOTemplates()
        expected = {('foo', None): [template2]}
        self._compareResult(expected, classes)

    def test_GetSharingPOTemplates(self):
        # getSharingTemplates simply returns a list of sharing templates.
        trunk_template = self.factory.makePOTemplate(
            productseries=self.trunk, name='foo')
        stable_template = self.factory.makePOTemplate(
            productseries=self.stable, name='foo')
        self.factory.makePOTemplate(
            productseries=self.stable, name='foo-other')

        templates = set(list(self.subset.getSharingPOTemplates('foo')))
        self.assertEqual(set([trunk_template, stable_template]), templates)


class TestDistroTemplateEquivalenceClasses(TestCaseWithFactory,
                                           EquivalenceClassTestMixin):
    """Which templates in Distributions will and will not share messages."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestDistroTemplateEquivalenceClasses, self).setUp()
        self.ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        self.hoary = self.ubuntu['hoary']
        self.warty = self.ubuntu['warty']
        self.package = self.factory.makeSourcePackageName()

    def test_PackageTemplateEquivalence(self):
        # Two identically-named templates in the same source package in
        # different releases of the same distribution form an
        # equivalence class.
        hoary_template = self.factory.makePOTemplate(
            distroseries=self.hoary, sourcepackagename=self.package,
            name='foo')
        warty_template = self.factory.makePOTemplate(
            distroseries=self.warty, sourcepackagename=self.package,
            name='foo')

        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=self.ubuntu, sourcepackagename=self.package)
        classes = subset.groupEquivalentPOTemplates()

        expected = {
            ('foo', self.package.name): [hoary_template, warty_template],
        }
        self._compareResult(expected, classes)

    def test_DifferentlyNamedDistroTemplatesAreNotEquivalent(self):
        # Two differently-named templates in a distribution package do
        # not form an equivalence class.
        hoary_template = self.factory.makePOTemplate(
            distroseries=self.hoary, sourcepackagename=self.package,
            name='foo')
        warty_template = self.factory.makePOTemplate(
            distroseries=self.warty, sourcepackagename=self.package,
            name='bar')

        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=self.ubuntu, sourcepackagename=self.package)
        classes = subset.groupEquivalentPOTemplates()

        expected = {
            ('foo', self.package.name): [hoary_template],
            ('bar', self.package.name): [warty_template],
        }
        self._compareResult(expected, classes)

    def test_NoEquivalenceAcrossPackages(self):
        # Two identically-named templates in the same distribution do
        # not form an equivalence class if they don't have the same
        # source package name.
        other_package = self.factory.makeSourcePackageName()
        our_template = self.factory.makePOTemplate(
            distroseries=self.hoary, sourcepackagename=self.package,
            name='foo')
        other_template = self.factory.makePOTemplate(
            distroseries=self.warty, sourcepackagename=other_package,
            name='foo')

        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=self.ubuntu)
        classes = subset.groupEquivalentPOTemplates()

        self.assertTrue(('foo', self.package.name) in classes)
        self.assertEqual(classes[('foo', self.package.name)], [our_template])
        self.assertTrue(('foo', other_package.name) in classes)
        self.assertEqual(
            classes[('foo', other_package.name)], [other_template])

    def test_EquivalenceByNamePattern(self):
        # We can obtain equivalence classes for a distribution by
        # template name pattern.
        unique_name = (
            'krungthepmahanakornamornrattanakosinmahintaramahadilok-etc')
        bangkok_template = self.factory.makePOTemplate(
            distroseries=self.hoary, sourcepackagename=self.package,
            name=unique_name)

        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=self.ubuntu)
        classes = subset.groupEquivalentPOTemplates(
            name_pattern='krungthepmahanakorn.*-etc')

        expected = {
            (unique_name, self.package.name): [bangkok_template],
        }
        self._compareResult(expected, classes)

    def _test_GetSharingPOTemplates(self, template_name, not_matching_name):
        # getSharingTemplates simply returns a list of sharing templates.
        warty_template = self.factory.makePOTemplate(
            distroseries=self.hoary, sourcepackagename=self.package,
            name=template_name)
        hoary_template = self.factory.makePOTemplate(
            distroseries=self.warty, sourcepackagename=self.package,
            name=template_name)
        self.factory.makePOTemplate(
            distroseries=self.warty, sourcepackagename=self.package,
            name=not_matching_name)
        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=self.ubuntu, sourcepackagename=self.package)

        templates = set(list(subset.getSharingPOTemplates(template_name)))
        self.assertEqual(set([warty_template, hoary_template]), templates)

    def test_GetSharingPOTemplates(self):
        # getSharingTemplates returns all sharing templates named foo.
        self._test_GetSharingPOTemplates('foo', 'foo-other')

    def test_GetSharingPOTemplates_special_name(self):
        # Valid template names may also contain '+', '-' and '.' .
        # But they must not be interpreted as regular expressions.
        template_name = 'foo-bar.baz+'
        # This name would match if the template_name was interpreted as a
        # regular expression
        not_matching_name = 'foo-barybazz'
        self._test_GetSharingPOTemplates(template_name, not_matching_name)

    def test_GetSharingPOTemplates_NoSourcepackagename(self):
        # getSharingPOTemplates needs a sourcepackagename to be set.
        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=self.ubuntu)

        self.assertRaises(AssertionError, subset.getSharingPOTemplates, 'foo')


class TestTemplatePrecedence(TestCaseWithFactory):
    """Which of a set of "equivalent" `POTMsgSet`s is "representative." """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestTemplatePrecedence, self).setUp(user='mark@example.com')
        self.product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        self.trunk = self.product.getSeries('trunk')
        self.one_dot_oh = self.factory.makeProductSeries(
            product=self.product, name='one')
        self.two_dot_oh = self.factory.makeProductSeries(
            product=self.product, name='two')
        self.trunk_template = self.factory.makePOTemplate(
            productseries=self.trunk, name='trunk')
        self.one_dot_oh_template = self.factory.makePOTemplate(
            productseries=self.one_dot_oh, name='one')
        self.two_dot_oh_template = self.factory.makePOTemplate(
            productseries=self.two_dot_oh, name='two')

        self.templates = [
            self.trunk_template,
            self.one_dot_oh_template,
            self.two_dot_oh_template,
            ]

        # Make sure there's another current template for every series.
        # This is to make sure that we can disable the templates we
        # care about without Product.primary_translatable ever falling
        # back on a different series and confusing our test.
        for template in self.templates:
            self.factory.makePOTemplate(productseries=template.productseries)

        self._setTranslationFocus(self.trunk)

    def _setTranslationFocus(self, focus_series):
        """Set focus_series as translation focus."""
        self.product.development_focus = focus_series
        self.assertEqual(self.product.primary_translatable, focus_series)

    def _sortTemplates(self, templates=None):
        """Order templates by precedence."""
        if templates is None:
            templates = self.templates
        return sorted(templates, key=methodcaller('sharingKey'), reverse=True)

    def _getPrimaryTemplate(self, templates=None):
        """Get first template in order of precedence."""
        return self._sortTemplates(templates)[0]

    def _enableTemplates(self, enable):
        """Set iscurrent flag for all templates."""
        for template in self.templates:
            template.iscurrent = enable

    def test_disabledTemplatesComeLast(self):
        # A disabled (non-current) template comes after a current one.
        candidates = [self.one_dot_oh_template, self.two_dot_oh_template]

        self.one_dot_oh_template.iscurrent = False
        self.assertEqual(
            self._getPrimaryTemplate(candidates), self.two_dot_oh_template)

        # This goes both ways, regardless of any other ordering the two
        # templates may have.
        self.one_dot_oh_template.iscurrent = True
        self.two_dot_oh_template.iscurrent = False
        self.assertEqual(
            self._getPrimaryTemplate(candidates), self.one_dot_oh_template)

    def test_focusSeriesComesFirst(self):
        # Unless disabled, a template with translation focus always
        # comes first.
        self.assertEqual(self._getPrimaryTemplate(), self.trunk_template)

        # This is the case regardless of any other ordering there
        # may be between the templates.
        self._setTranslationFocus(self.one_dot_oh)
        self.assertEqual(self._getPrimaryTemplate(), self.one_dot_oh_template)
        self._setTranslationFocus(self.two_dot_oh)
        self.assertEqual(self._getPrimaryTemplate(), self.two_dot_oh_template)

    def test_disabledTemplateComesLastDespiteFocus(self):
        # A disabled template comes after an enabled one regardless of
        # translation focus.
        self.trunk_template.iscurrent = False
        self.assertNotEqual(self._getPrimaryTemplate(), self.trunk_template)

    def test_disabledFocusBeatsOtherDisabledTemplate(self):
        # A disabled template with translation focus comes before
        # another disabled template.
        self._enableTemplates(False)
        self.assertEqual(self._getPrimaryTemplate(), self.trunk_template)

        # Both ways, regardless of any other ordering they may have.
        self._setTranslationFocus(self.one_dot_oh)
        self.assertEqual(self._getPrimaryTemplate(), self.one_dot_oh_template)

    def test_ageBreaksTie(self):
        # Of two templates that are both enabled but don't have
        # translation focus, the newest one (by id) has precedence.
        candidates = [self.one_dot_oh_template, self.two_dot_oh_template]
        self.assertEqual(
            self._getPrimaryTemplate(candidates), self.two_dot_oh_template)

    def test_ageBreaksTieWhenDisabled(self):
        # Age also acts as a tie-breaker between disabled templates.
        self._enableTemplates(False)
        self.test_ageBreaksTie()


class TestTranslationFoci(TestCaseWithFactory):
    """Test the precedence rules for tranlation foci."""

    layer = DatabaseFunctionalLayer

    def assertFirst(self, expected, templates):
        templates = sorted(
            templates, key=methodcaller('sharingKey'), reverse=True)
        self.assertEqual(expected, templates[0])

    @staticmethod
    def makeProductFocus(template):
        with person_logged_in(template.productseries.product.owner):
            template.productseries.product.translation_focus = (
                template.productseries)

    @staticmethod
    def makePackageFocus(template):
        distribution = template.distroseries.distribution
        removeSecurityProxy(distribution).translation_focus = (
        template.distroseries)

    def makeProductPOTemplate(self):
        """Create a product that is not the translation focus."""
        # Manually creating a productseries to get one that is not the
        # translation focus.
        other_productseries = self.factory.makeProductSeries()
        self.factory.makePOTemplate(
            productseries=other_productseries)
        product = other_productseries.product
        productseries = self.factory.makeProductSeries(
            product=product,
            owner=product.owner)
        with person_logged_in(product.owner):
            product.translation_focus = other_productseries
            other_productseries.product.translations_usage = (
                ServiceUsage.LAUNCHPAD)
            productseries.product.translations_usage = ServiceUsage.LAUNCHPAD
        return self.factory.makePOTemplate(productseries=productseries)

    def test_product_focus(self):
        """Template priority respects product translation focus."""
        product = self.makeProductPOTemplate()
        package = self.factory.makePOTemplate(side=TranslationSide.UBUNTU)
        # default ordering is database id.
        self.assertFirst(package, [package, product])
        self.makeProductFocus(product)
        self.assertFirst(product, [package, product])

    def test_package_focus(self):
        """Template priority respects package translation focus."""
        package = self.factory.makePOTemplate(side=TranslationSide.UBUNTU)
        product = self.makeProductPOTemplate()
        self.assertFirst(product, [package, product])
        # default ordering is database id.
        self.makePackageFocus(package)
        self.assertFirst(package, [package, product])

    def test_product_package_focus(self):
        """Template priority respects product translation focus."""
        product = self.makeProductPOTemplate()
        package = self.factory.makePOTemplate(side=TranslationSide.UBUNTU)
        # default ordering is database id.
        self.assertFirst(package, [package, product])
        self.makeProductFocus(product)
        self.makePackageFocus(package)
        self.assertFirst(product, [package, product])


class TestGetPOFilesFor(TestCaseWithFactory):
    """Test `get_pofiles_for`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGetPOFilesFor, self).setUp()
        self.potemplate = self.factory.makePOTemplate()
        self.greek = getUtility(ILanguageSet).getLanguageByCode('el')

    def _makePOFile(self):
        """Produce Greek `POFile` for `self.potemplate`."""
        return self.factory.makePOFile('el', potemplate=self.potemplate)

    def test_get_pofiles_for_empty_template_list(self):
        # get_pofiles_for sensibly returns the empty list for an empty
        # template list.
        pofiles = get_pofiles_for([], self.greek)
        self.assertEqual([], pofiles)

    def test_get_pofiles_for_translated_template(self):
        # get_pofiles_for finds a POFile for a given template in a given
        # language.
        greek_pofile = self._makePOFile()
        pofiles = get_pofiles_for([self.potemplate], self.greek)
        self.assertEqual([greek_pofile], pofiles)

    def test_get_pofiles_for_untranslated_template(self):
        # If there is no POFile for a template in a language,
        # get_pofiles_for makes up a DummyPOFile.

        # Avoid circular imports.
        from lp.translations.model.pofile import DummyPOFile

        pofiles = get_pofiles_for([self.potemplate], self.greek)
        pofile = pofiles[0]
        self.assertIsInstance(pofile, DummyPOFile)


class TestPOTemplateUbuntuUpstreamSharingMixin:
    """Test sharing between Ubuntu und upstream POTemplates."""

    layer = ZopelessDatabaseLayer

    def createData(self):
        self.shared_template_name = self.factory.getUniqueString()
        self.distroseries = self.factory.makeUbuntuDistroSeries()
        self.distroseries.distribution.translation_focus = (
            self.distroseries)
        self.sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.distroseries)
        self.productseries = self.factory.makeProductSeries()

    def makeThisSidePOTemplate(self):
        """Create POTemplate on this side."""
        raise NotImplementedError

    def makeOtherSidePOTemplate(self):
        """Create POTemplate on the other side. Override in subclass."""
        raise NotImplementedError

    def _setPackagingLink(self):
        """Create the packaging link from source package to product series."""
        self.factory.makePackagingLink(
            productseries=self.productseries,
            sourcepackage=self.sourcepackage)

    def test_getOtherSidePOTemplate_none(self):
        # Without a packaging link, None is returned.
        potemplate = self.makeThisSidePOTemplate()
        self.assertIs(None, potemplate.getOtherSidePOTemplate())

    def test_getOtherSidePOTemplate_linked_no_template(self):
        # No sharing template exists on the other side.
        self._setPackagingLink()
        potemplate = self.makeThisSidePOTemplate()
        self.assertIs(None, potemplate.getOtherSidePOTemplate())

    def test_getOtherSidePOTemplate_shared(self):
        # This is how sharing should look like.
        this_potemplate = self.makeThisSidePOTemplate()
        other_potemplate = self.makeOtherSidePOTemplate()
        self._setPackagingLink()
        self.assertEquals(
            other_potemplate, this_potemplate.getOtherSidePOTemplate())


class TestPOTemplateUbuntuSharing(TestCaseWithFactory,
                                  TestPOTemplateUbuntuUpstreamSharingMixin):
    """Test sharing on Ubuntu side."""

    def setUp(self):
        super(TestPOTemplateUbuntuSharing, self).setUp()
        self.createData()

    def makeThisSidePOTemplate(self):
        return self.factory.makePOTemplate(
            sourcepackage=self.sourcepackage, name=self.shared_template_name)

    def makeOtherSidePOTemplate(self):
        return self.factory.makePOTemplate(
            productseries=self.productseries, name=self.shared_template_name)


class TestPOTemplateUpstreamSharing(TestCaseWithFactory,
                                    TestPOTemplateUbuntuUpstreamSharingMixin):
    """Test sharing on upstream side."""

    def setUp(self):
        super(TestPOTemplateUpstreamSharing, self).setUp()
        self.createData()

    def makeThisSidePOTemplate(self):
        return self.factory.makePOTemplate(
            productseries=self.productseries, name=self.shared_template_name)

    def makeOtherSidePOTemplate(self):
        return self.factory.makePOTemplate(
            sourcepackage=self.sourcepackage, name=self.shared_template_name)


class TestPOTemplateSubset(TestCaseWithFactory):
    """Test POTemplate functions not covered by doctests."""

    layer = ZopelessDatabaseLayer

    def test_getPOTemplatesByTranslationDomain_filters_by_domain(self):
        domain = self.factory.getUniqueString()
        series = self.factory.makeProductSeries()

        # The template we'll be looking for:
        template = self.factory.makePOTemplate(
            translation_domain=domain, productseries=series)

        # Another template in the same context with a different domain:
        self.factory.makePOTemplate(productseries=series)

        subset = getUtility(IPOTemplateSet).getSubset(productseries=series)
        self.assertContentEqual(
            [template], subset.getPOTemplatesByTranslationDomain(domain))

    def test_getPOTemplatesByTranslationDomain_finds_by_productseries(self):
        domain = self.factory.getUniqueString()
        productseries = self.factory.makeProductSeries()

        # The template we'll be looking for:
        template = self.factory.makePOTemplate(
            translation_domain=domain, productseries=productseries)

        # Similar templates that should not come up in the same search:
        # * Different series (even for the same product).
        self.factory.makePOTemplate(
            translation_domain=domain,
            productseries=self.factory.makeProductSeries(
                product=template.productseries.product))
        # * Distro and series (even with the same name as the domain
        # we're looking for).
        self.factory.makePOTemplate(
            translation_domain=domain,
            distroseries=self.factory.makeDistroSeries(
                name=domain, distribution=self.factory.makeDistribution(
                    name=domain)))
        # * Source package (even with the same name as the domain we're
        # looking for).
        self.factory.makePOTemplate(
            translation_domain=domain,
            distroseries=self.factory.makeDistroSeries(),
            sourcepackagename=self.factory.makeSourcePackageName(name=domain))

        subset = getUtility(IPOTemplateSet).getSubset(
            productseries=productseries)
        self.assertContentEqual(
            [template], subset.getPOTemplatesByTranslationDomain(domain))

    def test_getPOTemplatesByTranslationDomain_finds_by_sourcepackage(self):
        domain = self.factory.getUniqueString()
        package = self.factory.makeSourcePackage()

        # The template we'll be looking for:
        template = self.factory.makePOTemplate(
            translation_domain=domain, distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

        # Similar templates that should not come up in the same search:
        # * Productseries (even with the same names the domain we're
        # looking for).
        self.factory.makePOTemplate(
            translation_domain=domain,
            productseries=self.factory.makeProductSeries(
                name=domain, product=self.factory.makeProduct(name=domain)))

        # * Different series (even for the same source package name and
        # distribution).
        self.factory.makePOTemplate(
            translation_domain=domain,
            sourcepackagename=package.sourcepackagename,
            distroseries=self.factory.makeDistroSeries(
                distribution=package.distroseries.distribution))

        subset = getUtility(IPOTemplateSet).getSubset(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        self.assertContentEqual(
            [template], subset.getPOTemplatesByTranslationDomain(domain))

    def test_getPOTemplatesByTranslationDomain_finds_by_distroseries(self):
        domain = self.factory.getUniqueString()
        distroseries = self.factory.makeDistroSeries()

        # The template we'll be looking for:
        template = self.factory.makePOTemplate(
            translation_domain=domain, distroseries=distroseries)

        # Similar templates that should not come up in the same search:
        # * Productseries (even with the same names the domain we're
        # looking for).
        self.factory.makePOTemplate(
            translation_domain=domain,
            productseries=self.factory.makeProductSeries(
                name=domain, product=self.factory.makeProduct(name=domain)))

        # * Different series (even for the same distribution).
        self.factory.makePOTemplate(
            translation_domain=domain,
            distroseries=self.factory.makeDistroSeries(
                distribution=distroseries.distribution))

        subset = getUtility(IPOTemplateSet).getSubset(
            distroseries=distroseries)
        self.assertContentEqual(
            [template], subset.getPOTemplatesByTranslationDomain(domain))

    def test_getPOTemplatesByTranslationDomain_can_ignore_iscurrent(self):
        domain = self.factory.getUniqueString()
        series = self.factory.makeProductSeries()
        templates = [
            self.factory.makePOTemplate(
                translation_domain=domain, productseries=series,
                iscurrent=iscurrent)
            for iscurrent in [False, True]]

        subset = getUtility(IPOTemplateSet).getSubset(productseries=series)
        self.assertContentEqual(
            templates, subset.getPOTemplatesByTranslationDomain(domain))

    def test_getPOTemplatesByTranslationDomain_can_filter_by_iscurrent(self):
        domain = self.factory.getUniqueString()
        series = self.factory.makeProductSeries()

        templates = dict(
            (iscurrent, [self.factory.makePOTemplate(
                translation_domain=domain, productseries=series,
                iscurrent=iscurrent)])
            for iscurrent in [False, True])

        potset = getUtility(IPOTemplateSet)
        found_templates = dict((
            iscurrent,
            list(potset.getSubset(productseries=series, iscurrent=iscurrent
                ).getPOTemplatesByTranslationDomain(domain),)
            )
            for iscurrent in [False, True])

        self.assertEqual(templates, found_templates)

    def test_isNameUnique(self):
        # The isNameUnique method ignored the iscurrent filter to provide
        # an authoritative answer to whether a new template can be created
        # with the name.
        series = self.factory.makeProductSeries()
        self.factory.makePOTemplate(productseries=series, name='cat')
        self.factory.makePOTemplate(
            productseries=series, name='dog', iscurrent=False)
        potset = getUtility(IPOTemplateSet)
        subset = potset.getSubset(productseries=series, iscurrent=True)
        self.assertFalse(subset.isNameUnique('cat'))
        self.assertFalse(subset.isNameUnique('dog'))
        self.assertTrue(subset.isNameUnique('fnord'))

    def test_getPOTemplatesByTranslationDomain_returns_result_set(self):
        subset = getUtility(IPOTemplateSet).getSubset(
            productseries=self.factory.makeProductSeries())
        self.assertEqual(
            0, subset.getPOTemplatesByTranslationDomain("foo").count())
