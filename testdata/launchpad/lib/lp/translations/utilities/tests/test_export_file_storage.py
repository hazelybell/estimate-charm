# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `ExportFileStorage`."""

__metaclass__ = type

from cStringIO import StringIO
from tarfile import TarFile
import unittest

from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.utilities.translation_export import ExportFileStorage


class ExportFileStorageTestCase(unittest.TestCase):
    """Test class for translation importer component."""
    layer = LaunchpadZopelessLayer

    def testEmpty(self):
        """Behaviour of empty storage."""
        mime = 'application/x-po'
        storage = ExportFileStorage()
        # Try not inserting any files, so the storage object remains empty.
        self.assertTrue(storage._store.isEmpty())
        self.assertFalse(storage._store.isFull())
        # Can't export an empty storage.
        self.assertRaises(AssertionError, storage.export)

    def testFull(self):
        """Behaviour of isFull."""
        mime = 'application/x-po'
        storage = ExportFileStorage()
        storage.addFile('/tmp/a/test/file.po', 'po', 'test file', mime)
        # The storage object starts out with a SingleFileStorageStrategy, so
        # it's full now that we've added one file.
        self.assertTrue(storage._store.isFull())
        # If we add another file however, the storage object transparently
        # switches to a TarballFileStorageStrategy.  That type of storage
        # object is never full.
        storage.addFile(
            '/tmp/another/test/file.po', 'po', 'test file two', mime)
        self.assertFalse(storage._store.isFull())
        # We can now add any number of files without filling the storage
        # object.
        storage.addFile(
            '/tmp/yet/another/test/file.po', 'po', 'test file 3', mime)
        self.assertFalse(storage._store.isFull())

    def testSingle(self):
        """Test export of single file."""
        mime = 'application/x-po'
        storage = ExportFileStorage()
        storage.addFile('/tmp/a/test/file.po', 'po', 'test file', mime)
        outfile = storage.export()
        self.assertEquals(outfile.path, '/tmp/a/test/file.po')
        self.assertEquals(outfile.file_extension, 'po')
        self.assertEquals(outfile.read(), 'test file')

    def testTarball(self):
        """Test export of tarball."""
        mime = 'application/x-po'
        storage = ExportFileStorage()
        storage.addFile('/tmp/a/test/file.po', 'po', 'test file', mime)
        storage.addFile(
            '/tmp/another/test.po', 'po', 'another test file', mime)
        outfile = storage.export()
        tarball = TarFile.open(mode='r|gz', fileobj=StringIO(outfile.read()))
        elements = set(tarball.getnames())
        self.assertTrue('/tmp/a/test/file.po' in elements)
        self.assertTrue('/tmp/another/test.po' in elements)
