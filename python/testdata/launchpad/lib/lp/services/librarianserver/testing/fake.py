# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Fake, in-process implementation of the Librarian API.

This works in-process only.  It does not support exchange of files
between processes, or URL access.  Nor will it completely support all
details of the Librarian interface.  But where it's enough, this
provides a simple and fast alternative to the full Librarian in unit
tests.
"""

__metaclass__ = type
__all__ = [
    'FakeLibrarian',
    ]

import hashlib
from StringIO import StringIO
from urlparse import urljoin

from fixtures import Fixture
import transaction
from transaction.interfaces import ISynchronizer
import zope.component
from zope.interface import implements

from lp.services.config import config
from lp.services.librarian.client import get_libraryfilealias_download_path
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.interfaces.client import (
    ILibrarianClient,
    LIBRARIAN_SERVER_DEFAULT_TIMEOUT,
    )
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileContent,
    )


class InstrumentedLibraryFileAlias(LibraryFileAlias):
    """A `ILibraryFileAlias` implementation that fakes library access."""

    file_committed = False

    def checkCommitted(self):
        """Raise an error if this file has not been committed yet."""
        if not self.file_committed:
            raise LookupError(
                "Attempting to retrieve file '%s' from the fake "
                "librarian, but the file has not yet been committed to "
                "storage." % self.filename)

    def open(self, timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        self.checkCommitted()
        self._datafile = StringIO(self.content_string)

    def read(self, chunksize=None, timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        return self._datafile.read(chunksize)


class FakeLibrarian(Fixture):
    """A test double Librarian which works in-process.

    This takes the role of both the librarian client and the LibraryFileAlias
    utility.
    """
    provided_utilities = [ILibrarianClient, ILibraryFileAliasSet]
    implements(ISynchronizer, *provided_utilities)

    def setUp(self):
        """Fixture API: install as the librarian."""
        Fixture.setUp(self)
        self.aliases = {}
        self.download_url = config.librarian.download_url
        transaction.manager.registerSynch(self)
        self.addCleanup(transaction.manager.unregisterSynch, self)

        site_manager = zope.component.getGlobalSiteManager()
        for utility in self.provided_utilities:
            original = zope.component.getUtility(utility)
            if site_manager.unregisterUtility(original, utility):
                # We really disabled a utility, restore it later.
                self.addCleanup(
                    zope.component.provideUtility, original, utility)
            zope.component.provideUtility(self, utility)
            self.addCleanup(site_manager.unregisterUtility, self, utility)

    def addFile(self, name, size, file, contentType, expires=None):
        """See `IFileUploadClient`."""
        return self._storeFile(
            name, size, file, contentType, expires=expires).id

    def _storeFile(self, name, size, file, contentType, expires=None):
        """Like `addFile`, but returns the `LibraryFileAlias`."""
        content = file.read()
        real_size = len(content)
        if real_size != size:
            raise AssertionError(
                "Uploading '%s' to the fake librarian with incorrect "
                "size %d; actual size is %d." % (name, size, real_size))

        file_ref = self._makeLibraryFileContent(content)
        alias = self._makeAlias(file_ref.id, name, content, contentType)
        self.aliases[alias.id] = alias
        return alias

    def remoteAddFile(self, name, size, file, contentType, expires=None):
        """See `IFileUploadClient`."""
        return NotImplementedError()

    def getURLForAlias(self, aliasID, secure=False):
        """See `IFileDownloadClient`."""
        return self.getURLForAliasObject(self.aliases.get(int(aliasID)))

    def getURLForAliasObject(self, alias):
        """See `IFileDownloadClient`."""
        if alias.deleted:
            return None
        path = get_libraryfilealias_download_path(alias.id, alias.filename)
        return urljoin(self.download_url, path)

    def getFileByAlias(self, aliasID,
                       timeout=LIBRARIAN_SERVER_DEFAULT_TIMEOUT):
        """See `IFileDownloadClient`."""
        alias = self[aliasID]
        alias.checkCommitted()
        return StringIO(alias.content_string)

    def pretendCommit(self):
        """Pretend that there's been a commit.

        When you add a file to the librarian (real or fake), it is not
        fully available until the transaction that added the file has
        been committed.  Call this method to make the FakeLibrarian act
        as if there's been a commit, without actually committing a
        database transaction.
        """
        # Note that all files have been committed to storage.
        for alias in self.aliases.itervalues():
            alias.file_committed = True

    def _makeAlias(self, file_id, name, content, content_type):
        """Create a `LibraryFileAlias`."""
        alias = InstrumentedLibraryFileAlias(
            contentID=file_id, filename=name, mimetype=content_type)
        alias.content_string = content
        return alias

    def _makeLibraryFileContent(self, content):
        """Create a `LibraryFileContent`."""
        size = len(content)
        md5 = hashlib.md5(content).hexdigest()
        sha1 = hashlib.sha1(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()

        content_object = LibraryFileContent(
            filesize=size, md5=md5, sha1=sha1, sha256=sha256)
        return content_object

    def create(self, name, size, file, contentType, expires=None,
               debugID=None, restricted=False):
        "See `ILibraryFileAliasSet`."""
        return self._storeFile(name, size, file, contentType, expires=expires)

    def __getitem__(self, key):
        "See `ILibraryFileAliasSet`."""
        alias = self.aliases.get(key)
        if alias is None:
            raise LookupError(
                "Attempting to retrieve file alias %d from the fake "
                "librarian, who has never heard of it." % key)
        return alias

    def findBySHA1(self, sha1):
        "See `ILibraryFileAliasSet`."""
        for alias in self.aliases.itervalues():
            if alias.content.sha1 == sha1:
                return alias

        return None

    def beforeCompletion(self, txn):
        """See `ISynchronizer`."""

    def afterCompletion(self, txn):
        """See `ISynchronizer`."""
        self.pretendCommit()

    def newTransaction(self, txn):
        """See `ISynchronizer`."""
