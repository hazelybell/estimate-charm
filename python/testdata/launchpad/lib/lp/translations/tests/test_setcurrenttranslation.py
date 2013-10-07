# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    )
from lp.translations.model.translationmessage import TranslationMessage
from lp.translations.tests.helpers import (
    make_translationmessage_for_context,
    summarize_current_translations,
    )

# This test is based on the matrix described on:
#  https://dev.launchpad.net/Translations/Specs
#     /UpstreamImportIntoUbuntu/FixingIsImported
#     /setCurrentTranslation#Execution%20matrix


class SetCurrentTranslationTestMixin:
    """Tests for `POTMsgSet.setCurrentTranslation`.

    Depending on the setUp implementation available, this can test
    either from the perspective of translating an Ubuntu template or
    from the perspective of translating an upstream template.
    """

    def constructTranslationMessage(self, pofile=None, potmsgset=None,
                                    current=True, other=False, diverged=False,
                                    translations=None):
        """Creates a TranslationMessage directly for `pofile` context."""
        if pofile is None:
            pofile = self.pofile
        if potmsgset is None:
            potmsgset = self.potmsgset
        return make_translationmessage_for_context(
            self.factory, pofile, potmsgset,
            current, other, diverged, translations)

    def constructOtherTranslationMessage(self, potmsgset=None, current=True,
                                         other=False, diverged=False,
                                         translations=None):
        """Creates a TranslationMessage for self.other_pofile context."""
        return self.constructTranslationMessage(
            self.other_pofile, potmsgset, current, other, diverged,
            translations)

    def constructDivergingTranslationMessage(self, potmsgset=None,
                                             current=True, other=False,
                                             diverged=False,
                                             translations=None):
        """Creates a TranslationMessage for self.diverging_pofile context."""
        return self.constructTranslationMessage(
            self.diverging_pofile, potmsgset, current, other, diverged,
            translations)

    def setCurrentTranslation(self, translations,
                              share_with_other_side=False):
        """Helper method to call 'setCurrentTranslation' method.

        It passes all the same parameters we use throughout the tests,
        including self.potmsgset, self.pofile, self.pofile.owner and origin.
        """
        translations = dict(enumerate(translations))
        return self.potmsgset.setCurrentTranslation(
            self.pofile, self.pofile.owner, translations,
            origin=RosettaTranslationOrigin.ROSETTAWEB,
            share_with_other_side=share_with_other_side)

    def assert_Current_Diverged_Other_DivergencesElsewhere_are(
        self, current, diverged, other_shared, divergences_elsewhere):
        """Assert that 'important' translations match passed-in values.

        Takes four parameters:
         * current: represents a current shared translation for this context.
         * diverged: represents a diverged translation for this context.
         * other_shared: represents a shared translation for "other" context.
         * divergences_elsewhere: a list of other divergences in both
            contexts.
        """
        new_current, new_diverged, new_other, new_divergences = (
            summarize_current_translations(self.pofile, self.potmsgset))

        if new_current is None:
            self.assertIs(new_current, current)
        else:
            self.assertEquals(new_current, current)
        if new_diverged is None:
            self.assertIs(new_diverged, diverged)
        else:
            self.assertEquals(new_diverged, diverged)
        if new_other is None:
            self.assertIs(new_other, other_shared)
        else:
            self.assertEquals(new_other, other_shared)

        self.assertContentEqual(new_divergences, divergences_elsewhere)

    def assertTranslationMessageDeleted(self, translationmessage_id):
        """Assert that a translation message doesn't exist.

        Until deletion of TMs is implemented, it just checks that
        translation message is not current in any context.
        """
        # XXX DaniloSegan 20100528: we should assert that tm_other
        # doesn't exist in the DB anymore instead.
        tm = TranslationMessage.get(translationmessage_id)
        self.assertFalse(tm.is_current_ubuntu)
        self.assertFalse(tm.is_current_upstream)
        self.assertIs(None, tm.potemplate)

    # These tests follow a naming pattern to reflect exhaustive
    # coverage.  We had to abbreviate them.  In the names,
    #  'c' means the current message translating self.potmsgset in
    #      self.pofile;
    #  'n' means the "new" message, i.e. a pre-existing translation for
    #      self.potmsgset with the same translation text that the test
    #      will set;
    #  'o' means a message on the "other side," i.e. a shared message
    #      that is current there.  (We don't care about diverged
    #      messages on the other side since those would be for a
    #      different template than the one we're working on).

    def test_c_None__n_None__o_None(self):
        # Current translation is None, and we have found no
        # existing TM matching new translations.
        # There is neither 'other' current translation.
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [])

        new_translations = [self.factory.getUniqueString()]
        tm = self.setCurrentTranslation(new_translations)

        # We end up with a shared current translation.
        self.assertTrue(tm is not None)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

    def test_c_None__n_None__o_None__follows(self):
        # Current translation is None, and we have found no
        # existing TM matching new translations.
        # There is neither 'other' current translation.

        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [])

        new_translations = [self.factory.getUniqueString()]
        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # We end up with a shared current translation,
        # activated in other context as well.
        self.assertTrue(tm is not None)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

    def selectUpstreamTranslation(self, tm, tm_other):
        # Return the upstream translation.
        # :param tm: A translation for this side.
        # :param tm_other: A translation for the other side.
        raise NotImplementedError

    def test_c_None__n_None__o_shared(self, follows=False):
        # Current translation is None, and we have found no
        # existing TM matching new translations.
        # There is a current translation in "other" context.
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, tm_other, [])

        new_translations = [self.factory.getUniqueString()]
        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # We end up with a shared current translation.
        # Current for other context one stays the same, if the
        # other side does not follow this side.
        self.assertTrue(tm is not None)
        if follows:
            # Even if the other side is supposed to follow this side,
            # we ovverride the other only if the current side is Ubuntu.
            expected_other = self.selectUpstreamTranslation(tm, tm_other)
        else:
            expected_other = tm_other
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, expected_other, [])

    def test_c_None__n_None__o_shared__follows(self):
        # There is no current translation, though there is a shared one
        # on the other side.  There is no message with translations
        # identical to the one we're setting.
        # The sharing policy has no effect in this case.
        self.test_c_None__n_None__o_shared(follows=True)

    def test_c_None__n_None__o_diverged(self):
        # Current translation is None, and we have found no
        # existing TM matching new translations.
        # There is a current but diverged translation in "other" context.
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [tm_other])

        new_translations = [self.factory.getUniqueString()]
        tm = self.setCurrentTranslation(new_translations)

        # We end up with a shared current translation.
        self.assertTrue(tm is not None)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [tm_other])

        # Previously current is still diverged and current
        # in exactly one context.
        self.assertFalse(
            tm_other.is_current_upstream and tm_other.is_current_ubuntu)
        self.assertTrue(
            tm_other.is_current_upstream or tm_other.is_current_ubuntu)
        self.assertEquals(self.other_pofile.potemplate, tm_other.potemplate)

    def test_c_None__n_None__o_diverged__follows(self):
        # Current translation is None, and we have found no
        # existing TM matching new translations.
        # There is a current but diverged translation in "other" context.
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [tm_other])

        new_translations = [self.factory.getUniqueString()]
        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # We end up with a shared current translation.
        self.assertTrue(tm is not None)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [tm_other])

        # Previously current is still diverged and current
        # in exactly one context.
        self.assertFalse(tm_other.is_current_upstream and
                         tm_other.is_current_ubuntu)
        self.assertTrue(tm_other.is_current_upstream or
                         tm_other.is_current_ubuntu)
        self.assertEquals(self.other_pofile.potemplate, tm_other.potemplate)

    def test_c_None__n_shared__o_None(self):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations (a regular suggestion).
        # There is neither 'other' current translation.
        new_translations = [self.factory.getUniqueString()]
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)

        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [])

        tm = self.setCurrentTranslation(new_translations)

        # We end up with tm_suggestion being activated.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

    def test_c_None__n_shared__o_None__follows(self):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations (a regular suggestion).
        # There is neither 'other' current translation.
        new_translations = [self.factory.getUniqueString()]
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)

        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # We end up with tm_suggestion being activated in both contexts.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

    def test_c_None__n_shared__o_shared(self):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations (a regular suggestion).
        # There is a current translation in "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, tm_other, [])

        tm = self.setCurrentTranslation(new_translations)

        # tm_suggestion becomes current.
        # Current for other context one stays the same.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm_other, [])

    def test_c_None__n_shared__o_shared__follows(self):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations (a regular suggestion).
        # There is a current translation in "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # tm_suggestion becomes current.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_suggestion, tm)
        # If a translation is set for the first time in upstream,
        # this translation becomes current in Ubuntu too, but if the
        # translation is set for the first time in Ubuntu, this does
        # not affect the upstream translation.
        expected_other = self.selectUpstreamTranslation(tm, tm_other)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, expected_other, [])

    def test_c_None__n_shared__o_shared__identical(self, follows=False):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations and it's
        # also a current translation in "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # tm_other becomes current in this context as well,
        # and remains current for the other context.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_other, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

    def test_c_None__n_shared__o_shared__identical__follows(self):
        # As above, and 'share_with_other_side' is a no-op in this case.
        self.test_c_None__n_shared__o_shared__identical(follows=True)

    def test_c_None__n_shared__o_diverged(self):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations (a regular suggestion).
        # There is a current but diverged translation in "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [tm_other])

        tm = self.setCurrentTranslation(new_translations)

        # We end up with a shared current translation.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [tm_other])

        # Previously current is still diverged and current
        # in exactly one context.
        self.assertFalse(tm_other.is_current_upstream and
                         tm_other.is_current_ubuntu)
        self.assertTrue(tm_other.is_current_upstream or
                         tm_other.is_current_ubuntu)
        self.assertEquals(self.other_pofile.potemplate, tm_other.potemplate)

    def test_c_None__n_shared__o_diverged__follows(self):
        # Current translation is None, and we have found a
        # shared existing TM matching new translations (a regular suggestion).
        # There is a current but diverged translation in "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, None, None, [tm_other])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # We end up with a shared current translation.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [tm_other])

        # Previously current is still diverged and current
        # in exactly one context.
        self.assertFalse(
            tm_other.is_current_upstream and tm_other.is_current_ubuntu)
        self.assertTrue(
            tm_other.is_current_upstream or tm_other.is_current_ubuntu)
        self.assertEquals(self.other_pofile.potemplate, tm_other.potemplate)

    def test_c_shared__n_None__o_None(self):
        # Current translation is 'shared', and we have found
        # no existing TM matching new translations.
        # There is neither a translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message is shared and current only for
        # the active context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_None__o_None__follows(self):
        # Current translation is 'shared', and we have found
        # no existing TM matching new translations.
        # There is neither a translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # New translation message is shared and current for both
        # active and "other" context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_None__o_shared(self, follows=False):
        # Current translation is 'shared', and we have found
        # no existing TM matching new translations.
        # There is a shared translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message is shared and current only for
        # the active context.  Current for "other" context is left
        # untouched.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertNotEquals(tm_other, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm_other, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_None__o_shared__follows(self):
        # The choice of sharing policy has no effect when the Ubuntu
        # translation differs from the upstream translation.
        self.test_c_shared__n_None__o_shared(follows=True)

    def test_c_shared__n_shared__o_None(self):
        # Current translation is 'shared', and we have found
        # a shared existing TM matching new translations (a suggestion).
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message is shared and current only for
        # the active context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_shared__o_None__follows(self):
        # Current translation is 'shared', and we have found
        # a shared existing TM matching new translations (a suggestion).
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # New translation message is shared and current only for
        # the active context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_shared__o_None__identical(self):
        # Current translation is 'shared', and we are trying
        # to change it to identical translations. NO-OP.
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message is shared and current only for
        # the active context.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

    def test_c_shared__n_shared__o_None__identical__follows(self):
        # Current translation is 'shared', and we are trying
        # to change it to identical translations.
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # New translation message is shared and current for both contexts.
        self.assertTrue(tm is not None)
        self.assertEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

    def test_c_shared__n_shared__o_shared(self, follows=False):
        # Current translation is 'shared', and we have found
        # a shared existing TM matching new translations (a suggestion).
        # There is a shared translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message is shared and current only for
        # the active context. Translation for other context is untouched.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm_other, [])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_shared__o_shared__follows(self):
        # The choice of sharing policy has no effect when the Ubuntu
        # translation differs from the upstream translation.
        self.test_c_shared__n_shared__o_shared(follows=True)

    def test_c_shared__n_shared__o_shared__identical(self, follows=False):
        # Current translation is 'shared', and we have found
        # a shared existing TM matching new translations that is
        # also current for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message is shared for both contexts.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertEquals(tm_other, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm, [])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_shared__o_shared_identical_follows(self):
        # Since we are converging to the 'other' context anyway, it behaves
        # the same when 'share_with_other_side=True' is passed in.
        self.test_c_shared__n_shared__o_shared__identical(follows=True)

    def test_c_shared__n_shared__o_diverged__identical(self):
        # Current translation is 'shared', and we have found
        # a shared existing TM matching new translations (a suggestion).
        # There is a divergence in the 'other' context that is
        # exactly the same as the new translation.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_other_diverged = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [tm_other_diverged])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message is shared for current context,
        # and identical divergence in other context is kept.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertNotEquals(tm_other_diverged, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [tm_other_diverged])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_diverged__o_diverged_shared(self):
        # Current translation is 'shared', and we have found
        # a diverged (in other context) existing TM matching new translations.
        # There is also a shared translation for the "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        tm_other_diverged = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, tm_other, [tm_other_diverged])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message is shared and current only for
        # the active context.  "Other" translation is unchanged.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertNotEquals(tm_other, tm)
        self.assertNotEquals(tm_other_diverged, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm_other, [tm_other_diverged])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_shared__n_diverged__o_diverged__identical(self):
        # Current translation is 'shared', and we have found
        # a diverged existing TM matching new translations
        # for the "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False)
        tm_other_diverged = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, None, None, [tm_other_diverged])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message is shared and current only for
        # the active context.  "Other" translation is unchanged.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_shared, tm)
        self.assertNotEquals(tm_other_diverged, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [tm_other_diverged])

        # Previous shared translation is now a suggestion.
        self.assertFalse(
            tm_shared.is_current_ubuntu or tm_shared.is_current_upstream)

    def test_c_diverged__n_None__o_None(self, follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # no existing TM matching new translations.
        # There is neither a translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: (tm, None, None, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, None, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_None__o_None__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_None__o_None(follows=True)

    def test_c_diverged__n_None__o_shared(self, follows=False):
        # Current translation is 'diverged' (with shared), and we have found
        # no existing TM matching new translations.
        # There is neither a translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertNotEquals(tm_other, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, tm_other, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_None__o_shared__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_None__o_shared(True)

    def test_c_diverged__n_shared__o_None(self, follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # an existing shared TM matching new translations (a suggestion).
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: (tm, None, None, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, None, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_shared__o_None__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_shared__o_None(follows=True)

    def test_c_diverged__n_shared__o_None__identical(self):
        # Current translation is 'diverged', and we have found an existing
        # current shared TM matching new translations (converging).
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, tm_diverged, None, [])

        tm = self.setCurrentTranslation(new_translations)

        # New translation message converges for the active context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_shared__o_None_identical_follows(self):
        # Current translation is 'diverged', and we have found an existing
        # current shared TM matching new translations (converging).
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, tm_diverged, None, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=True)

        # New translation message converges for the active context.
        # The other side is not set because we're working on a diverged
        # message.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, None, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_shared__o_shared(self, follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # an existing shared TM matching new translations (a suggestion).
        # There is a shared translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_suggestion = self.constructTranslationMessage(
            current=False, other=False, diverged=False,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: (tm, None, None, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertEquals(tm_suggestion, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, tm_other, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_shared__o_shared__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_shared__o_shared(follows=True)

    def test_c_diverged__n_shared__o_shared__identical_other(self,
                                                             follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # a shared TM matching new translations, that is also
        # current in "other" context.  (Converging to 'other')
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message is diverged and current only for
        # the active context.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: tm_other==tm and (tm, None, tm, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertNotEquals(tm_other, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, tm_other, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_shared__o_shared__identical_o__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_shared__o_shared__identical_other(
            follows=True)

    def test_c_diverged__n_shared__o_shared__identical_shared(self,
                                                              follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # a shared TM matching new translations, that is also
        # currently shared in "this" context.  (Converging to 'shared')
        # There is a shared translation in "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_shared = self.constructTranslationMessage(
            current=True, other=False, diverged=False,
            translations=new_translations)
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm_shared, tm_diverged, tm_other, [])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message is shared for current context.
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertNotEquals(tm_other, tm)
        self.assertEquals(tm_shared, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            tm, None, tm_other, [])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_shared__o_shared__identical_shared__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_shared__o_shared__identical_shared(
            follows=True)

    def test_c_diverged__n_diverged__o_None(self, follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # an existing diverged elsewhere TM matching new translations.
        # There is no translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_diverged_elsewhere = self.constructDivergingTranslationMessage(
            current=True, other=False, diverged=True,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, None, [tm_diverged_elsewhere])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.  Existing divergence elsewhere is untouched.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: (tm, None, None, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertNotEquals(tm_diverged_elsewhere, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, None, [tm_diverged_elsewhere])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_diverged__o_None__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_diverged__o_None(follows=True)

    def test_c_diverged__n_diverged__o_shared(self, follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # an existing diverged elsewhere TM matching new translations.
        # There is a shared translation for "other" context.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_diverged_elsewhere = self.constructDivergingTranslationMessage(
            current=True, other=False, diverged=True,
            translations=new_translations)
        tm_other = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=False)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, tm_other, [tm_diverged_elsewhere])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.  Existing divergence elsewhere is untouched.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: (tm, None, tm_other, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertNotEquals(tm_diverged_elsewhere, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, tm_other, [tm_diverged_elsewhere])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_diverged__o_shared__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_diverged__o_shared(follows=True)

    def test_c_diverged__n_diverged__o_diverged(self, follows=False):
        # Current translation is 'diverged' (no shared), and we have found
        # an existing diverged in other context TM matching new translations.
        new_translations = [self.factory.getUniqueString()]
        tm_diverged = self.constructTranslationMessage(
            current=True, other=False, diverged=True)
        tm_other_diverged = self.constructOtherTranslationMessage(
            current=True, other=False, diverged=True,
            translations=new_translations)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm_diverged, None, [tm_other_diverged])

        tm = self.setCurrentTranslation(
            new_translations, share_with_other_side=follows)

        # New translation message stays diverged and current only for
        # the active context.  Existing divergence elsewhere is untouched.
        # XXX DaniloSegan 20100530: it'd be nice to have this
        # converge the diverged translation (since shared is None),
        # though it's not a requirement: (tm, None, tm_other, [])
        self.assertTrue(tm is not None)
        self.assertNotEquals(tm_diverged, tm)
        self.assertNotEquals(tm_other_diverged, tm)
        self.assert_Current_Diverged_Other_DivergencesElsewhere_are(
            None, tm, None, [tm_other_diverged])

        # Previously current is not current anymore.
        self.assertFalse(
            tm_diverged.is_current_ubuntu or tm_diverged.is_current_upstream)

    def test_c_diverged__n_diverged__o_diverged__follows(self):
        # The choice of sharing policy has no effect when starting from
        # a diverged translation.
        self.test_c_diverged__n_diverged__o_diverged(follows=True)


class TestSetCurrentTranslation_Ubuntu(SetCurrentTranslationTestMixin,
                                       TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestSetCurrentTranslation_Ubuntu, self).setUp()
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        sourcepackagename = self.factory.makeSourcePackageName()
        potemplate = self.factory.makePOTemplate(
            distroseries=ubuntu.currentseries,
            sourcepackagename=sourcepackagename)
        sharing_series = self.factory.makeDistroSeries(distribution=ubuntu)
        sharing_potemplate = self.factory.makePOTemplate(
            distroseries=sharing_series,
            sourcepackagename=sourcepackagename,
            name=potemplate.name)
        self.pofile = self.factory.makePOFile(
            'sr', potemplate=potemplate, create_sharing=True)

        # A POFile in the same context as self.pofile, used for diverged
        # translations.
        self.diverging_pofile = sharing_potemplate.getPOFileByLang(
            self.pofile.language.code)

        # A POFile in a different context from self.pofile and
        # self.diverging_pofile.
        self.other_pofile = self.factory.makePOFile(
            language_code=self.pofile.language.code)

        self.potmsgset = self.factory.makePOTMsgSet(
            potemplate=potemplate)

    def selectUpstreamTranslation(self, tm, tm_other):
        # See `SetCurrentTranslationTestMixin`
        return tm_other


class TestSetCurrentTranslation_Upstream(SetCurrentTranslationTestMixin,
                                         TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestSetCurrentTranslation_Upstream, self).setUp()
        series = self.factory.makeProductSeries()
        sharing_series = self.factory.makeProductSeries(
            product=series.product)
        potemplate = self.factory.makePOTemplate(productseries=series)
        sharing_potemplate = self.factory.makePOTemplate(
            productseries=sharing_series, name=potemplate.name)
        self.pofile = self.factory.makePOFile(
            'sr', potemplate=potemplate, create_sharing=True)

        # A POFile in the same context as self.pofile, used for diverged
        # translations.
        self.diverging_pofile = sharing_potemplate.getPOFileByLang(
            self.pofile.language.code)

        # A POFile in a different context from self.pofile and
        # self.diverging_pofile.
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        sourcepackagename = self.factory.makeSourcePackageName()
        ubuntu_template = self.factory.makePOTemplate(
            distroseries=ubuntu.currentseries,
            sourcepackagename=sourcepackagename)
        self.other_pofile = self.factory.makePOFile(
            potemplate=ubuntu_template,
            language_code=self.pofile.language.code)

        self.potmsgset = self.factory.makePOTMsgSet(
            potemplate=potemplate)

    def selectUpstreamTranslation(self, tm, tm_other):
        # See `SetCurrentTranslationTestMixin`
        return tm
