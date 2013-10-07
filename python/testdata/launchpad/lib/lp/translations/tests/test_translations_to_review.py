# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the choice of "translations to review" for a user."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from pytz import UTC
import transaction
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.services.worlddata.model.language import LanguageSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.interfaces.translationsperson import ITranslationsPerson
from lp.translations.model.translator import TranslatorSet


class ReviewTestMixin:
    """Base for testing which translations a reviewer can review."""

    def setUpMixin(self, for_product=True):
        """Set up test environment.

        Sets up a person, as well as a translation that that person is a
        reviewer for and has contributed to.

        If for_product is true, the translation will be for a product.
        Otherwise, it will be for a distribution.
        """
        # Set up a person, and a translation that this person is a
        # reviewer for and has contributed to.
        self.base_time = datetime.now(UTC)
        self.person = self.factory.makePerson()
        self.translationgroup = self.factory.makeTranslationGroup(
            owner=self.factory.makePerson())
        self.dutch = LanguageSet().getLanguageByCode('nl')
        TranslatorSet().new(
            translationgroup=self.translationgroup, language=self.dutch,
            translator=self.person)

        if for_product:
            self.distroseries = None
            self.distribution = None
            self.sourcepackagename = None
            self.productseries = removeSecurityProxy(
                self.factory.makeProductSeries())
            self.product = self.productseries.product
            self.supercontext = self.product
        else:
            self.productseries = None
            self.product = None
            self.distroseries = removeSecurityProxy(
                self.factory.makeDistroSeries())
            self.distribution = self.distroseries.distribution
            self.distribution.translation_focus = self.distroseries
            self.sourcepackagename = self.factory.makeSourcePackageName()
            self.supercontext = self.distribution
        transaction.commit()

        self.supercontext.translationgroup = self.translationgroup
        self.supercontext.translations_usage = ServiceUsage.LAUNCHPAD

        self.potemplate = self.factory.makePOTemplate(
            productseries=self.productseries, distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename)
        self.pofile = removeSecurityProxy(self.factory.makePOFile(
            potemplate=self.potemplate, language_code='nl'))
        self.potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate, singular='hi')
        self.translation = self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=self.pofile,
            translator=self.person, translations=['bi'],
            date_created=self.base_time, date_reviewed=self.base_time)

        later_time = self.base_time + timedelta(0, 3600)
        self.suggestion = removeSecurityProxy(
            self.factory.makeSuggestion(
                potmsgset=self.potmsgset, pofile=self.pofile,
                translator=self.factory.makePerson(), translations=['wi'],
                date_created=later_time))

        self.pofile.updateStatistics()
        self.assertEqual(self.pofile.unreviewed_count, 1)

    def _getReviewables(self, *args, **kwargs):
        """Shorthand for `self.person.getReviewableTranslationFiles`."""
        person = ITranslationsPerson(self.person)
        return list(person.getReviewableTranslationFiles(
            *args, **kwargs))


class ReviewableTranslationFilesTest:
    """Test getReviewableTranslationFiles for a given setup.

    Can be applied to product or distribution setups.
    """

    def test_OneFileToReview(self):
        # In the base case, the method finds one POFile for self.person
        # to review.
        self.assertEqual(self._getReviewables(), [self.pofile])

    def test_getReviewableTranslationFiles_no_older_than_pass(self):
        # The no_older_than parameter keeps translations that the
        # reviewer worked on at least that recently.
        self.assertEqual(
            self._getReviewables(no_older_than=self.base_time), [self.pofile])

    def test_getReviewableTranslationFiles_no_older_than_filter(self):
        # The no_older_than parameter filters translations that the
        # reviewer has not worked on since the given time.
        next_day = self.base_time + timedelta(1)
        self.assertEqual(self._getReviewables(no_older_than=next_day), [])

    def test_getReviewableTranslationFiles_not_translating_in_launchpad(self):
        # We don't see products/distros that don't use Launchpad for
        # translations.
        self.supercontext.translations_usage = ServiceUsage.NOT_APPLICABLE
        self.assertEqual(self._getReviewables(), [])

    def test_getReviewableTranslationFiles_non_reviewer(self):
        # The method does not show translations that the user is not a
        # reviewer for.
        self.supercontext.translationgroup = None
        self.assertEqual(self._getReviewables(), [])

    def test_getReviewableTranslationFiles_other_language(self):
        # We only get translations in languages that the person is a
        # reviewer for.
        self.pofile.language = LanguageSet().getLanguageByCode('de')
        self.assertEqual(self._getReviewables(), [])

    def test_getReviewableTranslationFiles_no_new_suggestions(self):
        # Translation files only show up if they have new suggestions.
        self.suggestion.date_created -= timedelta(2)
        self.pofile.updateStatistics()
        self.assertEqual(self._getReviewables(), [])

    def test_getReviewableTranslationFiles_ignores_english(self):
        # POFiles that "translate to English" are ignored.
        english = LanguageSet().getLanguageByCode('en')
        TranslatorSet().new(
            translationgroup=self.translationgroup, language=english,
            translator=self.person)
        self.pofile.language = english
        self.assertEqual(self._getReviewables(), [])


class TestReviewableProductTranslationFiles(TestCaseWithFactory,
                                            ReviewTestMixin,
                                            ReviewableTranslationFilesTest):
    """Test `Person.getReviewableTranslationFiles` for products."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestReviewableProductTranslationFiles, self).setUp()
        ReviewTestMixin.setUpMixin(self, for_product=True)

    def test_getReviewableTranslationFiles_project_deactivated(self):
        # Deactive project are excluded from the list.
        from lp.testing import celebrity_logged_in
        with celebrity_logged_in('admin'):
            self.product.active = False
        self.assertEqual([], self._getReviewables())


class TestReviewableDistroTranslationFiles(TestCaseWithFactory,
                                           ReviewTestMixin,
                                           ReviewableTranslationFilesTest):
    """Test `Person.getReviewableTranslationFiles` for distros."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestReviewableDistroTranslationFiles, self).setUp()
        ReviewTestMixin.setUpMixin(self, for_product=False)
