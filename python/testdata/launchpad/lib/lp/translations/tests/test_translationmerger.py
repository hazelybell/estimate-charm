# Copyright 2009, 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import gc
from logging import ERROR

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.log.logger import FakeLogger
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.sampledata import ADMIN_EMAIL
from lp.translations.model.pomsgid import POMsgID
from lp.translations.model.potemplate import POTemplate
from lp.translations.model.potranslation import POTranslation
from lp.translations.translationmerger import (
    MessageSharingMerge,
    TransactionManager,
    TranslationMerger,
    )


class TranslatableProductMixin:
    """Mixin: set up product with two series & templates for testing.

    Sets up a product with series "trunk" and "stable," each with a
    template.
    """

    def setUpProduct(self):
        self.product = self.factory.makeProduct()
        self.trunk = self.product.getSeries('trunk')
        self.stable = self.factory.makeProductSeries(
            product=self.product, owner=self.product.owner, name='stable')
        self.trunk_template = self.factory.makePOTemplate(
            productseries=self.trunk, name='template',
            owner=self.product.owner)
        self.stable_template = self.factory.makePOTemplate(
            productseries=self.stable, name='template',
            owner=self.product.owner)

        # Force trunk to be the "most representative" template.
        self.stable_template.iscurrent = False
        self.templates = [self.trunk_template, self.stable_template]

        self.script = MessageSharingMerge(
            'tms-merging-test', test_args=[], logger=FakeLogger())
        self.script.logger.setLevel(ERROR)
        tm = TransactionManager(self.script.txn, self.script.options.dry_run)
        self.merger = TranslationMerger(self.templates, tm)


class TestPOTMsgSetMerging(TestCaseWithFactory, TranslatableProductMixin):
    """Test merging of POTMsgSets."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        # This test needs the privileges of rosettaadmin (to delete
        # POTMsgSets) but it also needs to set up test conditions which
        # requires other privileges.
        super(TestPOTMsgSetMerging, self).setUp(user=ADMIN_EMAIL)
        self.becomeDbUser('postgres')
        super(TestPOTMsgSetMerging, self).setUpProduct()

    def test_matchedPOTMsgSetsShare(self):
        # Two identically-keyed POTMsgSets will share.  Where two
        # sharing templates had matching POTMsgSets, they will share
        # one.
        trunk_potmsgset = self.factory.makePOTMsgSet(
            self.trunk_template, singular='foo')
        self.factory.makePOTMsgSet(self.stable_template, singular='foo')

        self.merger.mergePOTMsgSets()

        trunk_messages = list(self.trunk_template.getPOTMsgSets(False))
        stable_messages = list(self.stable_template.getPOTMsgSets(False))

        self.assertEqual(trunk_messages, [trunk_potmsgset])
        self.assertEqual(trunk_messages, stable_messages)

    def test_mergePOTMsgSets_is_idempotent(self):
        # merge_potmsgsets can be run again on a situation it's
        # produced.  It will produce the same situation.
        trunk_potmsgset = self.factory.makePOTMsgSet(
            self.trunk_template, singular='foo')
        self.factory.makePOTMsgSet(self.stable_template, singular='foo')

        self.merger.mergePOTMsgSets()
        self.merger.mergePOTMsgSets()

        trunk_messages = list(self.trunk_template.getPOTMsgSets(False))
        stable_messages = list(self.stable_template.getPOTMsgSets(False))

        self.assertEqual(trunk_messages, [trunk_potmsgset])
        self.assertEqual(trunk_messages, stable_messages)

    def test_unmatchedPOTMsgSetsDoNotShare(self):
        # Only identically-keyed potmsgsets get merged.
        trunk_potmsgset = self.factory.makePOTMsgSet(
            self.trunk_template, singular='foo')
        stable_potmsgset = self.factory.makePOTMsgSet(
            self.stable_template, singular='foo', context='bar')

        self.merger.mergePOTMsgSets()

        trunk_messages = list(self.trunk_template.getPOTMsgSets(False))
        stable_messages = list(self.stable_template.getPOTMsgSets(False))

        self.assertNotEqual(trunk_messages, stable_messages)

        self.assertEqual(trunk_messages, [trunk_potmsgset])
        self.assertEqual(stable_messages, [stable_potmsgset])

    def test_sharingPreservesSequenceNumbers(self):
        # Sequence numbers are preserved when sharing.
        self.factory.makePOTMsgSet(
            self.trunk_template, singular='foo', sequence=3)
        self.factory.makePOTMsgSet(
            self.stable_template, singular='foo', sequence=9)

        self.merger.mergePOTMsgSets()

        trunk_potmsgset = self.trunk_template.getPOTMsgSetByMsgIDText('foo')
        stable_potmsgset = self.stable_template.getPOTMsgSetByMsgIDText('foo')
        self.assertEqual(trunk_potmsgset.getSequence(self.trunk_template), 3)
        self.assertEqual(
            stable_potmsgset.getSequence(self.stable_template), 9)


class TranslatedProductMixin(TranslatableProductMixin):
    """Like TranslatableProductMixin, but adds actual POTMsgSets.

    Also provides handy methods to set and verify translations for the
    POTMsgSets.

    Creates one POTMsgSet for trunk and one for stable, i.e. a
    pre-sharing situation.
    """

    def setUpProduct(self):
        super(TranslatedProductMixin, self).setUpProduct()

        self.trunk_potmsgset = self.factory.makePOTMsgSet(
            self.trunk_template, singular='foo')

        self.stable_potmsgset = self.factory.makePOTMsgSet(
            self.stable_template, singular='foo')

        self.msgid = self.trunk_potmsgset.msgid_singular

        self.dutch = getUtility(ILanguageSet).getLanguageByCode('nl')

        self.trunk_pofile = self.factory.makePOFile(
            'nl', potemplate=self.trunk_template,
            owner=self.trunk_template.owner)
        self.stable_pofile = self.factory.makePOFile(
            'nl', potemplate=self.stable_template,
            owner=self.trunk_template.owner)

    def _makeTranslationMessage(self, pofile, potmsgset, text, diverged):
        """Set a translation for given message in given translation."""
        if diverged:
            message = self.factory.makeDivergedTranslationMessage(
                pofile=pofile, potmsgset=potmsgset, translations=[text],
                translator=pofile.owner)
        else:
            message = self.factory.makeCurrentTranslationMessage(
                pofile=pofile, potmsgset=potmsgset, translations=[text],
                translator=pofile.owner)

        return message

    def _makeTranslationMessages(self, trunk_string, stable_string,
                                 trunk_diverged=True, stable_diverged=True):
        """Translate the POTMsgSets in our trunk and stable templates.

        :param trunk_string: translation string to use in trunk.
        :param stable_string: translation string to use in stable.
        :return: a pair of new TranslationMessages for trunk and
            stable, respectively.
        """
        trunk_potmsgset, stable_potmsgset = self._getPOTMsgSets()
        trunk_message = self._makeTranslationMessage(
            pofile=self.trunk_pofile, potmsgset=trunk_potmsgset,
            text=trunk_string, diverged=trunk_diverged)
        stable_message = self._makeTranslationMessage(
            pofile=self.stable_pofile, potmsgset=stable_potmsgset,
            text=stable_string, diverged=stable_diverged)

        return (trunk_message, stable_message)

    def _getPOTMsgSet(self, template):
        """Get POTMsgSet for given template."""
        return removeSecurityProxy(template)._getPOTMsgSetBy(
            msgid_singular=self.msgid, sharing_templates=True)

    def _getPOTMsgSets(self):
        """Get POTMsgSets in our trunk and stable series."""
        return (
            self._getPOTMsgSet(self.trunk_template),
            self._getPOTMsgSet(self.stable_template))

    def _getMessage(self, potmsgset, template):
        """Get TranslationMessage for given POTMsgSet in given template."""
        message = potmsgset.getCurrentTranslation(
            template, self.dutch, template.translation_side)
        if not message:
            # No diverged message here, so check for a shared one.
            message = potmsgset.getSharedTranslation(
                language=self.dutch, side=template.translation_side)
        return message

    def _getMessages(self):
        """Get current TranslationMessages in trunk and stable POTMsgSets."""
        trunk_potmsgset, stable_potmsgset = self._getPOTMsgSets()
        return (
            self._getMessage(trunk_potmsgset, self.trunk_template),
            self._getMessage(stable_potmsgset, self.stable_template))

    def _getTranslation(self, message):
        """Get (singular) translation string from TranslationMessage."""
        if message and message.translations:
            return message.translations[0]
        else:
            return None

    def _getTranslations(self):
        """Get translated strings for trunk and stable POTMsgSets."""
        (trunk_message, stable_message) = self._getMessages()
        return (
            self._getTranslation(trunk_message),
            self._getTranslation(stable_message))


class TestPOTMsgSetMergingAndTranslations(TestCaseWithFactory,
                                          TranslatedProductMixin):
    """Test how merging of POTMsgSets affects translations."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Set up test environment.

        The test setup includes:
         * Two templates for the "trunk" and "stable" release series.
         * Matching POTMsgSets for the string "foo" in each.

        The matching POTMsgSets will be merged by the mergePOTMsgSets
        call.
        """
        super(TestPOTMsgSetMergingAndTranslations, self).setUp(
            user=ADMIN_EMAIL)
        self.becomeDbUser('postgres')
        super(TestPOTMsgSetMergingAndTranslations, self).setUpProduct()

    def test_sharingDivergedMessages(self):
        # Diverged TranslationMessages stay with their respective
        # templates even if their POTMsgSets are merged.
        trunk_message, stable_message = self._makeTranslationMessages(
            'bar', 'splat', trunk_diverged=True, stable_diverged=True)
        trunk_message.is_current_upstream = True
        stable_message.is_current_upstream = True

        self.merger.mergePOTMsgSets()

        self.assertEqual(self._getTranslations(), ('bar', 'splat'))
        self.assertEqual(self._getMessages(), (trunk_message, stable_message))

    def test_mergingIdenticalSharedMessages(self):
        # Shared, identical TranslationMessages do not clash when their
        # POTMsgSets are merged; the POTMsgSet will still have the same
        # translations in the merged templates.
        trunk_message, stable_message = self._makeTranslationMessages(
            'bar', 'bar', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = True
        stable_message.is_current_upstream = True

        self.merger.mergePOTMsgSets()

        self.assertEqual(self._getTranslations(), ('bar', 'bar'))

    def test_mergingSharedMessages(self):
        # Shared TranslationMessages don't clash as a result of merging.
        # Instead, the most representative shared message survives as
        # shared.  The translation that "loses out" becomes diverged.
        trunk_message, stable_message = self._makeTranslationMessages(
            'bar2', 'splat2', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = True
        stable_message.is_current_upstream = True

        self.merger.mergePOTMsgSets()

        # The POTMsgSets are now merged.

        # The "losing" message stays current within its template.
        self.assertEqual(self._getTranslations(), ('bar2', 'splat2'))

        trunk_message, stable_message = self._getMessages()

        # The TranslationMessage for trunk remains the shared one.
        self.assertEqual(trunk_message.potemplate, None)
        # The "losing" message became diverged; it is now specific to
        # its original template.
        self.assertEqual(stable_message.potemplate, self.stable_template)

    def test_mergingIdenticalSuggestions(self):
        # Identical suggestions can be merged without breakage.
        trunk_message, stable_message = self._makeTranslationMessages(
            'bar', 'bar', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = False
        stable_message.is_current_upstream = False

        self.merger.mergePOTMsgSets()

        # Having these suggestions does not mean that there are current
        # translations.
        self.assertEqual(self._getTranslations(), (None, None))

    def test_clashingSharedTranslations(self):
        # When merging POTMsgSets that both have shared translations,
        # the most representative shared translation wins.
        trunk_message, stable_message = self._makeTranslationMessages(
            'foe', 'barr', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = True
        stable_message.is_current_upstream = True

        self.merger.mergePOTMsgSets()

        trunk_message, stable_message = self._getMessages()
        self.assertEqual(trunk_message.potemplate, None)

        # There are still two separate messages; the second (least
        # representative) one is diverged.
        self.assertNotEqual(trunk_message, stable_message)
        self.assertEqual(stable_message.potemplate, self.stable_template)

    def test_currentMessageDoesNotMergeIntoSuggestion(self):
        # A less-representative, current TranslationMessage is not merged
        # into an identical suggestion if the target already has another
        # translation for the same message.
        trunk_message, stable_message = self._makeTranslationMessages(
            'smurf', 'smurf', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = False
        stable_message.is_current_upstream = True

        current_message = self._makeTranslationMessage(
            self.trunk_pofile, trunk_message.potmsgset, 'bzo', False)
        current_message.is_current_upstream = True

        self.assertEqual(self._getTranslations(), ('bzo', 'smurf'))

        self.merger.mergePOTMsgSets()

        # The current translations stay as they are.
        self.assertEqual(self._getTranslations(), ('bzo', 'smurf'))

        # All three of the messages still exist, despite two of the
        # translations being near-identical.
        current_message, stable_message = self._getMessages()
        expected_tms = set([current_message, trunk_message, stable_message])
        tms = set(trunk_message.potmsgset.getAllTranslationMessages())
        self.assertEqual(tms, expected_tms)
        self.assertEqual(len(tms), 3)


class TestTranslationMessageNonMerging(TestCaseWithFactory,
                                       TranslatedProductMixin):
    """Test TranslationMessages that don't share."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationMessageNonMerging, self).setUp(user=ADMIN_EMAIL)
        self.becomeDbUser('postgres')
        super(TestTranslationMessageNonMerging, self).setUpProduct()

    def test_MessagesAreNotSharedAcrossPOTMsgSets(self):
        # Merging TranslationMessages does not merge messages that
        # belong to different POTMsgSets, no matter how similar they may
        # be.
        self._makeTranslationMessages('x', 'x')

        self.merger.mergeTranslationMessages()

        trunk_message, stable_message = self._getMessages()
        self.assertNotEqual(trunk_message, stable_message)

        # Each message may of course still become shared within the
        # context of its respective POTMsgSet.
        self.assertEqual(trunk_message.potemplate, None)
        self.assertEqual(stable_message.potemplate, None)


class TestTranslationMessageMerging(TestCaseWithFactory,
                                    TranslatedProductMixin):
    """Test merging of TranslationMessages."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationMessageMerging, self).setUp(user=ADMIN_EMAIL)
        self.becomeDbUser('postgres')
        super(TestTranslationMessageMerging, self).setUpProduct()

    def test_messagesCanStayDiverged(self):
        # When POTMsgSets with diverged translations are merged, the
        # most-representative translation becomes shared but the rest
        # stays diverged.
        self._makeTranslationMessages(
            'a', 'b', trunk_diverged=True, stable_diverged=True)

        self.merger.mergePOTMsgSets()
        self.merger.mergeTranslationMessages()

        # Translations for the existing templates stay as they are.
        self.assertEqual(self._getTranslations(), ('a', 'b'))

        trunk_message, stable_message = self._getMessages()
        self.assertNotEqual(trunk_message, stable_message)
        self.assertEqual(trunk_message.potemplate, None)
        self.assertEqual(stable_message.potemplate, self.stable_template)

    def test_sharingIdenticalMessages(self):
        # Identical translation messages are merged into one.
        self._makeTranslationMessages(
            'x', 'x', trunk_diverged=True, stable_diverged=True)

        self.merger.mergePOTMsgSets()
        self.merger.mergeTranslationMessages()

        trunk_message, stable_message = self._getMessages()
        self.assertEqual(trunk_message, stable_message)
        self.assertEqual(trunk_message.potemplate, None)

        # Translations for the existing templates stay as they are.
        self.assertEqual(self._getTranslations(), ('x', 'x'))

        # Redundant messages are deleted.
        tms = trunk_message.potmsgset.getAllTranslationMessages()
        self.assertEqual(list(tms), [trunk_message])

    def test_sharingSuggestions(self):
        # POTMsgSet merging may leave suggestions diverged.
        # TranslationMessage merging makes sure those are shared.
        trunk_message, stable_message = self._makeTranslationMessages(
            'gah', 'ulp', trunk_diverged=False, stable_diverged=True)

        trunk_message.is_current_upstream = False
        stable_message.is_current_upstream = False

        self.merger.mergePOTMsgSets()
        self.merger.mergeTranslationMessages()

        # Translations for the existing templates stay as they are.
        self.assertEqual(self._getTranslations(), (None, None))

        # Suggestions all become shared.
        self.assertEqual(trunk_message.potemplate, None)
        self.assertEqual(stable_message.potemplate, None)

    def test_mergingLessRepresentativeShared(self):
        # If a less-representative shared message is merged with a
        # more-representative diverged message, the previously shared
        # message stays the shared one.
        self._makeTranslationMessages(
            'ips', 'unq', trunk_diverged=True, stable_diverged=False)

        self.merger.mergePOTMsgSets()
        self.merger.mergeTranslationMessages()

        # Translations for the existing templates stay as they are.
        self.assertEqual(self._getTranslations(), ('ips', 'unq'))

        trunk_message, stable_message = self._getMessages()
        self.assertEqual(trunk_message.potemplate, self.trunk_template)
        self.assertEqual(stable_message.potemplate, None)

    def test_suggestionMergedIntoCurrentMessage(self):
        # A less-representative suggestion can be merged into an
        # existing, more-representative current message.  (If the
        # suggestion's POTMsgSet did not have a current translation,
        # this implies that it gains one).
        trunk_message, stable_message = self._makeTranslationMessages(
            'n', 'n', trunk_diverged=False, stable_diverged=True)
        stable_message.is_current_upstream = False

        self.assertEqual(self._getTranslations(), ('n', None))

        self.merger.mergePOTMsgSets()
        self.merger.mergeTranslationMessages()

        # The less-representative POTMsgSet gains a translation, because
        # it now uses the shared translation.
        self.assertEqual(self._getTranslations(), ('n', 'n'))

        trunk_message, stable_message = self._getMessages()
        self.assertEqual(trunk_message, stable_message)
        self.assertEqual(trunk_message.potemplate, None)
        self.assertTrue(trunk_message.is_current_upstream)

        # Redundant messages are deleted.
        tms = trunk_message.potmsgset.getAllTranslationMessages()
        self.assertEqual(list(tms), [trunk_message])


class TestRemoveDuplicates(TestCaseWithFactory, TranslatedProductMixin):
    """Test _scrubPOTMsgSetTranslations and friends."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestRemoveDuplicates, self).setUp(user=ADMIN_EMAIL)
        self.becomeDbUser('postgres')
        super(TestRemoveDuplicates, self).setUpProduct()

    def test_duplicatesAreCleanedUp(self):
        # The duplicates removal function cleans up any duplicate
        # TranslationMessages that might get in the way of merging.
        trunk_message, stable_message = self._makeTranslationMessages(
            'snaggle', 'snaggle')
        trunk_message.is_current_upstream = False
        trunk_message.sync()

        potmsgset = trunk_message.potmsgset

        stable_message.is_current_ubuntu = True
        stable_message.potemplate = trunk_message.potemplate
        stable_message.potmsgset = potmsgset
        stable_message.sync()

        # We've set up a situation where trunk has two identical
        # messages (one of which is current, the other imported) and
        # stable has none.
        self.assertEqual(self._getTranslations(), ('snaggle', None))
        tms = set(potmsgset.getAllTranslationMessages())
        self.assertEqual(tms, set([trunk_message, stable_message]))

        self.merger._removeDuplicateMessages()

        # The duplicates have been cleaned up.
        self.assertEqual(potmsgset.getAllTranslationMessages().count(), 1)

        # The is_current_upstream and is_current_ubuntu flags from the
        # duplicate messages have been merged into a single message,
        # current in both ubuntu and upstream.

        message = self._getMessage(potmsgset, self.trunk_template)
        self.assertTrue(message.is_current_upstream)
        self.assertTrue(message.is_current_ubuntu)

    def test_ScrubPOTMsgSetTranslationsWithoutDuplication(self):
        # _scrubPOTMsgSetTranslations eliminates duplicated
        # TranslationMessages.  If it doesn't find any, nothing happens.
        self._makeTranslationMessage(
            pofile=self.trunk_pofile, potmsgset=self.trunk_potmsgset,
            text='gbzidh', diverged=False)

        self.merger._scrubPOTMsgSetTranslations(self.trunk_potmsgset)

        message1, message2 = self._getMessages()
        self.assertIsNot(None, message1)
        self.assertIs(None, message2)

    def test_ScrubPOTMsgSetTranslationsWithDuplication(self):
        # If there are duplicate TranslationMessages, one inherits all
        # their is_current_upstream/is_is_current_ubuntu flags and the
        # others disappear.
        # XXX JeroenVermeulen 2009-06-15
        # spec=message-sharing-prevent-duplicates: We're going to have a
        # unique index for this.  When it becomes impossible to perform
        # this test, both it and _scrubPOTMsgSetTranslations can be
        # retired.
        message1, message2 = self._makeTranslationMessages(
            'tigidou', 'tigidou', trunk_diverged=True, stable_diverged=True)
        message2.is_current_upstream = False
        message2.is_current_ubuntu = True
        message2.potmsgset = self.trunk_potmsgset
        message2.potemplate = self.trunk_template

        self.merger._scrubPOTMsgSetTranslations(self.trunk_potmsgset)

        message, no_message = self._getMessages()

        # One of the two messages is now gone.
        self.assertIs(None, no_message)

        # The remaining message combines the flags from both its
        # predecessors.
        self.assertEqual(
            (message.is_current_upstream, message.is_current_ubuntu),
            (True, True))

    def test_FindCurrentClash(self):
        # _findClashes finds messages that would be "in the way" (as far
        # as the is_current_upstream/is_current_ubuntu flags are
        # concerned) if we try to move a message to another template and
        # potmsgset.
        trunk_message, stable_message = self._makeTranslationMessages(
            'ex', 'why', trunk_diverged=False, stable_diverged=False)
        ubuntu_clash, upstream_clash, twin = self.merger._findClashes(
            stable_message, self.trunk_potmsgset, None)

        # Moving stable_message fully into trunk would clash with
        # trunk_message.
        self.assertEqual(upstream_clash, trunk_message)

        # There's no conflict for the is_current_ubuntu flag.
        self.assertEqual(ubuntu_clash, None)

        # Nor does stable_message have a twin in trunk.
        self.assertEqual(twin, None)

    def test_FindUbuntuClash(self):
        # Finding is_current_ubuntu clashes works just like finding
        # is_current_upstream clashes.
        trunk_message, stable_message = self._makeTranslationMessages(
            'ex', 'why', trunk_diverged=False, stable_diverged=False)

        for message in (trunk_message, stable_message):
            message.is_current_upstream = False
            message.is_current_ubuntu = True

        ubuntu_clash, upstream_clash, twin = self.merger._findClashes(
            stable_message, self.trunk_potmsgset, None)

        self.assertEqual(upstream_clash, None)
        self.assertEqual(ubuntu_clash, trunk_message)
        self.assertEqual(twin, None)

    def test_FindTwin(self):
        # _findClashes also finds "twin" messages: ones with the same
        # translations, for the same language.
        trunk_message, stable_message = self._makeTranslationMessages(
            'klob', 'klob', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = False

        ubuntu_clash, upstream_clash, twin = self.merger._findClashes(
            stable_message, self.trunk_potmsgset, None)

        self.assertEqual(upstream_clash, None)
        self.assertEqual(ubuntu_clash, None)
        self.assertEqual(twin, trunk_message)

    def test_FindClashesWithTwin(self):
        # Clashes with a twin are ignored; they can be resolved by
        # merging messages.
        trunk_message, stable_message = self._makeTranslationMessages(
            'sniw', 'sniw', trunk_diverged=False, stable_diverged=False)

        ubuntu_clash, upstream_clash, twin = self.merger._findClashes(
            stable_message, self.trunk_potmsgset, None)

        self.assertEqual(upstream_clash, None)
        self.assertEqual(ubuntu_clash, None)
        self.assertEqual(twin, trunk_message)

    def test_FindClashesWithNonTwin(self):
        # _findClashes can find both a twin and a "flag conflict" in the
        # same place.
        trunk_message, stable_message = self._makeTranslationMessages(
            'sniw', 'sniw', trunk_diverged=False, stable_diverged=False)
        trunk_message.is_current_upstream = False
        current_message = self._makeTranslationMessage(
            self.trunk_pofile, self.trunk_potmsgset, 'gah', False)

        ubuntu_clash, upstream_clash, twin = self.merger._findClashes(
            stable_message, self.trunk_potmsgset, None)

        self.assertEqual(upstream_clash, current_message)
        self.assertEqual(ubuntu_clash, None)
        self.assertEqual(twin, trunk_message)


class TestSharingMigrationPerformance(TestCaseWithFactory,
                                      TranslatedProductMixin):
    """Test performance-related aspects of migration.

    Memory usage is a particular problem for this script, so this class
    particularly looks for regressions in that area.
    """
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestSharingMigrationPerformance, self).setUp()
        self.becomeDbUser('postgres')
        super(TestSharingMigrationPerformance, self).setUpProduct()

    def _flushDbObjects(self):
        """Flush ORM-backed objects from memory as much as possible.

        This involves a commit.
        """
        transaction.commit()
        gc.collect()

    def _resetReferences(self):
        """Reset translation-related references in the test object.

        This stops the test itself from pinning things in memory as
        caches are cleared.

        Transactions are committed and the templates list is discarded
        and rebuilt to get rid of pinned objects.
        """
        if self.templates is None:
            template_ids = []
        else:
            template_ids = [template.id for template in self.templates]

        self.templates = None
        self.trunk_potmsgset = None
        self.stable_potmsgset = None
        self.msgid = None
        self.trunk_pofile = None
        self.stable_pofile = None
        self._flushDbObjects()

        self.templates = [POTemplate.get(id) for id in template_ids]

    def assertNoStatementsInvolvingTable(self, table_name, statements):
        """The specified table name is not in any of the statements."""
        table_name = table_name.upper()
        self.assertFalse(
            any([table_name in statement.upper()
                 for statement in statements]))

    def test_merging_loads_no_msgids_or_potranslations(self):
        # Migration does not touch the POMsgID or POTranslation tables.
        self._makeTranslationMessages('x', 'y', trunk_diverged=True)
        self._makeTranslationMessages('1', '2', stable_diverged=True)
        self._resetReferences()
        self.assertNotEqual([], self.templates)

        with StormStatementRecorder() as recorder:
            self.merger.mergePOTMsgSets()
        self.assertNoStatementsInvolvingTable(
            POMsgID._table, recorder.statements)
        self.assertNoStatementsInvolvingTable(
            POTranslation._table, recorder.statements)

        with StormStatementRecorder() as recorder:
            self.merger.mergeTranslationMessages()
        self.assertNoStatementsInvolvingTable(
            POMsgID._table, recorder.statements)
        self.assertNoStatementsInvolvingTable(
            POTranslation._table, recorder.statements)


class TestFindMergablePackagings(TestCaseWithFactory):
    """Test TranslationMerger.findMergeablePackagings."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Remove sample data to simplify tests."""
        super(TestFindMergablePackagings, self).setUp()
        for packaging in set(TranslationMerger.findMergeablePackagings()):
            with person_logged_in(packaging.owner):
                packaging.destroySelf()

    def makePackagingLink(self, non_ubuntu=False):
        if non_ubuntu:
            distroseries = self.factory.makeDistroSeries()
        else:
            distroseries = self.factory.makeUbuntuDistroSeries()
        return self.factory.makePackagingLink(distroseries=distroseries)

    def test_no_templates(self):
        """A Packaging with no templates is ignored."""
        self.makePackagingLink()
        self.assertContentEqual(
            [], TranslationMerger.findMergeablePackagings())

    def test_no_product_template(self):
        """A Packaging with no product templates is ignored."""
        packaging = self.makePackagingLink()
        self.factory.makePOTemplate(sourcepackage=packaging.sourcepackage)
        self.assertContentEqual(
            [], TranslationMerger.findMergeablePackagings())

    def test_no_package_template(self):
        """A Packaging with no sourcepackage templates is ignored."""
        packaging = self.makePackagingLink()
        self.factory.makePOTemplate(productseries=packaging.productseries)
        self.assertContentEqual(
            [], TranslationMerger.findMergeablePackagings())

    def test_both_templates(self):
        """A Packaging with product and package templates is included."""
        packaging = self.makePackagingLink()
        self.factory.makePOTemplate(productseries=packaging.productseries)
        self.factory.makePOTemplate(sourcepackage=packaging.sourcepackage)
        self.assertContentEqual(
            [packaging], TranslationMerger.findMergeablePackagings())

    def test_multiple_templates(self):
        """A Packaging with multiple templates appears only once."""
        packaging = self.makePackagingLink()
        self.factory.makePOTemplate(productseries=packaging.productseries)
        self.factory.makePOTemplate(productseries=packaging.productseries)
        self.factory.makePOTemplate(sourcepackage=packaging.sourcepackage)
        self.factory.makePOTemplate(sourcepackage=packaging.sourcepackage)
        self.assertContentEqual(
            [packaging], TranslationMerger.findMergeablePackagings())

    def test_non_ubuntu(self):
        """A Packaging not for Ubuntu is ignored."""
        packaging = self.makePackagingLink(non_ubuntu=True)
        self.factory.makePOTemplate(productseries=packaging.productseries)
        self.factory.makePOTemplate(sourcepackage=packaging.sourcepackage)
        self.assertContentEqual(
            [], TranslationMerger.findMergeablePackagings())
