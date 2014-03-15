# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `TranslationSide` and friends."""

__metaclass__ = type

from zope.component import getUtility
from zope.interface.verify import verifyObject

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.interfaces.side import (
    ITranslationSideTraits,
    ITranslationSideTraitsSet,
    TranslationSide,
    )


class TestTranslationSideTraitsSet(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_baseline(self):
        utility = getUtility(ITranslationSideTraitsSet)
        self.assertTrue(verifyObject(ITranslationSideTraitsSet, utility))
        for traits in utility.getAllTraits().itervalues():
            self.assertTrue(verifyObject(ITranslationSideTraits, traits))

    def test_other_sides(self):
        utility = getUtility(ITranslationSideTraitsSet)
        upstream = utility.getTraits(TranslationSide.UPSTREAM)
        ubuntu = utility.getTraits(TranslationSide.UBUNTU)

        self.assertEqual(ubuntu, upstream.other_side_traits)
        self.assertEqual(upstream, ubuntu.other_side_traits)

    def test_getTraits(self):
        utility = getUtility(ITranslationSideTraitsSet)
        for side in [TranslationSide.UPSTREAM, TranslationSide.UBUNTU]:
            traits = utility.getTraits(side)
            self.assertTrue(verifyObject(ITranslationSideTraits, traits))

    def test_getForTemplate_upstream(self):
        utility = getUtility(ITranslationSideTraitsSet)
        productseries = self.factory.makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        traits = utility.getForTemplate(template)
        self.assertEqual(TranslationSide.UPSTREAM, traits.side)

    def test_getForTemplate_ubuntu(self):
        utility = getUtility(ITranslationSideTraitsSet)
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        traits = utility.getForTemplate(template)
        self.assertEqual(TranslationSide.UBUNTU, traits.side)

    def test_getAllTraits(self):
        utility = getUtility(ITranslationSideTraitsSet)
        traits_dict = utility.getAllTraits()

        self.assertContentEqual(
            [TranslationSide.UPSTREAM, TranslationSide.UBUNTU],
            traits_dict.keys())

        for side, traits in traits_dict.iteritems():
            self.assertEqual(side, traits.side)
            self.assertEqual(traits, utility.getTraits(side))


class TraitsScenario:
    """Tests that can be run on either the upstream or the Ubuntu side."""

    def _makeTemplate(self):
        """Create a template for the side being tested."""
        raise NotImplementedError()

    def _makeTemplateAndTranslationMessage(self):
        """Create a POTemplate with a TranslationMessage.

        Creates a POFile and POTMsgSet along the way.

        The TranslationMessage will not be current.
        """
        template = self._makeTemplate()
        pofile = self.factory.makePOFile('nl', template)
        potmsgset = self.factory.makePOTMsgSet(template)
        translationmessage = potmsgset.submitSuggestion(
            pofile, self.factory.makePerson(),
            {0: self.factory.getUniqueString()})
        return template, translationmessage

    def _getTraits(self, template):
        """Shortcut: get TranslationSideTraits for template."""
        return getUtility(ITranslationSideTraitsSet).getForTemplate(template)

    def test_getFlag_and_setFlag(self):
        template, message = self._makeTemplateAndTranslationMessage()
        traits = self._getTraits(template)
        other_side_traits = traits.other_side_traits

        traits.setFlag(message, True)

        self.assertEqual(
            (True, False),
            (traits.getFlag(message), other_side_traits.getFlag(message)))

        traits.setFlag(message, False)

        self.assertEqual(
            (False, False),
            (traits.getFlag(message), other_side_traits.getFlag(message)))

    def test_getCurrentMessage(self):
        template, message = self._makeTemplateAndTranslationMessage()
        traits = self._getTraits(template)

        traits.setFlag(message, True)

        current_message = traits.getCurrentMessage(
            message.potmsgset, template, message.language)
        self.assertEqual(message, current_message)

        traits.setFlag(message, False)

        current_message = traits.getCurrentMessage(
            message.potmsgset, template, message.language)
        self.assertIs(None, current_message)

    def test_getCurrentMessage_ignores_other_flag(self):
        template, message = self._makeTemplateAndTranslationMessage()
        traits = self._getTraits(template)
        other_side_traits = traits.other_side_traits

        other_side_traits.setFlag(message, True)

        current_message = traits.getCurrentMessage(
            message.potmsgset, template, message.language)
        self.assertIs(None, current_message)

        other_side_traits.setFlag(message, False)

        current_message = traits.getCurrentMessage(
            message.potmsgset, template, message.language)
        self.assertIs(None, current_message)


class UpstreamTranslationSideTraitsTest(TraitsScenario, TestCaseWithFactory):
    """Run the TraitsScenario tests on the upstream side."""
    layer = DatabaseFunctionalLayer

    def _makeTemplate(self):
        """See `TraitsScenario`."""
        return self.factory.makePOTemplate(
            productseries=self.factory.makeProductSeries())

    def test_getFlag_reads_upstream_flag(self):
        # This test case looks on the upstream side.  We're really
        # working with the is_current_upstream flag underneath the
        # traits interface.
        template, message = self._makeTemplateAndTranslationMessage()
        traits = self._getTraits(template)
        traits.setFlag(message, True)
        self.assertTrue(message.is_current_upstream)


class UbuntuTranslationSideTraitsTest(TraitsScenario, TestCaseWithFactory):
    """Run the TraitsScenario tests on the Ubuntu side."""
    layer = DatabaseFunctionalLayer

    def _makeTemplate(self):
        """See `TraitsScenario`."""
        package = self.factory.makeSourcePackage()
        return self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

    def test_getFlag_reads_ubuntu_flag(self):
        # This test case looks on the Ubuntu side.  We're really
        # working with the is_current_ubuntu flag underneath the traits
        # interface.
        template, message = self._makeTemplateAndTranslationMessage()
        traits = self._getTraits(template)
        traits.setFlag(message, True)
        self.assertTrue(message.is_current_ubuntu)
