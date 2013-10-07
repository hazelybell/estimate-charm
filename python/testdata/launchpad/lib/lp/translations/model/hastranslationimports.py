# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Model code for `IHasTranslationImports."""

__metaclass__ = type
__all__ = [
    'HasTranslationImportsMixin',
    ]

from zope.component import getUtility

from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


class HasTranslationImportsMixin:
    """Helper class for implementing `IHasTranslationImports`."""

    def getFirstEntryToImport(self):
        """See `IHasTranslationImports`."""
        translation_import_queue = getUtility(ITranslationImportQueue)
        return translation_import_queue.getFirstEntryToImport(target=self)

    def getTranslationImportQueueEntries(self, import_status=None,
                                         file_extension=None):
        """See `IHasTranslationImports`."""
        if file_extension is None:
            extensions = None
        else:
            extensions = [file_extension]
        translation_import_queue = getUtility(ITranslationImportQueue)
        return translation_import_queue.getAllEntries(
            target=self, import_status=import_status,
            file_extensions=extensions)
