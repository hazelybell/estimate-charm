# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Export module for gettext's .po file format.

Find more about this file format at:
http://www.gnu.org/software/gettext/manual/html_node/PO-Files.html
"""

__metaclass__ = type

__all__ = [
    'GettextPOChangedExporter',
    'GettextPOExporter',
    ]

import logging
import os

from zope.interface import implements

from lp.translations.interfaces.translationexporter import (
    ITranslationFormatExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )


def strip_last_newline(text):
    """Return text with the final newline/carriage return stripped."""
    if text.endswith('\r\n'):
        return text[:-2]
    elif text[-1] in '\r\n':
        return text[:-1]
    else:
        return text


def comments_text_representation(translation_message):
    """Return text representation of the comments.

    :param translation_message: An ITranslationMessageData that will get
        comments exported.
    """
    comment_lines = []
    comment_lines_previous_msgids = []
    # Previous msgsid comments (indicated by a | symbol) have to come
    # after the other comments to preserve the order expected by msgfmt.
    if translation_message.comment:
        unparsed_comment = strip_last_newline(translation_message.comment)
        for line in unparsed_comment.split('\n'):
            if line.startswith('|'):
                if translation_message.is_obsolete:
                    comment_prefix = u'#~'
                else:
                    comment_prefix = u'#'
                comment_lines_previous_msgids.append(comment_prefix + line)
            else:
                comment_lines.append(u'#' + line)
    if not translation_message.is_obsolete:
        # Source comments are only exported if it's not an obsolete entry.
        if translation_message.source_comment:
            unparsed_comment = (
                strip_last_newline(translation_message.source_comment))
            for line in unparsed_comment.split('\n'):
                comment_lines.append(u'#. ' + line)
        if translation_message.file_references:
            for line in translation_message.file_references.split('\n'):
                comment_lines.append(u'#: ' + line)
    if translation_message.flags:
        flags = sorted(translation_message.flags)
        if 'fuzzy' in flags:
            # Force 'fuzzy' to be the first flag in the list like gettext's
            # tools do.
            flags.remove('fuzzy')
            flags.insert(0, 'fuzzy')
        comment_lines.append(u'#, %s' % u', '.join(flags))

    return u'\n'.join(comment_lines + comment_lines_previous_msgids)


def wrap_text(text, prefix, wrap_width):
    """Return a list of strings with the given text wrapped to given width.

    We are not using textwrap module because the .po file format has some
    peculiarities like:

    msgid ""
    "a really long line."

    instead of:

    msgid "a really long"
    "line."

    with a wrapping width of 21.

    :param text: Unicode string to wrap.
    :param prefix: Unicode prefix to prepend to the given text before wrapping
        it.
    :param wrap_width: The width where the text should be wrapped.
    """

    def local_escape(text):
        ret = text.replace(u'\\', u'\\\\')
        ret = ret.replace(ur'"', ur'\"')
        ret = ret.replace(u'\t', u'\\t')
        ret = ret.replace(u'\r', u'\\r')
        return ret.replace(u'\n', u'\\n')

    # Quickly get escaped character byte widths using
    #   escaped_length.get(char, 1).
    escaped_length = {
        '\\': 2,
        '\"': 2,
        '\t': 2,
        '\r': 2,
        '\n': 2,
        }

    # Wrap at these characters.
    wrap_at = [' ', '\t', '\n', '-', '\\']

    if wrap_width is None:
        raise AssertionError('wrap_width should not be None')
    wrapped_lines = [u'%s%s' % (prefix, u' ""')]
    if not text:
        return wrapped_lines
    if '\n' not in text[:-1]:
        # Either there are no new-lines, or it's at the end of string.
        unwrapped_line = u'%s "%s"' % (prefix, local_escape(text))
        if len(unwrapped_line) <= wrap_width:
            return [unwrapped_line]
        del unwrapped_line
    paragraphs = text.split('\n')
    end = len(paragraphs) - 1
    for i, paragraph in enumerate(paragraphs):
        if i == end:
            if not paragraph:
                break
        else:
            paragraph += '\n'

        if len(local_escape(paragraph)) <= wrap_width:
            wrapped_line = [paragraph]
        else:
            line = u''
            escaped_line_len = 0
            new_block = u''
            escaped_new_block_len = 0
            wrapped_line = []
            for char in paragraph:
                escaped_char_len = escaped_length.get(char, 1)
                if (escaped_line_len + escaped_new_block_len
                    + escaped_char_len <= wrap_width):
                    if char in wrap_at:
                        line += u'%s%s' % (new_block, char)
                        escaped_line_len += (escaped_new_block_len
                                             + escaped_char_len)
                        new_block = u''
                        escaped_new_block_len = 0
                    else:
                        new_block += char
                        escaped_new_block_len += escaped_char_len
                else:
                    if escaped_line_len == 0:
                        # Word is too long to fit into single line.
                        # Break it carefully; avoid doing so in the middle of
                        # the escape sequence.
                        line = new_block
                        line_len = len(line)
                        escaped_line_len = escaped_new_block_len
                        while escaped_line_len > wrap_width:
                            escaped_line_len -= (
                                escaped_length.get(line[line_len-1], 1))
                            line_len -= 1
                        line = line[:line_len]
                        new_block = new_block[line_len:]
                        escaped_new_block_len -= escaped_line_len
                    wrapped_line.append(line)
                    line = u''
                    escaped_line_len = 0
                    new_block += char
                    escaped_new_block_len += escaped_char_len
            if line or new_block:
                wrapped_line.append(u'%s%s' % (line, new_block))
        for line in wrapped_line:
            wrapped_lines.append(u'"%s"' % (local_escape(line)))
    return wrapped_lines


def msgid_text_representation(translation_message, wrap_width):
    """Return text representation of the msgids.

    :param translation_message: An `ITranslationMessageData` that will get its
        msgids exported.
    :param wrap_width: The width where the text should be wrapped.
    """
    text = []
    if translation_message.context is not None:
        text.extend(
            wrap_text(translation_message.context, u'msgctxt', wrap_width))
    text.extend(
        wrap_text(translation_message.msgid_singular, u'msgid', wrap_width))
    if translation_message.msgid_plural:
        # This message has a plural form that we must export.
        text.extend(
            wrap_text(
                translation_message.msgid_plural, u'msgid_plural',
                wrap_width))
    if translation_message.is_obsolete:
        text = ['#~ ' + line for line in text]

    return u'\n'.join(text)


def translation_text_representation(translation_message, wrap_width):
    """Return text representation of the translations.

    :param translation_message: An `ITranslationMessageData` that will get its
        translations exported.
    :param wrap_width: The width where the text should be wrapped.
    """
    text = []
    if translation_message.msgid_plural:
        # It's a message with plural forms.
        for i, translation in enumerate(translation_message.translations):
            text.extend(wrap_text(translation, u'msgstr[%s]' % i, wrap_width))

        if len(text) == 0:
            # We don't have any translation for it.
            text = [u'msgstr[0] ""', u'msgstr[1] ""']
    else:
        # It's a message without plural form.
        if translation_message.translations:
            translation = translation_message.translations[
                TranslationConstants.SINGULAR_FORM]
            text = wrap_text(translation, u'msgstr', wrap_width)
        else:
            text = [u'msgstr ""']

    if translation_message.is_obsolete:
        text = ['#~ ' + line for line in text]

    return u'\n'.join(text)


def export_translation_message(translation_message, wrap_width=77):
    """Return a text representing translation_message.
    """
    return u'\n'.join([
        comments_text_representation(translation_message),
        msgid_text_representation(translation_message, wrap_width),
        translation_text_representation(translation_message, wrap_width),
        ]).strip()


class GettextPOExporterBase:
    """Base support class to export Gettext .po files.

    To get a working implementation, derived classes must assign values to
    format and supported_source_formats and must implement
    _makeExportedHeader.
    """
    implements(ITranslationFormatExporter)

    format = None
    supported_source_formats = []
    mime_type = 'application/x-po'

    # Does the format we're exporting allow messages to be distinguished
    # by just their msgid_plural?
    msgid_plural_distinguishes_messages = False

    def exportTranslationMessageData(self, translation_message):
        """See `ITranslationFormatExporter`."""
        return export_translation_message(translation_message)

    def _makeExportedHeader(self, translation_file):
        """Transform the header information into a format suitable for export.

        :return: Unicode string containing the header.
        """
        raise NotImplementedError

    def _encode_file_content(self, translation_file, exported_content):
        """Try to encode the file using the charset given in the header."""
        file_content = (
            self._makeExportedHeader(translation_file) +
            u'\n\n' +
            exported_content)
        encoded_file_content = file_content.encode(
            translation_file.header.charset)
        return encoded_file_content

    def exportTranslationFile(self, translation_file, storage,
                              ignore_obsolete=False, force_utf8=False):
        """See `ITranslationFormatExporter`."""
        mime_type = 'application/x-po'

        dirname = os.path.dirname(translation_file.path)
        if dirname == '':
            # There is no directory in the path. Use translation_domain
            # as its directory.
            dirname = translation_file.translation_domain

        if translation_file.is_template:
            file_extension = 'pot'
            file_path = os.path.join(
                dirname, '%s.%s' % (
                    translation_file.translation_domain,
                    file_extension))
        else:
            file_extension = 'po'
            file_path = os.path.join(
                dirname, '%s-%s.%s' % (
                    translation_file.translation_domain,
                    translation_file.language_code,
                    file_extension))

        chunks = []
        seen_keys = {}

        for message in translation_file.messages:
            key = (message.context, message.msgid_singular)
            if key in seen_keys:
                # Launchpad can deal with messages that are
                # identical to gettext, but differ in plural msgid.
                if not self.msgid_plural_distinguishes_messages:
                    # Suppress messages that are duplicative to
                    # gettext so that gettext doesn't choke on the
                    # resulting file.
                    continue
            else:
                seen_keys[key] = message

            if (message.is_obsolete and
                (ignore_obsolete or len(message.translations) == 0)):
                continue
            chunks.append(self.exportTranslationMessageData(message))

        # Gettext .po files are supposed to end with a new line.
        exported_file_content = u'\n\n'.join(chunks) + u'\n'

        # Try to encode the file
        if force_utf8:
            translation_file.header.charset = 'UTF-8'
        try:
            encoded_file_content = self._encode_file_content(
                translation_file, exported_file_content)
        except UnicodeEncodeError:
            if translation_file.header.charset.upper() == 'UTF-8':
                # It's already UTF-8, we cannot do anything.
                raise
            # This file content cannot be represented in the current
            # encoding.
            if translation_file.path:
                file_description = translation_file.path
            elif translation_file.language_code:
                file_description = (
                    "%s translation" % translation_file.language_code)
            else:
                file_description = "template"
            logging.info(
                "Can't represent %s as %s; using UTF-8 instead." % (
                    file_description,
                    translation_file.header.charset.upper()))
            # Use UTF-8 instead.
            translation_file.header.charset = 'UTF-8'
            # This either succeeds or raises UnicodeError.
            encoded_file_content = self._encode_file_content(
                translation_file, exported_file_content)

        storage.addFile(
            file_path, file_extension, encoded_file_content, mime_type)

    def acceptSingularClash(self, previous_message, current_message):
        """Handle clash of (singular) msgid and context with other message.

        Define in derived class how it should behave when this happens.

        Obsolete messages are guaranteed to be processed after
        non-obsolete ones.

        :param previous_message: already processed message in this
            export.
        :param current_message: another message with the same (singular)
            msgid and context as `previous_message`.
        :return: boolean: True to accept `current_message`, or False to
            leave it out of the export.
        """
        raise NotImplementedError()


class GettextPOExporter(GettextPOExporterBase):
    """Support class to export Gettext .po files."""

    def __init__(self, context=None):
        # 'context' is ignored because it's only required by the way the
        # exporters are instantiated but it isn't used by this class.
        self.format = TranslationFileFormat.PO
        self.supported_source_formats = [
            TranslationFileFormat.PO,
            TranslationFileFormat.KDEPO]

    def _makeExportedHeader(self, translation_file):
        """Create a standard gettext PO header, encoded as a message.

        :return: The header message as a unicode string.
        """
        header_translation_message = TranslationMessageData()
        header_translation_message.addTranslation(
            TranslationConstants.SINGULAR_FORM,
            translation_file.header.getRawContent())
        header_translation_message.comment = (
            translation_file.header.comment)
        if translation_file.is_template:
            header_translation_message.flags.update(['fuzzy'])
        exported_header = self.exportTranslationMessageData(
            header_translation_message)
        return exported_header


class GettextPOChangedExporter(GettextPOExporterBase):
    """Support class to export changed Gettext .po files."""

    exported_header = (
        u"# IMPORTANT: This file does NOT contain a complete PO file "
            u"structure.\n"
        u"# DO NOT attempt to import this file back into Launchpad.\n\n"
        u"# This file is a partial export from Launchpad.net.\n"
        u"# See https://help.launchpad.net/Translations/PartialPOExport\n"
        u"# for more information.")

    def __init__(self, context=None):
        # 'context' is ignored because it's only required by the way the
        # exporters are instantiated but it isn't used by this class.
        self.format = TranslationFileFormat.POCHANGED
        self.supported_source_formats = []

    def _makeExportedHeader(self, translation_file):
        """Create a header for changed PO files.
        This is a reduced header containing a warning that this is an
        icomplete gettext PO file.
        :return: The header as a unicode string.
        """
        return self.exported_header

    def acceptSingularClash(self, previous_message, current_message):
        """See `GettextPOExporterBase`."""
        return True
