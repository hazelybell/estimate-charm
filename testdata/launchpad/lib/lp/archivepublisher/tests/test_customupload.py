# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `CustomUploads`."""

__metaclass__ = type


import cStringIO
import os
import shutil
import tarfile
import tempfile
import unittest

from lp.archivepublisher.customupload import (
    CustomUpload,
    CustomUploadTarballBadFile,
    CustomUploadTarballBadSymLink,
    CustomUploadTarballInvalidFileType,
    )
from lp.testing import TestCase


class TestCustomUpload(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='archive_root_')

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def assertEntries(self, entries):
        self.assertEqual(
            entries, sorted(os.listdir(self.test_dir)))

    def testFixCurrentSymlink(self):
        """Test `CustomUpload.fixCurrentSymlink` behaviour.

        Ensure only 3 entries named as valid versions are kept around and
        the 'current' symbolic link is created (or updated) to point to the
        latests entry.

        Also check if it copes with entries not named as valid versions and
        leave them alone.
        """
        # Setup a bogus `CustomUpload` object with the 'targetdir' pointing
        # to the directory created for the test.
        custom_processor = CustomUpload()
        custom_processor.targetdir = self.test_dir

        # Let's create 4 entries named as valid versions.
        os.mkdir(os.path.join(self.test_dir, '1.0'))
        os.mkdir(os.path.join(self.test_dir, '1.1'))
        os.mkdir(os.path.join(self.test_dir, '1.2'))
        os.mkdir(os.path.join(self.test_dir, '1.3'))
        self.assertEntries(['1.0', '1.1', '1.2', '1.3'])

        # `fixCurrentSymlink` will keep only the latest 3 and create a
        # 'current' symbolic link the highest one.
        custom_processor.fixCurrentSymlink()
        self.assertEntries(['1.1', '1.2', '1.3', 'current'])
        self.assertEqual(
            '1.3', os.readlink(os.path.join(self.test_dir, 'current')))

        # When there is a invalid version present in the directory it is
        # ignored, since it was probably put there manually. The symbolic
        # link still pointing to the latest version.
        os.mkdir(os.path.join(self.test_dir, '1.4'))
        os.mkdir(os.path.join(self.test_dir, 'alpha-5'))
        custom_processor.fixCurrentSymlink()
        self.assertEntries(['1.2', '1.3', '1.4', 'alpha-5', 'current'])
        self.assertEqual(
            '1.4', os.readlink(os.path.join(self.test_dir, 'current')))


class TestTarfileVerification(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.tarfile_path = "/tmp/_verify_extract"
        self.tarfile_name = os.path.join(self.tarfile_path, "test_tarfile.tar")
        self.custom_processor = CustomUpload()
        self.custom_processor.tmpdir = self.makeTemporaryDirectory()
        self.custom_processor.tarfile_path = self.tarfile_name

    def createTarfile(self):
        self.tar_fileobj = cStringIO.StringIO()
        tar_file = tarfile.open(name=None, mode="w", fileobj=self.tar_fileobj)
        root_info = tarfile.TarInfo(name='./')
        root_info.type = tarfile.DIRTYPE
        tar_file.addfile(root_info)
        # Ordering matters here, addCleanup pushes onto a stack which is
        # popped in reverse order.
        self.addCleanup(self.tar_fileobj.close)
        self.addCleanup(tar_file.close)
        return tar_file

    def createSymlinkInfo(self, target, name="i_am_a_symlink"):
        info = tarfile.TarInfo(name=name)
        info.type = tarfile.SYMTYPE
        info.linkname = target
        return info

    def createTarfileWithSymlink(self, target):
        info = self.createSymlinkInfo(target)
        tar_file = self.createTarfile()
        tar_file.addfile(info)
        return tar_file

    def createTarfileWithFile(self, file_type, name="testfile"):
        info = tarfile.TarInfo(name=name)
        info.type = file_type
        tar_file = self.createTarfile()
        tar_file.addfile(info)
        return tar_file

    def assertFails(self, exception, tar_file):
        self.assertRaises(
            exception,
            self.custom_processor.verifyBeforeExtracting,
            tar_file)

    def assertPasses(self, tar_file):
        result = self.custom_processor.verifyBeforeExtracting(tar_file)
        self.assertTrue(result)

    def testFailsToExtractBadSymlink(self):
        """Fail if a symlink's target is outside the tmp tree."""
        tar_file = self.createTarfileWithSymlink(target="/etc/passwd")
        self.assertFails(CustomUploadTarballBadSymLink, tar_file)

    def testFailsToExtractBadRelativeSymlink(self):
        """Fail if a symlink's relative target is outside the tmp tree."""
        tar_file = self.createTarfileWithSymlink(target="../outside")
        self.assertFails(CustomUploadTarballBadSymLink, tar_file)

    def testFailsToExtractBadFileType(self):
        """Fail if a file in a tarfile is not a regular file or a symlink."""
        tar_file = self.createTarfileWithFile(tarfile.FIFOTYPE)
        self.assertFails(CustomUploadTarballInvalidFileType, tar_file)

    def testFailsToExtractBadFileLocation(self):
        """Fail if the file resolves to a path outside the tmp tree."""
        tar_file = self.createTarfileWithFile(tarfile.REGTYPE, "../outside")
        self.assertFails(CustomUploadTarballBadFile, tar_file)

    def testFailsToExtractBadAbsoluteFileLocation(self):
        """Fail if the file resolves to a path outside the tmp tree."""
        tar_file = self.createTarfileWithFile(tarfile.REGTYPE, "/etc/passwd")
        self.assertFails(CustomUploadTarballBadFile, tar_file)

    def testRegularFileDoesntRaise(self):
        """Adding a normal file should pass inspection."""
        tar_file = self.createTarfileWithFile(tarfile.REGTYPE)
        self.assertPasses(tar_file)

    def testDirectoryDoesntRaise(self):
        """Adding a directory should pass inspection."""
        tar_file = self.createTarfileWithFile(tarfile.DIRTYPE)
        self.assertPasses(tar_file)

    def testSymlinkDoesntRaise(self):
        """Adding a symlink should pass inspection."""
        tar_file = self.createTarfileWithSymlink(target="something/blah")
        self.assertPasses(tar_file)

    def testRelativeSymlinkToRootDoesntRaise(self):
        tar_file = self.createTarfileWithSymlink(target=".")
        self.assertPasses(tar_file)

    def testRelativeSymlinkTargetInsideDirectoryDoesntRaise(self):
        tar_file = self.createTarfileWithFile(
            tarfile.DIRTYPE, name="testdir")
        info = self.createSymlinkInfo(
            name="testdir/symlink", target="../dummy")
        tar_file.addfile(info)
        self.assertPasses(tar_file)

    def test_extract(self):
        """Test that the extract method calls the verify function.

        This test is different from the previous tests in that it actually
        pokes a fake tar file on disk.  This is slower, so it's only done
        once, here.
        """
        # Make a bad tarfile and poke it into the custom processor.
        self.custom_processor.tmpdir = None
        try:
            os.makedirs(self.tarfile_path)
            tar_file = tarfile.open(self.tarfile_name, mode="w")
            info = tarfile.TarInfo("test_file")
            info.type = tarfile.FIFOTYPE
            tar_file.addfile(info)
            tar_file.close()
            self.assertRaises(
                CustomUploadTarballInvalidFileType,
                self.custom_processor.extract)
        finally:
            shutil.rmtree(self.tarfile_path)
