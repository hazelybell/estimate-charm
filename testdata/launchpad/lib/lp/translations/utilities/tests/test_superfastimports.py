# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )
from lp.translations.utilities.translation_import import (
    ExistingPOFileInDatabase,
    )


class TestSuperFastImports(TestCaseWithFactory):
    """Test how ExistingPOFileInDatabase cache works."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Set up a single POFile in the database to be cached and
        # examined.
        super(TestSuperFastImports, self).setUp()

    def getTranslationMessageData(self, translationmessage):
        # Convert a TranslationMessage to TranslationMessageData object,
        # which is used during import.
        potmsgset = translationmessage.potmsgset
        message_data = TranslationMessageData()
        message_data.context = potmsgset.context
        message_data.msgid_singular = potmsgset.singular_text
        message_data.msgid_plural = potmsgset.plural_text
        translations = translationmessage.translations
        for plural_form, translation in enumerate(translations):
            message_data.addTranslation(plural_form, translation)
        return message_data

    def _makeUpstreamPOFile(self):
        """Create a `POFile` for an upstream project."""
        pofile = self.factory.makePOFile()
        self.assertIsNot(None, pofile.potemplate.productseries)
        return pofile

    def _makeUbuntuPOFile(self):
        """Create a `POFile` for a distribution package."""
        package = self.factory.makeSourcePackage()
        potemplate = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        return self.factory.makePOFile(potemplate=potemplate)

    def test_caches_current_upstream_message(self):
        # Current upstream TranslationMessages are properly cached in
        # ExistingPOFileInDatabase.
        pofile = self._makeUpstreamPOFile()
        current_message = self.factory.makeCurrentTranslationMessage(
            pofile=pofile)
        cached_file = ExistingPOFileInDatabase(pofile)
        message_data = self.getTranslationMessageData(current_message)
        self.assertTrue(cached_file.isAlreadyTranslatedTheSame(message_data))

    def test_caches_current_ubuntu_message(self):
        pofile = self._makeUbuntuPOFile()
        current_message = self.factory.makeCurrentTranslationMessage(
            pofile=pofile)
        cached_file = ExistingPOFileInDatabase(pofile)
        message_data = self.getTranslationMessageData(current_message)
        self.assertTrue(cached_file.isAlreadyTranslatedTheSame(message_data))

    def test_does_not_cache_inactive_message(self):
        # Non-current messages (i.e. suggestions) are not cached in
        # ExistingPOFileInDatabase.
        pofile = self._makeUpstreamPOFile()
        inactive_message = self.factory.makeSuggestion(pofile=pofile)
        cached_file = ExistingPOFileInDatabase(pofile)
        message_data = self.getTranslationMessageData(inactive_message)
        self.assertFalse(cached_file.isAlreadyTranslatedTheSame(message_data))

    def test_does_not_cache_upstream_message_for_ubuntu_import(self):
        pofile = self._makeUbuntuPOFile()
        upstream_message = self.factory.makeSuggestion(pofile=pofile)
        upstream_message.is_current_upstream = True

        cached_file = ExistingPOFileInDatabase(pofile)
        message_data = self.getTranslationMessageData(upstream_message)
        self.assertFalse(cached_file.isAlreadyTranslatedTheSame(message_data))

    def test_does_not_cache_ubuntu_message_for_upstream_import(self):
        pofile = self._makeUpstreamPOFile()
        ubuntu_message = self.factory.makeSuggestion(pofile=pofile)
        ubuntu_message.is_current_ubuntu = True

        cached_file = ExistingPOFileInDatabase(pofile)
        message_data = self.getTranslationMessageData(ubuntu_message)
        self.assertFalse(cached_file.isAlreadyTranslatedTheSame(message_data))

    def test_query_timeout(self):
        # Test that super-fast-imports doesn't cache anything when it hits
        # a timeout.
        pofile = self.factory.makePOFile()

        # Add a message that would otherwise be cached (see other tests).
        current_message = self.factory.makeCurrentTranslationMessage(
            pofile=pofile)
        message_data = self.getTranslationMessageData(current_message)
        cached_file = ExistingPOFileInDatabase(pofile, simulate_timeout=True)
        self.assertFalse(cached_file.isAlreadyTranslatedTheSame(message_data))
