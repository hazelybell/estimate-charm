# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `POTMsgSet.clearCurrentTranslation`."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from pytz import UTC
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.database.constants import UTC_NOW
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.interfaces.side import ITranslationSideTraitsSet
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    TranslationConflict,
    )


ORIGIN = RosettaTranslationOrigin.SCM


def get_traits(potemplate):
    """Obtain the translation side traits for template."""
    return getUtility(ITranslationSideTraitsSet).getTraits(
        potemplate.translation_side)


class ScenarioMixin:
    layer = DatabaseFunctionalLayer

    def makePOTemplate(self):
        """Create a POTemplate for the side that's being tested."""
        raise NotImplementedError()

    def makeOtherPOTemplate(self):
        """Create a POTemplate for the other side."""
        raise NotImplementedError()

    def makeUpstreamTemplate(self):
        """Create a POTemplate for a project."""
        productseries = self.factory.makeProductSeries()
        return self.factory.makePOTemplate(productseries=productseries)

    def makeUbuntuTemplate(self):
        """Create a POTemplate for an Ubuntu package."""
        package = self.factory.makeSourcePackage()
        return self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

    def _makePOFile(self, potemplate=None):
        """Create a `POFile` for the given template.

        Also creates a POTemplate if none is given, using
        self.makePOTemplate.
        """
        if potemplate is None:
            potemplate = self.makePOTemplate()
        return self.factory.makePOFile('nl', potemplate=potemplate)

    def _makeTranslationMessage(self, potmsgset, pofile, translations=None,
                                diverged=False):
        """Create a (non-current) TranslationMessage for potmsgset."""
        message = self.factory.makeSuggestion(
            pofile=pofile, potmsgset=potmsgset, translations=translations)
        if diverged:
            removeSecurityProxy(message).potemplate = pofile.potemplate
        return message

    def test_creates_empty_message(self):
        # Even if there is no current message, clearCurrentTranslation
        # will create an empty message so as to mark the review time.
        pofile = self._makePOFile()
        template = pofile.potemplate
        potmsgset = self.factory.makePOTMsgSet(template)

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        current = get_traits(template).getCurrentMessage(
            potmsgset, template, pofile.language)
        self.assertEqual(
            [],
            [msgstr for msgstr in current.translations if msgstr is not None])

    def test_deactivates_shared_message(self):
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        tm = self._makeTranslationMessage(potmsgset, pofile)
        traits.setFlag(tm, True)
        self.assertTrue(traits.getFlag(tm))

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        self.assertFalse(traits.getFlag(tm))

    def test_deactivates_diverged_message(self):
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        tm = self._makeTranslationMessage(potmsgset, pofile, diverged=True)
        traits.setFlag(tm, True)

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        self.assertFalse(traits.getFlag(tm))

    def test_hides_unmasked_shared_message(self):
        # When disabling a diverged message that masks a (nonempty)
        # shared message, clearCurrentTranslation leaves an empty
        # diverged message to mask the shared message.
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        shared_tm = self._makeTranslationMessage(potmsgset, pofile)
        traits.setFlag(shared_tm, True)
        diverged_tm = self._makeTranslationMessage(
            potmsgset, pofile, diverged=True)
        traits.setFlag(diverged_tm, True)

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        current = traits.getCurrentMessage(
            potmsgset, template, pofile.language)
        self.assertNotEqual(shared_tm, current)
        self.assertNotEqual(diverged_tm, current)
        self.assertTrue(current.is_empty)
        self.assertTrue(current.is_diverged)
        self.assertEqual(template.owner, current.reviewer)

        self.assertTrue(traits.getFlag(shared_tm))

    def test_ignores_other_message(self):
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        tm = self._makeTranslationMessage(potmsgset, pofile)
        traits.setFlag(tm, True)

        other_template = self.makeOtherPOTemplate()
        other_pofile = self._makePOFile(potemplate=other_template)
        other_tm = self._makeTranslationMessage(potmsgset, pofile)
        traits.other_side_traits.setFlag(other_tm, True)

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        self.assertTrue(traits.other_side_traits.getFlag(other_tm))

    def test_deactivates_one_side(self):
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        tm = self._makeTranslationMessage(potmsgset, pofile)
        traits.setFlag(tm, True)
        traits.other_side_traits.setFlag(tm, True)

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        self.assertFalse(traits.getFlag(tm))
        self.assertTrue(traits.other_side_traits.getFlag(tm))

    def test_deactivates_both_sides(self):
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        tm = self._makeTranslationMessage(potmsgset, pofile)
        traits.setFlag(tm, True)
        traits.other_side_traits.setFlag(tm, True)

        potmsgset.clearCurrentTranslation(
            pofile, template.owner, ORIGIN, share_with_other_side=True)

        self.assertFalse(traits.getFlag(tm))
        self.assertFalse(traits.other_side_traits.getFlag(tm))

    def test_converges_with_empty_shared_message(self):
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        diverged_tm = self._makeTranslationMessage(
            potmsgset, pofile, diverged=True)
        traits.setFlag(diverged_tm, True)
        blank_shared_tm = self._makeTranslationMessage(potmsgset, pofile, [])
        traits.setFlag(blank_shared_tm, True)

        potmsgset.clearCurrentTranslation(pofile, template.owner, ORIGIN)

        self.assertTrue(traits.getFlag(blank_shared_tm))
        current = traits.getCurrentMessage(
            potmsgset, template, pofile.language)
        self.assertEqual(blank_shared_tm, current)

    def test_reviews_new_blank(self):
        # When clearCurrentTranslation creates a blank message in order
        # to mark the review, the blank message does indeed have its
        # review fields set.
        pofile = self._makePOFile()
        template = pofile.potemplate
        potmsgset = self.factory.makePOTMsgSet(template)
        reviewer = self.factory.makePerson()

        potmsgset.clearCurrentTranslation(pofile, reviewer, ORIGIN)

        blank = get_traits(template).getCurrentMessage(
            potmsgset, template, pofile.language)

        self.assertNotEqual(None, blank.date_reviewed)
        self.assertEqual(reviewer, blank.reviewer)

    def test_reviews_existing_blank(self):
        # When clearCurrentTranslation reuses an existing blank message
        # in order to mark the review, the blank message's review
        # information is updated.
        pofile = self._makePOFile()
        template = pofile.potemplate
        traits = get_traits(template)
        potmsgset = self.factory.makePOTMsgSet(template)
        blank = self.factory.makeSuggestion(
            potmsgset=potmsgset, pofile=pofile, translations=[])

        old_review_date = datetime.now(UTC) - timedelta(days=7)
        old_reviewer = self.factory.makePerson()
        blank.markReviewed(old_reviewer, timestamp=old_review_date)

        current = self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)

        new_reviewer = self.factory.makePerson()

        potmsgset.clearCurrentTranslation(pofile, new_reviewer, ORIGIN)

        current = traits.getCurrentMessage(
            potmsgset, template, pofile.language)

        self.assertEqual(new_reviewer, current.reviewer)
        self.assertSqlAttributeEqualsDate(current, 'date_reviewed', UTC_NOW)

    def test_detects_conflict(self):
        pofile = self._makePOFile()
        current_message = self.factory.makeCurrentTranslationMessage(
            pofile=pofile)
        old = datetime.now(UTC) - timedelta(days=7)

        self.assertRaises(
            TranslationConflict,
            current_message.potmsgset.clearCurrentTranslation,
            pofile, self.factory.makePerson(), ORIGIN, lock_timestamp=old)


class TestClearCurrentTranslationUpstream(TestCaseWithFactory,
                                          ScenarioMixin):
    """Test clearCurrentTranslationUpstream on upstream side."""
    makePOTemplate = ScenarioMixin.makeUpstreamTemplate
    makeOtherPOTemplate = ScenarioMixin.makeUbuntuTemplate

    def setUp(self):
        super(TestClearCurrentTranslationUpstream, self).setUp(
            'carlos@canonical.com')


class TestClearCurrentTranslationUbuntu(TestCaseWithFactory,
                                        ScenarioMixin):
    """Test clearCurrentTranslationUpstream on Ubuntu side."""
    makePOTemplate = ScenarioMixin.makeUbuntuTemplate
    makeOtherPOTemplate = ScenarioMixin.makeUpstreamTemplate

    def setUp(self):
        super(TestClearCurrentTranslationUbuntu, self).setUp(
            'carlos@canonical.com')
