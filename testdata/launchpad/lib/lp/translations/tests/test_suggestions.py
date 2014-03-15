# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from pytz import timezone
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.services.config import config
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.potemplate import IPOTemplateSet


class TestTranslationSuggestions(TestCaseWithFactory):
    """Test discovery of translation suggestions."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Set up context to test in."""
        super(TestTranslationSuggestions, self).setUp()

        # Pretend we have two products Foo and Bar being translated.
        # Translations used or suggested in the one may show up as
        # suggestions for the other.
        foo_product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        bar_product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        self.foo_trunk = self.factory.makeProductSeries(
            product=foo_product)
        self.bar_trunk = self.factory.makeProductSeries(
            product=bar_product)
        self.foo_template = self.factory.makePOTemplate(self.foo_trunk)
        self.bar_template = self.factory.makePOTemplate(self.bar_trunk)
        self.nl = getUtility(ILanguageSet).getLanguageByCode('nl')
        self.foo_nl = self.factory.makePOFile(
            'nl', potemplate=self.foo_template)
        self.bar_nl = self.factory.makePOFile(
            'nl', potemplate=self.bar_template)
        self._refreshSuggestiveTemplatesCache()

    def _refreshSuggestiveTemplatesCache(self):
        """Update the `SuggestivePOTemplate` cache."""
        getUtility(IPOTemplateSet).populateSuggestivePOTemplatesCache()

    def test_NoSuggestions(self):
        # When a msgid string is unique and nobody has submitted any
        # translations for it, there are no suggestions for translating
        # it whatsoever.
        potmsgset = self.factory.makePOTMsgSet(self.foo_template)
        self.assertEquals(
            potmsgset.getExternallyUsedTranslationMessages(self.nl), [])
        self.assertEquals(
            potmsgset.getExternallySuggestedTranslationMessages(self.nl), [])
        self.assertEqual({},
            potmsgset.getExternallySuggestedOrUsedTranslationMessages(
                suggested_languages=[self.nl], used_languages=[self.nl]))

    def test_SimpleExternallyUsedSuggestion(self):
        # If foo wants to translate "error message 936" and bar happens
        # to have a translation for that, that's an externally used
        # suggestion.
        text = "error message 936"
        foomsg = self.factory.makePOTMsgSet(self.foo_template, text)
        barmsg = self.factory.makePOTMsgSet(self.bar_template, text)
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.bar_nl, current_other=False, potmsgset=barmsg)

        transaction.commit()

        def check_used_suggested():
            self.assertEquals(len(used_suggestions), 1)
            self.assertEquals(used_suggestions[0], translation)
            self.assertEquals(len(other_suggestions), 0)
        used_suggestions = foomsg.getExternallyUsedTranslationMessages(
            self.nl)
        other_suggestions = foomsg.getExternallySuggestedTranslationMessages(
            self.nl)
        check_used_suggested()
        other_suggestions, used_suggestions = \
            foomsg.getExternallySuggestedOrUsedTranslationMessages(
                suggested_languages=[self.nl],
                used_languages=[self.nl])[self.nl]
        check_used_suggested()

    def test_DisabledExternallyUsedSuggestions(self):
        # If foo wants to translate "error message 936" and bar happens
        # to have a translation for that, that's an externally used
        # suggestion.
        # If global suggestions are disabled, empty list is returned.
        text = "error message 936"
        foomsg = self.factory.makePOTMsgSet(self.foo_template, text)
        barmsg = self.factory.makePOTMsgSet(self.bar_template, text)
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.bar_nl, current_other=False, potmsgset=barmsg)

        transaction.commit()

        # There is a global (externally used) suggestion.
        used_suggestions = foomsg.getExternallyUsedTranslationMessages(
            self.nl)
        self.assertEquals(len(used_suggestions), 1)
        used_suggestions = foomsg.getExternallySuggestedOrUsedTranslationMessages(
            used_languages=[self.nl], suggested_languages=[self.nl])[self.nl].used
        self.assertEquals(len(used_suggestions), 1)

        # Override the config option to disable global suggestions.
        new_config = ("""
            [rosetta]
            global_suggestions_enabled = False
            """)
        config.push('disabled_suggestions', new_config)
        disabled_used_suggestions = (
            foomsg.getExternallyUsedTranslationMessages(self.nl))
        self.assertEquals(len(disabled_used_suggestions), 0)
        disabled_used_suggestions = (
            foomsg.getExternallySuggestedOrUsedTranslationMessages(
                used_languages=[self.nl],
                suggested_languages=[self.nl]))[self.nl].used
        self.assertEquals(len(disabled_used_suggestions), 0)
        # Restore the old configuration.
        config.pop('disabled_suggestions')

    def test_SimpleOtherSuggestion(self):
        # Suggestions made for bar can also be useful suggestions for foo.
        text = "Welcome to our application!  We hope to have code soon."
        foomsg = self.factory.makePOTMsgSet(self.foo_template, text)
        barmsg = self.factory.makePOTMsgSet(self.bar_template, text)
        suggestion = barmsg.submitSuggestion(
            self.bar_nl, self.foo_template.owner, {0: "Noueh hallo dus."})

        transaction.commit()

        def check_used_suggested():
            self.assertEquals(len(used_suggestions), 0)
            self.assertEquals(len(other_suggestions), 1)
            self.assertEquals(other_suggestions[0], suggestion)
        used_suggestions = foomsg.getExternallyUsedTranslationMessages(
            self.nl)
        other_suggestions = foomsg.getExternallySuggestedTranslationMessages(
            self.nl)
        check_used_suggested()
        other_suggestions, used_suggestions = \
            foomsg.getExternallySuggestedOrUsedTranslationMessages(
                used_languages=[self.nl],
                suggested_languages=[self.nl])[self.nl]
        check_used_suggested()

    def test_IdenticalSuggestions(self):
        # If two suggestions are identical, the most recent one is used.
        text = "The application has exploded."
        suggested_dutch = "De applicatie is ontploft."
        now = datetime.now(timezone('UTC'))
        before = now - timedelta(1, 1, 1)

        foomsg = self.factory.makePOTMsgSet(self.foo_template, text)
        barmsg = self.factory.makePOTMsgSet(self.bar_template, text)
        suggestion1 = self.factory.makeCurrentTranslationMessage(
            pofile=self.bar_nl, potmsgset=foomsg,
            translations={0: suggested_dutch})
        suggestion2 = self.factory.makeCurrentTranslationMessage(
            pofile=self.bar_nl, potmsgset=barmsg,
            translations={0: suggested_dutch})
        self.assertNotEqual(suggestion1, suggestion2)
        removeSecurityProxy(suggestion1).date_created = before
        removeSecurityProxy(suggestion2).date_created = before

        # When a third project, oof, contains the same translatable
        # string, only the most recent of the identical suggestions is
        # shown.
        oof_template = self.factory.makePOTemplate()
        oof_potmsgset = self.factory.makePOTMsgSet(
            oof_template, singular=text)
        from storm.store import Store
        Store.of(oof_template).flush()
        transaction.commit()
        suggestions = oof_potmsgset.getExternallyUsedTranslationMessages(
            self.nl)
        self.assertEquals(len(suggestions), 1)
        self.assertEquals(suggestions[0], suggestion1)
        suggestions = oof_potmsgset.getExternallySuggestedOrUsedTranslationMessages(
            suggested_languages=[self.nl], used_languages=[self.nl])[self.nl].used
        self.assertEquals(len(suggestions), 1)
        self.assertEquals(suggestions[0], suggestion1)

    def test_RevertingToUpstream(self):
        # When a msgid string is unique and nobody has submitted any
        # translations for it, there are no suggestions for translating
        # it whatsoever.
        translated_in_ubuntu = "Ubuntu translation."
        translated_upstream = "Upstream translation."
        potmsgset = self.factory.makePOTMsgSet(self.foo_template)
        suggestion1 = self.factory.makeCurrentTranslationMessage(
            pofile=self.foo_nl, potmsgset=potmsgset,
            translations={0: translated_in_ubuntu},
            current_other=False)
        suggestion2 = self.factory.makeCurrentTranslationMessage(
            pofile=self.foo_nl, potmsgset=potmsgset,
            translations={0: translated_upstream},
            current_other=True)
        ubuntu_translation = potmsgset.getCurrentTranslation(
            self.foo_template, self.foo_nl.language,
            side=self.foo_template.translation_side)
        upstream_translation = potmsgset.getOtherTranslation(
            self.foo_nl.language, self.foo_template.translation_side)

        self.assertEquals(
            upstream_translation, ubuntu_translation,
            "Upstream message should become current in Ubuntu if there are "
            "no previous imported messages.")
