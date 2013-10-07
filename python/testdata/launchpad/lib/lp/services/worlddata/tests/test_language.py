# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lazr.lifecycle.interfaces import IDoNotSnapshot
from testtools.matchers import Equals
from zope.component import getUtility

from lp.registry.interfaces.karma import IKarmaCacheManager
from lp.registry.model.karma import KarmaCategory
from lp.services.database.interfaces import IStore
from lp.services.worlddata.interfaces.language import (
    ILanguage,
    ILanguageSet,
    )
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import HasQueryCount


class TestLanguageWebservice(TestCaseWithFactory):
    """Test Language web service API."""

    layer = DatabaseFunctionalLayer

    def test_translators(self):
        self.failUnless(
            IDoNotSnapshot.providedBy(ILanguage['translators']),
            "ILanguage.translators should not be included in snapshots, "
            "see bug 553093.")

    def test_guessed_pluralforms_guesses(self):
        language = self.factory.makeLanguage(pluralforms=None)
        self.assertIs(None, language.pluralforms)
        self.assertEqual(2, language.guessed_pluralforms)

    def test_guessed_pluralforms_knows(self):
        language = self.factory.makeLanguage(pluralforms=3)
        self.assertEqual(language.pluralforms, language.guessed_pluralforms)


class TestTranslatorsCounts(TestCaseWithFactory):
    """Test preloading of Language.translators_counts."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslatorsCounts, self).setUp()
        self.translated_lang = self.factory.makeLanguage(pluralforms=None)
        self.untranslated_lang = self.factory.makeLanguage(pluralforms=None)
        for i in range(3):
            translator = self.factory.makePerson()
            translator.addLanguage(self.translated_lang)
            with dbuser('karma'):
                translations_category = IStore(KarmaCategory).find(
                    KarmaCategory, name='translations').one()
                getUtility(IKarmaCacheManager).new(
                    person_id=translator.id,
                    category_id=translations_category.id,
                    value=100)

    def test_translators_count(self):
        # translators_count works.
        self.assertEquals(3, self.translated_lang.translators_count)
        self.assertEquals(0, self.untranslated_lang.translators_count)

    def test_translators_count_queries(self):
        # translators_count issues a single query.
        with StormStatementRecorder() as recorder:
            self.translated_lang.translators_count
        self.assertThat(recorder, HasQueryCount(Equals(1)))

    def test_getAllLanguages_can_preload_translators_count(self):
        # LanguageSet.getAllLanguages() can preload translators_count.
        list(getUtility(ILanguageSet).getAllLanguages(
            want_translators_count=True))
        with StormStatementRecorder() as recorder:
            self.assertEquals(3, self.translated_lang.translators_count)
            self.assertEquals(0, self.untranslated_lang.translators_count)
        self.assertThat(recorder, HasQueryCount(Equals(0)))
