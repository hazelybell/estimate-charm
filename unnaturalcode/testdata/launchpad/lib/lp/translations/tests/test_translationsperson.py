# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for TranslationsPerson."""

__metaclass__ = type

from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.interfaces.translationsperson import ITranslationsPerson


class TestTranslationsPerson(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_baseline(self):
        person = ITranslationsPerson(self.factory.makePerson())
        self.assertTrue(verifyObject(ITranslationsPerson, person))

    def test_hasTranslated(self):
        person = self.factory.makePerson()
        translationsperson = ITranslationsPerson(person)
        self.assertFalse(translationsperson.hasTranslated())
        self.factory.makeSuggestion(translator=person)
        self.assertTrue(translationsperson.hasTranslated())
