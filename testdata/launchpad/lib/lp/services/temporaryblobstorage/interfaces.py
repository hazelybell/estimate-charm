# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Temporary blob storage interfaces."""

__metaclass__ = type

__all__ = [
    'ITemporaryBlobStorage',
    'ITemporaryStorageManager',
    'BlobTooLarge',
    ]

from lazr.restful.declarations import (
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_parameters,
    rename_parameters_as,
    )
from lazr.restful.interface import copy_field
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bytes,
    Datetime,
    Text,
    )

from lp import _


class BlobTooLarge(Exception):
    """Raised if attempting to create a blob larger than the maximum
       allowed size.
    """
    pass


class ITemporaryBlobStorage(Interface):
    """A blob which we will store in the database temporarily."""
    export_as_webservice_entry(
        singular_name='temporary_blob', plural_name='temporary_blobs',
        as_of="beta")

    uuid = exported(
        Text(title=_('UUID'), required=True, readonly=True),
        exported_as='token', as_of="beta")
    blob = Bytes(title=_('BLOB'), required=True, readonly=True)
    date_created = Datetime(title=_('Date created'),
        required=True, readonly=True)
    file_alias = Attribute("Link to actual storage of blob")

    @export_read_operation()
    def hasBeenProcessed():
        """Return True if this blob has been processed."""

    @export_read_operation()
    def getProcessedData():
        """Returns a dict containing the processed blob data."""


class ITemporaryStorageManager(Interface):
    """A tool to create temporary blobs."""
    export_as_webservice_collection(ITemporaryBlobStorage)

    def new(blob, expires=None):
        """Create a new blob for storage in the database, returning the
        UUID assigned to it.

        May raise a BlobTooLarge exception.

        Default expiry timestamp is calculated using
        config.launchpad.default_blob_expiry
        """

    @rename_parameters_as(uuid='token')
    @operation_parameters(uuid=copy_field(ITemporaryBlobStorage['uuid']))
    @export_read_operation()
    def fetch(uuid):
        """Retrieve a TemporaryBlobStorage by uuid."""

    def delete(uuid):
        """Delete a TemporaryBlobStorage by uuid."""

    @collection_default_content()
    def default_temporary_blob_storage_list():
        """Return an empty set - only exists to keep lazr.restful happy."""
