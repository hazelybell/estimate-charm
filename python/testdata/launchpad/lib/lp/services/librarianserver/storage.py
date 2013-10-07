# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import errno
import hashlib
import os
import shutil
import tempfile

from lp.registry.model.product import Product
from lp.services.config import dbconfig
from lp.services.database import write_transaction
from lp.services.database.interfaces import IStore
from lp.services.database.postgresql import ConnectionString


__all__ = [
    'DigestMismatchError',
    'LibrarianStorage',
    'LibraryFileUpload',
    'DuplicateFileIDError',
    'WrongDatabaseError',
    # _relFileLocation needed by other modules in this package.
    # Listed here to keep the import fascist happy
    '_relFileLocation',
    '_sameFile',
    ]


class DigestMismatchError(Exception):
    """The given digest doesn't match the SHA-1 digest of the file."""


class DuplicateFileIDError(Exception):
    """Given File ID already exists."""


class WrongDatabaseError(Exception):
    """The client's database name doesn't match our database."""

    def __init__(self, clientDatabaseName, serverDatabaseName):
        Exception.__init__(self, clientDatabaseName, serverDatabaseName)
        self.clientDatabaseName = clientDatabaseName
        self.serverDatabaseName = serverDatabaseName


class LibrarianStorage:
    """Blob storage.

    This manages the actual storage of files on disk and the record of those
    in the database; it has nothing to do with the network interface to those
    files.
    """

    def __init__(self, directory, library):
        self.directory = directory
        self.library = library
        self.incoming = os.path.join(self.directory, 'incoming')
        try:
            os.mkdir(self.incoming)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def hasFile(self, fileid):
        return os.access(self._fileLocation(fileid), os.F_OK)

    def _fileLocation(self, fileid):
        return os.path.join(self.directory, _relFileLocation(str(fileid)))

    def startAddFile(self, filename, size):
        return LibraryFileUpload(self, filename, size)

    def getFileAlias(self, aliasid, token, path):
        return self.library.getAlias(aliasid, token, path)


class LibraryFileUpload(object):
    """A file upload from a client."""
    srcDigest = None
    mimetype = 'unknown/unknown'
    contentID = None
    aliasID = None
    expires = None
    databaseName = None
    debugID = None

    def __init__(self, storage, filename, size):
        self.storage = storage
        self.filename = filename
        self.size = size
        self.debugLog = []

        # Create temporary file
        tmpfile, tmpfilepath = tempfile.mkstemp(dir=self.storage.incoming)
        self.tmpfile = os.fdopen(tmpfile, 'w')
        self.tmpfilepath = tmpfilepath
        self.md5_digester = hashlib.md5()
        self.sha1_digester = hashlib.sha1()
        self.sha256_digester = hashlib.sha256()

    def append(self, data):
        self.tmpfile.write(data)
        self.md5_digester.update(data)
        self.sha1_digester.update(data)
        self.sha256_digester.update(data)

    @write_transaction
    def store(self):
        self.debugLog.append('storing %r, size %r'
                             % (self.filename, self.size))
        self.tmpfile.close()

        # Verify the digest matches what the client sent us
        dstDigest = self.sha1_digester.hexdigest()
        if self.srcDigest is not None and dstDigest != self.srcDigest:
            # XXX: Andrew Bennetts 2004-09-20: Write test that checks that
            # the file really is removed or renamed, and can't possibly be
            # left in limbo
            os.remove(self.tmpfilepath)
            raise DigestMismatchError(self.srcDigest, dstDigest)

        try:
            # If the client told us the name of the database it's using,
            # check that it matches.
            if self.databaseName is not None:
                # Per Bug #840068, there are two methods of getting the
                # database name (connection string and db
                # introspection), and they can give different results
                # due to pgbouncer database aliases. Lets check both,
                # and succeed if either matches.
                config_dbname = ConnectionString(
                    dbconfig.rw_main_master).dbname

                result = IStore(Product).execute("SELECT current_database()")
                real_dbname = result.get_one()[0]
                if self.databaseName not in (config_dbname, real_dbname):
                    raise WrongDatabaseError(
                        self.databaseName, (config_dbname, real_dbname))

            self.debugLog.append(
                'database name %r ok' % (self.databaseName, ))
            # If we haven't got a contentID, we need to create one and return
            # it to the client.
            if self.contentID is None:
                contentID = self.storage.library.add(
                        dstDigest, self.size, self.md5_digester.hexdigest(),
                        self.sha256_digester.hexdigest())
                aliasID = self.storage.library.addAlias(
                        contentID, self.filename, self.mimetype, self.expires)
                self.debugLog.append('created contentID: %r, aliasID: %r.'
                                     % (contentID, aliasID))
            else:
                contentID = self.contentID
                aliasID = None
                self.debugLog.append('received contentID: %r' % (contentID, ))

        except:
            # Abort transaction and re-raise
            self.debugLog.append('failed to get contentID/aliasID, aborting')
            raise

        # Move file to final location
        try:
            self._move(contentID)
        except:
            # Abort DB transaction
            self.debugLog.append('failed to move file, aborting')

            # Remove file
            os.remove(self.tmpfilepath)

            # Re-raise
            raise

        # Commit any DB changes
        self.debugLog.append('committed')

        # Return the IDs if we created them, or None otherwise
        return contentID, aliasID

    def _move(self, fileID):
        location = self.storage._fileLocation(fileID)
        if os.path.exists(location):
            raise DuplicateFileIDError(fileID)
        try:
            os.makedirs(os.path.dirname(location))
        except OSError as e:
            # If the directory already exists, that's ok.
            if e.errno != errno.EEXIST:
                raise
        shutil.move(self.tmpfilepath, location)


def _sameFile(path1, path2):
    file1 = open(path1, 'rb')
    file2 = open(path2, 'rb')

    blk = 1024 * 64
    chunksIter = iter(lambda: (file1.read(blk), file2.read(blk)), ('', ''))
    for chunk1, chunk2 in chunksIter:
        if chunk1 != chunk2:
            return False
    return True


def _relFileLocation(file_id):
    """Return the relative location for the given file_id.

    The relative location is obtained by converting file_id into a 8-digit hex
    and then splitting it across four path segments.
    """
    h = "%08x" % int(file_id)
    return '%s/%s/%s/%s' % (h[:2], h[2:4], h[4:6], h[6:])
