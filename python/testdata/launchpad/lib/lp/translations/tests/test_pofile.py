# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from textwrap import dedent

import pytz
from zope.component import (
    getAdapter,
    getUtility,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.database.constants import UTC_NOW
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    monkey_patch,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.pofile import IPOFileSet
from lp.translations.interfaces.side import ITranslationSideTraitsSet
from lp.translations.interfaces.translationcommonformat import (
    ITranslationFileData,
    )
from lp.translations.interfaces.translationgroup import TranslationPermission
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    )
from lp.translations.interfaces.translationsperson import ITranslationsPerson


def set_relicensing(person, choice):
    """Set `person`'s choice for the translations relicensing agreement.

    :param person: A `Person`.
    :param choice: The person's tri-state boolean choice on the
        relicensing agreement.  None means undecided, which is the
        default initial choice for any person.
    """
    ITranslationsPerson(person).translations_relicensing_agreement = choice


class TestTranslationSharedPOFileSourcePackage(TestCaseWithFactory):
    """Test behavior of PO files with shared POTMsgSets on a source package.
    """

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a product with two series and a shared POTemplate
        # in different series ('devel' and 'stable').
        super(TestTranslationSharedPOFileSourcePackage, self).setUp()
        self.foo = self.factory.makeDistribution()
        self.foo_devel = self.factory.makeDistroSeries(
            name='devel', distribution=self.foo)
        self.foo_stable = self.factory.makeDistroSeries(
            name='stable', distribution=self.foo)
        self.sourcepackagename = self.factory.makeSourcePackageName()

        # Two POTemplates share translations if they have the same name,
        # in this case 'messages'.
        self.devel_potemplate = self.factory.makePOTemplate(
            distroseries=self.foo_devel,
            sourcepackagename=self.sourcepackagename,
            name="messages")
        self.stable_potemplate = self.factory.makePOTemplate(
            distroseries=self.foo_stable,
            sourcepackagename=self.sourcepackagename,
            name="messages")

        # We'll use two PO files, one for each series.
        self.devel_pofile = self.factory.makePOFile(
            'sr', self.devel_potemplate)
        self.stable_pofile = self.factory.makePOFile(
            'sr', self.stable_potemplate)

        # The POTMsgSet is added to only one of the POTemplates.
        self.potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate)

    def test_getPOTMsgSetWithNewSuggestions_shared(self):
        # Test listing of suggestions for POTMsgSets with a shared
        # translation.

        # A POTMsgSet has a shared, current translation created 5 days ago.
        date_created = datetime.now(pytz.UTC) - timedelta(5)
        translation = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], date_created=date_created)
        translation.is_current_ubuntu = True

        # When there are no suggestions, nothing is returned.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [])

        # When a suggestion is added one day after, the potmsgset is returned.
        suggestion_date = date_created + timedelta(1)
        suggestion = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Suggestion"], date_created=suggestion_date)
        self.assertEquals(suggestion.is_current_ubuntu, False)

        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [self.potmsgset])

        # Setting a suggestion as current makes it have no unreviewed
        # suggestions.
        # XXX henninge 2010-08-17: It looks like this test passes by
        # accident as the suggestion already is the newest translation
        # available. Other tests may be passing just by accident, too.
        # This will have to be investigated when all bits and pieces are in
        # place.
        translation.is_current_ubuntu = False
        suggestion.is_current_ubuntu = True
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [])

        # And adding another suggestion 2 days later, the potmsgset is
        # again returned.
        suggestion_date += timedelta(2)
        translation = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"New suggestion"], date_created=suggestion_date)
        self.assertEquals(translation.is_current_ubuntu, False)

        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [self.potmsgset])

    def test_getPOTMsgSetWithNewSuggestions_diverged(self):
        # Test listing of suggestions for POTMsgSets with a shared
        # translation and a later diverged one.

        # First we create a shared translation (5 days old), a diverged
        # translation 1 day later.
        # Then we make sure that getting unreviewed messages works when:
        #  * A suggestion is added 1 day after (shows as unreviewed).
        #  * A new diverged translation is added another day later (nothing).
        #  * A new suggestion is added after another day (shows).
        #  * Suggestion is made active (nothing).

        # A POTMsgSet has a shared, current translation created 5 days ago.
        date_created = datetime.now(pytz.UTC) - timedelta(5)
        translation = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Shared translation"], date_created=date_created)
        translation.is_current_ubuntu = True

        # And we also have a diverged translation created a day after a shared
        # current translation.
        diverged_date = date_created + timedelta(1)
        diverged_translation = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Old translation"], date_created=diverged_date)
        diverged_translation.potemplate = self.devel_potemplate
        diverged_translation.is_current_ubuntu = True

        # There is also a suggestion against the shared translation
        # created 2 days after the shared translation.
        suggestion_date = date_created + timedelta(2)
        suggestion = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Shared suggestion"], date_created=suggestion_date)
        self.assertEquals(suggestion.is_current_ubuntu, False)

        # A suggestion is shown since diverged_date < suggestion_date.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [self.potmsgset])

        # When a diverged translation is added after the shared suggestion,
        # there are no unreviewed suggestions.
        diverged_date = suggestion_date + timedelta(1)
        diverged_translation_2 = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], date_created=diverged_date,
            date_reviewed=diverged_date, diverged=True)
        diverged_translation.is_current_ubuntu = False
        diverged_translation_2.potemplate = self.devel_potemplate
        diverged_translation_2.is_current_ubuntu = True
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [])

        # When a suggestion is added one day after, the potmsgset is returned.
        suggestion_date = diverged_date + timedelta(1)
        suggestion = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Suggestion"], date_created=suggestion_date)
        self.assertEquals(suggestion.is_current_ubuntu, False)

        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [self.potmsgset])

        # Setting a suggestion as current makes it have no unreviewed
        # suggestions.
        translation.is_current_ubuntu = False
        suggestion.is_current_ubuntu = True
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [])


class TestTranslationSharedPOFile(TestCaseWithFactory):
    """Test behaviour of PO files with shared POTMsgSets."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a product with two series and a shared POTemplate
        # in different series ('devel' and 'stable').
        super(TestTranslationSharedPOFile, self).setUp()
        self.foo = self.factory.makeProduct(
            name='foo',
            translations_usage=ServiceUsage.LAUNCHPAD)
        self.foo_devel = self.factory.makeProductSeries(
            name='devel', product=self.foo)
        self.foo_stable = self.factory.makeProductSeries(
            name='stable', product=self.foo)

        # Two POTemplates share translations if they have the same name,
        # in this case 'messages'.
        self.devel_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="messages")
        self.stable_potemplate = self.factory.makePOTemplate(self.foo_stable,
                                                        name="messages")

        # We'll use two PO files, one for each series.
        self.devel_pofile = self.factory.makePOFile(
            'sr', self.devel_potemplate)
        self.stable_pofile = self.factory.makePOFile(
            'sr', self.stable_potemplate)

        # The POTMsgSet is added to only one of the POTemplates.
        self.potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate)

    def test_POFile_canonical_url(self):
        # Test the canonical_url of the POFile.
        pofile_url = (
            'http://translations.launchpad.dev/foo/devel/+pots/messages/'
            '%s' % self.devel_pofile.language.code)
        self.assertEqual(pofile_url, canonical_url(self.devel_pofile))
        view_name = '+details'
        view_url = "%s/%s" % (pofile_url, view_name)
        self.assertEqual(
            view_url, canonical_url(self.devel_pofile, view_name=view_name))

    def test_findPOTMsgSetsContaining(self):
        # Test that search works correctly.

        # Searching for English strings.
        potmsgset = self.factory.makePOTMsgSet(self.devel_potemplate,
                                               u"Some wild text", sequence=2)

        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"wild"))
        self.assertEquals(found_potmsgsets, [potmsgset])

        # Just linking an existing POTMsgSet into another POTemplate
        # will make it be returned in searches.
        potmsgset.setSequence(self.stable_potemplate, 2)
        found_potmsgsets = list(
            self.stable_pofile.findPOTMsgSetsContaining(u"wild"))
        self.assertEquals(found_potmsgsets, [potmsgset])

        # Searching for singular in plural messages works as well.
        plural_potmsgset = self.factory.makePOTMsgSet(self.devel_potemplate,
                                                      u"Some singular text",
                                                      u"Some plural text",
                                                      sequence=3)

        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"singular"))
        self.assertEquals(found_potmsgsets, [plural_potmsgset])

        # And searching for plural text returns only the matching plural
        # message.
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"plural"))
        self.assertEquals(found_potmsgsets, [plural_potmsgset])

        # Search translations as well.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"One translation message"])
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"translation"))
        self.assertEquals(found_potmsgsets, [potmsgset])

        # Search matches all plural forms.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=plural_potmsgset,
            translations=[u"One translation message",
                          u"Plural translation message",
                          u"Third translation message"])
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(
                u"Plural translation"))
        self.assertEquals(found_potmsgsets, [plural_potmsgset])

        # Search works case insensitively for English strings.
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"WiLd"))
        self.assertEquals(found_potmsgsets, [potmsgset])
        # ...English plural forms.
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"PLurAl"))
        self.assertEquals(found_potmsgsets, [plural_potmsgset])
        # ...translations.
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"tRANSlaTIon"))
        self.assertEquals(found_potmsgsets, [potmsgset, plural_potmsgset])
        # ...and translated plurals.
        found_potmsgsets = list(
            self.devel_pofile.findPOTMsgSetsContaining(u"THIRD"))
        self.assertEquals(found_potmsgsets, [plural_potmsgset])

    def test_getTranslationsFilteredBy_none(self):
        # When a person has submitted no translations, empty result set
        # is returned.

        # A person to be submitting all translations.
        submitter = self.factory.makePerson()

        # When there are no translations, empty list is returned.
        found_translations = list(
            self.devel_pofile.getTranslationsFilteredBy(submitter))
        self.assertEquals(found_translations, [])

    def test_getTranslationsFilteredBy(self):
        # If 'submitter' provides a translation for a pofile,
        # it's returned in a list.

        potmsgset = self.potmsgset
        submitter = self.factory.makePerson()

        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Translation message"],
            translator=submitter)
        found_translations = list(
            self.devel_pofile.getTranslationsFilteredBy(submitter))
        self.assertEquals(found_translations, [translation])

    def test_getTranslationsFilteredBy_someone_else(self):
        # If somebody else provides a translation, it's not added to the
        # list of submitter's translations.

        potmsgset = self.potmsgset
        submitter = self.factory.makePerson()

        someone_else = self.factory.makePerson()
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Another translation"],
            translator=someone_else)
        found_translations = list(
            self.devel_pofile.getTranslationsFilteredBy(submitter))
        self.assertEquals(found_translations, [])

    def test_getTranslationsFilteredBy_other_pofile(self):
        # Adding a translation for the same POTMsgSet, but to a different
        # POFile (different language) will not add the translation
        # to the list of submitter's translations for *original* POFile.

        potmsgset = self.potmsgset
        submitter = self.factory.makePerson()

        self.factory.makeLanguage('sr@test', 'Serbian Test')

        self.devel_sr_test_pofile = self.factory.makePOFile(
            'sr@test', potemplate=self.devel_potemplate)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_sr_test_pofile, potmsgset=potmsgset,
            translations=[u"Yet another translation"],
            translator=submitter)
        found_translations = list(
            self.devel_pofile.getTranslationsFilteredBy(submitter))
        self.assertEquals(found_translations, [])

    def test_getTranslationsFilteredBy_shared(self):
        # If a POTMsgSet is shared between two templates, a
        # translation on one is listed on both.

        potmsgset = self.potmsgset
        submitter = self.factory.makePerson()
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Translation message"],
            translator=submitter)

        potmsgset.setSequence(self.stable_potemplate, 1)
        stable_translations = list(
            self.stable_pofile.getTranslationsFilteredBy(submitter))
        self.assertEquals(stable_translations, [translation])
        devel_translations = list(
            self.devel_pofile.getTranslationsFilteredBy(submitter))
        self.assertEquals(devel_translations, [translation])

    def test_getPOTMsgSetTranslated_NoShared(self):
        # Test listing of translated POTMsgSets when there is no shared
        # translation for the POTMsgSet.

        # When there is no diverged translation either, nothing is returned.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [])

        # When a diverged translation is added, the potmsgset is returned.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [self.potmsgset])

        # If diverged translation is empty, POTMsgSet is not listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [])

    def test_getPOTMsgSetTranslated_Shared(self):
        # Test listing of translated POTMsgSets when there is a shared
        # translation for the POTMsgSet as well.

        # We create a shared translation first.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Shared translation"])

        # When there is no diverged translation, shared one is returned.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [self.potmsgset])

        # When an empty diverged translation is added, nothing is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [])

        # If diverged translation is non-empty, POTMsgSet is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [self.potmsgset])

    def test_getPOTMsgSetTranslated_EmptyShared(self):
        # Test listing of translated POTMsgSets when there is an
        # empty shared translation for the POTMsgSet as well.

        # We create an empty shared translation first.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""])

        # When there is no diverged translation, shared one is returned,
        # but since it's empty, there are no results.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [])

        # When an empty diverged translation is added, nothing is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [])

        # If diverged translation is non-empty, POTMsgSet is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [self.potmsgset])

    def test_getPOTMsgSetTranslated_Multiple(self):
        # Test listing of translated POTMsgSets if there is more than one
        # translated message.
        self.potmsgset.setSequence(self.devel_potemplate, 1)

        # Add a diverged translation on the included POTMsgSet...
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Diverged translation"], diverged=True)

        # and a shared translation on newly added POTMsgSet...
        potmsgset = self.factory.makePOTMsgSet(self.devel_potemplate,
                                               u"Translated text", sequence=2)

        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Shared translation"])

        # Both POTMsgSets are listed.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(found_translations, [self.potmsgset, potmsgset])

    def test_getPOTMsgSetUntranslated_NoShared(self):
        # Test listing of translated POTMsgSets when there is no shared
        # translation for the POTMsgSet.

        # When there is no diverged translation either, nothing is returned.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [self.potmsgset])

        # When a diverged translation is added, the potmsgset is returned.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [])

        # If diverged translation is empty, POTMsgSet is not listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [self.potmsgset])

    def test_getPOTMsgSetUntranslated_Shared(self):
        # Test listing of translated POTMsgSets when there is a shared
        # translation for the POTMsgSet as well.

        # We create a shared translation first.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Shared translation"])

        # When there is no diverged translation, shared one is returned.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [])

        # When an empty diverged translation is added, nothing is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [self.potmsgset])

        # If diverged translation is non-empty, POTMsgSet is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [])

    def test_getPOTMsgSetUntranslated_EmptyShared(self):
        # Test listing of translated POTMsgSets when there is an
        # empty shared translation for the POTMsgSet as well.

        # We create an empty shared translation first.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""])

        # When there is no diverged translation, shared one is returned,
        # but since it's empty, there are no results.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [self.potmsgset])

        # When an empty diverged translation is added, nothing is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [self.potmsgset])

        # If diverged translation is non-empty, POTMsgSet is listed.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"], diverged=True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [])

    def test_getPOTMsgSetUntranslated_Multiple(self):
        # Test listing of untranslated POTMsgSets if there is more than one
        # untranslated message.
        self.potmsgset.setSequence(self.devel_potemplate, 1)

        # Add an empty translation to the included POTMsgSet...
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u""])

        # ...and a new untranslated POTMsgSet.
        potmsgset = self.factory.makePOTMsgSet(self.devel_potemplate,
                                               u"Translated text", sequence=2)

        # Both POTMsgSets are listed.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(found_translations, [self.potmsgset, potmsgset])

    def test_getPOTMsgSetWithNewSuggestions(self):
        # Test listing of POTMsgSets with unreviewed suggestions.

        # When there are no suggestions, nothing is returned.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [])

        # When a suggestion is added, the potmsgset is returned.
        translation = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Suggestion"])
        self.assertEquals(translation.is_current_ubuntu, False)

        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [self.potmsgset])

    def test_getPOTMsgSetWithNewSuggestions_multiple(self):
        # Test that multiple unreviewed POTMsgSets are returned.
        self.potmsgset.setSequence(self.devel_potemplate, 1)

        # One POTMsgSet has no translations, but only a suggestion.
        self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"New suggestion"])

        # Another POTMsgSet has both a translation and a suggestion.
        potmsgset = self.factory.makePOTMsgSet(self.devel_potemplate,
                                               u"Translated text",
                                               sequence=2)
        date_created = datetime.now(pytz.UTC) - timedelta(5)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Translation"],
            date_created=date_created, date_reviewed=date_created)
        suggestion_date = date_created + timedelta(1)
        self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"New suggestion"], date_created=suggestion_date)

        # Both POTMsgSets are listed.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(found_translations, [self.potmsgset, potmsgset])

    def test_getPOTMsgSetWithNewSuggestions_distinct(self):
        # Provide two suggestions on a single message and make sure
        # a POTMsgSet is returned only once.
        self.factory.makeSuggestion(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset,
            translations=["A suggestion"])
        self.factory.makeSuggestion(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset,
            translations=["Another suggestion"])

        potmsgsets = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals(potmsgsets,
                          [self.potmsgset])
        self.assertEquals(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions().count(),
            1)

    def test_getPOTMsgSetWithNewSuggestions_empty(self):
        # Test listing of POTMsgSets with empty strings as suggestions.

        # When an empty suggestion is added, the potmsgset is NOT returned.
        translation = self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[])
        self.assertEquals(False, translation.is_current_ubuntu)

        found_translations = list(
            self.devel_pofile.getPOTMsgSetWithNewSuggestions())
        self.assertEquals([], found_translations)

    def _getThisSideFlag(self, translation_message):
        """Return the value of the "is_current_*" flag on this side."""
        traits = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.devel_potemplate)
        return traits.getFlag(translation_message)

    def _getOtherSideFlag(self, translation_message):
        """Return the value of the "is_current_*" flag on the other side."""
        traits = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.devel_potemplate).other_side_traits
        return traits.getFlag(translation_message)

    def test_getPOTMsgSetDifferentTranslations(self):
        # Test listing of POTMsgSets which have different translations on
        # both sides.
        # This test case is set up with templates and pofiles linked to
        # product series, therefore they are "upstream" files. As a
        # consequence "this side" in this test refers to "upstream" and
        # "other side"  refers to "ubuntu" translations. We keep the generic
        # terms, though, because the behavior is symmetrical.

        # If there are no translations on either side, nothing is listed.
        found_translations = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(found_translations, [])

        # Adding a current translation on one side doesn't change anything.
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"This side translation"])
        self.assertEquals(self._getThisSideFlag(translation), True)
        self.assertEquals(self._getOtherSideFlag(translation), False)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(found_translations, [])

        # Adding a translation on both sides does not introduce a difference.
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Both sides translation"], current_other=True)
        self.assertEquals(self._getThisSideFlag(translation), True)
        self.assertEquals(self._getOtherSideFlag(translation), True)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(found_translations, [])

        # Adding a different translation on one side to creates a difference
        # between this side and the other side.
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Different translation"])
        self.assertEquals(self._getThisSideFlag(translation), True)
        self.assertEquals(self._getOtherSideFlag(translation), False)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(found_translations, [self.potmsgset])

        # A diverged translation is different, too.
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=self.potmsgset,
            translations=[u"Diverged translation"], diverged=True)
        self.assertEquals(self._getThisSideFlag(translation), True)
        self.assertEquals(self._getOtherSideFlag(translation), False)
        found_translations = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(found_translations, [self.potmsgset])

    def test_messageCount(self):
        # POFile.messageCount just forwards to POTmeplate.messageCount.
        naked_pofile = removeSecurityProxy(self.factory.makePOFile())
        naked_pofile.potemplate.messageCount = FakeMethod(result=99)
        self.assertEqual(99, naked_pofile.messageCount())

    def test_initial_statistics_consistency(self):
        # A `POFile` starts out with consistent statistics.
        self.assertTrue(self.factory.makePOFile().testStatistics())

    def test_updateStatistics_counts_zero_for_empty_template(self):
        # Statistics for an empty template are all calculated as zero.
        pofile = self.factory.makePOFile()
        pofile.updateStatistics()
        self.assertEquals(0, self.devel_pofile.messageCount())
        self.assertEquals(0, self.devel_pofile.translatedCount())
        self.assertEquals(0, self.devel_pofile.untranslatedCount())
        self.assertEquals(0, self.devel_pofile.currentCount())
        self.assertEquals(0, self.devel_pofile.rosettaCount())
        self.assertEquals(0, self.devel_pofile.updatesCount())
        self.assertEquals(0, self.devel_pofile.unreviewedCount())

    def test_updateStatistics(self):
        # Test that updating statistics keeps working.

        # We are constructing a POFile with:
        #  - 2 untranslated message
        #  - 2 unreviewed suggestions (for translated and untranslated each)
        #  - 2 imported translations, out of which 1 is changed in Ubuntu
        #  - 1 LP-provided translation
        # For a total of 6 messages, 4 translated (1 from import,
        # 3 only in LP, where 1 is changed from imported).

        # First POTMsgSet (self.potmsgset) is untranslated.

        # Second POTMsgSet is untranslated, but with a suggestion.
        potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=2)
        self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Unreviewed suggestion"])

        # Third POTMsgSet is translated, and with a suggestion.
        potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=3)
        update_date = datetime.now(pytz.UTC) - timedelta(1)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Translation"], date_created=update_date,
            date_reviewed=update_date)
        self.factory.makeSuggestion(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Another suggestion"])

        # Fourth POTMsgSet is translated in import.
        potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=4)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Imported translation"], current_other=True)

        # Fifth POTMsgSet is translated in import, but changed in Ubuntu.
        potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=5)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"Imported translation"], current_other=True)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"LP translation"], current_other=False)

        # Sixth POTMsgSet is translated in LP only.
        potmsgset = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=6)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile, potmsgset=potmsgset,
            translations=[u"New translation"], current_other=False)

        removeSecurityProxy(self.devel_potemplate).messagecount = (
            self.devel_potemplate.getPOTMsgSetsCount())

        # Returns current, updates, rosetta, unreviewed counts.
        stats = self.devel_pofile.updateStatistics()
        self.assertEquals((1, 1, 3, 2), stats)

        self.assertEquals(6, self.devel_pofile.messageCount())
        self.assertEquals(4, self.devel_pofile.translatedCount())
        self.assertEquals(2, self.devel_pofile.untranslatedCount())
        self.assertEquals(1, self.devel_pofile.currentCount())
        self.assertEquals(3, self.devel_pofile.rosettaCount())
        self.assertEquals(1, self.devel_pofile.updatesCount())
        self.assertEquals(2, self.devel_pofile.unreviewedCount())

    def test_TranslationFileData_adapter(self):
        # Test that exporting works correctly with shared and diverged
        # messages.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset,
            translations=["Shared translation"])

        # Get the adapter and extract only English singular and
        # first translation form from all messages.
        translation_file_data = getAdapter(
            self.devel_pofile, ITranslationFileData, 'all_messages')
        exported_messages = [
            (msg.singular_text, msg.translations[0])
            for msg in translation_file_data.messages]
        self.assertEquals(exported_messages,
                          [(self.potmsgset.singular_text,
                            "Shared translation")])

        # When we add a diverged translation, only that is exported.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset,
            translations=["Diverged translation"],
            diverged=True)

        # Get the adapter and extract only English singular and
        # first translation form from all messages.
        translation_file_data = getAdapter(
            self.devel_pofile, ITranslationFileData, 'all_messages')
        exported_messages = [
            (msg.singular_text, msg.translations[0])
            for msg in translation_file_data.messages]
        # Only the diverged translation is exported.
        self.assertEquals(exported_messages,
                          [(self.potmsgset.singular_text,
                            "Diverged translation")])


class TestSharingPOFileCreation(TestCaseWithFactory):
    """Test that POFiles are created in sharing POTemplates."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a product with two series and a sharing POTemplate
        # in different series ('devel' and 'stable').
        super(TestSharingPOFileCreation, self).setUp()
        self.foo = self.factory.makeProduct()
        self.foo_devel = self.factory.makeProductSeries(
            name='devel', product=self.foo)
        self.foo_stable = self.factory.makeProductSeries(
            name='stable', product=self.foo)

    def test_pofile_creation_sharing(self):
        # When a pofile is created in a POTemplate it is also created in
        # all sharing templates.
        # Two POTemplates are sharing if they have the same name ('messages').
        devel_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="messages")
        stable_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_stable, name="messages")

        self.assertEqual(None, stable_potemplate.getPOFileByLang('eo'))
        pofile_devel = devel_potemplate.newPOFile('eo')
        pofile_stable = stable_potemplate.getPOFileByLang('eo')
        self.assertNotEqual(None, pofile_stable)
        self.assertEqual(pofile_devel.language.code,
                         pofile_stable.language.code)

    def test_pofile_creation_sharing_upstream(self):
        # When a pofile is created in a POTemplate of an Ubuntu package
        # it is also created in all shared templates in the upstream project.
        # POTemplate is 'shared' if it has the same name ('messages').
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries = self.factory.makeDistroSeries(distribution=ubuntu)
        ubuntu.translation_focus = distroseries
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        sourcepackage.setPackaging(self.foo_stable, self.factory.makePerson())
        package_potemplate = self.factory.makePOTemplate(
            distroseries=distroseries,
            sourcepackagename=sourcepackage.sourcepackagename,
            name="messages")
        devel_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="messages")
        stable_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_stable, name="messages")

        self.assertEqual(None, devel_potemplate.getPOFileByLang('eo'))
        self.assertEqual(None, stable_potemplate.getPOFileByLang('eo'))

        # Package PO file.
        package_potemplate.newPOFile('eo')

        devel_pofile = devel_potemplate.getPOFileByLang('eo')
        self.assertNotEqual(None, devel_pofile)
        stable_pofile = stable_potemplate.getPOFileByLang('eo')
        self.assertNotEqual(None, stable_pofile)

    def test_pofile_creation_sharing_in_ubuntu(self):
        # When a pofile is created in a POTemplate of a project it is also
        # created in all sharing templates in the linked Ubuntu package.
        # Two POTemplates are sharing if they have the same name ('messages').
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries1 = self.factory.makeDistroSeries(distribution=ubuntu)
        distroseries2 = self.factory.makeDistroSeries(distribution=ubuntu)
        packagename = self.factory.makeSourcePackageName()
        self.factory.makeSourcePackage(packagename, distroseries1)
        self.factory.makeSourcePackage(packagename, distroseries2)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=packagename, distroseries=distroseries1)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=packagename, distroseries=distroseries2)
        owner = self.factory.makePerson()
        self.foo_stable.setPackaging(distroseries1, packagename, owner)
        self.foo_stable.setPackaging(distroseries2, packagename, owner)

        stable_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_stable, name="messages")
        distroseries1_potemplate = self.factory.makePOTemplate(
            distroseries=distroseries1, sourcepackagename=packagename,
            name="messages")
        distroseries2_potemplate = self.factory.makePOTemplate(
            distroseries=distroseries2, sourcepackagename=packagename,
            name="messages")

        self.assertEqual(None, distroseries1_potemplate.getPOFileByLang('eo'))
        self.assertEqual(None, distroseries2_potemplate.getPOFileByLang('eo'))

        # Stable PO file.
        stable_potemplate.newPOFile('eo')

        distroseries1_pofile = distroseries1_potemplate.getPOFileByLang('eo')
        self.assertNotEqual(None, distroseries1_pofile)
        distroseries2_pofile = distroseries2_potemplate.getPOFileByLang('eo')
        self.assertNotEqual(None, distroseries2_pofile)

    def test_pofile_creation_not_sharing(self):
        # When a pofile is created in a POTemplate it is not created in
        # other templates that are not sharing.
        potemplate_devel_1 = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="template-1")
        potemplate_stable_2 = self.factory.makePOTemplate(
            productseries=self.foo_stable, name="template-2")

        self.assertEqual(None, potemplate_devel_1.getPOFileByLang('eo'))
        potemplate_devel_1.newPOFile('eo')
        self.assertEqual(None, potemplate_stable_2.getPOFileByLang('eo'))

    def test_potemplate_creation(self):
        # When a potemplate is created it receives a copy of all pofiles in
        # all sharing potemplates.
        foo_other = self.factory.makeProductSeries(
            name='other', product=self.foo)
        self.factory.makePOTemplate(
            productseries=foo_other, name="messages")
        devel_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="messages")
        # These will automatically be shared across all sharing templates.
        # They will also be created in the 'other' series.
        devel_potemplate.newPOFile('eo')
        devel_potemplate.newPOFile('de')

        stable_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_stable, name="messages")

        self.assertEqual(2, len(list(stable_potemplate.pofiles)))
        self.assertNotEqual(None, stable_potemplate.getPOFileByLang('eo'))
        self.assertNotEqual(None, stable_potemplate.getPOFileByLang('de'))

    def test_pofile_creation_sharing_with_credits(self):
        # When pofiles are created due to sharing, any credits messages
        # in the new pofiles are translated, even if they have different
        # names.
        devel_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="messages")
        stable_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_stable, name="messages")
        devel_credits = self.factory.makePOTMsgSet(
            potemplate=devel_potemplate, singular=u'translator-credits')
        stable_credits = self.factory.makePOTMsgSet(
            potemplate=stable_potemplate, singular=u'translation-credits')

        # Create one language from the devel end, and the other from
        # stable.
        devel_eo = devel_potemplate.newPOFile('eo')
        stable_eo = stable_potemplate.getPOFileByLang('eo')
        stable_is = stable_potemplate.newPOFile('is')
        devel_is = devel_potemplate.getPOFileByLang('is')

        # Even though the devel and stable credits msgids are different,
        # both are translated for both languages.
        for ms, po in [
                (devel_credits, devel_eo),
                (devel_credits, devel_is),
                (stable_credits, stable_eo),
                (stable_credits, stable_is)]:
            self.assertIsNot(
                None,
                ms.getCurrentTranslation(
                    po.potemplate, po.language,
                    po.potemplate.translation_side))


class TestTranslationCredits(TestCaseWithFactory):
    """Test generation of translation credits."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTranslationCredits, self).setUp()
        self.pofile = self.factory.makePOFile('sr')
        self.potemplate = self.pofile.potemplate

        self.potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate)
        self.credits_potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate, singular=u'translator-credits')

    def compose_launchpad_credits_text(self, imported_credits_text):
        return u"%s\n\nLaunchpad Contributions:\n  %s" % (
                imported_credits_text,
                "\n  ".join(["%s %s" % (person.displayname,
                                        canonical_url(person))
                             for person in self.pofile.contributors]))

    def test_prepareTranslationCredits_noop(self):
        # With no contributions, translator credits message is not None,
        # yet it's ignored in prepareTranslationCredits.
        credits = self.credits_potmsgset.getCurrentTranslation(
            self.potemplate, self.pofile.language,
            self.potemplate.translation_side)
        self.assertIsNot(None, credits)
        self.assertIs(
            None,
            self.pofile.prepareTranslationCredits(self.credits_potmsgset))

    def test_prepareTranslationCredits_gnome(self):
        # Preparing translation credits for GNOME-like credits message.
        translator = self.factory.makePerson(
            name=u'the-translator',
            displayname=u'Launchpad Translator')
        self.credits_potmsgset.setCurrentTranslation(
            self.pofile, translator, {0: 'upstream credits'},
            RosettaTranslationOrigin.SCM, share_with_other_side=True)
        self.assertEquals(
            u'upstream credits\n\n'
            'Launchpad Contributions:\n'
            '  Launchpad Translator http://launchpad.dev/~the-translator',
            self.pofile.prepareTranslationCredits(self.credits_potmsgset))

    def test_prepareTranslationCredits_gnome_extending(self):
        # This test ensures that continuous updates to the translation credits
        # don't result in duplicate entries.
        # Only the 'translator-credits' message is covered right now.
        person = self.factory.makePerson()

        imported_credits_text = u"Imported Contributor <name@project.org>"

        # Import a translation credits message to 'translator-credits'.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.credits_potmsgset,
            translations=[imported_credits_text],
            current_other=True)

        # `person` updates the translation using Launchpad.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translator=person)

        # The first translation credits export.
        credits_text = self.pofile.prepareTranslationCredits(
            self.credits_potmsgset)
        self.assertEquals(
            self.compose_launchpad_credits_text(imported_credits_text),
            credits_text)

        # Now, re-import this generated message.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.credits_potmsgset,
            translations=[credits_text],
            current_other=True)

        credits_text = self.pofile.prepareTranslationCredits(
            self.credits_potmsgset)
        self.assertEquals(
            self.compose_launchpad_credits_text(imported_credits_text),
            credits_text)

    def test_prepareTranslationCredits_old_kde_names(self):
        # Preparing translation credits for old (pre-KDE4) KDE-like
        # credits message for contributor names.
        translator = self.factory.makePerson(
            displayname=u'Launchpad Translator')
        kde_names_potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate,
            singular=u'_: NAME OF TRANSLATORS\nYour names')
        kde_names_potmsgset.setCurrentTranslation(
            self.pofile, translator,
            {0: 'Upstream credits'},
            RosettaTranslationOrigin.SCM, share_with_other_side=True)
        self.assertEquals(
            u'Upstream credits, ,Launchpad Contributions:,'
            'Launchpad Translator',
            self.pofile.prepareTranslationCredits(kde_names_potmsgset))

    def test_prepareTranslationCredits_old_kde_emails(self):
        # Preparing translation credits for old (pre-KDE4) KDE-like
        # credits message for contributor emails.
        translator = self.factory.makePerson(
            email=u'translator@launchpad')
        kde_emails_potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate,
            singular=u'_: EMAIL OF TRANSLATORS\nYour emails')
        kde_emails_potmsgset.setCurrentTranslation(
            self.pofile, translator,
            {0: 'translator@upstream'},
            RosettaTranslationOrigin.SCM, share_with_other_side=True)
        self.assertEquals(
            u'translator@upstream,,,translator@launchpad',
            self.pofile.prepareTranslationCredits(kde_emails_potmsgset))

    def test_prepareTranslationCredits_kde_names(self):
        # Preparing translation credits for new (KDE4 and later)
        # KDE-like credits message for contributor names.
        translator = self.factory.makePerson(
            displayname=u'Launchpad Translator')
        kde_names_potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate,
            context=u'NAME OF TRANSLATORS',
            singular=u'Your names')
        kde_names_potmsgset.setCurrentTranslation(
            self.pofile, translator,
            {0: 'Upstream credits'},
            RosettaTranslationOrigin.SCM, share_with_other_side=True)
        self.assertEquals(
            u'Upstream credits, ,Launchpad Contributions:,'
            'Launchpad Translator',
            self.pofile.prepareTranslationCredits(kde_names_potmsgset))

    def test_prepareTranslationCredits_kde_emails(self):
        # Preparing translation credits for new (KDE4 and later)
        # KDE-like credits message for contributor emails.
        translator = self.factory.makePerson(
            email=u'translator@launchpad')
        kde_emails_potmsgset = self.factory.makePOTMsgSet(
            potemplate=self.potemplate,
            context=u'EMAIL OF TRANSLATORS',
            singular=u'Your emails')
        kde_emails_potmsgset.setCurrentTranslation(
            self.pofile, translator,
            {0: 'translator@upstream'},
            RosettaTranslationOrigin.SCM, share_with_other_side=True)
        self.assertEquals(
            u'translator@upstream,,,translator@launchpad',
            self.pofile.prepareTranslationCredits(kde_emails_potmsgset))


class TestTranslationPOFilePOTMsgSetOrdering(TestCaseWithFactory):
    """Test ordering of POTMsgSets as returned by PO file methods."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a product with two series and a sharing POTemplate
        # in different series ('devel' and 'stable').
        super(TestTranslationPOFilePOTMsgSetOrdering, self).setUp()
        self.foo = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        self.foo_devel = self.factory.makeProductSeries(
            name='devel', product=self.foo)
        self.foo_stable = self.factory.makeProductSeries(
            name='stable', product=self.foo)

        # Two POTemplates are sharing if they have the same name ('messages').
        self.devel_potemplate = self.factory.makePOTemplate(
            productseries=self.foo_devel, name="messages")
        self.stable_potemplate = self.factory.makePOTemplate(self.foo_stable,
                                                             name="messages")

        # We'll use two PO files, one for each series.
        self.devel_pofile = self.factory.makePOFile(
            'sr', self.devel_potemplate)
        self.stable_pofile = self.factory.makePOFile(
            'sr', self.stable_potemplate)

        # Create two POTMsgSets that can be used to test in what order
        # are they returned.  Add them only to devel_potemplate sequentially.
        self.potmsgset1 = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=1)
        self.potmsgset2 = self.factory.makePOTMsgSet(
            self.devel_potemplate, sequence=2)

    def test_getPOTMsgSetTranslated_ordering(self):
        # Translate both POTMsgSets in devel_pofile, so
        # they are returned with getPOTMsgSetTranslated() call.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset1,
            translations=["Shared translation"])
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset2,
            translations=["Another shared translation"])

        translated_potmsgsets = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], translated_potmsgsets)

        # Insert these two POTMsgSets into self.stable_potemplate in reverse
        # order.
        self.potmsgset2.setSequence(self.stable_potemplate, 1)
        self.potmsgset1.setSequence(self.stable_potemplate, 2)

        # And they are returned in the new order as desired.
        translated_potmsgsets = list(
            self.stable_pofile.getPOTMsgSetTranslated())
        self.assertEquals(
            [self.potmsgset2, self.potmsgset1], translated_potmsgsets)

        # Order is unchanged for the previous template.
        translated_potmsgsets = list(
            self.devel_pofile.getPOTMsgSetTranslated())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], translated_potmsgsets)

    def test_getPOTMsgSetUntranslated_ordering(self):
        # Both POTMsgSets in devel_pofile are untranslated.
        untranslated_potmsgsets = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], untranslated_potmsgsets)

        # Insert these two POTMsgSets into self.stable_potemplate in reverse
        # order.
        self.potmsgset2.setSequence(self.stable_potemplate, 1)
        self.potmsgset1.setSequence(self.stable_potemplate, 2)

        # And they are returned in the new order as desired.
        untranslated_potmsgsets = list(
            self.stable_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(
            [self.potmsgset2, self.potmsgset1], untranslated_potmsgsets)

        # Order is unchanged for the previous template.
        untranslated_potmsgsets = list(
            self.devel_pofile.getPOTMsgSetUntranslated())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], untranslated_potmsgsets)

    def test_getPOTMsgSetDifferentTranslations_ordering(self):
        # Suggest a translation on both POTMsgSets in devel_pofile,
        # so they are returned with getPOTMsgSetDifferentTranslations() call.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset1,
            translations=["Both sides"],
            current_other=True)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset1,
            translations=["This side"])
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset2,
            translations=["Both sides 2"],
            current_other=True)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.devel_pofile,
            potmsgset=self.potmsgset2,
            translations=["This side 2"])

        potmsgsets = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], potmsgsets)

        # Insert these two POTMsgSets into self.stable_potemplate in reverse
        # order.
        self.potmsgset2.setSequence(self.stable_potemplate, 1)
        self.potmsgset1.setSequence(self.stable_potemplate, 2)

        # And they are returned in the new order as desired.
        potmsgsets = list(
            self.stable_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(
            [self.potmsgset2, self.potmsgset1], potmsgsets)

        # Order is unchanged for the previous template.
        potmsgsets = list(
            self.devel_pofile.getPOTMsgSetDifferentTranslations())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], potmsgsets)

    def test_getPOTMsgSets_ordering(self):
        # Both POTMsgSets in devel_potemplate are untranslated.
        potmsgsets = list(
            self.devel_potemplate.getPOTMsgSets())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], potmsgsets)

        # Insert these two POTMsgSets into self.stable_potemplate in reverse
        # order.
        self.potmsgset2.setSequence(self.stable_potemplate, 1)
        self.potmsgset1.setSequence(self.stable_potemplate, 2)

        # And they are returned in the new order as desired.
        potmsgsets = list(
            self.stable_potemplate.getPOTMsgSets())
        self.assertEquals(
            [self.potmsgset2, self.potmsgset1], potmsgsets)

        # Order is unchanged for the previous template.
        potmsgsets = list(
            self.devel_potemplate.getPOTMsgSets())
        self.assertEquals(
            [self.potmsgset1, self.potmsgset2], potmsgsets)


class TestPOFileSet(TestCaseWithFactory):
    """Test PO file set methods."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a POFileSet to work with.
        super(TestPOFileSet, self).setUp()
        self.pofileset = getUtility(IPOFileSet)

    def test_POFileSet_getPOFilesTouchedSince_none(self):
        # Make sure getPOFilesTouchedSince returns nothing
        # when there are no touched PO files.
        now = datetime.now(pytz.UTC)
        pofiles = self.pofileset.getPOFilesTouchedSince(now)
        self.assertContentEqual([], pofiles)

        week_ago = now - timedelta(7)
        pofiles = self.pofileset.getPOFilesTouchedSince(week_ago)
        self.assertContentEqual([], pofiles)

        # Even when a POFile is touched, but earlier than
        # what we are looking for, nothing is returned.
        pofile = self.factory.makePOFile('sr')
        pofile.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(now)
        self.assertContentEqual([], pofiles)

    def test_POFileSet_getPOFilesTouchedSince_unshared(self):
        # Make sure actual touched POFiles are returned by
        # getPOFilesTouchedSince.
        now = datetime.now(pytz.UTC)
        yesterday = now - timedelta(1)

        new_pofile = self.factory.makePOFile('sr')
        new_pofile.date_changed = now
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([new_pofile], pofiles)

        # An older file means is not returned.
        week_ago = now - timedelta(7)
        old_pofile = self.factory.makePOFile('sr')
        old_pofile.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([new_pofile], pofiles)

        # Unless we extend the time period we ask for.
        pofiles = self.pofileset.getPOFilesTouchedSince(week_ago)
        self.assertContentEqual([new_pofile, old_pofile], pofiles)

    def test_POFileSet_getPOFilesTouchedSince_shared_in_product(self):
        # Make sure actual touched POFiles and POFiles that are sharing
        # with them in the same product are all returned by
        # getPOFilesTouchedSince.

        # We create a product with two series, and attach
        # a POTemplate and Serbian POFile to each, making
        # sure they share translations (potemplates have the same name).
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        series1 = self.factory.makeProductSeries(product=product,
                                                 name='one')
        series2 = self.factory.makeProductSeries(product=product,
                                                 name='two')
        potemplate1 = self.factory.makePOTemplate(name='shared',
                                                  productseries=series1)
        pofile1 = self.factory.makePOFile('sr', potemplate=potemplate1)
        potemplate2 = self.factory.makePOTemplate(name='shared',
                                                  productseries=series2)
        pofile2 = potemplate2.getPOFileByLang('sr')

        now = datetime.now(pytz.UTC)
        yesterday = now - timedelta(1)
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

        # Even if one of the sharing POFiles is older, it's still returned.
        week_ago = now - timedelta(7)
        pofile2.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

        # A POFile in a different language is not returned.
        pofile3 = self.factory.makePOFile('de', potemplate=potemplate2)
        pofile3.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

    def test_POFileSet_getPOFilesTouchedSince_smaller_ids(self):
        # Make sure that all relevant POFiles are returned,
        # even the sharing ones with smaller IDs.
        # This is a test for bug #414832 which caused sharing POFiles
        # of the touched POFile not to be returned if they had
        # IDs smaller than the touched POFile.
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        series1 = self.factory.makeProductSeries(product=product,
                                                 name='one')
        series2 = self.factory.makeProductSeries(product=product,
                                                 name='two')
        potemplate1 = self.factory.makePOTemplate(name='shared',
                                                  productseries=series1)
        pofile1 = self.factory.makePOFile('sr', potemplate=potemplate1)
        potemplate2 = self.factory.makePOTemplate(name='shared',
                                                  productseries=series2)
        pofile2 = potemplate2.getPOFileByLang('sr')
        now = datetime.now(pytz.UTC)
        yesterday = now - timedelta(1)
        week_ago = now - timedelta(7)
        pofile1.date_changed = week_ago

        # Let's make sure the condition from the bug holds,
        # since pofile2 is created implicitely with the makePOTemplate call.
        self.assertTrue(pofile1.id < pofile2.id)
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

    def test_POFileSet_getPOFilesTouchedSince_shared_in_distribution(self):
        # Make sure actual touched POFiles and POFiles that are sharing
        # with them in the same distribution/sourcepackage are all returned
        # by getPOFilesTouchedSince.

        # We create a distribution with two series with the same
        # sourcepackage in both, and attach a POTemplate and Serbian
        # POFile to each, making sure they share translations
        # (potemplates have the same name).
        distro = self.factory.makeDistribution()
        distro.translations_usage = ServiceUsage.LAUNCHPAD
        series1 = self.factory.makeDistroSeries(
            distribution=distro, name='one')
        sourcepackagename = self.factory.makeSourcePackageName()
        potemplate1 = self.factory.makePOTemplate(
            name='shared', distroseries=series1,
            sourcepackagename=sourcepackagename)
        pofile1 = self.factory.makePOFile('sr', potemplate=potemplate1)

        series2 = self.factory.makeDistroSeries(
            distribution=distro, name='two')
        potemplate2 = self.factory.makePOTemplate(
            name='shared', distroseries=series2,
            sourcepackagename=sourcepackagename)
        pofile2 = potemplate2.getPOFileByLang('sr')

        # Now the test actually starts.
        now = datetime.now(pytz.UTC)
        yesterday = now - timedelta(1)
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

        # Even if one of the sharing POFiles is older, it's still returned.
        week_ago = now - timedelta(7)
        pofile2.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

        # A POFile in a different language is not returned.
        pofile3 = self.factory.makePOFile('de', potemplate=potemplate2)
        pofile3.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1, pofile2], pofiles)

    def test_POFileSet_getPOFilesTouchedSince_external_pofiles(self):
        # Make sure POFiles which are in different products
        # are not returned even though they have the same potemplate name.
        series1 = self.factory.makeProductSeries(name='one')
        series1.product.translations_usage = ServiceUsage.LAUNCHPAD
        series2 = self.factory.makeProductSeries(name='two')
        series1.product.translations_usage = ServiceUsage.LAUNCHPAD
        self.assertNotEqual(series1.product, series2.product)

        potemplate1 = self.factory.makePOTemplate(name='shared',
                                                  productseries=series1)
        pofile1 = self.factory.makePOFile('sr', potemplate=potemplate1)

        potemplate2 = self.factory.makePOTemplate(name='shared',
                                                  productseries=series2)
        pofile2 = self.factory.makePOFile('sr', potemplate=potemplate2)

        # Now the test actually starts.
        now = datetime.now(pytz.UTC)
        yesterday = now - timedelta(1)
        week_ago = now - timedelta(7)

        # Second POFile has been modified earlier than yesterday,
        # and is attached to a different product, even if the template
        # name is the same.  It's not returned.
        pofile2.date_changed = week_ago
        pofiles = self.pofileset.getPOFilesTouchedSince(yesterday)
        self.assertContentEqual([pofile1], pofiles)

    def test_getPOFilesWithTranslationCredits(self):
        # Initially, we only get data from the sampledata.
        sampledata_pofiles = list(
            self.pofileset.getPOFilesWithTranslationCredits())
        total = len(sampledata_pofiles)
        self.assertEquals(3, total)

        def list_of_tuples_into_list(list_of_tuples):
            return [item[0] for item in list_of_tuples]

        # All POFiles with translation credits messages are
        # returned along with relevant POTMsgSets.
        potemplate1 = self.factory.makePOTemplate()
        self.factory.makePOTMsgSet(
            potemplate1, singular=u'translator-credits')

        sr_pofile = self.factory.makePOFile('sr', potemplate=potemplate1)
        self.assertIn(sr_pofile,
                      list_of_tuples_into_list(
                          self.pofileset.getPOFilesWithTranslationCredits()))
        self.assertEquals(
            total + 1,
            self.pofileset.getPOFilesWithTranslationCredits().count())

        # If there's another POFile on this template, it's returned as well.
        de_pofile = self.factory.makePOFile('de', potemplate=potemplate1)
        self.assertIn(de_pofile,
                      list_of_tuples_into_list(
                          self.pofileset.getPOFilesWithTranslationCredits()))

        # If another POTemplate has a translation credits message, it's
        # returned as well.
        potemplate2 = self.factory.makePOTemplate()
        self.factory.makePOTMsgSet(
            potemplate2, singular=u'Your names',
            context=u'NAME OF TRANSLATORS')
        sr_kde_pofile = self.factory.makePOFile('sr', potemplate=potemplate2)
        self.assertIn(sr_kde_pofile,
                      list_of_tuples_into_list(
                          self.pofileset.getPOFilesWithTranslationCredits()))

        # And let's confirm that the full listing contains all of the
        # above.
        all_pofiles = list_of_tuples_into_list(sampledata_pofiles)
        all_pofiles.extend([sr_pofile, de_pofile, sr_kde_pofile])
        self.assertContentEqual(
            all_pofiles,
            list_of_tuples_into_list(
                self.pofileset.getPOFilesWithTranslationCredits()))

    def test_getPOFilesWithTranslationCredits_untranslated(self):
        # With "untranslated=True," getPOFilesWithTranslationCredits
        # looks for POFiles whose translation credits messages are
        # untranslated.

        # The sample data may contain some matching POFiles, but we'll
        # ignore those.
        initial_matches = set(
            self.pofileset.getPOFilesWithTranslationCredits(
                untranslated=True))

        potemplate = self.factory.makePOTemplate()
        credits_potmsgset = self.factory.makePOTMsgSet(
            potemplate, singular=u'translator-credits')
        pofile = self.factory.makePOFile(potemplate=potemplate)

        credits_translation = credits_potmsgset.getCurrentTranslation(
            potemplate, pofile.language, potemplate.translation_side)

        # Clearing is_current_upstream will make this an "untranslated"
        # credits message.
        credits_translation.is_current_upstream = False

        self.assertEqual(
            initial_matches.union([(pofile, credits_potmsgset)]),
            set(self.pofileset.getPOFilesWithTranslationCredits(
                untranslated=True)))

    def test_getPOFilesByPathAndOrigin_path_mismatch(self):
        # getPOFilesByPathAndOrigin matches on POFile path.
        template = self.factory.makePOTemplate()
        template.newPOFile('ta')

        not_found = self.pofileset.getPOFilesByPathAndOrigin(
            'tu.po', distroseries=template.distroseries,
            sourcepackagename=template.sourcepackagename,
            productseries=template.productseries)

        self.assertContentEqual([], not_found)

    def test_getPOFilesByPathAndOrigin_productseries_none(self):
        # getPOFilesByPathAndOrigin returns an empty result set if a
        # ProductSeries search matches no POFiles.
        productseries = self.factory.makeProductSeries()

        # Look for zh.po, which does not exist.
        not_found = self.pofileset.getPOFilesByPathAndOrigin(
            'zh.po', productseries=productseries)

        self.assertContentEqual([], not_found)

    def test_getPOFilesByPathAndOrigin_productseries(self):
        # getPOFilesByPathAndOrigin finds a POFile for a productseries.
        productseries = self.factory.makeProductSeries()
        template = self.factory.makePOTemplate(productseries=productseries)
        pofile = template.newPOFile('nl')
        removeSecurityProxy(pofile).path = 'nl.po'

        found = self.pofileset.getPOFilesByPathAndOrigin(
            'nl.po', productseries=productseries)

        self.assertContentEqual([pofile], found)

    def test_getPOFilesByPathAndOrigin_sourcepackage_none(self):
        # getPOFilesByPathAndOrigin returns an empty result set if a
        # source-package search matches no POFiles.
        package = self.factory.makeSourcePackage()

        # Look for no.po, which does not exist.
        not_found = self.pofileset.getPOFilesByPathAndOrigin(
            'no.po', distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

        self.assertContentEqual([], not_found)

    def test_getPOFilesByPathAndOrigin_sourcepackage(self):
        # getPOFilesByPathAndOrigin finds a POFile for a source package
        # name.
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        pofile = template.newPOFile('kk')
        removeSecurityProxy(pofile).path = 'kk.po'

        found = self.pofileset.getPOFilesByPathAndOrigin(
            'kk.po', distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)

        self.assertContentEqual([pofile], found)

    def test_getPOFilesByPathAndOrigin_from_sourcepackage_none(self):
        # getPOFilesByPathAndOrigin returns an empty result set if a
        # from-source-package search matches no POFiles.
        upload_package = self.factory.makeSourcePackage()

        # Look for la.po, which does not exist.
        not_found = self.pofileset.getPOFilesByPathAndOrigin(
            'la.po', distroseries=upload_package.distroseries,
            sourcepackagename=upload_package.sourcepackagename)

        self.assertContentEqual([], not_found)

    def test_getPOFilesByPathAndOrigin_from_sourcepackage(self):
        # getPOFilesByPathAndOrigin finds a POFile for the source
        # package it was uploaded for (which may not be the same as the
        # source package it's actually in).
        upload_package = self.factory.makeSourcePackage()
        distroseries = upload_package.distroseries
        target_package = self.factory.makeSourcePackage(
            distroseries=distroseries)
        template = self.factory.makePOTemplate(
            distroseries=distroseries,
            sourcepackagename=target_package.sourcepackagename)
        removeSecurityProxy(template).from_sourcepackagename = (
            upload_package.sourcepackagename)
        pofile = template.newPOFile('ka')
        removeSecurityProxy(pofile).path = 'ka.po'
        removeSecurityProxy(pofile).from_sourcepackagename = (
            upload_package.sourcepackagename)

        found = self.pofileset.getPOFilesByPathAndOrigin(
            'ka.po', distroseries=distroseries,
            sourcepackagename=upload_package.sourcepackagename)

        self.assertContentEqual([pofile], found)

    def test_getPOFilesByPathAndOrigin_includes_obsolete_templates(self):
        pofile = self.factory.makePOFile()
        template = pofile.potemplate
        template.iscurrent = False
        self.assertContentEqual(
            [pofile],
            self.pofileset.getPOFilesByPathAndOrigin(
                pofile.path, productseries=template.productseries))

    def test_getPOFilesByPathAndOrigin_can_ignore_obsolete_templates(self):
        pofile = self.factory.makePOFile()
        template = pofile.potemplate
        template.iscurrent = False
        self.assertContentEqual(
            [],
            self.pofileset.getPOFilesByPathAndOrigin(
                pofile.path, productseries=template.productseries,
                ignore_obsolete=True))


class TestPOFileStatistics(TestCaseWithFactory):
    """Test PO files statistics calculation."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a POFile to calculate statistics on.
        super(TestPOFileStatistics, self).setUp()
        self.pofile = self.factory.makePOFile('sr')
        self.potemplate = self.pofile.potemplate

        # Create a single POTMsgSet that is used across all tests,
        # and add it to only one of the POTemplates.
        self.potmsgset = self.factory.makePOTMsgSet(self.potemplate)

    def test_POFile_updateStatistics_currentCount(self):
        # Make sure count of translations which are active both
        # in import and in Launchpad is correct.
        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.currentCount(), 0)

        # Adding an imported translation increases currentCount().
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["Imported current"],
            current_other=True)
        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.currentCount(), 1)

        # Adding a suggestion (i.e. unused translation)
        # will not change the current count when there's
        # already an imported message.
        self.factory.makeSuggestion(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["A suggestion"])
        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.currentCount(), 1)

    def test_POFile_updateStatistics_newCount(self):
        # Make sure count of translations which are provided
        # only in Launchpad (and not in imports) is correct.
        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.newCount(), 0)

        # Adding a current translation for an untranslated
        # message increases the count of new translations in LP.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["Current"])
        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.newCount(), 1)

    def test_POFile_updateStatistics_newCount_reimporting(self):
        # If we get an 'imported' translation for what
        # we already have as 'new', it's not considered 'new'
        # anymore since it has been synced.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["Current"])
        # Reimport it but with is_current_ubuntu=True.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["Current"],
            current_other=True)

        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.newCount(), 0)

    def test_POFile_updateStatistics_newCount_changed(self):
        # If we change an 'imported' translation through
        # Launchpad, it's still not considered 'new',
        # but an 'update' instead.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["Imported"],
            current_other=True)
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile,
            potmsgset=self.potmsgset,
            translations=["Changed"])
        self.pofile.updateStatistics()
        self.assertEquals(self.pofile.newCount(), 0)
        self.assertEquals(self.pofile.updatesCount(), 1)

    def test_empty_messages_count_as_untranslated(self):
        # A message with all its msgstr* set to None counts as if
        # there's no message at all.  It doesn't show up in any of the
        # counts except as untranslated.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=self.potmsgset, translations=[])
        self.pofile.updateStatistics()
        self.assertEqual(0, self.pofile.translatedCount())
        self.assertEqual(1, self.pofile.untranslatedCount())
        self.assertEqual(0, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())

    def test_partial_translations_count_as_untranslated(self):
        # A translation requiring plural forms is considered to be
        # untranslated if at least one plural translation required
        # for the given language is missing.
        plural_potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular='singular-en', plural='plural-en')
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-singular', 'sr-plural-1'])
        self.pofile.updateStatistics()
        self.assertEqual(0, self.pofile.translatedCount())
        self.assertEqual(2, self.pofile.untranslatedCount())
        self.assertEqual(0, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())

    def test_complete_translations_count_as_translated(self):
        # A translation requiring plural forms is considered to be
        # translated if all variants are translated.
        plural_potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular='singular-en', plural='plural-en')
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-singular', 'sr-plural-1', 'sr-plural-2'])
        self.pofile.updateStatistics()
        self.assertEqual(1, self.pofile.translatedCount())
        self.assertEqual(1, self.pofile.untranslatedCount())
        self.assertEqual(1, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())

    def test_empty_messages_on_this_side_count_as_untranslated(self):
        # A POTMsgSet whose current TranslationMessage on this side is
        # empty is counted only as untranslated, regardless of any
        # translations it may have on the other side.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=self.potmsgset, translations=[])
        other_message = self.factory.makeSuggestion(
            pofile=self.pofile, potmsgset=self.potmsgset)
        other_message.is_current_ubuntu = True
        self.pofile.updateStatistics()
        self.assertEqual(0, self.pofile.translatedCount())
        self.assertEqual(1, self.pofile.untranslatedCount())
        self.assertEqual(0, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())

    def test_partial_messages_on_this_side_count_as_untranslated(self):
        # A POTMsgSet whose current TranslationMessage on this side is
        # partially translated is considered to be untranslated, regardless
        # of any translations it may have on the other side.
        plural_potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular='singular-en', plural='plural-en')
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-singular', 'sr-plural-1'])
        other_message = self.factory.makeSuggestion(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-ubuntu', 'sr-ubuntu-2', 'sr-ubuntu-3'])
        other_message.is_current_ubuntu = True
        self.pofile.updateStatistics()
        self.assertEqual(0, self.pofile.translatedCount())
        self.assertEqual(2, self.pofile.untranslatedCount())
        self.assertEqual(0, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())

    def test_empty_messages_on_other_side_count_as_untranslated(self):
        # A POTMsgSet that's translated on this side but has an empty
        # translation on the other side counts as translated on this
        # side, but not equal between both sides (currentCount) or
        # translated differently between the two sides (updatesCount).
        # Instead, it's counted as translated on this side but not on
        # the other (newCount).
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=self.potmsgset)
        other_message = self.factory.makeSuggestion(
            pofile=self.pofile, potmsgset=self.potmsgset, translations=[])
        other_message.is_current_ubuntu = True
        self.pofile.updateStatistics()
        self.assertEqual(1, self.pofile.translatedCount())
        self.assertEqual(0, self.pofile.untranslatedCount())
        self.assertEqual(1, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())
        self.assertEqual(0, self.pofile.currentCount())

    def test_partial_messages_on_other_side_count_as_untranslated(self):
        # A POTMsgSet that's translated on this side and has a different
        # partial translation on the other side counts as translated on
        # this side, but not equal between both sides (currentCount) or
        # translated differently between the two sides (updatesCount).
        # Instead, it's counted as translated on this side but not on
        # the other (newCount).
        plural_potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular='singular-en', plural='plural-en')
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-singular', 'sr-plural1', 'sr-plural2'])
        other_message = self.factory.makeSuggestion(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-ubuntu'])
        other_message.is_current_ubuntu = True
        self.pofile.updateStatistics()
        self.assertEqual(1, self.pofile.translatedCount())
        self.assertEqual(1, self.pofile.untranslatedCount())
        self.assertEqual(1, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())
        self.assertEqual(0, self.pofile.currentCount())

    def test_tracking_empty_messages_count_as_untranslated(self):
        # An empty TranslationMessage that's current on both sides
        # counts as untranslated.
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=self.potmsgset, translations=[],
            current_other=True)
        self.pofile.updateStatistics()
        self.assertEqual(0, self.pofile.translatedCount())
        self.assertEqual(1, self.pofile.untranslatedCount())
        self.assertEqual(0, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())
        self.assertEqual(0, self.pofile.currentCount())

    def test_tracking_partial_translations_count_as_untranslated(self):
        # A partial Translations that's current on both sides
        # counts as untranslated.
        plural_potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular='singular-en', plural='plural-en')
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=plural_potmsgset,
            translations=['sr-singular', 'sr-plural1'], current_other=True)
        self.pofile.updateStatistics()
        self.assertEqual(0, self.pofile.translatedCount())
        self.assertEqual(2, self.pofile.untranslatedCount())
        self.assertEqual(0, self.pofile.newCount())
        self.assertEqual(0, self.pofile.updatesCount())
        self.assertEqual(0, self.pofile.currentCount())

    def makeDivergedTranslationForOtherTarget(self, for_sourcepackage):
        """Create a translation message that is diverged for another target.
        """
        if for_sourcepackage:
            ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
            distroseries = self.factory.makeDistroSeries(distribution=ubuntu)
            sourcepackage = self.factory.makeSourcePackage(
                distroseries=distroseries)
            sourcepackagename = sourcepackage.sourcepackagename
        else:
            distroseries = None
            sourcepackagename = None
        other_potemplate = self.factory.makePOTemplate(
            distroseries=distroseries, sourcepackagename=sourcepackagename)
        other_pofile = self.factory.makePOFile(
            language_code=self.pofile.language.code,
            potemplate=other_potemplate)
        self.potmsgset.setSequence(
            other_potemplate, self.factory.getUniqueInteger())
        self.factory.makeCurrentTranslationMessage(
            pofile=other_pofile, potmsgset=self.potmsgset, diverged=True)

    def test_POFile_updateStatistics_diverged_message_this_side(self):
        # Translations that are diverged for a given target on this side
        # do not appear in the statistical data for another target.
        self.makeDivergedTranslationForOtherTarget(for_sourcepackage=False)
        self.pofile.updateStatistics()
        self.assertEqual(self.pofile.rosettaCount(), 0)
        self.assertEqual(self.pofile.unreviewedCount(), 0)

    def test_POFile_updateStatistics_diverged_message_other_side(self):
        # Translations that are diverged for a given target on the other side
        # do not appear in the statistical data for another target.
        self.makeDivergedTranslationForOtherTarget(for_sourcepackage=True)
        self.pofile.updateStatistics()
        self.assertEqual(self.pofile.rosettaCount(), 0)
        self.assertEqual(self.pofile.unreviewedCount(), 0)


class TestPOFile(TestCaseWithFactory):
    """Test PO file methods."""

    layer = ZopelessDatabaseLayer

    # The sequence number 0 is put at the beginning of the data to verify that
    # it really gets sorted to the end.
    TEST_MESSAGES = [
        {'msgid':'computer', 'string':'komputilo', 'sequence':0},
        {'msgid':'mouse', 'string':'muso', 'sequence':0},
        {'msgid':'Good morning', 'string':'Bonan matenon', 'sequence':2},
        {'msgid':'Thank you', 'string':'Dankon', 'sequence':1},
        ]
    EXPECTED_SEQUENCE = [1, 2, 0, 0]

    def setUp(self):
        # Create a POFile to calculate statistics on.
        super(TestPOFile, self).setUp()
        self.pofile = self.factory.makePOFile('eo')
        self.potemplate = self.pofile.potemplate

    def _createMessageSet(self, testmsg):
        # Create a message set from the test data.
        potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, testmsg['msgid'], sequence=testmsg['sequence'])
        self.factory.makeCurrentTranslationMessage(
            self.pofile, potmsgset=potmsgset, translator=self.pofile.owner,
            translations={0: testmsg['string'], }, current_other=True)

    def test_getTranslationRows_sequence(self):
        # Test for correct sorting of obsolete messages (where sequence=0).
        [self._createMessageSet(msg) for msg in self.TEST_MESSAGES]
        for rownum, row in enumerate(
            self.pofile.getTranslationRows()):
            self.failUnlessEqual(
                row.sequence, self.EXPECTED_SEQUENCE[rownum],
                "getTranslationRows does not sort obsolete messages "
                "(sequence=0) to the end of the file.")

    def test_getTranslationRows_obsolete_upstream(self):
        # getTranslationRows includes translations marked as current
        # that are for obsolete messages.
        potmsgset = self.factory.makePOTMsgSet(self.potemplate, sequence=0)
        text = self.factory.getUniqueString()
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=potmsgset, translations=[text])

        rows = list(self.pofile.getTranslationRows())
        self.assertEqual(1, len(rows))
        vpoexport = rows[0]
        self.assertEqual(self.pofile, vpoexport.pofile)
        self.assertEqual(potmsgset, vpoexport.potmsgset)
        self.assertEqual(text, vpoexport.translation0)

        # The message is included, but is still marked as obsolete.
        self.assertEqual(0, vpoexport.sequence)

    def test_getTranslationRows_obsolete_ubuntu(self):
        # getTranslationRows handles obsolete messages for Ubuntu
        # POFiles just like it does for upstream POFiles.
        package = self.factory.makeSourcePackage()
        self.potemplate = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        self.pofile = self.factory.makePOFile(potemplate=self.potemplate)
        potmsgset = self.factory.makePOTMsgSet(self.potemplate, sequence=0)
        text = self.factory.getUniqueString()
        self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile, potmsgset=potmsgset, translations=[text])

        rows = list(self.pofile.getTranslationRows())
        self.assertEqual(1, len(rows))
        vpoexport = rows[0]
        self.assertEqual(self.pofile, vpoexport.pofile)
        self.assertEqual(potmsgset, vpoexport.potmsgset)
        self.assertEqual(text, vpoexport.translation0)

        # The message is included, but is still marked as obsolete.
        self.assertEqual(0, vpoexport.sequence)

    def test_markChanged_sets_date(self):
        timestamp = datetime.now(pytz.UTC) - timedelta(days=14)
        self.pofile.markChanged(timestamp=timestamp)
        self.assertEqual(timestamp, self.pofile.date_changed)

    def test_markChanged_defaults_to_now(self):
        self.pofile.date_changed = datetime.now(pytz.UTC) - timedelta(days=99)
        self.pofile.markChanged()
        self.assertSqlAttributeEqualsDate(
            self.pofile, 'date_changed', UTC_NOW)

    def test_markChanged_leaves_lasttranslator_unchanged(self):
        old_lasttranslator = self.pofile.lasttranslator
        self.pofile.markChanged()
        self.assertEqual(old_lasttranslator, self.pofile.lasttranslator)

    def test_markChanged_sets_lasttranslator(self):
        translator = self.factory.makePerson()
        self.pofile.markChanged(translator=translator)
        self.assertEqual(translator, self.pofile.lasttranslator)

    def test_owner_has_no_privileges(self):
        # Being a POFile's owner does not imply edit privileges.
        creator = self.factory.makePerson()
        removeSecurityProxy(self.pofile).owner = creator
        naked_product = removeSecurityProxy(
            self.potemplate.productseries.product)
        naked_product.translationpermission = TranslationPermission.RESTRICTED

        self.assertFalse(self.pofile.canEditTranslations(creator))

    def test_hasPluralFormInformation_bluffs_if_irrelevant(self):
        # If the template has no messages that use plural forms, the
        # POFile has all the relevant plural-form information regardless
        # of whether we know the plural forms for the language.
        language = self.factory.makeLanguage()
        pofile, potmsgset = self.factory.makePOFileAndPOTMsgSet(
            language.code, with_plural=False)
        self.assertTrue(pofile.hasPluralFormInformation())

    def test_hasPluralFormInformation_admits_defeat(self):
        # If there are messages with plurals, hasPluralFormInformation
        # needs the plural-form information for the language.
        language = self.factory.makeLanguage()
        pofile, potmsgset = self.factory.makePOFileAndPOTMsgSet(
            language.code, with_plural=True)
        self.assertFalse(pofile.hasPluralFormInformation())

    def test_hasPluralFormInformation_uses_language_info(self):
        # hasPluralFormInformation returns True if plural forms
        # information is available for the language.
        language = self.factory.makeLanguage(pluralforms=5)
        pofile, potmsgset = self.factory.makePOFileAndPOTMsgSet(
            language.code, with_plural=True)
        self.assertTrue(pofile.hasPluralFormInformation())

    def test_prepare_pomessage_error_message(self):
        # The method returns subject, template_mail, and errorsdetails
        # to make an email message about errors.
        errors = []
        errors.append({
            'potmsgset': self.factory.makePOTMsgSet(
                potemplate=self.pofile.potemplate, sequence=1),
            'pomessage': 'purrs',
            'error-message': 'claws error',
            })
        errors.append({
            'potmsgset': self.factory.makePOTMsgSet(
                potemplate=self.pofile.potemplate, sequence=2),
            'pomessage': 'plays',
            'error-message': 'string error',
            })
        replacements = {'numberofmessages': 5}
        pofile = removeSecurityProxy(self.pofile)
        data = pofile._prepare_pomessage_error_message(
            errors, replacements)
        subject, template_mail, errorsdetails = data
        pot_displayname = self.pofile.potemplate.displayname
        self.assertEqual(
            'Translation problems - Esperanto (eo) - %s' % pot_displayname,
            subject)
        self.assertEqual('poimport-with-errors.txt', template_mail)
        self.assertEqual(2, replacements['numberoferrors'])
        self.assertEqual(3, replacements['numberofcorrectmessages'])
        self.assertEqual(errorsdetails, replacements['errorsdetails'])
        self.assertEqual(
            '1. "claws error":\n\npurrs\n\n2. "string error":\n\nplays\n\n',
            errorsdetails)

    def test_prepare_pomessage_error_message_sequence_is_invalid(self):
        # The errordetails can be contructed when the sequnce is invalid.
        errors = [{
            'potmsgset': self.factory.makePOTMsgSet(
                potemplate=self.pofile.potemplate, sequence=None),
            'pomessage': 'purrs',
            'error-message': 'claws error',
            }]
        replacements = {'numberofmessages': 5}
        pofile = removeSecurityProxy(self.pofile)
        potmsgset = removeSecurityProxy(errors[0]['potmsgset'])

        def get_sequence(pot):
            return None

        with monkey_patch(potmsgset, getSequence=get_sequence):
            data = pofile._prepare_pomessage_error_message(
                errors, replacements)
        subject, template_mail, errorsdetails = data
        self.assertEqual('-1. "claws error":\n\npurrs\n\n', errorsdetails)


class TestPOFileUbuntuUpstreamSharingMixin:
    """Test sharing between Ubuntu und upstream POFiles."""

    layer = ZopelessDatabaseLayer

    def createData(self):
        self.shared_template_name = self.factory.getUniqueString()
        self.shared_language = self.factory.makeLanguage()

        self.distroseries = self.factory.makeUbuntuDistroSeries()
        self.distroseries.distribution.translation_focus = (
            self.distroseries)
        self.sourcepackagename = self.factory.makeSourcePackageName()
        self.sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename)
        self.productseries = self.factory.makeProductSeries()

    def makeThisSidePOFile(self, create_sharing=False):
        """Create POFile on this side. Override in subclass.

        :param create_sharing: Pass to factory function to enable automatic
            pofile creation, like in production code.
        """
        raise NotImplementedError

    def makeOtherSidePOFile(self):
        """Create POFile on the other side. Override in subclass."""
        raise NotImplementedError

    def makeOtherSidePOTemplate(self):
        """Create POTemplate on the other side. Override in subclass."""
        raise NotImplementedError

    def makeSharedUbuntuPOTemplate(self):
        """Create template ready for sharing on the Ubuntu side."""
        return self.factory.makePOTemplate(
            distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename,
            name=self.shared_template_name)

    def makeSharedUbuntuPOFile(self, create_sharing=False):
        """Create template and POFile ready for sharing on the Ubuntu side.
        """
        potemplate = self.makeSharedUbuntuPOTemplate()
        return self.factory.makePOFile(
            language=self.shared_language, potemplate=potemplate,
            create_sharing=create_sharing)

    def makeSharedUpstreamPOTemplate(self):
        """Create template ready for sharing on the upstream side."""
        return self.factory.makePOTemplate(
            productseries=self.productseries,
            name=self.shared_template_name)

    def makeSharedUpstreamPOFile(self, create_sharing=False):
        """Create template and POFile ready for sharing on the upstream side.
        """
        potemplate = self.makeSharedUpstreamPOTemplate()
        return self.factory.makePOFile(
            language=self.shared_language, potemplate=potemplate,
            create_sharing=create_sharing)

    def _setPackagingLink(self):
        """Create the packaging link from source package to product series."""
        # Packaging links want an owner.
        self.sourcepackage.setPackaging(
            self.productseries, self.factory.makePerson())

    def test_getOtherSidePOFile_none(self):
        # Without a packaging link, None is returned.
        pofile = self.makeThisSidePOFile()
        self.assertIs(None, pofile.getOtherSidePOFile())

    def test_getOtherSidePOFile_linked_no_template(self):
        # If no sharing template exists on the other side, no POFile can be
        # found, even with a packaging link.
        self._setPackagingLink()
        pofile = self.makeThisSidePOFile()
        self.assertIs(None, pofile.getOtherSidePOFile())

    def test_getOtherSidePOFile_shared(self):
        # This is how sharing should look like.
        this_pofile = self.makeThisSidePOFile()
        other_pofile = self.makeOtherSidePOFile()
        self._setPackagingLink()
        self.assertEquals(other_pofile, this_pofile.getOtherSidePOFile())

    def test_getOtherSidePOFile_automatic(self):
        # As expected, sharing POFiles are created automatically if the
        # packaging link already exists.
        self._setPackagingLink()
        other_potemplate = self.makeOtherSidePOTemplate()
        this_pofile = self.makeThisSidePOFile(create_sharing=True)
        self.assertEquals(
            other_potemplate, this_pofile.getOtherSidePOFile().potemplate)


class TestPOFileUbuntuSharing(TestCaseWithFactory,
                              TestPOFileUbuntuUpstreamSharingMixin):
    """Test sharing on Ubuntu side."""

    def setUp(self):
        super(TestPOFileUbuntuSharing, self).setUp()
        self.createData()

    def makeThisSidePOFile(self, create_sharing=False):
        return self.makeSharedUbuntuPOFile(create_sharing)

    def makeOtherSidePOFile(self):
        return self.makeSharedUpstreamPOFile()

    def makeOtherSidePOTemplate(self):
        return self.makeSharedUpstreamPOTemplate()


class TestPOFileUpstreamSharing(TestCaseWithFactory,
                                TestPOFileUbuntuUpstreamSharingMixin):
    """Test sharing on upstream side."""

    def setUp(self):
        super(TestPOFileUpstreamSharing, self).setUp()
        self.createData()

    def makeThisSidePOFile(self, create_sharing=False):
        return self.makeSharedUpstreamPOFile(create_sharing)

    def makeOtherSidePOFile(self):
        return self.makeSharedUbuntuPOFile()

    def makeOtherSidePOTemplate(self):
        return self.makeSharedUbuntuPOTemplate()


class TestPOFileTranslationMessages(TestCaseWithFactory):
    """Test PO file getTranslationMessages method."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestPOFileTranslationMessages, self).setUp()
        self.pofile = self.factory.makePOFile('eo')
        self.potemplate = self.pofile.potemplate
        self.potmsgset = self.factory.makePOTMsgSet(
            self.potemplate)

    def test_getTranslationMessages_current_shared(self):
        # A shared message is included in this POFile's messages.
        message = self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=self.pofile)

        self.assertEqual(
            [message], list(self.pofile.getTranslationMessages()))

    def test_getTranslationMessages_current_diverged(self):
        # A diverged message is included in this POFile's messages.
        message = self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=self.pofile, diverged=True)

        self.assertEqual(
            [message], list(self.pofile.getTranslationMessages()))

    def test_getTranslationMessages_suggestion(self):
        # A suggestion is included in this POFile's messages.
        message = self.factory.makeSuggestion(
            potmsgset=self.potmsgset, pofile=self.pofile)

        self.assertEqual(
            [message], list(self.pofile.getTranslationMessages()))

    def test_getTranslationMessages_obsolete(self):
        # A message on an obsolete POTMsgSEt is included in this
        # POFile's messages.
        potmsgset = self.factory.makePOTMsgSet(self.potemplate, sequence=0)
        message = self.factory.makeCurrentTranslationMessage(
            potmsgset=potmsgset, pofile=self.pofile)

        self.assertEqual(
            [message], list(self.pofile.getTranslationMessages()))

    def test_getTranslationMessages_other_pofile(self):
        # A message from another POFiles is not included.
        other_pofile = self.factory.makePOFile('de')
        self.potmsgset.setSequence(
            other_pofile.potemplate, self.factory.getUniqueInteger())
        self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=other_pofile)

        self.assertEqual([], list(self.pofile.getTranslationMessages()))

    def test_getTranslationMessages_condition_matches(self):
        # A message matching the given condition is included.
        # Diverged messages are linked to a specific POTemplate.
        message = self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=self.pofile, diverged=True)

        self.assertContentEqual(
            [message],
            self.pofile.getTranslationMessages(
                "TranslationMessage.potemplate IS NOT NULL"))

    def test_getTranslationMessages_condition_matches_not(self):
        # A message not matching the given condition is excluded.
        # Shared messages are not linked to a POTemplate.
        self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=self.pofile)

        self.assertContentEqual(
            [],
            self.pofile.getTranslationMessages(
                "TranslationMessage.potemplate IS NOT NULL"))

    def test_getTranslationMessages_condition_matches_in_other_pofile(self):
        # A message matching given condition but located in another POFile
        # is not included.
        other_pofile = self.factory.makePOFile('de')
        self.potmsgset.setSequence(
            other_pofile.potemplate, self.factory.getUniqueInteger())
        self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=other_pofile,
            diverged=True)

        self.assertContentEqual(
            [],
            self.pofile.getTranslationMessages(
                "TranslationMessage.potemplate IS NOT NULL"))

    def test_getTranslationMessages_diverged_elsewhere(self):
        # Diverged messages from sharing POTemplates are not included.
        # Create a sharing potemplate in another product series and share
        # potmsgset in both templates.
        other_series = self.factory.makeProductSeries(
            product=self.potemplate.productseries.product)
        other_template = self.factory.makePOTemplate(
            productseries=other_series, name=self.potemplate.name)
        other_pofile = other_template.getPOFileByLang(
            self.pofile.language.code)
        self.potmsgset.setSequence(other_template, 1)
        self.factory.makeCurrentTranslationMessage(
            potmsgset=self.potmsgset, pofile=other_pofile,
            diverged=True)

        self.assertEqual([], list(self.pofile.getTranslationMessages()))


class TestPOFileToTranslationFileDataAdapter(TestCaseWithFactory):
    """Test POFile being adapted to IPOFileToTranslationFileData."""

    layer = ZopelessDatabaseLayer

    header = dedent("""
        Project-Id-Version: foo
        Report-Msgid-Bugs-To:
        POT-Creation-Date: 2007-07-09 03:39+0100
        PO-Revision-Date: 2001-09-09 01:46+0000
        Last-Translator: Kubla Kahn <kk@pleasure-dome.com>
        Language-Team: Serbian <sr@li.org>
        MIME-Version: 1.0
        Content-Type: text/plain; charset=UTF-8
        Content-Transfer-Encoding: 8bit
        Plural-Forms: %s""")

    western_plural = "nplurals=2; plural=(n != 1)"
    other_2_plural = "nplurals=2; plural=(n > 0)"
    generic_plural = "nplurals=INTEGER; plural=EXPRESSION"
    serbian3_plural = ("nplurals=3; plural=(n%10==1 && n%100!=11 "
                      "? 0 : n%10>=2 && n%10<=4 && (n% 100<10 || n%100>=20) "
                      "? 1 : 2)")
    serbian4_plural = ("nplurals=4; plural=(n==1 ? 3 : (n%10==1 && n%100!=11 "
                      "? 0 : n%10>=2 && n%10<=4 && (n% 100<10 || n%100>=20) "
                      "? 1 : 2))")
    plural_template = "nplurals=%d; plural=%s"

    def _makePOFileWithPlural(self, language_code):
        pofile = removeSecurityProxy(self.factory.makePOFile(language_code))
        self.factory.makePOTMsgSet(
            pofile.potemplate, singular=u"Foo", plural=u"Bar")
        return pofile

    def test_header_pluralform_equal(self):
        # If the number of plural forms in the header is equal to that in the
        # language entry, use the data from the language entry.
        sr_pofile = self._makePOFileWithPlural('sr')
        sr_pofile.header = self.header % self.serbian3_plural

        translation_file_data = getAdapter(
            sr_pofile, ITranslationFileData, 'all_messages')
        self.assertEqual(3, translation_file_data.header.number_plural_forms)
        # The expression from the header starts with a "(", the language entry
        # does not.
        self.assertEqual(
            u"n%10==1 && n%100!=11",
            translation_file_data.header.plural_form_expression[:20])

    def test_header_pluralform_larger(self):
        # If the number of plural forms in the header is larger than in the
        # language entry, use the data from the header.
        sr_pofile = self._makePOFileWithPlural('sr')
        sr_pofile.header = self.header % self.serbian4_plural

        translation_file_data = getAdapter(
            sr_pofile, ITranslationFileData, 'all_messages')
        self.assertEqual(4, translation_file_data.header.number_plural_forms)
        self.assertEqual(
            u"(n==1 ? 3 : (n%10==1",
            translation_file_data.header.plural_form_expression[:20])

    def test_header_pluralform_larger_but_western(self):
        # If the plural form expression in the header is the standard western
        # expression, use the data from the language entry if present.
        # Use Japanese because it has only one plural form which is less
        # than the 2 the western style has.
        ja_pofile = self._makePOFileWithPlural('ja')
        # The expression comes in different forms.
        for expr in ('(n != 1)', '1 != n', 'n>1', '(1 < n)'):
            plural_info = self.plural_template % (2, expr)
            ja_pofile.header = self.header % plural_info

            translation_file_data = getAdapter(
                ja_pofile, ITranslationFileData, 'all_messages')
            nplurals_expected = 1
            nplurals = translation_file_data.header.number_plural_forms
            self.assertEqual(
                nplurals_expected, nplurals,
                "%d != %d for '%s'" % (nplurals_expected, nplurals, expr))
            # The plural form expression for Japanese (or any other language
            # with just one form) is simply '0'.
            self.assertEqual(
                u"0", translation_file_data.header.plural_form_expression)

    def test_header_pluralform_2_but_not_western(self):
        # If the plural form expression in the header reports two but is not
        # the standard western expression, use the data from the header.
        # Use Japanese because it has only one plural form which is less
        # than the 2 the western style has.
        ja_pofile = self._makePOFileWithPlural('ja')
        ja_pofile.header = self.header % self.other_2_plural

        translation_file_data = getAdapter(
            ja_pofile, ITranslationFileData, 'all_messages')
        self.assertEqual(2, translation_file_data.header.number_plural_forms)
        self.assertEqual(
            u"(n > 0)", translation_file_data.header.plural_form_expression)

    def test_header_pluralform_generic(self):
        # If the plural form expression in the header is a generic one (no
        # information), use the data from the language entry if present.
        ja_pofile = self._makePOFileWithPlural('ja')
        ja_pofile.header = self.header % self.generic_plural

        translation_file_data = getAdapter(
            ja_pofile, ITranslationFileData, 'all_messages')
        self.assertEqual(1, translation_file_data.header.number_plural_forms)
        self.assertEqual(
            u"0", translation_file_data.header.plural_form_expression)


class TestPOFilePermissions(TestCaseWithFactory):
    """Test `POFile` access privileges.

        :ivar pofile: A `POFile` for a `ProductSeries`.
    """
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestPOFilePermissions, self).setUp()
        self.pofile = self.factory.makePOFile()

    def makeDistroPOFile(self):
        """Replace `self.pofile` with one for a `Distribution`."""
        template = self.factory.makePOTemplate(
            distroseries=self.factory.makeDistroSeries(),
            sourcepackagename=self.factory.makeSourcePackageName())
        self.pofile = self.factory.makePOFile(potemplate=template)

    def getTranslationPillar(self):
        """Return `self.pofile`'s `Product` or `Distribution`."""
        template = self.pofile.potemplate
        if template.productseries is not None:
            return template.productseries.product
        else:
            return template.distroseries.distribution

    def closeTranslations(self):
        """Set translation permissions for `self.pofile` to CLOSED.

        This is useful for showing that a particular person has rights
        to work on a translation despite it being generally closed to
        the public.
        """
        self.getTranslationPillar().translationpermission = (
            TranslationPermission.CLOSED)

    def test_makeDistroPOFile(self):
        # Test the makeDistroPOFile helper.
        self.assertEqual(
            self.pofile.potemplate.productseries.product,
            self.getTranslationPillar())
        self.makeDistroPOFile()
        self.assertEqual(
            self.pofile.potemplate.distroseries.distribution,
            self.getTranslationPillar())

    def test_closeTranslations_product(self):
        # Test the closeTranslations helper for Products.
        self.assertNotEqual(
            TranslationPermission.CLOSED,
            self.getTranslationPillar().translationpermission)
        self.closeTranslations()
        self.assertEqual(
            TranslationPermission.CLOSED,
            self.getTranslationPillar().translationpermission)

    def test_closeTranslations_distro(self):
        # Test the closeTranslations helper for Distributions.
        self.makeDistroPOFile()
        self.assertNotEqual(
            TranslationPermission.CLOSED,
            self.getTranslationPillar().translationpermission)
        self.closeTranslations()
        self.assertEqual(
            TranslationPermission.CLOSED,
            self.getTranslationPillar().translationpermission)

    def test_anonymous_cannot_submit(self):
        # Anonymous users cannot edit translations or enter suggestions.
        self.assertFalse(self.pofile.canEditTranslations(None))
        self.assertFalse(self.pofile.canAddSuggestions(None))

    def test_licensing_agreement_decliners_cannot_submit(self):
        # Users who decline the translations relicensing agreement can't
        # edit translations or enter suggestions.
        decliner = self.factory.makePerson()
        set_relicensing(decliner, False)
        self.assertFalse(self.pofile.canEditTranslations(decliner))
        self.assertFalse(self.pofile.canAddSuggestions(decliner))

    def test_licensing_agreement_accepters_can_submit(self):
        # Users who accept the translations relicensing agreement can
        # edit translations and enter suggestions as circumstances
        # allow.
        accepter = self.factory.makePerson()
        set_relicensing(accepter, True)
        self.assertTrue(self.pofile.canEditTranslations(accepter))
        self.assertTrue(self.pofile.canAddSuggestions(accepter))

    def test_admin_can_edit(self):
        # Administrators can edit all translations and make suggestions
        # anywhere.
        self.closeTranslations()
        admin = self.factory.makePerson()
        getUtility(ILaunchpadCelebrities).admin.addMember(admin, admin)
        self.assertTrue(self.pofile.canEditTranslations(admin))
        self.assertTrue(self.pofile.canAddSuggestions(admin))

    def test_translations_admin_can_edit(self):
        # Translations admins can edit all translations and make
        # suggestions anywhere.
        self.closeTranslations()
        translations_admin = self.factory.makePerson()
        getUtility(ILaunchpadCelebrities).rosetta_experts.addMember(
            translations_admin, translations_admin)
        self.assertTrue(self.pofile.canEditTranslations(translations_admin))
        self.assertTrue(self.pofile.canAddSuggestions(translations_admin))

    def test_product_owner_can_edit(self):
        # A Product owner can edit the Product's translations and enter
        # suggestions even when a regular user isn't allowed to.
        self.closeTranslations()
        product = self.getTranslationPillar()
        self.assertTrue(self.pofile.canEditTranslations(product.owner))
        self.assertTrue(self.pofile.canAddSuggestions(product.owner))

    def test_product_owner_can_edit_after_declining_agreement(self):
        # A Product owner can edit the Product's translations even after
        # declining the translations licensing agreement.
        product = self.getTranslationPillar()
        set_relicensing(product.owner, False)
        self.assertTrue(self.pofile.canEditTranslations(product.owner))

    def test_distro_owner_gets_no_privileges(self):
        # A Distribution owner gets no special privileges.
        self.makeDistroPOFile()
        self.closeTranslations()
        distro = self.getTranslationPillar()
        self.assertFalse(self.pofile.canEditTranslations(distro.owner))
        self.assertFalse(self.pofile.canAddSuggestions(distro.owner))

    def test_productseries_owner_gets_no_privileges(self):
        # A ProductSeries owner gets no special privileges.
        self.closeTranslations()
        productseries = self.pofile.potemplate.productseries
        productseries.owner = self.factory.makePerson()
        self.assertFalse(self.pofile.canEditTranslations(productseries.owner))
        self.assertFalse(self.pofile.canAddSuggestions(productseries.owner))

    def test_potemplate_owner_gets_no_privileges(self):
        # A POTemplate owner gets no special privileges.
        self.closeTranslations()
        template = self.pofile.potemplate
        template.owner = self.factory.makePerson()
        self.assertFalse(self.pofile.canEditTranslations(template.owner))
        self.assertFalse(self.pofile.canAddSuggestions(template.owner))

    def test_pofile_owner_gets_no_privileges(self):
        # A POFile owner has no special privileges.
        self.closeTranslations()
        self.pofile.owner = self.factory.makePerson()
        self.assertFalse(self.pofile.canEditTranslations(self.pofile.owner))
        self.assertFalse(self.pofile.canAddSuggestions(self.pofile.owner))

    def test_product_translation_group_owner_gets_no_privileges(self):
        # A translation group owner manages the translation group
        # itself.  There are no special privileges.
        self.closeTranslations()
        group = self.factory.makeTranslationGroup()
        self.getTranslationPillar().translationgroup = group
        self.assertFalse(self.pofile.canEditTranslations(group.owner))
        self.assertFalse(self.pofile.canAddSuggestions(group.owner))

    def test_distro_translation_group_owner_gets_no_privileges(self):
        # Owners of Distribution translation groups get no special edit
        # privileges.
        self.makeDistroPOFile()
        self.closeTranslations()
        group = self.factory.makeTranslationGroup()
        self.getTranslationPillar().translationgroup = group
        self.assertFalse(self.pofile.canEditTranslations(group.owner))
        self.assertFalse(self.pofile.canAddSuggestions(group.owner))


class StatisticsTestScenario:
    """Test case mixin: `POFile` statistics.

    It is used to test the actual statistics functions but also to test that
    the related filter functions return the same counts.
    """
    layer = ZopelessDatabaseLayer

    def makePOFile(self):
        """Create a `POFile` to run statistics tests against."""
        raise NotImplementedError("makePOFile")

    def exerciseFunction(self, pofile):
        """Run the function under test."""
        raise NotImplementedError("exerciseFunction")

    def getCurrentCount(self, pofile):
        raise NotImplementedError("getCurrentCount")

    def getRosettaCount(self, pofile):
        raise NotImplementedError("getRosettaCount")

    def getTranslatedCount(self, pofile):
        raise NotImplementedError("getTranslatedCount")

    def getUnreviewedCount(self, pofile):
        raise NotImplementedError("getUnreviewedCount")

    def getUntranslatedCount(self, pofile):
        raise NotImplementedError("getUntranslatedCount")

    def getUpdatesCount(self, pofile):
        raise NotImplementedError("getUpdatesCount")

    def _getSideTraits(self, potemplate):
        """Return `TranslationSideTraits` for `potemplate`."""
        return getUtility(ITranslationSideTraitsSet).getForTemplate(
            potemplate)

    def _makeOtherSideTranslation(self, pofile, potmsgset=None,
                                  translations=None):
        """Create a current `TranslationMessage` for the other side."""
        message = self.factory.makeSuggestion(
            pofile=pofile, potmsgset=potmsgset, translations=translations)
        traits = self._getSideTraits(pofile.potemplate)
        traits.other_side_traits.setFlag(message, True)
        return message

    def test_translatedCount_initial(self):
        pofile = self.makePOFile()
        self.assertEqual(0, self.getTranslatedCount(pofile))

    def test_translatedCount_potmsgset_initial(self):
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getTranslatedCount(pofile))

    def test_translatedCount(self):
        # A current translation message counts towards the POFile's
        # translatedCount.
        pofile = self.makePOFile()
        self.factory.makeCurrentTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getTranslatedCount(pofile))

    def test_translatedCount_ignores_obsolete(self):
        # Translations of obsolete POTMsgSets do not count as
        # translated.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate, sequence=0)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getTranslatedCount(pofile))

    def test_translatedCount_other_side(self):
        # Translations on the other side do not count as translated.
        pofile = self.makePOFile()
        self._makeOtherSideTranslation(pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getTranslatedCount(pofile))

    def test_translatedCount_diverged(self):
        # Diverged translations are also counted.
        pofile = self.makePOFile()
        self.factory.makeDivergedTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getTranslatedCount(pofile))

    def test_translatedCount_ignores_masked_shared_translations(self):
        # A shared current translation that is masked by a diverged one
        # is not counted.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.factory.makeDivergedTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)

        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getTranslatedCount(pofile))

    def test_untranslatedCount_potmsgset_initial(self):
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUntranslatedCount(pofile))

    def test_untranslatedCount_initial(self):
        pofile = self.makePOFile()
        self.assertEqual(0, pofile.untranslatedCount())

    def test_untranslatedCount(self):
        # Translating a message removes it from the untranslatedCount.
        pofile = self.makePOFile()
        self.factory.makeCurrentTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUntranslatedCount(pofile))

    def test_untranslatedCount_ignores_obsolete(self):
        # Translations of obsolete POTMsgSets do not count as
        # untranslated.
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate, sequence=0)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUntranslatedCount(pofile))

    def test_untranslatedCount_other_side(self):
        # Messages that are translated on the other side can still be in
        # the untranslatedCount.
        pofile = self.makePOFile()
        self._makeOtherSideTranslation(pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUntranslatedCount(pofile))

    def test_untranslatedCount_diverged(self):
        # Diverged translations are also counted.
        pofile = self.makePOFile()
        self.factory.makeDivergedTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUntranslatedCount(pofile))

    def test_untranslatedCount_ignores_masked_shared_translations(self):
        # A shared current translation that is masked by a diverged one
        # is only subtracted from the untranslatedCount once.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.factory.makeDivergedTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUntranslatedCount(pofile))

    def test_currentCount_initial(self):
        pofile = self.makePOFile()
        self.assertEqual(0, self.getCurrentCount(pofile))

    def test_currentCount_potmsgset_initial(self):
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getCurrentCount(pofile))

    def test_currentCount(self):
        # A translation that is shared between Ubuntu and upstream is
        # counted in currentCount.
        pofile = self.makePOFile()
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, current_other=True)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getCurrentCount(pofile))

    def test_currentCount_ignores_obsolete(self):
        # The currentCount does not include obsolete messages.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate, sequence=0)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset, current_other=True)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getCurrentCount(pofile))

    def test_currentCount_ignores_onesided_translation(self):
        # A translation that is only current on one side is not included
        # in currentCount.
        pofile = self.makePOFile()
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, current_other=False)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getCurrentCount(pofile))

    def test_currentCount_different(self):
        # A message that is translated differently in Ubuntu than
        # upstream is not included in currentCount.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self._makeOtherSideTranslation(pofile, potmsgset=potmsgset)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getCurrentCount(pofile))

    def test_currentCount_diverged(self):
        # Diverging from a translation that's shared between Ubuntu and
        # upstream decrements the currentCount.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset, current_other=True)
        self.factory.makeDivergedTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getCurrentCount(pofile))

    def test_rosettaCount_initial(self):
        pofile = self.makePOFile()
        self.assertEqual(0, pofile.rosettaCount())

    def test_rosettaCount_potmsgset_initial(self):
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getRosettaCount(pofile))

    def test_rosettaCount(self):
        # rosettaCount counts messages that are translated on this side
        # but not the other side.
        pofile = self.makePOFile()
        self.factory.makeCurrentTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getRosettaCount(pofile))

    def test_rosettaCount_ignores_obsolete(self):
        # The rosettaCount ignores obsolete messages.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate, sequence=0)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getRosettaCount(pofile))

    def test_rosettaCount_diverged(self):
        # Diverged messages are also counted towards the rosettaCount.
        pofile = self.makePOFile()
        self.factory.makeDivergedTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getRosettaCount(pofile))

    def test_rosettaCount_ignores_shared_messages(self):
        # Messages that are shared with the other side are not part of
        # the rosettaCount.
        pofile = self.makePOFile()
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, current_other=True)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getRosettaCount(pofile))

    def test_rosettaCount_ignores_messages_translated_on_other_side(self):
        # Messages that are translated on the other side but not on this
        # one do not count towards the rosettaCount.
        pofile = self.makePOFile()
        self._makeOtherSideTranslation(pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getRosettaCount(pofile))

    def test_rosettaCount_includes_different_translations(self):
        # The rosettaCount does include messages that are translated
        # differently on the two sides.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self._makeOtherSideTranslation(pofile, potmsgset=potmsgset)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getRosettaCount(pofile))

    def test_updatesCount_initial(self):
        pofile = self.makePOFile()
        self.assertEqual(0, self.getUpdatesCount(pofile))

    def test_updatesCount_potmsgset_initial(self):
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUpdatesCount(pofile))

    def test_updatesCount(self):
        # The updatesCount counts messages that are translated on the
        # other side, but differently.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self._makeOtherSideTranslation(pofile, potmsgset=potmsgset)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUpdatesCount(pofile))

    def test_updatesCount_ignores_obsolete(self):
        # The updatesCount ignores obsolete messages.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate, sequence=0)
        self._makeOtherSideTranslation(pofile, potmsgset=potmsgset)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUpdatesCount(pofile))

    def test_updatesCount_diverged(self):
        # Diverged messages can be part of the updatesCount.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset, current_other=True)
        self.factory.makeDivergedTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUpdatesCount(pofile))

    def test_updatesCount_diverged_ignores_untranslated_other(self):
        # Diverged messages are not part of the updatesCount if there is
        # no translation on the other side; they fall under rosettaCount.
        pofile = self.makePOFile()
        self.factory.makeDivergedTranslationMessage(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUpdatesCount(pofile))

    def test_unreviewedCount_initial(self):
        pofile = self.makePOFile()
        self.assertEqual(0, self.getUnreviewedCount(pofile))

    def test_unreviewedCount_potmsgset_initial(self):
        pofile = self.makePOFile()
        self.factory.makePOTMsgSet(pofile.potemplate)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUnreviewedCount(pofile))

    def test_unreviewedCount(self):
        # A completely untranslated message with a suggestion counts as
        # unreviewed.
        pofile = self.makePOFile()
        self.factory.makeSuggestion(pofile=pofile)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUnreviewedCount(pofile))

    def test_unreviewedCount_ignores_obsolete(self):
        # The unreviewedCount ignores obsolete messages.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate, sequence=0)
        self.factory.makeSuggestion(pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUnreviewedCount(pofile))

    def test_unreviewedCount_counts_msgids_not_suggestions(self):
        # The unreviewedCount counts messages with unreviewed
        # suggestions, not the suggestions themselves.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeSuggestion(pofile=pofile, potmsgset=potmsgset)
        self.factory.makeSuggestion(pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUnreviewedCount(pofile))

    def test_unreviewedCount_ignores_reviewed_suggestions(self):
        # In order to affect the unreviewedCount, a suggestion has to be
        # newer than the review date on the current translation.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        self.factory.makeSuggestion(
            pofile=pofile, potmsgset=potmsgset)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(0, self.getUnreviewedCount(pofile))

    def test_unreviewedCount_includes_new_suggestions(self):
        # Suggestions that are newer than the review date om the current
        # translation are included in the unreviewedCount.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        translation = self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        translation.date_reviewed -= timedelta(1)
        self.factory.makeSuggestion(
            pofile=pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUnreviewedCount(pofile))

    def test_unreviewedCount_includes_other_side_translation(self):
        # A translation on the other side that's newer than the review
        # date on the current translation on this side also counts as an
        # unreviewed suggestion on this side.
        pofile = self.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(pofile.potemplate)
        this_translation = self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        this_translation.date_reviewed -= timedelta(1)
        self._makeOtherSideTranslation(pofile, potmsgset=potmsgset)
        self.exerciseFunction(pofile)
        self.assertEqual(1, self.getUnreviewedCount(pofile))


class StatistcsCountsTestScenario(StatisticsTestScenario):
    """Test statistics on upstream `POFile`s."""

    def exerciseFunction(self, pofile):
        """Run the function under test."""
        pofile.updateStatistics()

    def getCurrentCount(self, pofile):
        return pofile.currentCount()

    def getRosettaCount(self, pofile):
        return pofile.rosettaCount()

    def getTranslatedCount(self, pofile):
        return pofile.translatedCount()

    def getUnreviewedCount(self, pofile):
        return pofile.unreviewedCount()

    def getUntranslatedCount(self, pofile):
        return pofile.untranslatedCount()

    def getUpdatesCount(self, pofile):
        return pofile.updatesCount()

    def test_statistics_are_initialized_correctly(self):
        # When a POFile is created, its statistics are initialized as if
        # they had been freshly updated.
        pofile = self.makePOFile()
        stats = pofile.getStatistics()
        self.exerciseFunction(pofile)
        self.assertEqual(stats, pofile.getStatistics())


class TestUpstreamStatistics(StatistcsCountsTestScenario,
                             TestCaseWithFactory):
    """Test statistics on upstream `POFile`s."""

    def makePOFile(self):
        return self.factory.makePOFile()


class TestUbuntuStatistics(StatistcsCountsTestScenario, TestCaseWithFactory):
    """Test statistics on Ubuntu `POFile`s."""

    def makePOFile(self):
        package = self.factory.makeSourcePackage()
        return self.factory.makePOFile(
            potemplate=self.factory.makePOTemplate(
                distroseries=package.distroseries,
                sourcepackagename=package.sourcepackagename))


class StatistcsFiltersTestScenario(StatisticsTestScenario):
    """Test the filter functions in `POFile`s compared to statistics."""

    def exerciseFunction(self, pofile):
        """Run the function under test."""
        pofile.updateStatistics()

    def getCurrentCount(self, pofile):
        return pofile.currentCount()

    def getRosettaCount(self, pofile):
        return pofile.rosettaCount()

    def getTranslatedCount(self, pofile):
        return pofile.getPOTMsgSetTranslated().count()

    def getUnreviewedCount(self, pofile):
        return pofile.getPOTMsgSetWithNewSuggestions().count()

    def getUntranslatedCount(self, pofile):
        return pofile.getPOTMsgSetUntranslated().count()

    def getUpdatesCount(self, pofile):
        return pofile.getPOTMsgSetDifferentTranslations().count()


class TestUpstreamFilters(StatistcsFiltersTestScenario, TestCaseWithFactory):
    """Test filters on upstream `POFile`s."""

    def makePOFile(self):
        return self.factory.makePOFile()


class TestUbuntuFilters(StatistcsFiltersTestScenario, TestCaseWithFactory):
    """Test filters on Ubuntu `POFile`s."""

    def makePOFile(self):
        package = self.factory.makeSourcePackage()
        return self.factory.makePOFile(
            potemplate=self.factory.makePOTemplate(
                distroseries=package.distroseries,
                sourcepackagename=package.sourcepackagename))
