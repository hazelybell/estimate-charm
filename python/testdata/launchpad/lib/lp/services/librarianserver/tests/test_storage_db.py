# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import hashlib
import shutil
import tempfile
import unittest

from lp.services.database.sqlbase import flush_database_updates
from lp.services.librarian.model import LibraryFileContent
from lp.services.librarianserver import db
from lp.services.librarianserver.storage import (
    DigestMismatchError,
    DuplicateFileIDError,
    LibrarianStorage,
    LibraryFileUpload,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class LibrarianStorageDBTests(unittest.TestCase):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        switch_dbuser('librarian')
        self.directory = tempfile.mkdtemp()
        self.storage = LibrarianStorage(self.directory, db.Library())

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_addFile(self):
        data = 'data ' * 50
        digest = hashlib.sha1(data).hexdigest()
        newfile = self.storage.startAddFile('file1', len(data))
        newfile.srcDigest = digest
        newfile.append(data)
        fileid, aliasid = newfile.store()
        self.failUnless(self.storage.hasFile(fileid))

    def test_addFiles_identical(self):
        # Start adding two files with identical data
        data = 'data ' * 5000
        newfile1 = self.storage.startAddFile('file1', len(data))
        newfile2 = self.storage.startAddFile('file2', len(data))
        newfile1.append(data)
        newfile2.append(data)
        id1, alias1 = newfile1.store()
        id2, alias2 = newfile2.store()

        # Make sure we actually got an id
        self.assertNotEqual(None, id1)
        self.assertNotEqual(None, id2)

        # But they are two different ids, because we leave duplicate handling
        # to the garbage collector
        self.failIfEqual(id1, id2)

    def test_badDigest(self):
        data = 'data ' * 50
        digest = 'crud'
        newfile = self.storage.startAddFile('file', len(data))
        newfile.srcDigest = digest
        newfile.append(data)
        self.assertRaises(DigestMismatchError, newfile.store)

    def test_alias(self):
        # Add a file (and so also add an alias)
        data = 'data ' * 50
        newfile = self.storage.startAddFile('file1', len(data))
        newfile.mimetype = 'text/unknown'
        newfile.append(data)
        fileid, aliasid = newfile.store()

        # Check that its alias has the right mimetype
        fa = self.storage.getFileAlias(aliasid, None, '/')
        self.assertEqual('text/unknown', fa.mimetype)

        # Re-add the same file, with the same name and mimetype...
        newfile2 = self.storage.startAddFile('file1', len(data))
        newfile2.mimetype = 'text/unknown'
        newfile2.append(data)
        fileid2, aliasid2 = newfile2.store()

        # Verify that we didn't get back the same alias ID
        self.assertNotEqual(fa.id,
            self.storage.getFileAlias(aliasid2, None, '/').id)

    def test_clientProvidedDuplicateIDs(self):
        # This test checks the new behaviour specified by LibrarianTransactions
        # spec: don't create IDs in DB, but do check they don't exist.

        # Create a new file
        newfile = LibraryFileUpload(self.storage, 'filename', 0)

        # Set a content ID on the file (same as would happen with a
        # client-generated ID) and store it
        newfile.contentID = 666
        newfile.store()

        newfile = LibraryFileUpload(self.storage, 'filename', 0)
        newfile.contentID = 666
        self.assertRaises(DuplicateFileIDError, newfile.store)

    def test_clientProvidedDuplicateContent(self):
        # Check the new behaviour specified by LibrarianTransactions
        # spec: allow duplicate content with distinct IDs.

        content = 'some content'

        # Store a file with id 6661
        newfile1 = LibraryFileUpload(self.storage, 'filename', 0)
        newfile1.contentID = 6661
        newfile1.append(content)
        fileid1, aliasid1 = newfile1.store()

        # Store second file identical to the first, with id 6662
        newfile2 = LibraryFileUpload(self.storage, 'filename', 0)
        newfile2.contentID = 6662
        newfile2.append(content)
        fileid2, aliasid2 = newfile2.store()

        # Create rows in the database for these files.
        LibraryFileContent(
            filesize=0, sha1='foo', md5='xx', sha256='xx', id=6661)
        LibraryFileContent(
            filesize=0, sha1='foo', md5='xx', sha256='xx', id=6662)

        flush_database_updates()
        # And no errors should have been raised!
