# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'GettextPOImporter',
    ]

from zope.component import getUtility
from zope.interface import implements

from lp.services.librarian.interfaces.client import ILibrarianClient
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationFormatImporter,
    )
from lp.translations.utilities.gettext_po_parser import (
    POHeader,
    POParser,
    )


class GettextPOImporter:
    """Support class to import gettext .po files."""
    implements(ITranslationFormatImporter)

    def __init__(self, context=None):
        self.basepath = None
        self.productseries = None
        self.distroseries = None
        self.sourcepackagename = None
        self.by_maintainer = False
        self.content = None

    def getFormat(self, file_contents):
        """See `ITranslationFormatImporter`."""
        return TranslationFileFormat.PO

    priority = 0

    content_type = 'application/x-po'

    file_extensions = ['.po', '.pot']
    template_suffix = '.pot'

    uses_source_string_msgids = False

    def parse(self, translation_import_queue_entry):
        """See `ITranslationFormatImporter`."""
        self.basepath = translation_import_queue_entry.path
        self.productseries = translation_import_queue_entry.productseries
        self.distroseries = translation_import_queue_entry.distroseries
        self.sourcepackagename = (
            translation_import_queue_entry.sourcepackagename)
        self.by_maintainer = translation_import_queue_entry.by_maintainer

        librarian_client = getUtility(ILibrarianClient)
        self.content = librarian_client.getFileByAlias(
            translation_import_queue_entry.content.id)

        pofile = translation_import_queue_entry.pofile
        if pofile is None:
            pluralformula = None
        else:
            pluralformula = pofile.language.pluralexpression
        parser = POParser(pluralformula)
        return parser.parse(self.content.read())

    def getHeaderFromString(self, header_string):
        """See `ITranslationFormatImporter`."""
        return POHeader(header_string)
