# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test debian-installer custom uploads.

See also lp.soyuz.tests.test_distroseriesqueue_debian_installer for
high-level tests of debian-installer upload and queue manipulation.
"""

import os

from lp.archivepublisher.customupload import (
    CustomUploadAlreadyExists,
    CustomUploadBadUmask,
    )
from lp.archivepublisher.debian_installer import (
    DebianInstallerUpload,
    process_debian_installer,
    )
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.testing import TestCase


class FakeConfig:
    """A fake publisher configuration."""
    def __init__(self, archiveroot):
        self.archiveroot = archiveroot


class TestDebianInstaller(TestCase):

    def setUp(self):
        super(TestDebianInstaller, self).setUp()
        self.temp_dir = self.makeTemporaryDirectory()
        self.pubconf = FakeConfig(self.temp_dir)
        self.suite = "distroseries"
        # CustomUpload.installFiles requires a umask of 022.
        old_umask = os.umask(022)
        self.addCleanup(os.umask, old_umask)

    def openArchive(self):
        self.version = "20070214ubuntu1"
        self.arch = "i386"
        self.path = os.path.join(
            self.temp_dir,
            "debian-installer-images_%s_%s.tar.gz" % (self.version, self.arch))
        self.buffer = open(self.path, "wb")
        self.archive = LaunchpadWriteTarFile(self.buffer)

    def addFile(self, path, contents):
        self.archive.add_file(
            "installer-%s/%s/%s" % (self.arch, self.version, path), contents)

    def addSymlink(self, path, target):
        self.archive.add_symlink(
            "installer-%s/%s/%s" % (self.arch, self.version, path), target)

    def process(self):
        self.archive.close()
        self.buffer.close()
        process_debian_installer(self.pubconf, self.path, self.suite)

    def getInstallerPath(self, versioned_filename=None):
        installer_path = os.path.join(
            self.temp_dir, "dists", self.suite, "main",
            "installer-%s" % self.arch)
        if versioned_filename is not None:
            installer_path = os.path.join(
                installer_path, self.version, versioned_filename)
        return installer_path

    def test_basic(self):
        # Processing a simple correct tar file succeeds.
        self.openArchive()
        self.addFile("hello", "world")
        self.process()

    def test_already_exists(self):
        # If the target directory already exists, processing fails.
        self.openArchive()
        os.makedirs(self.getInstallerPath("."))
        self.assertRaises(CustomUploadAlreadyExists, self.process)

    def test_bad_umask(self):
        # The umask must be 022 to avoid incorrect permissions.
        self.openArchive()
        self.addFile("dir/file", "foo")
        os.umask(002)  # cleanup already handled by setUp
        self.assertRaises(CustomUploadBadUmask, self.process)

    def test_current_symlink(self):
        # A "current" symlink is created to the last version.
        self.openArchive()
        self.addFile("hello", "world")
        self.process()
        installer_path = self.getInstallerPath()
        self.assertContentEqual(
            [self.version, "current"], os.listdir(installer_path))
        self.assertEqual(
            self.version, os.readlink(os.path.join(installer_path, "current")))

    def test_correct_file(self):
        # Files in the tarball are extracted correctly.
        self.openArchive()
        directory = ("images/netboot/ubuntu-installer/i386/"
                     "pxelinux.cfg.serial-9600")
        filename = os.path.join(directory, "default")
        long_filename = os.path.join(
            directory, "very_very_very_very_very_very_long_filename")
        self.addFile(filename, "hey")
        self.addFile(long_filename, "long")
        self.process()
        with open(self.getInstallerPath(filename)) as f:
            self.assertEqual("hey", f.read())
        with open(self.getInstallerPath(long_filename)) as f:
            self.assertEqual("long", f.read())

    def test_correct_symlink(self):
        # Symbolic links in the tarball are extracted correctly.
        self.openArchive()
        foo_path = "images/netboot/foo"
        foo_target = "ubuntu-installer/i386/pxelinux.cfg.serial-9600/default"
        link_to_dir_path = "images/netboot/link_to_dir"
        link_to_dir_target = "ubuntu-installer/i386/pxelinux.cfg.serial-9600"
        self.addSymlink(foo_path, foo_target)
        self.addSymlink(link_to_dir_path, link_to_dir_target)
        self.process()
        self.assertEqual(
            foo_target, os.readlink(self.getInstallerPath(foo_path)))
        self.assertEqual(
            link_to_dir_target,
            os.path.normpath(os.readlink(
                self.getInstallerPath(link_to_dir_path))))

    def test_top_level_permissions(self):
        # Top-level directories are set to mode 0755 (see bug 107068).
        self.openArchive()
        self.addFile("hello", "world")
        self.process()
        installer_path = self.getInstallerPath()
        self.assertEqual(0755, os.stat(installer_path).st_mode & 0777)
        self.assertEqual(
            0755,
            os.stat(os.path.join(installer_path, os.pardir)).st_mode & 0777)

    def test_extracted_permissions(self):
        # Extracted files and directories are set to 0644/0755.
        self.openArchive()
        directory = ("images/netboot/ubuntu-installer/i386/"
                     "pxelinux.cfg.serial-9600")
        filename = os.path.join(directory, "default")
        self.addFile(filename, "hey")
        self.process()
        self.assertEqual(
            0644, os.stat(self.getInstallerPath(filename)).st_mode & 0777)
        self.assertEqual(
            0755, os.stat(self.getInstallerPath(directory)).st_mode & 0777)

    def test_getSeriesKey_extracts_architecture(self):
        # getSeriesKey extracts the architecture from an upload's filename.
        self.openArchive()
        self.assertEqual(
            self.arch, DebianInstallerUpload.getSeriesKey(self.path))

    def test_getSeriesKey_returns_None_on_mismatch(self):
        # getSeriesKey returns None if the filename does not match the
        # expected pattern.
        self.assertIsNone(DebianInstallerUpload.getSeriesKey("argh_1.0.jpg"))

    def test_getSeriesKey_refuses_names_with_wrong_number_of_fields(self):
        # getSeriesKey requires exactly three fields.
        self.assertIsNone(DebianInstallerUpload.getSeriesKey(
            "package_1.0.tar.gz"))
        self.assertIsNone(DebianInstallerUpload.getSeriesKey(
            "one_two_three_four_5.tar.gz"))
