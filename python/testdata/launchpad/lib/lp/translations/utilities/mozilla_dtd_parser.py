# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Importer for DTD files as found in XPI archives."""

__metaclass__ = type
__all__ = [
    'DtdFile'
    ]

from old_xmlplus.parsers.xmlproc import (
    dtdparser,
    utils,
    xmldtd,
    )

from lp.translations.interfaces.translationimporter import (
    TranslationFormatInvalidInputError,
    TranslationFormatSyntaxError,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )


class MozillaDtdConsumer(xmldtd.WFCDTD):
    """Mozilla DTD translatable message parser.

    msgids are stored as entities. This class extracts it along
    with translations, comments and source references.
    """
    def __init__(self, parser, filename, chrome_path, messages):
        self.started = False
        self.last_comment = None
        self.chrome_path = chrome_path
        self.messages = messages
        self.filename = filename
        xmldtd.WFCDTD.__init__(self, parser)

    def dtd_start(self):
        """See `xmldtd.WFCDTD`."""
        self.started = True

    def dtd_end(self):
        """See `xmldtd.WFCDTD`."""
        self.started = False

    def handle_comment(self, contents):
        """See `xmldtd.WFCDTD`."""
        if not self.started:
            return

        if self.last_comment is not None:
            self.last_comment += contents
        elif len(contents) > 0:
            self.last_comment = contents

        if self.last_comment and not self.last_comment.endswith('\n'):
            # Comments must end always with a new line.
            self.last_comment += '\n'

    def new_general_entity(self, name, value):
        """See `xmldtd.WFCDTD`."""
        if not self.started:
            return

        message = TranslationMessageData()
        message.msgid_singular = name
        # CarlosPerelloMarin 20070326: xmldtd parser does an inline
        # parsing which means that the content is all in a single line so we
        # don't have a way to show the line number with the source reference.
        message.file_references_list = ["%s(%s)" % (self.filename, name)]
        message.addTranslation(TranslationConstants.SINGULAR_FORM, value)
        message.singular_text = value
        message.context = self.chrome_path
        message.source_comment = self.last_comment
        self.messages.append(message)
        self.started += 1
        self.last_comment = None


class DtdErrorHandler(utils.ErrorCounter):
    """Error handler for the DTD parser."""
    filename = None

    def error(self, msg):
        raise TranslationFormatSyntaxError(
            filename=self.filename, message=msg)

    def fatal(self, msg):
        raise TranslationFormatInvalidInputError(
            filename=self.filename, message=msg)


class DummyDtdFile:
    """"File" returned when DTD SYSTEM entity tries to include a file."""
    done = False

    def read(self, *args, **kwargs):
        """Minimally satisfy attempt to read an included DTD file."""
        if self.done:
            return ''
        else:
            self.done = True
            return '<!-- SYSTEM entities not supported. -->'

    def close(self):
        """Satisfy attempt to close file."""
        pass


class DtdInputSourceFactoryStub:
    """Replace the class the DTD parser uses to include other DTD files."""

    def create_input_source(self, sysid):
        """Minimally satisfy attempt to open an included DTD file.

        This is called when the DTD parser hits a SYSTEM entity.
        """
        return DummyDtdFile()


class DtdFile:
    """Class for reading translatable messages from a .dtd file.

    It uses DTDParser which fills self.messages with parsed messages.
    """
    def __init__(self, filename, chrome_path, content):
        self.messages = []
        self.filename = filename
        self.chrome_path = chrome_path

        # .dtd files are supposed to be using UTF-8 encoding, if the file is
        # using another encoding, it's against the standard so we reject it
        try:
            content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise TranslationFormatInvalidInputError, (
                'Content is not valid UTF-8 text')

        error_handler = DtdErrorHandler()
        error_handler.filename = filename

        parser = dtdparser.DTDParser()
        parser.set_error_handler(error_handler)
        parser.set_inputsource_factory(DtdInputSourceFactoryStub())
        dtd = MozillaDtdConsumer(parser, filename, chrome_path, self.messages)
        parser.set_dtd_consumer(dtd)
        parser.parse_string(content)
