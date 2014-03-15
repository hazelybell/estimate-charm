# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'MozillaXpiImporter',
    'MozillaZipImportParser',
    ]

from cStringIO import StringIO
import textwrap

from zope.component import getUtility
from zope.interface import implements

from lp.services.librarian.interfaces.client import ILibrarianClient
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationFormatImporter,
    TranslationFormatInvalidInputError,
    TranslationFormatSyntaxError,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.utilities.mozilla_dtd_parser import DtdFile
from lp.translations.utilities.mozilla_zip import MozillaZipTraversal
from lp.translations.utilities.translation_common_format import (
    TranslationFileData,
    TranslationMessageData,
    )
from lp.translations.utilities.xpi_header import XpiHeader


def add_source_comment(message, comment):
    """Add the given comment inside message.source_comment."""
    if message.source_comment:
        message.source_comment += comment
    else:
        message.source_comment = comment

    if not message.source_comment.endswith('\n'):
        message.source_comment += '\n'


class MozillaZipImportParser(MozillaZipTraversal):
    """XPI and jar parser for import purposes.

    Looks for DTD and properties files, and parses them for messages.
    All messages found are left in `self.messages`.
    """

    # List of ITranslationMessageData representing messages found.
    messages = None

    def _begin(self):
        """Overridable hook for `MozillaZipTraversal`."""
        self.messages = []

    def _finish(self):
        """Overridable hook for `MozillaZipTraversal`."""
        # Eliminate duplicate messages.
        seen_messages = set()
        deletions = []
        for index, message in enumerate(self.messages):
            identifier = (message.msgid_singular, message.context)
            if identifier in seen_messages:
                # This message is a duplicate.  Mark it for removal.
                deletions.append(index)
            else:
                seen_messages.add(identifier)
        for index in reversed(deletions):
            del self.messages[index]

        for message in self.messages:
            message.file_references = ', '.join(message.file_references_list)

    def _processTranslatableFile(self, entry, locale_code, xpi_path,
                                 chrome_path, filename_suffix):
        """Overridable hook for `MozillaZipTraversal`.

        This implementation is only interested in DTD and properties
        files.
        """
        if filename_suffix == '.dtd':
            parser = DtdFile
        elif filename_suffix == '.properties':
            parser = PropertyFile
        else:
            # We're not interested in other file types here.
            return

        # Parse file, subsume its messages.
        content = self.archive.read(entry)
        parsed_file = parser(
            filename=xpi_path, chrome_path=chrome_path, content=content)
        if parsed_file is not None:
            self.extend(parsed_file.messages)

    def _isTemplate(self):
        """Is this a template?"""
        name = self.filename
        return name is not None and name.startswith('en-US.xpi')

    def _processNestedJar(self, zip_instance):
        """Overridable hook for `MozillaZipTraversal`.

        This implementation complements `self.messages` with those found in
        the jar file we just parsed.
        """
        self.extend(zip_instance.messages)

    def _isCommandKeyMessage(self, message):
        """Whether the message represents a command key shortcut."""
        return (
            self._isTemplate() and
            message.translations and (
                message.msgid_singular.endswith('.commandkey') or
                message.msgid_singular.endswith('.key')))

    def _isAccessKeyMessage(self, message):
        """Whether the message represents an access key shortcut."""
        return (
            self._isTemplate() and
            message.translations and (
                message.msgid_singular.endswith('.accesskey')))

    def extend(self, newdata):
        """Complement `self.messages` with messages found in contained file.

        :param newdata: a sequence representing the messages found in a
            contained file.
        """
        for message in newdata:
            # Special case accesskeys and commandkeys:
            # these are single letter messages, lets display
            # the value as a source comment.
            if self._isCommandKeyMessage(message):
                comment = u'\n'.join(textwrap.wrap(
                    u"""Select the shortcut key that you want to use. It
                    should be translated, but often shortcut keys (for
                    example Ctrl + KEY) are not changed from the original. If
                    a translation already exists, please don't change it if
                    you are not sure about it. Please find the context of
                    the key from the end of the 'Located in' text below."""))
                add_source_comment(message, comment)
            elif self._isAccessKeyMessage(message):
                comment = u'\n'.join(textwrap.wrap(
                    u"""Select the access key that you want to use. These have
                    to be translated in a way that the selected character is
                    present in the translated string of the label being
                    referred to, for example 'i' in 'Edit' menu item in
                    English. If a translation already exists, please don't
                    change it if you are not sure about it. Please find the
                    context of the key from the end of the 'Located in' text
                    below."""))
                add_source_comment(message, comment)
            self.messages.append(message)




def valid_property_msgid(msgid):
    """Whether the given msgid follows the restrictions to be valid.

    Checks done are:
        - It cannot have white spaces.
    """
    return u' ' not in msgid


class PropertyFile:
    """Class for reading translatable messages from a .properties file.

    The file format is described at:
    http://www.mozilla.org/projects/l10n/mlp_chrome.html#text
    """

    license_block_text = u'END LICENSE BLOCK'

    def __init__(self, filename, chrome_path, content):
        """Constructs a dictionary from a .properties file.

        :arg filename: The file name where the content came from.
        :arg content: The file content that we want to parse.
        """
        self.filename = filename
        self.chrome_path = chrome_path
        self.messages = []

        # Parse the content.
        self.parse(content)

    def parse(self, content):
        """Parse given content as a property file.

        Once the parse is done, self.messages has a list of the available
        `ITranslationMessageData`s.
        """

        # .properties files are supposed to be unicode-escaped, but we know
        # that there are some .xpi language packs that instead, use UTF-8.
        # That's against the specification, but Mozilla applications accept
        # it anyway, so we try to support it too.
        # To do this support, we read the text as being in UTF-8
        # because unicode-escaped looks like ASCII files.
        try:
            content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise TranslationFormatInvalidInputError, (
                'Content is not valid unicode-escaped text')

        line_num = 0
        is_multi_line_comment = False
        last_comment = None
        last_comment_line_num = 0
        ignore_comment = False
        is_message = False
        translation = u''
        for line in content.splitlines():
            # Now, to "normalize" all to the same encoding, we encode to
            # unicode-escape first, and then decode it to unicode
            # XXX: Danilo 2006-08-01: we _might_ get performance
            # improvements if we reimplement this to work directly,
            # though, it will be hard to beat C-based de/encoder.
            # This call unescapes everything so we don't need to care about
            # quotes escaping.
            try:
                string = line.encode('raw-unicode_escape')
                line = string.decode('unicode_escape')
            except UnicodeDecodeError as exception:
                raise TranslationFormatInvalidInputError(
                    filename=self.filename, line_number=line_num,
                    message=str(exception))

            line_num += 1
            if not is_multi_line_comment:
                # Remove any white space before the useful data, like
                # ' # foo'.
                line = line.lstrip()
                if len(line) == 0:
                    # It's an empty line. Reset any previous comment we have.
                    last_comment = None
                    last_comment_line_num = 0
                    ignore_comment = False
                elif line.startswith(u'#') or line.startswith(u'//'):
                    # It's a whole line comment.
                    ignore_comment = False
                    line = line[1:].strip()
                    if last_comment:
                        last_comment += line
                    elif len(line) > 0:
                        last_comment = line

                    if last_comment and not last_comment.endswith('\n'):
                        # Comments must end always with a new line.
                        last_comment += '\n'

                    last_comment_line_num = line_num
                    continue

            # Unescaped URLs are a common mistake: the "//" starts an
            # end-of-line comment.  To work around that, treat "://" as
            # a special case.
            just_saw_colon = False

            while line:
                if is_multi_line_comment:
                    if line.startswith(u'*/'):
                        # The comment ended, we jump the closing tag and
                        # continue with the parsing.
                        line = line[2:]
                        is_multi_line_comment = False
                        last_comment_line_num = line_num
                        if ignore_comment:
                            last_comment = None
                            ignore_comment = False

                        # Comments must end always with a new line.
                        last_comment += '\n'
                    elif line.startswith(self.license_block_text):
                        # It's a comment with a licence notice, this
                        # comment can be ignored.
                        ignore_comment = True
                        # Jump the whole tag
                        line = line[len(self.license_block_text):]
                    else:
                        # Store the character.
                        if last_comment is None:
                            last_comment = line[0]
                        elif last_comment_line_num == line_num:
                            last_comment += line[0]
                        else:
                            last_comment = u'%s\n%s' % (last_comment, line[0])
                            last_comment_line_num = line_num
                        # Jump the processed char.
                        line = line[1:]
                    continue
                elif line.startswith(u'/*'):
                    # It's a multi line comment
                    is_multi_line_comment = True
                    ignore_comment = False
                    last_comment_line_num = line_num
                    # Jump the comment starting tag
                    line = line[2:]
                    continue
                elif line.startswith(u'//') and not just_saw_colon:
                    # End-of-line comment.
                    last_comment = '%s\n' % line[2:].strip()
                    last_comment_line_num = line_num
                    # On to next line.
                    break
                elif is_message:
                    # Store the char and continue.
                    head_char = line[0]
                    translation += head_char
                    line = line[1:]
                    just_saw_colon = (head_char == ':')
                    continue
                elif u'=' in line:
                    # Looks like a message string.
                    (key, value) = line.split('=', 1)
                    # Remove leading and trailing white spaces.
                    key = key.strip()

                    if valid_property_msgid(key):
                        is_message = True
                        # Jump the msgid, control chars and leading white
                        # space.
                        line = value.lstrip()
                        continue
                    else:
                        raise TranslationFormatSyntaxError(
                            line_number=line_num,
                            message=u"invalid msgid: '%s'" % key)
                else:
                    # Got a line that is not a valid message nor a valid
                    # comment. Ignore it because main en-US.xpi catalog from
                    # Firefox has such line/error. We follow the 'be strict
                    # with what you export, be permisive with what you import'
                    # policy.
                    break
            if is_message:
                # We just parsed a message, so we need to add it to the list
                # of messages.
                if ignore_comment or last_comment_line_num < line_num - 1:
                    # We must ignore the comment or either the comment is not
                    # the last thing before this message or is not in the same
                    # line as this message.
                    last_comment = None
                    ignore_comment = False

                message = TranslationMessageData()
                message.msgid_singular = key
                message.context = self.chrome_path
                message.file_references_list = [
                    "%s:%d(%s)" % (self.filename, line_num, key)]
                value = translation.strip()
                message.addTranslation(
                    TranslationConstants.SINGULAR_FORM, value)
                message.singular_text = value
                message.source_comment = last_comment
                self.messages.append(message)

                # Reset status vars.
                last_comment = None
                last_comment_line_num = 0
                is_message = False
                translation = u''


class MozillaXpiImporter:
    """Support class to import Mozilla .xpi files."""

    implements(ITranslationFormatImporter)

    def __init__(self):
        self.basepath = None
        self.productseries = None
        self.distroseries = None
        self.sourcepackagename = None
        self.by_maintainer = False
        self._translation_file = None

    def getFormat(self, file_contents):
        """See `ITranslationFormatImporter`."""
        return TranslationFileFormat.XPI

    priority = 0

    # using "application/x-xpinstall" would trigger installation in
    # firefox.
    content_type = 'application/zip'

    file_extensions = ['.xpi']
    template_suffix = 'en-US.xpi'

    uses_source_string_msgids = True

    def parse(self, translation_import_queue_entry):
        """See `ITranslationFormatImporter`."""
        self._translation_file = TranslationFileData()
        self.basepath = translation_import_queue_entry.path
        self.productseries = translation_import_queue_entry.productseries
        self.distroseries = translation_import_queue_entry.distroseries
        self.sourcepackagename = (
            translation_import_queue_entry.sourcepackagename)
        self.by_maintainer = translation_import_queue_entry.by_maintainer

        librarian_client = getUtility(ILibrarianClient)
        content = librarian_client.getFileByAlias(
            translation_import_queue_entry.content.id).read()

        parser = MozillaZipImportParser(self.basepath, StringIO(content))
        if parser.header is None:
            raise TranslationFormatInvalidInputError("No install.rdf found")

        self._translation_file.header = parser.header
        self._translation_file.messages = parser.messages

        return self._translation_file

    def getHeaderFromString(self, header_string):
        """See `ITranslationFormatImporter`."""
        return XpiHeader(header_string)

