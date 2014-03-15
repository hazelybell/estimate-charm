# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'MixedNewlineMarkersError',
    'sanitize_translations_from_webui',
    'sanitize_translations_from_import',
    ]


class MixedNewlineMarkersError(ValueError):
    """Exception raised when we detect mixing of new line markers.

    Raised when the sanitization code detects that a msgid or msgstr uses
    more than one style of newline markers (windows, mac, unix).
    """


class Sanitizer(object):
    """Provide a function to sanitize a translation text."""

    # There are three different kinds of newlines:
    windows_style = u'\r\n'
    mac_style = u'\r'
    unix_style = u'\n'
    mixed_style = object()

    dot_char = u'\u2022'

    def __init__(self, english_singular):
        """Extract information from the English singular."""
        # Does the dot character appear in the Eglish singular?
        self.has_dots = self.dot_char in english_singular
        # Find out if there is leading or trailing whitespace in the English
        # singular.
        stripped_singular_text = english_singular.strip()
        self.is_empty_stripped = stripped_singular_text == ""
        if len(stripped_singular_text) != len(english_singular):
            # There is whitespace that we should copy to the 'text'
            # after stripping it.
            self.prefix = english_singular[:-len(english_singular.lstrip())]
            self.postfix = english_singular[len(english_singular.rstrip()):]
        else:
            self.prefix = ''
            self.postfix = ''
        # Get the newline style that is used in the English Singular.
        self.newline_style = self._getNewlineStyle(english_singular)

    @classmethod
    def _getNewlineStyle(cls, text):
        """Find out which newline style is used in text."""
        style = None
        # To avoid confusing the single-character newline styles for mac and
        # unix with the two-character windows one, remove the windows-style
        # newlines from the text and use that text to search for the other
        # two.
        stripped_text = text.replace(cls.windows_style, u'')
        if text != stripped_text:
            # Text contains windows style new lines.
            style = cls.windows_style

        for one_char_style in (cls.mac_style, cls.unix_style):
            if one_char_style in stripped_text:
                if style is not None:
                    return cls.mixed_style
                style = one_char_style

        return style

    def sanitize(self, translation_text):
        """Return 'translation_text' or None after doing some sanitization.

        The text is sanitized through the following filters:

          self.convertDotToSpace
          self.normalizeWhitespaces
          self.normalizeNewlines

        If the resulting string after these operations is an empty string,
        it returns None.

        :param english_singular: The text of the singular MsgId that this
            translation is for.
        :param translation_text: A unicode text that needs to be sanitized.
        """
        if translation_text is None:
            return None

        # Fix the visual point that users copy & paste from the web interface.
        new_text = self.convertDotToSpace(translation_text)
        # Now, fix the newline chars.
        new_text = self.normalizeNewlines(new_text)
        # Finally, set the same whitespace at the start/end of the string.
        new_text = self.normalizeWhitespace(new_text)
        # Also, if it's an empty string, replace it with None.
        if new_text == '':
            new_text = None

        return new_text

    def convertDotToSpace(self, translation_text):
        """Return 'translation_text' with the 'dot' char exchanged with a
        normal space.

        If the english_singular contains that character, 'translation_text' is
        returned without changes as it's a valid char instead of our way to
        represent a normal space to the user.
        """
        if self.has_dots or self.dot_char not in translation_text:
            return translation_text

        return translation_text.replace(u'\u2022', ' ')

    def normalizeWhitespace(self, translation_text):
        """Return 'translation_text' with the same trailing and leading
        whitespace that self.singular_text has.

        If 'translation_text' has only whitespace but english_singular has
        other characters, the empty string (u'') is returned to note it as an
        untranslated string.
        """
        if translation_text is None:
            return None

        stripped_translation_text = translation_text.strip()

        if not self.is_empty_stripped and len(stripped_translation_text) == 0:
            return ''

        return '%s%s%s' % (
            self.prefix, stripped_translation_text, self.postfix)

    def normalizeNewlines(self, translation_text):
        """Return 'translation_text' with newlines sync with english_singular.

        Raises an exception if the text has mixed newline styles.
        """
        if self.newline_style is None:
            # No newlines in the English singular, so we have nothing to do.
            return translation_text

        # Get the style that is used in the given text.
        translation_newline_style = self._getNewlineStyle(translation_text)

        if translation_newline_style == self.mixed_style:
            # The translation has mixed newlines in it; that is not allowed.
            raise MixedNewlineMarkersError(
                "Translations text (%r) mixes different newline markers." %
                    translation_text)

        if translation_newline_style is None:
            # The translation text doesn't contain any newlines, so there is
            # nothing for us to do.
            return translation_text

        if self.newline_style is self.mixed_style:
            # The original has mixed newlines (some very old data are like
            # this, new data with mixed newlines are rejected), so we're just
            # going to punt and normalize to unix style.
            return translation_text.replace(
                translation_newline_style, self.unix_style)
        else:
            # Otherwise the translation text should be normalized to use the
            # same newline style as the original.
            return translation_text.replace(
                translation_newline_style, self.newline_style)


def sanitize_translations(
        english_singular, translations, pluralforms):
    """Sanitize `translations` using sanitize_translation.

    If there is no certain pluralform in `translations`, set it to None.
    If there are `translations` with greater pluralforms than allowed,
    sanitize and keep them.
    :param english_singular: The text of the singular MsgId that these
        translations are for.
    :param translations: A dictionary of plural forms, with the
        integer plural form number as the key and the translation as the
        value.
    :param pluralforms: The number of expected pluralforms
    """
    # Sanitize all given translations.
    # Make sure the translations are stored in a dict.
    if isinstance(translations, (list, tuple)):
        translations = dict(enumerate(translations))
    # Unneeded plural forms are stored as well (needed since we may
    # have incorrect plural form data, so we can just reactivate them
    # once we fix the plural information for the language)
    sanitized_translations = {}
    sanitizer = Sanitizer(english_singular)
    for form, text in translations.items():
        sanitized_translations[form] = sanitizer.sanitize(text)

    # Expected plural forms should all exist and empty translations should
    # be normalized to None.
    if pluralforms is None:
        pluralforms = 2
    for pluralform in range(pluralforms):
        if pluralform not in sanitized_translations:
            sanitized_translations[pluralform] = None

    return sanitized_translations


def sanitize_translations_from_import(
        english_singular, translations, pluralforms):
    # At import time we want to ensure that the english_singular does not
    # contain mixed newline styles.
    if Sanitizer._getNewlineStyle(english_singular) is Sanitizer.mixed_style:
        raise MixedNewlineMarkersError(
            "Original text (%r) mixes different newline markers." %
                english_singular)
    return sanitize_translations(english_singular, translations, pluralforms)


def sanitize_translations_from_webui(
        english_singular, translations, pluralforms):
    return sanitize_translations(english_singular, translations, pluralforms)
