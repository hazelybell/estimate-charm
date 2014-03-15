# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Base classes for HTTP resources."""

__metaclass__ = type
__all__ = [
    'LibraryBackedByteStorage',
]


from cStringIO import StringIO

from lazr.restful.interfaces import IByteStorage
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.interface import implements

from lp.services.librarian.interfaces import (
    ILibraryFileAliasSet,
    ILibraryFileAliasWithParent,
    )
from lp.services.webapp.interfaces import ICanonicalUrlData


class LibraryBackedByteStorage:
    """See `IByteStorage`."""
    implements(IByteStorage, ICanonicalUrlData)

    def __init__(self, entry, field):
        """Initialize as the backing storage for one entry's field."""
        self.entry = entry
        self.field = field
        self.file_alias = getattr(self.entry, self.field.__name__)

    @property
    def rootsite(self):
        """See `ICanonicalUrlData`"""
        return None

    @property
    def inside(self):
        """See `ICanonicalUrlData`"""
        return self.entry.context

    @property
    def path(self):
        """See `ICanonicalUrlData`"""
        return self.field.__name__

    @property
    def alias_url(self):
        """See `IByteStorage`."""
        if self.file_alias.restricted:
            lfa_with_parent = getMultiAdapter(
                (self.file_alias, self.entry.context),
                ILibraryFileAliasWithParent)
            token = lfa_with_parent.createToken()
            return self.file_alias.private_url + '?token=%s' % token
        return self.file_alias.getURL()

    @property
    def filename(self):
        """See `IByteStorage`."""
        if self.is_stored:
            return self.file_alias.filename
        return self.field.__name__

    @property
    def is_stored(self):
        """See `IByteStorage`."""
        return self.file_alias is not None

    def createStored(self, mediaType, representation, filename=None):
        """See `IByteStorage`."""
        if filename is None:
            filename = self.filename
        stored = getUtility(ILibraryFileAliasSet).create(
            name=filename, size=len(representation),
            file=StringIO(representation), contentType=mediaType)
        setattr(self.entry, self.field.__name__, stored)

    def deleteStored(self):
        """See `IByteStorage`."""
        setattr(self.entry, self.field.__name__, None)
