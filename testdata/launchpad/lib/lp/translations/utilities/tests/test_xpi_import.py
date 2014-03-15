# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for XPI file format"""
__metaclass__ = type

import re
import unittest

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.utilities.mozilla_xpi_importer import MozillaXpiImporter
from lp.translations.utilities.tests.helpers import (
    import_pofile_or_potemplate,
    )
from lp.translations.utilities.tests.xpi_helpers import (
    access_key_source_comment,
    command_key_source_comment,
    get_en_US_xpi_file_to_import,
    )


def unwrap(text):
    """Remove line breaks and any other wrapping artifacts from text."""
    return re.sub('\s+', ' ', text.strip())


class XpiTestCase(unittest.TestCase):
    """XPI file import into Launchpad."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        # Get the importer.
        self.importer = getUtility(IPersonSet).getByName('mark')

        # Get the Firefox template.
        firefox_product = getUtility(IProductSet).getByName('firefox')
        firefox_productseries = firefox_product.getSeries('trunk')
        firefox_potemplate_subset = getUtility(IPOTemplateSet).getSubset(
            productseries=firefox_productseries)
        self.firefox_template = firefox_potemplate_subset.new(
            name='firefox',
            translation_domain='firefox',
            path='en-US.xpi',
            owner=self.importer)
        self.spanish_firefox = self.firefox_template.newPOFile('es')
        self.spanish_firefox.path = 'translations/es.xpi'

    def setUpTranslationImportQueueForTemplate(self, subdir):
        """Return an ITranslationImportQueueEntry for testing purposes.

        :param subdir: subdirectory in firefox-data to get XPI data from.
        """
        # Get the file to import.
        en_US_xpi = get_en_US_xpi_file_to_import(subdir)
        return import_pofile_or_potemplate(
            file_contents=en_US_xpi.read(),
            person=self.importer,
            potemplate=self.firefox_template)

    def setUpTranslationImportQueueForTranslation(self, subdir):
        """Return an ITranslationImportQueueEntry for testing purposes.

        :param subdir: subdirectory in firefox-data to get XPI data from.
        """
        # Get the file to import. Given the way XPI file format works, we can
        # just use the same template file like a translation one.
        es_xpi = get_en_US_xpi_file_to_import(subdir)
        return import_pofile_or_potemplate(
            file_contents=es_xpi.read(),
            person=self.importer,
            pofile=self.spanish_firefox,
            by_maintainer=True)

    def _assertXpiMessageInvariant(self, message):
        """Check whether invariant part of all messages are correct."""
        # msgid and singular_text are always different except for the keyboard
        # shortcuts which are the 'accesskey' and 'commandkey' ones.
        self.failIf(
            (message.msgid_singular.msgid == message.singular_text and
             message.msgid_singular.msgid not in (
                u'foozilla.menu.accesskey', u'foozilla.menu.commandkey')),
            'msgid and singular_text should be different but both are %s' % (
                message.msgid_singular.msgid))

        # Plural forms should be None as this format is not able to handle
        # them.
        self.assertEquals(message.msgid_plural, None)
        self.assertEquals(message.plural_text, None)

        # There is no way to know whether a comment is from a
        # translator or a developer comment, so we have comenttext
        # always as None and store all comments as source comments.
        self.assertEquals(message.commenttext, u'')

        # This format doesn't support any functionality like .po flags.
        self.assertEquals(message.flagscomment, u'')

    def test_TemplateImport(self):
        """Test XPI template file import."""
        # Prepare the import queue to handle a new .xpi import.
        entry = self.setUpTranslationImportQueueForTemplate('en-US')

        # The status is now IMPORTED:
        self.assertEquals(entry.status, RosettaImportStatus.IMPORTED)

        # Let's validate the content of the messages.
        potmsgsets = list(self.firefox_template.getPOTMsgSets())

        messages_msgid_list = []
        for message in potmsgsets:
            messages_msgid_list.append(message.msgid_singular.msgid)

            # Check the common values for all messages.
            self._assertXpiMessageInvariant(message)

            if message.msgid_singular.msgid == u'foozilla.name':
                # It's a normal message that lacks any comment.

                self.assertEquals(message.singular_text, u'FooZilla!')
                self.assertEquals(
                    message.filereferences,
                    u'jar:chrome/en-US.jar!/test1.dtd(foozilla.name)')
                self.assertEquals(message.sourcecomment, None)

            elif message.msgid_singular.msgid == u'foozilla.play.fire':
                # This one is also a normal message that has a comment.

                self.assertEquals(
                    message.singular_text, u'Do you want to play with fire?')
                self.assertEquals(
                    message.filereferences,
                    u'jar:chrome/en-US.jar!/test1.dtd(foozilla.play.fire)')
                self.assertEquals(
                    message.sourcecomment,
                    u" Translators, don't play with fire! \n")

            elif message.msgid_singular.msgid == u'foozilla.utf8':
                # Now, we can see that special UTF-8 chars are extracted
                # correctly.
                self.assertEquals(
                    message.singular_text, u'\u0414\u0430\u043d=Day')
                self.assertEquals(
                    message.filereferences,
                    u'jar:chrome/en-US.jar!/test1.properties:5' +
                        u'(foozilla.utf8)')
                self.assertEquals(message.sourcecomment, None)
            elif message.msgid_singular.msgid == u'foozilla.menu.accesskey':
                # access key is a special notation that is supposed to be
                # translated with a key shortcut.
                self.assertEquals(
                    message.singular_text, u'M')
                self.assertEquals(
                    message.filereferences,
                    u'jar:chrome/en-US.jar!/subdir/test2.dtd' +
                        u'(foozilla.menu.accesskey)')
                # The comment shows the key used when there is no translation,
                # which is noted as the en_US translation.
                self.assertEquals(
                    unwrap(message.sourcecomment),
                    unwrap(access_key_source_comment))
            elif message.msgid_singular.msgid == u'foozilla.menu.commandkey':
                # command key is a special notation that is supposed to be
                # translated with a key shortcut.
                self.assertEquals(
                    message.singular_text, u'm')
                self.assertEquals(
                    message.filereferences,
                    u'jar:chrome/en-US.jar!/subdir/test2.dtd' +
                        u'(foozilla.menu.commandkey)')
                # The comment shows the key used when there is no translation,
                # which is noted as the en_US translation.
                self.assertEquals(
                    unwrap(message.sourcecomment),
                    unwrap(command_key_source_comment))

        # Check that we got all messages.
        self.assertEquals(
            [u'foozilla.happytitle', u'foozilla.menu.accesskey',
             u'foozilla.menu.commandkey', u'foozilla.menu.title',
             u'foozilla.name', u'foozilla.nocomment', u'foozilla.play.fire',
             u'foozilla.play.ice', u'foozilla.title', u'foozilla.utf8',
             u'foozilla_something'],
            sorted(messages_msgid_list))

    def test_TwiceTemplateImport(self):
        """Test a template import done twice."""
        # Prepare the import queue to handle a new .xpi import.
        entry = self.setUpTranslationImportQueueForTemplate('en-US')

        # The status is now IMPORTED:
        self.assertEquals(entry.status, RosettaImportStatus.IMPORTED)

        # Retrieve the number of messages we got in this initial import.
        first_import_potmsgsets = self.firefox_template.getPOTMsgSets(
            ).count()

        # Force the entry to be imported again:
        entry.setStatus(RosettaImportStatus.APPROVED,
                        getUtility(ILaunchpadCelebrities).rosetta_experts)
        # Now, we tell the PO template to import from the file data it has.
        (subject, body) = self.firefox_template.importFromQueue(entry)

        # Retrieve the number of messages we got in this second import.
        second_import_potmsgsets = self.firefox_template.getPOTMsgSets(
            ).count()

        # Both must match.
        self.assertEquals(first_import_potmsgsets, second_import_potmsgsets)

    def test_TranslationImport(self):
        """Test XPI translation file import."""
        # Prepare the import queue to handle a new .xpi import.
        template_entry = self.setUpTranslationImportQueueForTemplate('en-US')
        translation_entry = self.setUpTranslationImportQueueForTranslation(
            'en-US')

        # The status is now IMPORTED:
        self.assertEquals(
            translation_entry.status, RosettaImportStatus.IMPORTED)
        self.assertEquals(template_entry.status, RosettaImportStatus.IMPORTED)

        # Let's validate the content of the messages.
        potmsgsets = list(self.firefox_template.getPOTMsgSets())

        messages = [message.msgid_singular.msgid for message in potmsgsets]
        messages.sort()
        self.assertEquals(
            [u'foozilla.happytitle',
             u'foozilla.menu.accesskey',
             u'foozilla.menu.commandkey',
             u'foozilla.menu.title',
             u'foozilla.name',
             u'foozilla.nocomment',
             u'foozilla.play.fire',
             u'foozilla.play.ice',
             u'foozilla.title',
             u'foozilla.utf8',
             u'foozilla_something'],
            messages)

        potmsgset = self.firefox_template.getPOTMsgSetByMsgIDText(
            u'foozilla.name', context='main/test1.dtd')
        translation = potmsgset.getCurrentTranslation(
            self.firefox_template, self.spanish_firefox.language,
            self.firefox_template.translation_side)

        # It's a normal message that lacks any comment.
        self.assertEquals(potmsgset.singular_text, u'FooZilla!')

        # With this first import, upstream and Ubuntu translations must match.
        self.assertEquals(
            translation.translations,
            potmsgset.getOtherTranslation(
                self.spanish_firefox.language,
                self.firefox_template.translation_side).translations)

        potmsgset = self.firefox_template.getPOTMsgSetByMsgIDText(
            u'foozilla.menu.accesskey', context='main/subdir/test2.dtd')

        # access key is a special notation that is supposed to be
        # translated with a key shortcut.
        self.assertEquals(potmsgset.singular_text, u'M')
        # The comment shows the key used when there is no translation,
        # which is noted as the en_US translation.
        self.assertEquals(
            unwrap(potmsgset.sourcecomment),
            unwrap(access_key_source_comment))
        # But for the translation import, we get the key directly.
        self.assertEquals(
            potmsgset.getOtherTranslation(
                self.spanish_firefox.language,
                self.firefox_template.translation_side).translations,
            [u'M'])

        potmsgset = self.firefox_template.getPOTMsgSetByMsgIDText(
            u'foozilla.menu.commandkey', context='main/subdir/test2.dtd')
        # command key is a special notation that is supposed to be
        # translated with a key shortcut.
        self.assertEquals(
            potmsgset.singular_text, u'm')
        # The comment shows the key used when there is no translation,
        # which is noted as the en_US translation.
        self.assertEquals(
            unwrap(potmsgset.sourcecomment),
            unwrap(command_key_source_comment))
        # But for the translation import, we get the key directly.
        self.assertEquals(
            potmsgset.getOtherTranslation(
                self.spanish_firefox.language,
                self.firefox_template.translation_side).translations,
            [u'm'])

    def test_GetLastTranslator(self):
        """Tests whether we extract last translator information correctly."""
        translation_entry = self.setUpTranslationImportQueueForTranslation(
            'en-US')
        importer = MozillaXpiImporter()
        translation_file = importer.parse(translation_entry)

        # Let's try with the translation file, it has valid Last Translator
        # information.
        name, email = translation_file.header.getLastTranslator()
        self.assertEqual(name, u'Carlos Perell\xf3 Mar\xedn')
        self.assertEqual(email, u'carlos@canonical.com')

    def test_Contexts(self):
        """Test that message context in XPI file is set to chrome path."""
        queue_entry = self.setUpTranslationImportQueueForTranslation(
            'clashing_ids')
        importer = MozillaXpiImporter()
        template = importer.parse(queue_entry)

        messages = sorted([
            (message.msgid_singular, message.context, message.singular_text)
            for message in template.messages])
        self.assertEquals(
            [
             (u'foozilla.clashing.key',
              u'mac/extra.dtd',
              u'This message is Mac-specific, and comes from DTD.'),
             (u'foozilla.clashing.key',
              u'mac/extra.properties',
              u'This message is Mac-specific, and comes from properties.'),
             (u'foozilla.clashing.key',
              u'main/main.dtd',
              u'This message is in the main DTD.'),
             (u'foozilla.clashing.key',
              u'main/main.properties',
              u'This message is in the main properties file.'),
             (u'foozilla.clashing.key',
              u'unix/extra.dtd',
              u'This message is Unix-specific, and comes from DTD.'),
             (u'foozilla.clashing.key',
              u'unix/extra.properties',
              u'This message is Unix-specific, and comes from properties.'),
             (u'foozilla.clashing.key',
              u'win/extra.dtd',
              u'This message is Windows-specific, and comes from DTD.'),
             (u'foozilla.clashing.key',
              u'win/extra.properties',
              u'This message is Windows-specific, '
                  'and comes from properties.'),
             (u'foozilla.regular.message',
              u'main/main.dtd',
              u'A non-clashing message.'),
            ],
            messages)

    def test_SystemEntityIsIgnored(self):
        """Test handling of SYSTEM entities in DTD files."""
        self.setUpTranslationImportQueueForTemplate('system-entity')
        msgids = [
            (potmsgset.msgid_singular.msgid, potmsgset.singular_text)
            for potmsgset in self.firefox_template.getPOTMsgSets()]
        self.assertEqual(msgids, [
            ('firststring', 'First translatable string'),
            ('secondstring', 'Second translatable string')])
