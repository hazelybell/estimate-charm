# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The `IHasTranslationImports` interface."""

__metaclass__ = type
__all__ = [
    'IHasTranslationImports',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    export_read_operation,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    )
from zope.interface import Interface
from zope.schema import (
    Choice,
    TextLine,
    )

from lp import _
from lp.translations.enums import RosettaImportStatus


class IHasTranslationImports(Interface):
    """An entity that has a translation import queue.

    Examples include `ProductSeries`, `SourcePackage`, `DistroSeries`,
    and `Person`.
    """
    export_as_webservice_entry(
        singular_name='object_with_translation_imports',
        plural_name='objects_with_translation_imports')

    def getFirstEntryToImport():
        """Return the first entry of the queue ready to be imported."""

    @operation_parameters(
        import_status=Choice(
            title=_("Status"),
            description=_("Show only entries with this status"),
            vocabulary=RosettaImportStatus,
            required=False),
        file_extension=TextLine(
            title=_("Filename extension"),
            description=_("Show only entries with this filename suffix"),
            required=False))
    # Really ITranslationImportQueueEntry.  Fixed up in
    # _schema_circular_imports.py.
    @operation_returns_collection_of(Interface)
    @export_read_operation()
    @operation_for_version('beta')
    def getTranslationImportQueueEntries(import_status=None,
                                         file_extension=None):
        """Return entries in the translation import queue for this entity.

        :arg import_status: RosettaImportStatus DB Schema entry.
        :arg file_extension: String with the file type extension, usually 'po'
            or 'pot'.

        If one of both of 'import_status' or 'file_extension' are given, the
        returned entries are filtered based on those values.
        """
