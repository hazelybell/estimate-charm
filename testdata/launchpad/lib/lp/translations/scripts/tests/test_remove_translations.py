#! /usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `remove_translations` and the `RemoveTranslations` script."""

__metaclass__ = type

import logging
from optparse import (
    OptionParser,
    OptionValueError,
    )
from unittest import TestLoader

from storm.store import Store
from testtools.matchers import MatchesStructure
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy
from zope.testing.loghandler import Handler

from lp.registry.interfaces.person import IPersonSet
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    )
from lp.translations.model.translationrelicensingagreement import (
    TranslationRelicensingAgreement,
    )
from lp.translations.scripts.remove_translations import (
    process_options,
    remove_translations,
    RemoveTranslations,
    )


def make_script(args=None):
    """Create a `RemoveTranslations` script with given options."""
    if isinstance(args, basestring):
        args = [args]
    script = RemoveTranslations('remove-translations-test', test_args=args)
    script.logger.setLevel(logging.ERROR)
    return script


class TestRemoveTranslationsConstraints(TestCase):
    """Test safety net for translations removal options."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestRemoveTranslationsConstraints, self).setUp()
        # Acquire privileges to delete TranslationMessages.  We won't
        # actually do that here, but we'll go through all the motions.
        switch_dbuser('postgres')

    def _check_options(self, opts):
        """Get `_check_constraints_safety`'s answer for given options."""
        script = make_script(opts)
        process_options(script.options)
        return script._check_constraints_safety()

    def test_RecklessRemoval(self):
        # The script will refuse to run if no specific person or id is
        # targeted.  Operator error is more likely than a use case for
        # casually deleting lots of loosely-specified translations.
        opts = [
            '--language=pa',
            '--not-language',
            '--is-current-ubuntu=False',
            '--is-current-upstream=true',
            '--msgid=foo',
            '--origin=1',
            '--force',
            '--dry-run',
            ]
        script = make_script(opts)
        self.assertRaises(LaunchpadScriptFailure, script.main)

        # The same removal will work if we add, say, a submitter id.
        opts.append('--submitter=8134719')
        make_script(opts).main()

    def test_RemoveBySubmitter(self):
        # Removing all translations by one submitter is allowed.
        approval, message = self._check_options('--submitter=1')
        self.assertTrue(approval)

    def test_RemoveByReviewer(self):
        # Removing all translations by one reviewer is allowed.
        approval, message = self._check_options('--reviewer=1')
        self.assertTrue(approval)

    def test_RemoveById(self):
        # Removing by ids is allowed.
        approval, message = self._check_options(
            ['--id=1', '--id=2', '--id=3'])
        self.assertTrue(approval)

    def test_RemoveByPOFile(self):
        # Removing all translations for a template is not allowed by default.
        opts = ['--potemplate=1']
        approval, message = self._check_options(opts)
        self.assertFalse(approval)

        # The --force option overrides the safety check.
        opts.append('--force')
        approval, message = self._check_options(opts)
        self.assertIn("Safety override in effect", message)
        self.assertTrue(approval)

    def test_remove_by_license_rejection(self):
        # Can't just remove _all_ translations by people who rejected
        # the licensing agreement.
        approval, message = self._check_options(['--reject-license'])
        self.assertFalse(approval)

        # We can do that for the non-upstream ones, however...
        approval, message = self._check_options([
            '--reject-license', '--is-current-upstream=False'])
        self.assertTrue(approval)

        # ...though not for the upstream ones.
        approval, message = self._check_options([
            '--reject-license', '--is-current-upstream=True'])
        self.assertFalse(approval)

        # Similar for ones submitted directly in Launchpad.
        approval, message = self._check_options([
            '--reject-license', '--origin=ROSETTAWEB'])
        self.assertTrue(approval)
        approval, message = self._check_options([
            '--reject-license', '--origin=SCM'])
        self.assertFalse(approval)

        # We can bypass the check using --force.
        approval, message = self._check_options([
            '--reject-license', '--force'])
        self.assertTrue(approval)


class OptionChecker(OptionParser):
    """`OptionParser` that doesn't abort the whole program on error."""

    def error(self, msg):
        """See `OptionParser`.  Raises exception instead of exiting."""
        raise OptionValueError(msg)


def parse_opts(opts):
    """Simulate options being parsed by `LaunchpadScript`."""
    if isinstance(opts, basestring):
        opts = [opts]

    parser = OptionChecker()
    parser.add_options(RemoveTranslations.my_options)
    options, arguments = parser.parse_args(args=opts)
    process_options(options)
    return options


class TestRemoveTranslationsOptionsHandling(TestCase):
    """Test `RemoveTranslations`' options parsing and type checking."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestRemoveTranslationsOptionsHandling, self).setUp()
        self.factory = LaunchpadObjectFactory()

    def test_WithNativeArgs(self):
        # Options can be passed as the string representations of the
        # types the script wants them in.
        options = parse_opts([
            '--submitter=1',
            '--reviewer=2',
            '--id=3',
            '--id=4',
            '--potemplate=5',
            '--language=te',
            '--not-language',
            '--is-current-ubuntu=True',
            '--is-current-upstream=False',
            '--msgid=Hello',
            '--origin=1',
            '--force',
            ])
        self.assertThat(options, MatchesStructure.byEquality(
            submitter=1,
            reviewer=2,
            ids=[3, 4],
            potemplate=5,
            language='te',
            not_language=True,
            is_current_ubuntu=True,
            is_current_upstream=False,
            origin=1,
            force=True))

    def test_WithLookups(self):
        # The script can also look up some items from different
        # representations: person names, numbers or different case
        # settings for booleans, and translation origin identifiers.
        submitter = self.factory.makePerson()
        reviewer = self.factory.makePerson()

        options = parse_opts([
            '--submitter=%s' % submitter.name,
            '--reviewer=%s' % reviewer.name,
            '--is-current-ubuntu=0',
            '--is-current-upstream=true',
            '--origin=SCM',
            ])
        self.assertThat(options, MatchesStructure.byEquality(
            submitter=submitter.id,
            reviewer=reviewer.id,
            is_current_ubuntu=False,
            is_current_upstream=True,
            origin=RosettaTranslationOrigin.SCM.value))

    def test_BadBool(self):
        self.assertRaises(Exception, parse_opts, '--is-current-ubuntu=None')

    def test_UnknownPerson(self):
        self.assertRaises(
            Exception, parse_opts, '--reviewer=unknownnonexistentpersonbird')

    def test_UnknownOrigin(self):
        self.assertRaises(Exception, parse_opts, '--origin=GAGA')


class TestRemoveTranslations(TestCase):
    """Test `remove_translations`."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestRemoveTranslations, self).setUp()
        # Acquire privileges to delete TranslationMessages.  That's not
        # something we normally do.  Actually we should test under
        # rosettaadmin, but that user does not have all the privileges
        # needed to set up this test.  A separate doctest
        # remove-translations-by.txt tests a realistic run of the
        # remove-translations-by.py script under the actual rosettaadmin
        # db user.
        switch_dbuser('postgres')

        # Set up a template with Dutch and German translations.  The
        # messages we set up here are invariant; they remain untouched
        # by deletions done in the test case.
        self.factory = LaunchpadObjectFactory()
        self.nl_pofile = self.factory.makePOFile('nl')
        self.potemplate = self.nl_pofile.potemplate
        self.de_pofile = self.factory.makePOFile(
            'de', potemplate=self.potemplate)

        self.nl_message, self.de_message = self._makeMessages(
            "This message is not to be deleted.",
            "Dit bericht mag niet worden verwijderd.",
            "Diese Nachricht soll nicht erloescht werden.")

        self.untranslated_message = self.factory.makePOTMsgSet(
            self.potemplate, 'This message is untranslated.', sequence=0)

        self._checkInvariant()

    def _setTranslation(self, potmsgset, pofile, text, submitter=None,
                        is_current_upstream=False):
        """Set translation for potmsgset in pofile to text."""
        if submitter is None:
            submitter = self.potemplate.owner
        return self.factory.makeCurrentTranslationMessage(
            pofile, potmsgset, translator=submitter,
            translations={0: text}, current_other=is_current_upstream)

    def _makeMessages(self, template_text, nl_text, de_text,
                      submitter=None, is_current_upstream=False):
        """Create message, and translate it to Dutch & German."""
        message = self.factory.makePOTMsgSet(self.potemplate, template_text,
                                             sequence=0)
        new_nl_message = self._setTranslation(
            message, self.nl_pofile, nl_text, submitter=submitter,
            is_current_upstream=is_current_upstream)
        new_de_message = self._setTranslation(
            message, self.de_pofile, de_text, submitter=submitter,
            is_current_upstream=is_current_upstream)
        return new_nl_message, new_de_message

    def _getContents(self, pofile):
        return sorted(
            message.msgstr0.translation
            for message in pofile.translation_messages
            if message.msgstr0 is not None)

    def _checkInvariant(self):
        """Check that our translations are in their original state.

        Tests in this test case don't work in the usual way, by making
        changes and then testing for them.  Instead they make changes by
        creating new messages, and then using `remove_translations` to
        undo those changes.

        We see that a removal worked correctly by verifying that the
        invariant is restored.
        """
        # First make sure we're not reading out of cache.
        Store.of(self.nl_pofile).flush()

        self.assertEqual(
            self._getContents(self.nl_pofile),
            ["Dit bericht mag niet worden verwijderd."])
        self.assertEqual(
            self._getContents(self.de_pofile),
            ["Diese Nachricht soll nicht erloescht werden."])

    def _removeMessages(self, **kwargs):
        """Front-end for `remove_translations`.  Flushes changes first."""
        Store.of(self.potemplate).flush()
        return remove_translations(**kwargs)

    def test_RemoveNone(self):
        # If no messages match the given constraints, nothing is
        # deleted.
        rowcount = self._removeMessages(
            submitter=1, ids=[self.de_message.id], language_code='br')
        self.assertEqual(rowcount, 0)
        self._checkInvariant()

    def test_RemoveById(self):
        # We can remove messages by id.  Other messages are not
        # affected.
        new_nl_message1 = self._setTranslation(
            self.untranslated_message, self.nl_pofile, "A Dutch translation")
        new_nl_message2 = self._setTranslation(
            self.untranslated_message, self.nl_pofile, "Double Dutch")
        self.assertEqual(
            self._getContents(self.nl_pofile), [
                "A Dutch translation",
                "Dit bericht mag niet worden verwijderd.",
                "Double Dutch",
                ])

        rowcount = self._removeMessages(
            ids=[new_nl_message1.id, new_nl_message2.id])

        self.assertEqual(rowcount, 2)
        self._checkInvariant()

    def test_RemoveBySubmitter(self):
        # Remove messages by submitter id.
        carlos = getUtility(IPersonSet).getByName('carlos')
        (new_nl_message, new_de_message) = self._makeMessages(
            "Submitted by Carlos", "Ingevoerd door Carlos",
            "Von Carlos eingefuehrt", submitter=carlos)

        # Ensure that at least one message's reviewer is not the same
        # as the submitter, so we know we're not accidentally matching
        # on reviewer instead.
        new_nl_message.reviewer = self.potemplate.owner

        self._removeMessages(submitter=carlos)
        self._checkInvariant()

    def test_RemoveByReviewer(self):
        # Remove messages by reviewer id.
        carlos = getUtility(IPersonSet).getByName('carlos')
        (new_nl_message, new_de_message) = self._makeMessages(
            "Submitted by Carlos", "Ingevoerd door Carlos",
            "Von Carlos eingefuehrt")
        new_nl_message.reviewer = carlos
        new_de_message.reviewer = carlos

        self._removeMessages(reviewer=carlos)
        self._checkInvariant()

    def test_RemoveByTemplate(self):
        # Remove messages by template.  Limit this deletion by ids as
        # well to avoid breaking the test invariant.  To show that the
        # template limitation really does add a limit on top of the ids
        # themselves, we also pass the id of another message in a
        # different template.  That message is not deleted.
        (new_nl_message, new_de_message) = self._makeMessages(
            "Foo", "Foe", "Fu")

        unrelated_nl_pofile = self.factory.makePOFile('nl')
        potmsgset = self.factory.makePOTMsgSet(
            unrelated_nl_pofile.potemplate, 'Foo',
            sequence=0)
        unrelated_nl_message = self.factory.makeCurrentTranslationMessage(
            unrelated_nl_pofile, potmsgset,
            translator=unrelated_nl_pofile.potemplate.owner,
            translations={0: "Foe"})

        ids = [new_nl_message.id, new_de_message.id, unrelated_nl_message.id]
        self._removeMessages(
            ids=ids, potemplate=self.potemplate.id)

        self._checkInvariant()
        self.assertEqual(self._getContents(unrelated_nl_pofile), ["Foe"])

    def test_RemoveByLanguage(self):
        # Remove messages by language.  Pass the ids of one Dutch
        # message and one German message, but specify Dutch as the
        # language to delete from; only the Dutch message is deleted.
        potmsgset = self.factory.makePOTMsgSet(self.potemplate, 'Bar',
                                               sequence=0)
        message = self._setTranslation(potmsgset, self.nl_pofile, 'Cafe')

        self._removeMessages(
            ids=[message.id, self.de_message.id], language_code='nl')

        self._checkInvariant()

    def test_RemoveByNotLanguage(self):
        # Remove messages, but spare otherwise matching messages that
        # are in German.
        potmsgset = self.factory.makePOTMsgSet(self.potemplate, 'Hi',
                                               sequence=0)
        message = self._setTranslation(potmsgset, self.nl_pofile, 'Hoi')

        self._removeMessages(
            ids=[message.id, self.de_message.id], language_code='de',
            not_language=True)

        self._checkInvariant()

    def test_RemoveCurrent(self):
        # Remove current messages, but not non-current messages.
        (new_nl_message, new_de_message) = self._makeMessages(
            "translate", "vertalen", "uebersetzen")
        self.nl_message.is_current_upstream = False

        messages_to_delete = [self.nl_message, new_nl_message, new_de_message]
        current_upstream_messages = [
            message for message in messages_to_delete
            if message.is_current_upstream]
        ids = [message.id for message in messages_to_delete]
        logger = logging.getLogger('test_remove_translations')
        logger.setLevel(logging.WARN)
        loghandler = Handler(self)
        loghandler.add(logger.name)
        self._removeMessages(ids=ids, is_current_upstream=True, logger=logger)

        self.nl_message.is_current_upstream = True
        self._checkInvariant()
        loghandler.assertLogsMessage(
            'Deleting messages currently in use:', level=logging.WARN)
        for message in current_upstream_messages:
            loghandler.assertLogsMessage(
                'Message %i is a current translation in upstream'
                % message.id,
                level=logging.WARN)
        self.assertEqual(
            1 + len(current_upstream_messages), len(loghandler.records))

    def test_RemoveNotCurrent(self):
        # Remove current messages, but not non-current messages.
        (new_nl_message, new_de_message) = self._makeMessages(
            "write", "schrijven", "schreiben")
        new_nl_message.is_current_upstream = False
        new_de_message.is_current_upstream = False

        ids = [self.nl_message.id, new_nl_message.id, new_de_message.id]
        self._removeMessages(ids=ids, is_current_upstream=False)

        self._checkInvariant()

    def test_RemoveImported(self):
        # Remove current messages, but not non-current messages.
        (new_nl_message, new_de_message) = self._makeMessages(
            "book", "boek", "Buch")
        new_nl_message.is_current_ubuntu = True
        new_de_message.is_current_ubuntu = True

        ids = [self.nl_message.id, new_nl_message.id, new_de_message.id]
        self._removeMessages(ids=ids, is_current_ubuntu=True)

        self._checkInvariant()

    def test_RemoveNotImported(self):
        # Remove current messages, but not non-current messages.
        (new_nl_message, new_de_message) = self._makeMessages(
            "helicopter", "helikopter", "Hubschauber")
        self.nl_message.is_current_ubuntu = True

        ids = [self.nl_message.id, new_nl_message.id, new_de_message.id]
        self._removeMessages(ids=ids, is_current_ubuntu=False)

        self.nl_message.is_current_ubuntu = False
        self._checkInvariant()

    def test_RemoveMsgId(self):
        # Remove translations by msgid_singular.
        (new_nl_message, new_de_message) = self._makeMessages(
            "save", "bewaren", "speichern")

        self._removeMessages(msgid_singular="save")

        self._checkInvariant()

    def test_RemoveOrigin(self):
        # Remove translations by origin.
        self.assertEqual(
            self.nl_message.origin, RosettaTranslationOrigin.ROSETTAWEB)
        (new_nl_message, new_de_message) = self._makeMessages(
            "new", "nieuw", "neu", is_current_upstream=True)
        removeSecurityProxy(new_nl_message).origin = (
            RosettaTranslationOrigin.SCM)
        removeSecurityProxy(new_de_message).origin = (
            RosettaTranslationOrigin.SCM)

        self._removeMessages(
            potemplate=self.potemplate, origin=RosettaTranslationOrigin.SCM)

        self._checkInvariant()

    def test_remove_by_license_rejection(self):
        # Remove translations submitted by users who rejected the
        # licensing agreement.
        refusenik = self.factory.makePerson()

        self._makeMessages(
            "Don't download this song", "Niet delen", "Nicht teilen",
            submitter=refusenik)

        TranslationRelicensingAgreement(
            person=refusenik, allow_relicensing=False)

        self._removeMessages(reject_license=True)

        self._checkInvariant()

    def test_remove_unlicensed_none(self):
        # Removing translations whose submitters rejected our
        # translations licence does not affect translations by those who
        # haven't answered the question yet.
        self._removeMessages(reject_license=True)

        self._checkInvariant()

    def test_remove_unlicensed_when_licensed(self):
        # Removing translations whose submitters rejected our
        # translations licence does not affect translations by those who
        # agreed to license.
        answer = TranslationRelicensingAgreement(
            person=self.nl_message.submitter, allow_relicensing=True)

        try:
            self._removeMessages(reject_license=True)
            self._checkInvariant()
        finally:
            # Clean up.
            answer.destroySelf()

    def test_remove_unlicensed_restriction(self):
        # When removing unlicensed translations, other restrictions
        # still apply.
        self.nl_message.is_current_upstream = True
        self.de_message.is_current_upstream = True
        answer = TranslationRelicensingAgreement(
            person=self.nl_message.submitter, allow_relicensing=False)

        try:
            self._removeMessages(
                reject_license=True, is_current_upstream=False)
            self._checkInvariant()
        finally:
            # Clean up.
            answer.destroySelf()


class TestRemoveTranslationsUnmasking(TestCaseWithFactory):
    """Test that `remove_translations` "unmasks" upstream messages.

    When a shared current Ubuntu message is deleted, the deletion
    code checks whether there is also an upstream translation.  If there
    was, it makes sense to make the upstream message the current Ubuntu
    message (as it would have been if the deleted message had never been
    there in the first place).
    """
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestRemoveTranslationsUnmasking, self).setUp()
        switch_dbuser('postgres')

        # Set up a template with a Laotian translation file.  There's
        # one message to be translated.
        potemplate = self.factory.makePOTemplate()
        self.potmsgset = self.factory.makePOTMsgSet(
            potemplate, 'foo', sequence=0)
        self.pofile = self.factory.makePOFile('lo', potemplate=potemplate)

        self.ubuntu = self.factory.makeCurrentTranslationMessage(
            self.pofile, self.potmsgset, current_other=True)
        self.upstream = self.factory.makeCurrentTranslationMessage(
            self.pofile, self.potmsgset, current_other=False)
        Store.of(self.upstream).flush()
        self.assertFalse(
            self.upstream.is_current_ubuntu, "Broken test setup.")
        self.assertTrue(
            self.upstream.is_current_upstream, "Broken test setup.")
        self.assertTrue(self.ubuntu.is_current_ubuntu, "Broken test setup.")
        self.assertFalse(
            self.ubuntu.is_current_upstream, "Broken test setup.")

    def test_unmask_upstream_message(self):
        # Basic use case: upstream message is unmasked.
        remove_translations(ids=[self.ubuntu.id])
        Store.of(self.upstream).autoreload()
        self.assertTrue(self.upstream.is_current_upstream)
        self.assertTrue(self.upstream.is_current_ubuntu)

    def test_unmask_right_message(self):
        # Unmasking picks the right message, and doesn't try to violate
        # the unique constraint on is_current_upstream.
        inactive = self.factory.makeSuggestion(self.pofile, self.potmsgset)
        remove_translations(ids=[self.ubuntu.id])
        Store.of(self.upstream).autoreload()
        self.assertTrue(self.upstream.is_current_ubuntu)
        self.assertFalse(inactive.is_current_ubuntu)


def test_suite():
    # Removing TranslationMessage rows requires special database privileges.
    return TestLoader().loadTestsFromName(__name__)
