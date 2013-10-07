# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `RepositoryIndexFile`."""

__metaclass__ = type

import bz2
import gzip
import os
import shutil
import stat
import tempfile
import unittest

from lp.archivepublisher.utils import RepositoryIndexFile


class TestRepositoryArchiveIndex(unittest.TestCase):

    def setUp(self):
        """Create temporary directories to be used in tests.

        'root': final destination for repository files.
        'temp_root': temporary destination for reporsitory files.
        """
        self.root = tempfile.mkdtemp()
        self.temp_root = tempfile.mkdtemp()

    def tearDown(self):
        """Purge temporary files created on `setUp`."""
        for path in [self.root, self.temp_root]:
            shutil.rmtree(path)

    def getRepoFile(self, filename):
        """Return a `RepositoryIndexFile` for the given filename.

        The `RepositoryIndexFile` is created with the test 'root' and
        'temp_root'.
        """
        return RepositoryIndexFile(
            os.path.join(self.root, filename), self.temp_root)

    def testWorkflow(self):
        """`RepositoryIndexFile` workflow.

        On creation, 3 temporary files are atomically created in the
        'temp_root' location (mkstemp). One for storing the plain contents
        and other for the corresponding compressed contents. At this point,
        no files were created in the 'root' location yet.

        Once the `RepositoryIndexFile` is closed, the files in 'temp_root'
        are closed and moved to 'root' with their expected names.

        Additionally, the resulting files are made readable and writable by
        their group and readable by others.
        """
        repo_file = self.getRepoFile('boing')

        self.assertEqual(0, len(os.listdir(self.root)))
        self.assertEqual(3, len(os.listdir(self.temp_root)))

        repo_file.close()

        self.assertEqual(3, len(os.listdir(self.root)))
        self.assertEqual(0, len(os.listdir(self.temp_root)))

        resulting_files = sorted(os.listdir(self.root))
        self.assertEqual(
            ['boing', 'boing.bz2', 'boing.gz'], resulting_files)

        for filename in resulting_files:
            file_path = os.path.join(self.root, filename)
            mode = stat.S_IMODE(os.stat(file_path).st_mode)
            self.assertTrue(
                (stat.S_IWGRP | stat.S_IRGRP | stat.S_IROTH) & mode)

    def testWrite(self):
        """`RepositoryIndexFile` writing.

        Writes to a `RepositoryIndexFile` happens simultaneously in both
        of its counter-parts (plain and gzipped contents). Once the file
        is closed both resulting files have the same contents, one plain and
        other compressed.
        """
        repo_file = self.getRepoFile('boing')
        repo_file.write('hello')
        repo_file.close()

        plain_content = open(os.path.join(self.root, 'boing')).read()
        gzip_content = gzip.open(os.path.join(self.root, 'boing.gz')).read()
        bz2_content = bz2.decompress(
            open(os.path.join(self.root, 'boing.bz2')).read())

        self.assertEqual(plain_content, bz2_content)
        self.assertEqual(plain_content, gzip_content)
        self.assertEqual('hello', plain_content)

    def testUnreferencing(self):
        """`RepositoryIndexFile` unreferencing.

        When a `RepositoryIndexFile` is unreferenced it takes care of
        removing the created files in the 'temp_root'.
        """
        repo_file = self.getRepoFile('boing')

        self.assertEqual(0, len(os.listdir(self.root)))
        self.assertEqual(3, len(os.listdir(self.temp_root)))

        del repo_file

        self.assertEqual(0, len(os.listdir(self.root)))
        self.assertEqual(0, len(os.listdir(self.temp_root)))

    def testRootCreation(self):
        """`RepositoryIndexFile` creates given 'root' path if necessary."""
        missing_root = os.path.join(self.root, 'donotexist')
        repo_file = RepositoryIndexFile(
            os.path.join(missing_root, 'boing'), self.temp_root)

        self.assertFalse(os.path.exists(missing_root))

        repo_file.close()

        self.assertEqual(
            ['boing', 'boing.bz2', 'boing.gz'],
            sorted(os.listdir(missing_root)))

    def testMissingTempRoot(self):
        """`RepositoryIndexFile` cannot be given a missing 'temp_root'."""
        missing_temp_root = os.path.join(self.temp_root, 'donotexist')
        self.assertRaises(
            AssertionError, RepositoryIndexFile,
            os.path.join(self.root, 'boing'), missing_temp_root)
