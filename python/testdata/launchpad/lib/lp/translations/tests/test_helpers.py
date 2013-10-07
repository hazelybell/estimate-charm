# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.tests.helpers import (
    make_translationmessage,
    summarize_current_translations,
    )


class TestTranslationMessageHelpers(TestCaseWithFactory):
    """Test discovery of translation suggestions."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTranslationMessageHelpers, self).setUp()
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        new_series = self.factory.makeDistroSeries(distribution=ubuntu)
        sourcepackagename = self.factory.makeSourcePackageName()
        potemplate = self.factory.makePOTemplate(
            distroseries=new_series,
            sourcepackagename=sourcepackagename)
        self.pofile = self.factory.makePOFile('sr', potemplate=potemplate)
        self.potmsgset = self.factory.makePOTMsgSet(potemplate=potemplate)

        # A POFile in a different context from self.pofile.
        self.other_pofile = self.factory.makePOFile(
            language_code=self.pofile.language.code)

    def test_make_translationmessage(self):
        translations = [u"testing"]
        tm = make_translationmessage(self.factory, pofile=self.pofile,
                                     potmsgset=self.potmsgset,
                                     translations=translations)
        self.assertEquals(translations, tm.translations)

    def test_summarize_current_translations_baseline(self):
        # The trivial case for summarize_current_translations: no
        # translations at all.
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))
        self.assertIs(None, current_shared)
        self.assertIs(None, current_diverged)
        self.assertIs(None, other)
        self.assertEquals([], divergences)

    def test_summarize_current_translations_current_shared(self):
        # summarize_current_translations when there is a single, shared
        # current message.
        tm = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=False)
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))
        self.assertEquals(tm, current_shared)
        self.assertIs(None, current_diverged)
        self.assertIs(None, other)
        self.assertEquals([], divergences)

    def test_summarize_current_translations_current_both(self):
        # summarize_current_translations when there is a single message
        # shared between Ubuntu and upstream.
        tm = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=True, diverged=False)
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))
        self.assertEquals(tm, current_shared)
        self.assertIs(None, current_diverged)
        self.assertEquals(tm, other)
        self.assertEquals([], divergences)

    def test_summarize_current_translations_current_both_same(self):
        # summarize_current_translations when there are identical but
        # separate shared current messages on the Ubuntu side and
        # upstream.
        tm_ubuntu = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=False)
        tm_upstream = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=False, upstream=True, diverged=False)
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))

        self.assertIn(current_shared, (tm_ubuntu, tm_upstream))
        if self.pofile.potemplate.distroseries is not None:
            self.assertEquals(tm_ubuntu, current_shared)
        else:
            self.assertEquals(tm_upstream, current_shared)

        self.assertIs(None, current_diverged)
        self.assertIn(other, (tm_ubuntu, tm_upstream))
        self.assertNotEqual(current_shared, other)
        self.assertEquals([], divergences)

    def test_summarize_current_translations_current_2_different(self):
        # summarize_current_translations when there are different
        # shared, current translations on the Ubuntu and upstream sides.
        tm_this = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=False)
        tm_other = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=False, upstream=True, diverged=False)
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))
        self.assertEquals(tm_this, current_shared)
        self.assertIs(None, current_diverged)
        self.assertEquals(tm_other, other)
        self.assertEquals([], divergences)

    def test_summarize_current_translations_current_3_different(self):
        # summarize_current_translations when there are different
        # shared current messages on the Ubuntu side and upstream, and
        # there is also a diverged message.
        tm_this = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=False)
        tm_other = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=False, upstream=True, diverged=False)
        tm_diverged = make_translationmessage(
            self.factory, pofile=self.pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=True)
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))
        self.assertEquals(tm_this, current_shared)
        self.assertEquals(tm_diverged, current_diverged)
        self.assertEquals(tm_other, other)
        self.assertEquals([], divergences)

    def test_summarize_current_translations_current_3_diverged_elsewh(self):
        # summarize_current_translations when there are different
        # shared current messages on the Ubuntu side and upstream, and
        # there is also a diverged message in another template than the
        # one we're looking at.
        tm_diverged = make_translationmessage(
            self.factory, pofile=self.other_pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=True)
        self.assertTrue(tm_diverged.is_current_ubuntu)
        self.assertEquals(
            tm_diverged.potemplate, self.other_pofile.potemplate)
        self.assertEquals(self.potmsgset, tm_diverged.potmsgset)
        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))
        self.assertIs(None, current_shared)
        self.assertIs(None, current_diverged)
        self.assertIs(None, other)
        self.assertEquals([tm_diverged], divergences)

    def test_summarize_current_translations_multiple_divergences_elsewh(self):
        # summarize_current_translations when there are diverged
        # messages on both the Ubuntu side and the upstream side.
        tm_diverged1 = make_translationmessage(
            self.factory, pofile=self.other_pofile, potmsgset=self.potmsgset,
            ubuntu=True, upstream=False, diverged=True)

        ubuntu = self.pofile.potemplate.distroseries.distribution
        potemplate2 = self.factory.makePOTemplate(
            distroseries=self.factory.makeDistroSeries(distribution=ubuntu),
            sourcepackagename=self.pofile.potemplate.sourcepackagename)
        pofile2 = self.factory.makePOFile(
            self.pofile.language.code, potemplate=potemplate2)
        tm_diverged2 = make_translationmessage(
            self.factory, pofile=pofile2, potmsgset=self.potmsgset,
            ubuntu=False, upstream=True, diverged=True)

        current_shared, current_diverged, other, divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))

        self.assertContentEqual([tm_diverged1, tm_diverged2], divergences)
