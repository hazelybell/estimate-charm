# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Export module for XPI files using .po file format."""

__metaclass__ = type

__all__ = [
    'XPIPOExporter',
    ]

from zope.interface import implements

from lp.translations.interfaces.translationexporter import (
    ITranslationFormatExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.utilities.gettext_po_exporter import GettextPOExporter


class XPIPOExporter(GettextPOExporter):
    """Support class for exporting XPI files as .po files."""
    implements(ITranslationFormatExporter)

    format = TranslationFileFormat.XPIPO

    def __init__(self, context=None):
        super(XPIPOExporter, self).__init__(context=context)
        # 'context' is ignored because it's only required by the way the
        # exporters are instantiated but it isn't used by this class.

        self.format = TranslationFileFormat.XPIPO
        # XPIPOExporter is also able to export `TranslationFileFormat.PO`,
        # but there is not much practical use for that, so we are not listing
        # it as one of the supported formats for this exporter.
        self.supported_source_formats = [TranslationFileFormat.XPI]

    def exportTranslationMessageData(self, translation_message):
        """See `ITranslationFormatExporter`."""
        # XPI file format uses singular_text and plural_text instead of
        # msgid_singular and msgid_plural.
        if translation_message.singular_text is not None:
            translation_message.msgid_singular = (
                translation_message.singular_text)
        if translation_message.plural_text is not None:
            translation_message.msgid_plural = translation_message.plural_text
        return GettextPOExporter.exportTranslationMessageData(
            self, translation_message)
