# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Runs the POFileTranslator test."""

__metaclass__ = type

from zope.component import getUtility

from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.pofiletranslator import IPOFileTranslatorSet


class TestPOFileTranslator(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def test_getForPersonPOFile_returns_None_if_not_found(self):
        self.assertIsNone(
            getUtility(IPOFileTranslatorSet).getForPersonPOFile(
                self.factory.makePerson(), self.factory.makePOFile()))

    def test_getForPersonPOFile_finds_record(self):
        pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        tm = self.factory.makeCurrentTranslationMessage(
            potmsgset=potmsgset, language=pofile.language)
        poft = getUtility(IPOFileTranslatorSet).getForPersonPOFile(
            tm.submitter, pofile)
        self.assertEqual(pofile, poft.pofile)
        self.assertEqual(tm.submitter, poft.person)

    def test_getForPersonPOFile_ignores_other_persons(self):
        pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeCurrentTranslationMessage(
            potmsgset=potmsgset, language=pofile.language)
        self.assertIsNone(
            getUtility(IPOFileTranslatorSet).getForPersonPOFile(
                self.factory.makePerson(), pofile))

    def test_getForPersonPOFile_ignores_other_POFiles(self):
        pofile = self.factory.makePOFile('nl')
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        tm = self.factory.makeCurrentTranslationMessage(
            potmsgset=potmsgset, language=pofile.language)
        other_pofile = self.factory.makePOFile('de', pofile.potemplate)
        self.assertIsNone(
            getUtility(IPOFileTranslatorSet).getForPersonPOFile(
                tm.submitter, other_pofile))

    def test_getForTemplate_finds_all_for_template(self):
        pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        tm = self.factory.makeCurrentTranslationMessage(
            potmsgset=potmsgset, language=pofile.language)
        [poft] = list(
            getUtility(IPOFileTranslatorSet).getForTemplate(pofile.potemplate))
        self.assertEqual(pofile.potemplate, poft.pofile.potemplate)
        self.assertEqual(tm.submitter, poft.person)
