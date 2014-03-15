# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import urllib

from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.services.webapp import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    BrowserTestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.translations.browser.person import PersonTranslationView
from lp.translations.model.translator import TranslatorSet


class TestPersonTranslationView(TestCaseWithFactory):
    """Test `PersonTranslationView`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestPersonTranslationView, self).setUp()
        person = removeSecurityProxy(self.factory.makePerson())
        self.view = PersonTranslationView(person, LaunchpadTestRequest())
        self.translationgroup = None
        self.language = self.factory.makeLanguage()
        self.view.context.addLanguage(self.language)

    def _makeReviewer(self):
        """Set up the person we're looking at as a reviewer."""
        owner = self.factory.makePerson()
        self.translationgroup = self.factory.makeTranslationGroup(owner=owner)
        TranslatorSet().new(
            translationgroup=self.translationgroup, language=self.language,
            translator=self.view.context)

    def _makePOFiles(self, count, previously_worked_on, languages=None):
        """Create `count` `POFile`s that the view's person can review.

        :param count: Number of POFiles to create.
        :param previously_worked_on: Whether these should be POFiles
            that the person has already worked on.
        :param languages: List of languages for each pofile. The length of
            the list must be the same as count. If None, all files will be
            created with self.language. Also, if languages is not None,
            all files will be created for the same template.
        """
        pofiles = []
        if languages is not None:
            potemplate = self.factory.makePOTemplate()
        for counter in xrange(count):
            if languages is None:
                pofile = self.factory.makePOFile(language=self.language)
            else:
                pofile = self.factory.makePOFile(
                    potemplate=potemplate, language=languages[counter])

            if self.translationgroup:
                product = pofile.potemplate.productseries.product
                product.translationgroup = self.translationgroup

            if previously_worked_on:
                if languages is not None:
                    sequence = counter + 1
                else:
                    sequence = 1
                potmsgset = self.factory.makePOTMsgSet(
                    potemplate=pofile.potemplate, sequence=sequence)
                self.factory.makeCurrentTranslationMessage(
                    potmsgset=potmsgset, pofile=pofile,
                    translator=self.view.context)

            removeSecurityProxy(pofile).unreviewed_count = 1
            pofiles.append(pofile)

        return pofiles

    def _addUntranslatedMessages(self, pofile, untranslated_messages):
        """Add to `pofile`'s count of untranslated messages."""
        template = pofile.potemplate
        removeSecurityProxy(template).messagecount += untranslated_messages

    def test_translation_groups(self):
        # translation_groups lists the translation groups a person is
        # in.
        self._makeReviewer()
        self.assertEqual(
            [self.translationgroup], self.view.translation_groups)

    def test_person_is_reviewer_false(self):
        # A regular person is not a reviewer.
        self.assertFalse(self.view.person_is_reviewer)

    def test_person_is_reviewer_true(self):
        # A person who's in a translation group is a reviewer.
        self._makeReviewer()
        self.assertTrue(self.view.person_is_reviewer)

    def test_num_projects_and_packages_to_review(self):
        # num_projects_and_packages_to_review counts the number of
        # reviewable targets that the person has worked on.
        self._makeReviewer()

        self._makePOFiles(1, previously_worked_on=True)

        self.assertEqual(1, self.view.num_projects_and_packages_to_review)

    def test_all_projects_and_packages_to_review_one(self):
        # all_projects_and_packages describes the translations available
        # for review by its person.
        self._makeReviewer()
        pofile = self._makePOFiles(1, previously_worked_on=True)[0]
        product = pofile.potemplate.productseries.product

        descriptions = self.view.all_projects_and_packages_to_review

        self.assertEqual(1, len(descriptions))
        self.assertEqual(product, descriptions[0]['target'])

    def test_all_projects_and_packages_to_review_none(self):
        # all_projects_and_packages_to_review works even if there is
        # nothing to review.  It will find nothing.
        self._makeReviewer()

        descriptions = self.view.all_projects_and_packages_to_review

        self.assertEqual([], descriptions)

    def test_all_projects_and_packages_to_review_string_singular(self):
        # A translation description says how many strings need review,
        # both as a number and as text.
        self._makeReviewer()
        pofile = self._makePOFiles(1, previously_worked_on=True)[0]
        removeSecurityProxy(pofile).unreviewed_count = 1

        description = self.view.all_projects_and_packages_to_review[0]

        self.assertEqual(1, description['count'])
        self.assertEqual("1 string", description['count_wording'])

    def test_all_projects_and_packages_to_review_string_plural(self):
        # For multiple strings, count_wording uses the plural.
        self._makeReviewer()
        pofile = self._makePOFiles(1, previously_worked_on=True)[0]
        removeSecurityProxy(pofile).unreviewed_count = 2

        description = self.view.all_projects_and_packages_to_review[0]

        self.assertEqual(2, description['count'])
        self.assertEqual("2 strings", description['count_wording'])

    def test_num_projects_and_packages_to_review_zero(self):
        # num_projects_and_packages does not count new suggestions.
        self._makeReviewer()

        self._makePOFiles(1, previously_worked_on=False)

        self.assertEqual(0, self.view.num_projects_and_packages_to_review)

    def test_top_projects_and_packages_to_review(self):
        # top_projects_and_packages_to_review tries to name at least one
        # translation target that the person has worked on.
        self._makeReviewer()
        pofile_worked_on = self._makePOFiles(1, previously_worked_on=True)[0]
        targets = self.view.top_projects_and_packages_to_review

        pofile_suffix = '/+translate?show=new_suggestions'
        expected_links = [canonical_url(pofile_worked_on) + pofile_suffix]
        self.assertEqual(
            set(expected_links), set(item['link'] for item in targets))

    def test_recent_translation_activity(self):
        # the recent_activity property lists the most recent translation
        # targets the person has worked on, for active projects only.
        self._makeReviewer()

        # make a translation record for an inactive project (will be excluded)
        [pofile] = self._makePOFiles(1, previously_worked_on=True)
        removeSecurityProxy(pofile.potemplate.product).active = False

        # and make one which has not been worked on (will be excluded)
        self._makePOFiles(1, previously_worked_on=False)

        # and make one which has a product no longer using translations (will
        # be excluded)
        [pofile] = self._makePOFiles(1, previously_worked_on=True)
        naked_product = removeSecurityProxy(pofile.potemplate.product)
        naked_product.translations_usage = ServiceUsage.NOT_APPLICABLE

        pofiles_worked_on = self._makePOFiles(11, previously_worked_on=True)

        # the expected results
        person_name = urllib.urlencode({'person': self.view.context.name})
        expected_links = [
            (pofile.potemplate.translationtarget.title,
            canonical_url(pofile, view_name="+filter") + "?%s" % person_name)
            for pofile in pofiles_worked_on[:10]]

        recent_activity = self.view.recent_activity
        self.assertContentEqual(
            expected_links,
            ((item.title, item.url) for item in recent_activity))

    def test_top_p_n_p_to_review_caps_existing_involvement(self):
        # top_projects_and_packages will return at most 9 POFiles that
        # the person has already worked on.
        self._makeReviewer()
        self._makePOFiles(10, previously_worked_on=True)

        targets = self.view.top_projects_and_packages_to_review

        self.assertEqual(9, len(targets))
        self.assertEqual(9, len(set(item['link'] for item in targets)))

    def test_top_p_n_p_to_review_caps_total(self):
        # top_projects_and_packages will show at most 9 POFiles
        # overall.
        self._makeReviewer()
        pofiles_worked_on = self._makePOFiles(11, previously_worked_on=True)

        targets = self.view.top_projects_and_packages_to_review

        self.assertEqual(9, len(targets))
        self.assertEqual(9, len(set(item['link'] for item in targets)))

    def test_person_is_translator_false(self):
        # By default, a user is not a translator.
        self.assertFalse(self.view.person_is_translator)

    def test_person_is_translator_true(self):
        # Doing translation work turns a user into a translator.
        self._makePOFiles(1, previously_worked_on=True)

        self.assertTrue(self.view.person_is_translator)

    def test_getTargetsForTranslation_nothing(self):
        # If there's nothing to translate, _getTargetsForTranslation
        # returns nothing.
        self.assertEqual([], self.view._getTargetsForTranslation())

    def test_getTargetsForTranslation(self):
        # If there's a translation that this person has worked on and
        # is not a reviewer for, and it has untranslated strings, it
        # shows up in _getTargetsForTranslation.
        pofile = self._makePOFiles(1, previously_worked_on=True)[0]
        self._addUntranslatedMessages(pofile, 1)
        product = pofile.potemplate.productseries.product

        descriptions = self.view._getTargetsForTranslation()

        self.assertEqual(1, len(descriptions))
        description = descriptions[0]
        self.assertEqual(product, description['target'])
        self.assertTrue(description['link'].startswith(canonical_url(pofile)))
        self.assertEqual(
            pofile.language.englishname, description['languages'])

    def test_getTargetsForTranslation_multiple_languages(self):
        # Translations in different languages are aggregated to one target
        # but the language names are listed.
        other_language = self.factory.makeLanguage()
        self.view.context.addLanguage(other_language)
        pofiles = self._makePOFiles(
            2, previously_worked_on=True,
            languages=[self.language, other_language])
        for pofile in pofiles:
            self._addUntranslatedMessages(pofile, 1)

        descriptions = self.view._getTargetsForTranslation()
        self.assertEqual(1, len(descriptions))
        description = descriptions[0]
        expected_languages = ', '.join(sorted([
            self.language.englishname, other_language.englishname]))
        self.assertContentEqual(expected_languages, description['languages'])

    def test_getTargetsForTranslation_max_fetch(self):
        # The max_fetch parameter limits how many POFiles are considered
        # by _getTargetsForTranslation.  This lets you get the target(s)
        # with the most untranslated messages.
        pofiles = self._makePOFiles(3, previously_worked_on=True)
        urgent_pofile = pofiles[2]
        medium_pofile = pofiles[1]
        nonurgent_pofile = pofiles[0]
        self._addUntranslatedMessages(urgent_pofile, 10)
        self._addUntranslatedMessages(medium_pofile, 2)
        self._addUntranslatedMessages(nonurgent_pofile, 1)

        descriptions = self.view._getTargetsForTranslation(1)
        self.assertEqual(1, len(descriptions))
        self.assertEqual(
            urgent_pofile.potemplate.productseries.product,
            descriptions[0]['target'])

        # Passing a negative max_fetch makes _getTargetsForTranslation
        # pick translations with the fewest untranslated messages.
        descriptions = self.view._getTargetsForTranslation(-1)
        self.assertEqual(1, len(descriptions))
        self.assertEqual(
            nonurgent_pofile.potemplate.productseries.product,
            descriptions[0]['target'])

    def test_top_projects_and_packages_to_translate(self):
        # top_projects_and_packages_to_translate lists targets that the
        # user has worked on and could help translate.
        worked_on = self._makePOFiles(1, previously_worked_on=True)[0]
        self._addUntranslatedMessages(worked_on, 1)
        not_worked_on = self._makePOFiles(1, previously_worked_on=False)[0]
        self._addUntranslatedMessages(not_worked_on, 1)

        descriptions = self.view.top_projects_and_packages_to_translate

        self.assertEqual(1, len(descriptions))
        self.assertEqual(
            worked_on.potemplate.productseries.product,
            descriptions[0]['target'])

    def test_top_p_n_p_to_translate_caps_existing_involvement(self):
        # top_projects_and_packages_to_translate shows up to ten
        # targets that the user has already worked on.
        pofiles = self._makePOFiles(7, previously_worked_on=True)
        for pofile in pofiles:
            self._addUntranslatedMessages(pofile, 1)

        descriptions = self.view.top_projects_and_packages_to_translate

        self.assertEqual(7, len(descriptions))

    def test_top_p_n_p_to_translate_lists_most_and_least_translated(self):
        # Of the maximum of ten translations that the user has already
        # worked on, the first 5 will be the ones with the most
        # untranslated strings; the last 5 will have the fewest.
        # We create a lot more POFiles because internally the property
        # will fetch many POFiles.
        pofiles = self._makePOFiles(50, previously_worked_on=True)
        for number, pofile in enumerate(pofiles):
            self._addUntranslatedMessages(pofile, number + 1)
        products = [
            pofile.potemplate.productseries.product for pofile in pofiles]

        descriptions = self.view.top_projects_and_packages_to_translate

        self.assertEqual(10, len(descriptions))
        targets = [item['target'] for item in descriptions]

        # We happen to know that no more than 25 POFiles are fetched for
        # each of the two categories, so the top 5 targets must be taken
        # from the last 25 pofiles and the next 5 must be taken from the
        # first 25 pofiles.
        self.assertTrue(set(targets[:5]).issubset(products[25:]))
        self.assertTrue(set(targets[5:]).issubset(products[:25]))

        # No target is mentioned more than once in the listing.
        self.assertEqual(len(targets), len(set(targets)))

    def test_top_p_n_p_to_translate_caps_total(self):
        # The list never shows more than 10 entries.
        for previously_worked_on in (True, False):
            pofiles = self._makePOFiles(
                11, previously_worked_on=previously_worked_on)
            for pofile in pofiles:
                self._addUntranslatedMessages(pofile, 1)

        descriptions = self.view.top_projects_and_packages_to_translate
        self.assertEqual(10, len(descriptions))

    def test_requires_preferred_languages(self):
        # requires_preferred_languages tells the page whether this
        # person still needs to set their preferred languages.
        # In this case, our person has set a preferred language, so no,
        # this is no longer required.
        self.assertFalse(self.view.requires_preferred_languages)

        # But the answer is True if the person has no preferred
        # languages.
        self.view.context.removeLanguage(self.language)
        self.assertTrue(self.view.requires_preferred_languages)


class TestPersonTranslationViewPermissions(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonTranslationViewPermissions, self).setUp()
        self.context = self.factory.makePerson()
        self.language = self.factory.makeLanguage()
        self.context.addLanguage(self.language)
        owner = self.factory.makePerson()
        self.translationgroup = self.factory.makeTranslationGroup(owner=owner)
        TranslatorSet().new(
            translationgroup=self.translationgroup, language=self.language,
            translator=self.context)

    def test_links_anon(self):
        browser = self.getViewBrowser(
            self.context, "+translations", no_login=True)
        self.assertFalse("+editmylanguages" in browser.contents)
        self.assertFalse("+edit" in browser.contents)

    def test_links_unauthorized(self):
        group = self.factory.makeTranslationGroup()
        browser = self.getViewBrowser(self.context, "+translations")
        self.assertFalse("+editmylanguages" in browser.contents)
        self.assertFalse("+edit" in browser.contents)

    def test_links_authorized(self):
        group = self.factory.makeTranslationGroup()
        browser = self.getViewBrowser(
            self.context, "+translations", user=self.context)
        self.assertTrue("+editmylanguages" in browser.contents)
        self.assertTrue("+edit" in browser.contents)
