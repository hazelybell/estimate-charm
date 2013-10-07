# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common file format classes shared across all formats."""

__metaclass__ = type

__all__ = [
    'TranslationFileData',
    'TranslationMessageData',
    ]

from zope.interface import implements

from lp.translations.interfaces.translationcommonformat import (
    ITranslationFileData,
    ITranslationMessageData,
    )
from lp.translations.interfaces.translationimporter import (
    TranslationFormatSyntaxError,
    )


class TranslationFileData:
    """See `ITranslationFileData`."""
    implements(ITranslationFileData)

    def __init__(self):
        self.header = None
        self.messages = []
        self.path = None
        self.translation_domain = None
        self.is_template = None
        self.language_code = None
        self.syntax_warnings = []


class TranslationMessageData:
    """See `ITranslationMessageData`."""
    implements(ITranslationMessageData)

    def __init__(self):
        self.msgid_singular = None
        self.msgid_plural = None
        self.singular_text = None
        self.plural_text = None
        self.context = None
        self._translations = []
        self.comment = u''
        self.source_comment = u''
        self.file_references = u''
        self.flags = set()
        self.is_obsolete = False

    @property
    def translations(self):
        """See `ITranslationMessageData`."""
        return self._translations

    def addTranslation(self, plural_form, translation):
        """See `ITranslationMessageData`."""
        # Unlike msgids, we can't assume that groups of translations are
        # contiguous. I.e. we might get translations for plural forms 0 and 2,
        # but not 1. This means we need to add empty values if plural_form >
        # len(self._translations).
        #
        # We raise an error if plural_form < len(self.translations) and
        # self.translations[plural_form] is not None.
        assert plural_form is not None, 'plural_form cannot be None!'

        is_duplicate = (
            plural_form < len(self._translations) and
            self._translations[plural_form] is not None and
            self._translations[plural_form] != translation)
        if is_duplicate:
            error = (
                "Message has more than one translation for plural form %d." %
                plural_form)
            raise TranslationFormatSyntaxError(message=error)

        if plural_form >= len(self.translations):
            # There is a hole in the list of translations so we fill it with
            # None.
            self._translations.extend(
                [None] * (1 + plural_form - len(self._translations)))

        self._translations[plural_form] = translation

    def resetAllTranslations(self):
        """See `ITranslationMessageData`."""
        self._translations = []

