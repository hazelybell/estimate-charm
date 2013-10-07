# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Originally based on code from msgfmt.py (available from python source
# code), written by Martin v. Loewis and changed by Christian 'Tiran'
# Heimes.  The code is no longer recognizably similar though, so don't
# blame these people for any mistakes.

__metaclass__ = type

__all__ = [
    'POHeader',
    'POParser',
    ]

import codecs
import datetime
from email.Utils import parseaddr
import logging
import re

import pytz
from zope import datetime as zope_datetime
from zope.interface import implements

from lp.app.versioninfo import revno
from lp.translations.interfaces.translationcommonformat import (
    ITranslationHeaderData,
    )
from lp.translations.interfaces.translationimporter import (
    TooManyPluralFormsError,
    TranslationFormatInvalidInputError,
    TranslationFormatSyntaxError,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.utilities.pluralforms import (
    make_plurals_identity_map,
    plural_form_mapper,
    )
from lp.translations.utilities.translation_common_format import (
    TranslationFileData,
    TranslationMessageData,
    )


class POSyntaxWarning(Warning):
    """Syntax warning in a PO file."""
    def __init__(self, message, line_number=None):
        """Create (and log) a warning.

        :param message: warning text.
        :param line_number: optional line number where the warning
            occurred.  Leave out or pass zero if unknown.
        """
        Warning.__init__(self, message, line_number)

        self.lno = line_number
        if line_number:
            self.message = 'Line %d: %s' % (line_number, message)
        else:
            self.message = message
        logging.info(self.message)

    def __unicode__(self):
        return unicode(self.message)


def parse_charset(string_to_parse, is_escaped=True):
    """Return charset used in the given string_to_parse."""
    # Scan for the charset in the same way that gettext does.
    default_charset = 'UTF-8'
    pattern = r'charset=([^\s]+)'
    if is_escaped:
        pattern = r'charset=([^\s]+)\\n'

    # Default to UTF-8 if the header still has the default value or
    # is unknown.
    charset = default_charset
    match = re.search(pattern, string_to_parse)
    if match is not None and match.group(1) != 'CHARSET':
        charset = match.group(1).strip()
        try:
            codecs.getencoder(charset)
        except LookupError:
            # The given codec is not valid, let's fallback to UTF-8.
            charset = default_charset

    return charset


class POHeader:
    """See `ITranslationHeaderData`."""
    implements(ITranslationHeaderData)

    # Set of known keys in the .po header.
    _handled_keys_mapping = {
        'project-id-version': 'Project-Id-Version',
        'report-msgid-bugs-to': 'Report-Msgid-Bugs-To',
        'pot-creation-date': 'POT-Creation-Date',
        'po-revision-date': 'PO-Revision-Date',
        'last-translator': 'Last-Translator',
        'language-team': 'Language-Team',
        'mime-version': 'MIME-Version',
        'content-type': 'Content-Type',
        'content-transfer-encoding': 'Content-Transfer-Encoding',
        'plural-forms': 'Plural-Forms',
        'x-launchpad-export-date': 'X-Launchpad-Export-Date',
        'x-rosetta-export-date': 'X-Rosetta-Export-Date',
        'x-generator': 'X-Generator',
        }

    _handled_keys_order = [
        'project-id-version', 'report-msgid-bugs-to', 'pot-creation-date',
        'po-revision-date', 'last-translator', 'language-team',
        'mime-version', 'content-type', 'content-transfer-encoding',
        'plural-forms', 'x-launchpad-export-date', 'x-rosetta-export-date',
        'x-generator'
        ]

    _strftime_text = '%F %R%z'

    translation_revision_date = None

    def __init__(self, header_content, comment=None):
        self._raw_header = header_content
        self.is_fuzzy = False
        UTC = pytz.timezone('UTC')
        self.template_creation_date = datetime.datetime.now(UTC)
        self._last_translator = 'FULL NAME <EMAIL@ADDRESS>'
        self.language_team = 'LANGUAGE <LL@li.org>'
        self.has_plural_forms = False
        self.number_plural_forms = None
        self.plural_form_expression = None
        self.launchpad_export_date = None
        self.syntax_warnings = []

        # First thing to do is to get the charset used to decode correctly the
        # header content.
        self.charset = parse_charset(self._raw_header, is_escaped=False)

        # Decode comment using the declared charset.
        self.comment = self._decode(comment)
        # And the same with the raw content.
        self._raw_header = self._decode(self._raw_header)

        # Parse the header in a dictionary so it's easy for us to export it
        # with updates later.
        self._header_dictionary = self._getHeaderDict(self._raw_header)
        self._parseHeaderFields()

    def _emitSyntaxWarning(self, message):
        """Issue syntax warning, add to warnings list."""
        self.syntax_warnings.append(unicode(POSyntaxWarning(message)))

    def _getHeaderDict(self, raw_header):
        """Return dictionary with all keys in raw_header.

        :param raw_header: string representing the header in native format.
        :param handled_keys_order: list of header keys in the order they must
            appear on export time.
        :return: dictionary with all key/values in raw_header.
        """
        header_dictionary = {}
        for line in raw_header.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                field, value = line.split(':', 1)
            except ValueError:
                self._emitSyntaxWarning(
                    'PO file header entry has a bad entry: %s' % line)
                continue

            # Store in lower case the entries we know about so we are sure
            # that we update entries even when it's not using the right
            # character case.
            if field.lower() in self._handled_keys_order:
                field = field.lower()

            header_dictionary[field] = value.strip()

        return header_dictionary

    def _decode(self, text):
        if text is None or isinstance(text, unicode):
            # There is noo need to do anything.
            return text
        charset = self.charset
        try:
            text = unicode(text, charset)
        except UnicodeError:
            self._emitSyntaxWarning(
                'String is not in declared charset %r' % charset)
            text = unicode(text, charset, 'replace')
        except LookupError:
            raise TranslationFormatInvalidInputError(
                message='Unknown charset %r' % charset)

        return text

    def _parseAssignments(self, text, separator=';', assigner='=',
                          skipfirst=False):
        """Parse "assignment" expressions in the plural-form header."""
        parts = {}
        if skipfirst:
            start = 1
        else:
            start = 0
        for assignment in text.split(separator)[start:]:
            if not assignment.strip():
                # empty
                continue
            if assigner in assignment:
                name, value = assignment.split(assigner, 1)
            else:
                self._emitSyntaxWarning(
                    "Found an error in the header content: %s" % text)
                continue

            parts[name.strip()] = value.strip()
        return parts

    def _parseOptionalDate(self, date_string):
        """Attempt to parse `date_string`, or return None if invalid."""
        try:
            return zope_datetime.parseDatetimetz(date_string)
        except (ValueError, zope_datetime.DateTimeError) as exception:
            return None

    def _parseHeaderFields(self):
        """Return plural form values based on the parsed header."""
        for key, value in self._header_dictionary.iteritems():
            if key == 'plural-forms':
                parts = self._parseAssignments(value)
                nplurals = parts.get('nplurals')
                if nplurals is None:
                    # Number of plurals not specified.  Default to single
                    # form.
                    self.number_plural_forms = 1
                    self.plural_form_expression = '0'
                elif nplurals != 'INTEGER':
                    # We found something different than gettext's default
                    # value.
                    try:
                        self.number_plural_forms = int(nplurals)
                    except (TypeError, ValueError):
                        # There are some po files with bad headers that have a
                        # non numeric value here and sometimes an empty value.
                        # In that case, set the default value.
                        raise TranslationFormatSyntaxError(
                            message="Invalid nplurals declaration in header: "
                                    "'%s' (should be a number)." % nplurals)

                    if self.number_plural_forms <= 0:
                        text = "Number of plural forms is impossibly low."
                        raise TranslationFormatSyntaxError(message=text)

                    max_forms = TranslationConstants.MAX_PLURAL_FORMS
                    if self.number_plural_forms > max_forms:
                        raise TooManyPluralFormsError()

                    self.plural_form_expression = parts.get('plural', '0')
                else:
                    # Plurals declaration contains default text.  This is
                    # probably a template, so leave the text as it is.
                    pass

            elif key == 'pot-creation-date':
                date = self._parseOptionalDate(value)
                if date:
                    self.template_creation_date = date
            elif key == 'po-revision-date':
                self.translation_revision_date = self._parseOptionalDate(
                    value)
            elif key == 'last-translator':
                self._last_translator = value
            elif key == 'language-team':
                self.language_team = value
            elif key in ('x-launchpad-export-date', 'x-rosetta-export-date'):
                # The key we use right now to note the export date is
                # X-Launchpad-Export-Date but we need to accept the old one
                # too so old exports will still work.
                self.launchpad_export_date = self._parseOptionalDate(value)
            else:
                # We don't use the other keys.
                pass

    def getRawContent(self):
        """See `ITranslationHeaderData`."""
        raw_content_list = []
        for key in self._handled_keys_order:
            value = self._handled_keys_mapping[key]
            if key == 'project-id-version':
                if key in self._header_dictionary:
                    content = self._header_dictionary[key]
                else:
                    # Use default one.
                    content = 'PACKAGE VERSION'
                raw_content_list.append('%s: %s\n' % (value, content))
            elif key == 'report-msgid-bugs-to':
                if key in self._header_dictionary:
                    content = self._header_dictionary[key]
                else:
                    # Use default one.
                    content = ' '
                raw_content_list.append(
                    '%s: %s\n' % (value, content))
            elif key == 'pot-creation-date':
                date_string = self._renderDate(self.template_creation_date)
                raw_content_list.append('%s: %s\n' % (value, date_string))
            elif key == 'po-revision-date':
                revision_date_text = self._renderDate(
                    self.translation_revision_date, 'YEAR-MO-DA HO:MI+ZONE')
                raw_content_list.append(
                    '%s: %s\n' % (
                        value, revision_date_text))
            elif key == 'last-translator':
                raw_content_list.append(
                    '%s: %s\n' % (value, self._last_translator))
            elif key == 'language-team':
                raw_content_list.append(
                    '%s: %s\n' % (value, self.language_team))
            elif key == 'mime-version':
                raw_content_list.append('%s: 1.0\n' % value)
            elif key == 'content-type':
                raw_content_list.append(
                    '%s: text/plain; charset=%s\n' % (value, self.charset))
            elif key == 'content-transfer-encoding':
                raw_content_list.append('%s: 8bit\n' % value)
            elif key == 'plural-forms':
                if not self.has_plural_forms:
                    # This file doesn't have plural forms so we don't export
                    # any plural form information in the header.
                    continue
                if self.number_plural_forms is None:
                    # Use the default values.
                    nplurals = 'INTEGER'
                    plural = 'EXPRESSION'
                else:
                    nplurals = str(self.number_plural_forms)
                    plural = self.plural_form_expression
                raw_content_list.append('%s: nplurals=%s; plural=%s;\n' % (
                    value, nplurals, plural))
            elif key == 'x-rosetta-export-date':
                # Ignore it, new exports use x-launchpad-export-date.
                continue
            elif key == 'x-launchpad-export-date':
                UTC = pytz.timezone('UTC')
                now = self._renderDate(datetime.datetime.now(UTC))
                raw_content_list.append('%s: %s\n' % (value, now))
            elif key == 'x-generator':
                # Note the revision number so it would help for debugging
                # problems with bad exports.
                if revno is None:
                    build = 'Unknown'
                else:
                    build = revno
                raw_content_list.append(
                    '%s: Launchpad (build %s)\n' % (value, build))
            else:
                raise AssertionError('key %s is not being handled!' % value)

        # Now, we copy any other header information in the original .po file.
        for key, value in self._header_dictionary.iteritems():
            if key in self._handled_keys_mapping:
                # It's already handled, skip it.
                continue

            raw_content_list.append('%s: %s\n' % (key, value.strip()))

        return u''.join(raw_content_list)

    def updateFromTemplateHeader(self, template_header):
        """See `ITranslationHeaderData`."""
        template_header_dictionary = self._getHeaderDict(
            template_header.getRawContent())
        # 'Domain' is a non standard header field. However, this is required
        # for good Plone support. It relies in that field to know the
        # translation domain. For more information you can take a look to
        # https://bugs.launchpad.net/rosetta/+bug/5
        fields_to_copy = ['Domain']

        for field in fields_to_copy:
            if field in template_header_dictionary:
                self._header_dictionary[field] = (
                    template_header_dictionary[field])

        # Standard fields update.
        self.template_creation_date = template_header.template_creation_date

    def getLastTranslator(self):
        """See `ITranslationHeaderData`."""
        # Get last translator information. If it's not found, we use the
        # default value from Gettext.
        name, email = parseaddr(self._last_translator)

        if email == 'EMAIL@ADDRESS' or '@' not in email:
            # Gettext (and Launchpad) sets by default the email address to
            # EMAIL@ADDRESS unless it knows the real address, thus,
            # we know this isn't a real account so we don't accept it as a
            # valid one.
            return None, None
        else:
            return name, email

    def setLastTranslator(self, email, name=None):
        """See `ITranslationHeaderData`."""
        assert email is not None, 'Email address cannot be None'

        if name is None:
            name = u''
        self._last_translator = u'%s <%s>' % (name, email)

    def _renderDate(self, date, default=None):
        """Return string representation of `date`, or `default`."""
        if date is None:
            return default
        else:
            return date.strftime(self._strftime_text)


# Special escape sequences.
ESCAPE_MAP = {
    'a': '\a',
    'b': '\b',
    'f': '\f',
    'n': '\n',
    'r': '\r',
    't': '\t',
    'v': '\v',
    '"': '"',
    '\'': '\'',
    '\\': '\\',
    }


# Compiled regex for a straight test run, i.e. anything up to the next
# double-quote or escaped character.
STRAIGHT_TEXT_RUN = re.compile('[^"\\\\]*')


class POParser(object):
    """Parser class for Gettext files."""

    def __init__(self, plural_formula=None):
        self._translation_file = None
        self._lineno = 0
        # This is a default plural form mapping (i.e. no mapping) when
        # no header is present in the PO file.
        self._plural_form_mapping = make_plurals_identity_map()
        self._expected_plural_formula = plural_formula

        # Marks when we're parsing a continuation of a string after an escaped
        # newline.
        self._escaped_line_break = False

    def _emitSyntaxWarning(self, message):
        warning = POSyntaxWarning(message, line_number=self._lineno)
        if self._translation_file:
            self._translation_file.syntax_warnings.append(unicode(warning))

    def _decode(self):
        # is there anything to convert?
        if not self._pending_chars:
            return

        # if the PO header hasn't been parsed, then we don't know the
        # encoding yet
        if self._translation_file.header is None:
            return

        charset = self._translation_file.header.charset
        decode = codecs.getdecoder(charset)
        # decode as many characters as we can:
        try:
            newchars, length = decode(self._pending_chars, 'strict')
        except UnicodeDecodeError as exc:
            # XXX: James Henstridge 2006-03-16:
            # If the number of unconvertable chars is longer than a
            # multibyte sequence to be, the UnicodeDecodeError indicates
            # a real error, rather than a partial read.
            # I don't know what the longest multibyte sequence in the
            # encodings we need to support, but it shouldn't be more
            # than 10 bytes ...
            if len(self._pending_chars) - exc.start > 10:
                raise TranslationFormatInvalidInputError(
                    line_number=self._lineno,
                    message="Could not decode input from %s" % charset)
            newchars, length = decode(self._pending_chars[:exc.start],
                                      'strict')
        self._pending_unichars += newchars
        self._pending_chars = self._pending_chars[length:]

    def _getHeaderLine(self):
        if self._translation_file.header is not None:
            # We know what charset the data is in, as we've already
            # parsed the header.  However, we're going to handle this
            # more efficiently, so we don't want to use _getHeaderLine
            # except for parsing the header.
            raise AssertionError(
                'using _getHeaderLine after header is parsed')

        # We don't know what charset the data is in, so we parse it one line
        # at a time until we have the header, and then we'll know how to
        # treat the rest of the data.
        parts = re.split(r'\n|\r\n|\r', self._pending_chars, 1)
        if len(parts) == 1:
            # only one line
            return None
        line, self._pending_chars = parts
        return line.strip()

    def parse(self, content_text):
        """Parse string as a PO file."""
        # Initialize the parser.
        self._translation_file = TranslationFileData()
        self._messageids = set()
        self._pending_chars = content_text
        self._pending_unichars = u''
        self._lineno = 0
        # Message specific variables.
        self._message = TranslationMessageData()
        self._message_lineno = self._lineno
        self._section = None
        self._plural_case = None
        self._parsed_content = u''

        # First thing to do is to get the charset used in the content_text.
        charset = parse_charset(content_text)

        # Now, parse the header, inefficiently. It ought to be short, so
        # this isn't disastrous.
        line = self._getHeaderLine()
        while line is not None:
            self._parseLine(line.decode(charset))
            if (self._translation_file.header is not None or
                self._message.msgid_singular):
                # Either found the header already or it's a message with a
                # non empty msgid which means is not a header.
                break
            line = self._getHeaderLine()

        if line is None:
            if (self._translation_file.header is None and
                not self._message.msgid_singular):
                # This file contains no actual messages.
                self._dumpCurrentSection()

                # It may contain a header though.
                if not self._message.translations:
                    raise TranslationFormatSyntaxError(
                        message="File contains no messages.")
                self._parseHeader(
                    self._message.translations[
                        TranslationConstants.SINGULAR_FORM],
                    self._message.comment)

            # There is nothing left to parse.
            return self._translation_file

        # Parse anything left all in one go.
        lines = re.split(r'\n|\r\n|\r', self._pending_unichars)
        for line in lines:
            self._parseLine(line)

        if self._translation_file.header is None:
            raise TranslationFormatSyntaxError(
                message='No header found in this pofile')

        if self._message is not None:
            # We need to dump latest message.
            if self._section is None:
                # The message has not content or it's just a comment, ignore
                # it.
                return self._translation_file
            elif self._section == 'msgstr':
                self._dumpCurrentSection()
                self._storeCurrentMessage()
            else:
                raise TranslationFormatSyntaxError(
                    line_number = self._lineno,
                    message='Got a truncated message!')

        return self._translation_file

    def _storeCurrentMessage(self):
        if self._message is not None:
            msgkey = self._message.msgid_singular
            if self._message.context is not None:
                msgkey = '%s\2%s' % (self._message.context, msgkey)
            if msgkey in self._messageids:
                # We use '%r' instead of '%d' because there are situations
                # when it returns an "<unprintable instance object>". You can
                # see more details on bug #2896
                raise TranslationFormatInvalidInputError(
                    message='PO file: duplicate msgid ending on line %r' % (
                        self._message_lineno))

            number_plural_forms = (
                self._translation_file.header.number_plural_forms)
            if (self._message.msgid_plural and
                len(self._message.translations) < number_plural_forms):
                # Has plural forms but the number of translations is lower.
                # Fill the others with an empty string.
                for index in range(
                    len(self._message.translations), number_plural_forms):
                    self._message.addTranslation(index, u'')

            self._translation_file.messages.append(self._message)
            self._messageids.add(msgkey)
            self._message = None

    def _parseHeader(self, header_text, header_comment):
        try:
            header = POHeader(header_text, header_comment)
            self._translation_file.header = header
            self._translation_file.syntax_warnings += header.syntax_warnings
        except TranslationFormatInvalidInputError as error:
            if error.line_number is None:
                error.line_number = self._message_lineno
            raise
        self._translation_file.header.is_fuzzy = (
            'fuzzy' in self._message.flags)

        if self._translation_file.messages:
            self._emitSyntaxWarning("Header entry is not first entry.")

        plural_formula = self._translation_file.header.plural_form_expression
        if plural_formula is None:
            # We default to a simple plural formula which uses
            # a single form for translations.
            plural_formula = '0'
        self._plural_form_mapping = plural_form_mapper(
            plural_formula, self._expected_plural_formula)
        # convert buffered input to the encoding specified in the PO header
        self._decode()

    def _unescapeNumericCharSequence(self, string):
        """Unescape leading sequence of escaped numeric character codes.

        This is for characters given in hexadecimal or octal escape notation.

        :return: a tuple: first, any leading part of `string` as an unescaped
            string (empty if `string` did not start with a numeric escape
            sequence), and second, the remainder of `string` after the leading
            numeric escape sequences have been parsed.
        """
        escaped_string = ''
        position = 0
        length = len(string)
        while position + 1 < length and string[position] == '\\':
            # Handle escaped characters given as numeric character codes.
            # These will still be in the original encoding.  We extract the
            # whole sequence of escaped chars to recode them later into
            # Unicode in a single call.
            lead_char = string[position + 1]
            if lead_char == 'x':
                # Hexadecimal escape.
                position += 4
            elif lead_char.isdigit():
                # Octal escape.
                position += 2
                # Up to two more octal digits.
                for i in xrange(2):
                    if string[position].isdigit():
                        position += 1
                    else:
                        break
            elif lead_char in ESCAPE_MAP:
                # It's part of our mapping table, we ignore it here.
                break
            else:
                raise TranslationFormatSyntaxError(
                    line_number=self._lineno,
                    message=("Unknown escape sequence %s" %
                             string[position:position + 2]))

        if position == 0:
            # No escaping to be done.
            return '', string

        # We found some text escaped that should be recoded to Unicode.
        # First, we unescape it.
        escaped_string, string = string[:position], string[position:]
        unescaped_string = escaped_string.decode('string-escape')

        if (self._translation_file is not None and
            self._translation_file.header is not None):
            # There is a header, so we know the original encoding for
            # the given string.
            charset = self._translation_file.header.charset
            know_charset = True
        else:
            # We don't know the original encoding of the imported file so we
            # cannot get the right values.  We try ASCII.
            # XXX JeroenVermeulen 2008-02-08: might as well try UTF-8 here.
            # It's a superset, and anything that's not UTF-8 is very unlikely
            # to validate as UTF-8.
            charset = 'ascii'
            know_charset = False

        try:
            decoded_text = unescaped_string.decode(charset)
        except UnicodeDecodeError:
            if know_charset:
                message = ("Could not decode escaped string as %s: (%s)"
                           % (charset, escaped_string))
            else:
                message = ("Could not decode escaped string: (%s)"
                           % escaped_string)
            raise TranslationFormatInvalidInputError(
                line_number=self._lineno, message=message)

        return decoded_text, string

    def _parseQuotedString(self, string):
        r"""Parse a quoted string, interpreting escape sequences.

          >>> parser = POParser()
          >>> parser._parseQuotedString(u'\"abc\"')
          u'abc'
          >>> parser._parseQuotedString(u'\"abc\\ndef\"')
          u'abc\ndef'
          >>> parser._parseQuotedString(u'\"ab\x63\"')
          u'abc'
          >>> parser._parseQuotedString(u'\"ab\143\"')
          u'abc'

          After the string has been converted to unicode, the backslash
          escaped sequences are still in the encoding that the charset header
          specifies. Such quoted sequences will be converted to unicode by
          this method.

          We don't know the encoding of the escaped characters and cannot be
          just recoded as Unicode so it's a TranslationFormatInvalidInputError
          >>> utf8_string = u'"view \\302\\253${version_title}\\302\\273"'
          >>> parser._parseQuotedString(utf8_string)
          Traceback (most recent call last):
          ...
          TranslationFormatInvalidInputError: Could not decode escaped string: (\302\253)

          Now, we note the original encoding so we get the right Unicode
          string.

          >>> class FakeHeader:
          ...     charset = 'UTF-8'
          >>> parser._translation_file = TranslationFileData()
          >>> parser._translation_file.header = FakeHeader()
          >>> parser._parseQuotedString(utf8_string)
          u'view \xab${version_title}\xbb'

          Let's see that we raise a TranslationFormatInvalidInputError
          exception when we have an escaped char that is not valid in the
          declared encoding of the original string:

          >>> iso8859_1_string = u'"foo \\xf9"'
          >>> parser._parseQuotedString(iso8859_1_string)
          Traceback (most recent call last):
          ...
          TranslationFormatInvalidInputError: Could not decode escaped string as UTF-8: (\xf9)

          An error will be raised if the entire string isn't contained in
          quotes properly:

          >>> parser._parseQuotedString(u'abc')
          Traceback (most recent call last):
            ...
          TranslationFormatSyntaxError: String is not quoted
          >>> parser._parseQuotedString(u'\"ab')
          Traceback (most recent call last):
            ...
          TranslationFormatSyntaxError: String not terminated
          >>> parser._parseQuotedString(u'\"ab\"x')
          Traceback (most recent call last):
            ...
          TranslationFormatSyntaxError: Extra content found after string: (x)
        """
        if self._escaped_line_break:
            # Continuing a line after an escaped newline.  Strip indentation.
            string = string.lstrip()
            self._escaped_line_break = False
        else:
            # Regular string.  Must start with opening quote, which we strip.
            if string[0] != '"':
                raise TranslationFormatSyntaxError(
                    line_number=self._lineno, message="String is not quoted")
            string = string[1:]

        output = ''
        while len(string) > 0:
            if string[0] == '"':
                # Reached the end of the quoted string.  It's rare, but there
                # may be another quoted string on the same line.  It should be
                # suffixed to what we already have, with any whitespace
                # between the strings removed.
                string = string[1:].lstrip()
                if len(string) == 0:
                    # End of line, end of string: the normal case
                    break
                if string[0] == '"':
                    # Start of a new string.  We've already swallowed the
                    # closing quote and any intervening whitespace; now
                    # swallow the re-opening quote and go on as if the string
                    # just went on normally
                    string = string[1:]
                    continue

                # if there is any non-string data afterwards, raise an
                # exception
                if len(string) > 0 and not string.isspace():
                    raise TranslationFormatSyntaxError(
                        line_number=self._lineno,
                        message=("Extra content found after string: (%s)" %
                                 string))
                break
            elif string[0] == '\\':
                if len(string) == 1:
                    self._escaped_line_break = True
                    string = ''
                    break
                elif string[1] in ESCAPE_MAP:
                    # We got one of the special escaped chars we know about.
                    # Unescape it using the mapping table.
                    output += ESCAPE_MAP[string[1]]
                    string = string[2:]
                else:
                    unescaped, string = (
                        self._unescapeNumericCharSequence(string))
                    output += unescaped
            else:
                # Normal text.  Eat up as much as we can in one go.
                text = re.match(STRAIGHT_TEXT_RUN, string)
                output += text.group()
                zero, runlength = text.span()
                string = string[runlength:]
        else:
            # We finished parsing the string without finding the ending quote
            # char.
            raise TranslationFormatSyntaxError(
                line_number=self._lineno, message="String not terminated")

        return output

    def _dumpCurrentSection(self):
        """Dump current parsed content inside the translation message."""
        if self._section is None:
            # There is nothing to dump.
            return
        elif self._section == 'msgctxt':
            self._message.context = self._parsed_content
        elif self._section == 'msgid':
            self._message.msgid_singular = self._parsed_content
        elif self._section == 'msgid_plural':
            self._message.msgid_plural = self._parsed_content
            # Note in the header that there are plural forms.
            self._translation_file.header.has_plural_forms = True
        elif self._section == 'msgstr':
            if self._message.msgid_plural is not None:
                self._message.addTranslation(
                    self._plural_form_mapping[self._plural_case],
                    self._parsed_content)
            else:
                self._message.addTranslation(
                    self._plural_case,
                    self._parsed_content)
        else:
            raise AssertionError('Unknown section %s' % self._section)

        self._parsed_content = u''

    def _parseFreshLine(self, line, original_line):
        """Parse a new line (not a continuation after escaped newline).

        :param line: Remaining part of input line.
        :param original_line: Line as it originally was on input.
        :return: If there is one, the first line of a quoted string belonging
            to the line's section.  Otherwise, None.
        """
        is_obsolete = False
        if line.startswith('#~'):
            if line.startswith('#~|'):
                # This is an old msgid for an obsolete message.
                return None
            else:
                is_obsolete = True
                line = line[2:].lstrip()
                if len(line) == 0:
                    return None

        # If we get a comment line after a msgstr or a line starting with
        # msgid or msgctxt, this is a new entry.
        if ((line.startswith('#') or line.startswith('msgid') or
            line.startswith('msgctxt')) and self._section == 'msgstr'):
            if self._message is None:
                # first entry - do nothing.
                pass
            elif self._message.msgid_singular:
                self._dumpCurrentSection()
                self._storeCurrentMessage()
            elif self._translation_file.header is None:
                # When there is no msgid in the parsed message, it's the
                # header for this file.
                self._dumpCurrentSection()
                self._parseHeader(
                    self._message.translations[
                        TranslationConstants.SINGULAR_FORM],
                    self._message.comment)
            else:
                self._emitSyntaxWarning("We got a second header.")

            # Start a new message.
            self._message = TranslationMessageData()
            self._message_lineno = self._lineno
            self._section = None
            self._plural_case = None
            self._parsed_content = u''

        if self._message is not None:
            # Record whether the message is obsolete.
            self._message.is_obsolete = is_obsolete

        if line[0] == '#':
            # Record flags
            if line[:2] == '#,':
                new_flags = [flag.strip() for flag in line[2:].split(',')]
                self._message.flags.update(new_flags)
                return None
            # Record file references
            if line[:2] == '#:':
                if self._message.file_references:
                    # There is already a file reference, let's split it from
                    # the new one with a new line char.
                    self._message.file_references += '\n'
                self._message.file_references += line[2:].strip()
                return None
            # Record source comments
            if line[:2] == '#.':
                self._message.source_comment += line[2:].strip() + '\n'
                return None
            # Record comments
            self._message.comment += line[1:] + '\n'
            return None

        # Now we are in a msgctxt or msgid section, output previous section
        if line.startswith('msgid_plural'):
            if self._section != 'msgid':
                raise TranslationFormatSyntaxError(
                    line_number=self._lineno,
                    message="Unexpected keyword: msgid_plural")
            self._dumpCurrentSection()
            self._section = 'msgid_plural'
            line = line[len('msgid_plural'):]
        elif line.startswith('msgctxt'):
            if (self._section is not None and
                (self._section == 'msgctxt' or
                 self._section.startswith('msgid'))):
                raise TranslationFormatSyntaxError(
                    line_number=self._lineno,
                    message="Unexpected keyword: msgctxt")
            self._section = 'msgctxt'
            line = line[len('msgctxt'):]
        elif line.startswith('msgid'):
            if (self._section is not None and
                self._section.startswith('msgid')):
                raise TranslationFormatSyntaxError(
                    line_number=self._lineno,
                    message="Unexpected keyword: msgid")
            if self._section is not None:
                self._dumpCurrentSection()
            self._section = 'msgid'
            line = line[len('msgid'):]
            self._plural_case = None
        # Now we are in a msgstr section
        elif line.startswith('msgstr'):
            self._dumpCurrentSection()
            self._section = 'msgstr'
            line = line[len('msgstr'):]
            # XXX kiko 2005-08-19: if line is empty, it means we got an msgstr
            # followed by a newline; that may be critical, but who knows?
            if line.startswith('['):
                # Plural case
                new_plural_case, line = line[1:].split(']', 1)

                try:
                    new_plural_case = int(new_plural_case)
                except ValueError:
                    # Trigger "invalid plural case number" error.
                    new_plural_case = -1

                if new_plural_case < 0:
                    raise TranslationFormatSyntaxError(
                        line_number=self._lineno,
                        message="Invalid plural case number.")
                elif new_plural_case >= TranslationConstants.MAX_PLURAL_FORMS:
                    raise TranslationFormatSyntaxError(
                        line_number=self._lineno,
                        message="Unsupported plural case number.")

                if (self._plural_case is not None) and (
                        new_plural_case != self._plural_case + 1):
                    self._emitSyntaxWarning("Bad plural case number.")
                if new_plural_case != self._plural_case:
                    self._plural_case = new_plural_case
                else:
                    self._emitSyntaxWarning(
                        "msgstr[] repeats same plural case number.")
            else:
                self._plural_case = TranslationConstants.SINGULAR_FORM
        elif self._section is None:
            raise TranslationFormatSyntaxError(
                line_number=self._lineno,
                message='Invalid content: %r' % original_line)
        else:
            # This line could be the continuation of a previous section.
            pass

        line = line.strip()
        if len(line) == 0:
            self._emitSyntaxWarning(
                "Line has no content; this is not supported by some "
                "implementations of msgfmt.")
        return line

    def _parseLine(self, original_line):
        self._lineno += 1
        # Skip empty lines
        line = original_line.strip()
        if len(line) == 0:
            return

        if not self._escaped_line_break:
            line = self._parseFreshLine(line, original_line)
            if line is None or len(line) == 0:
                return

        line = self._parseQuotedString(line)

        text_section_types = ('msgctxt', 'msgid', 'msgid_plural', 'msgstr')
        if self._section not in text_section_types:
            raise TranslationFormatSyntaxError(
                line_number=self._lineno,
                message='Invalid content: %r' % original_line)

        self._parsed_content += line 
