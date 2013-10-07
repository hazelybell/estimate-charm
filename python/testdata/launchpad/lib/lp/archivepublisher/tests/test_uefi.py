# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test UEFI custom uploads."""

__metaclass__ = type

import os

from lp.archivepublisher.customupload import (
    CustomUploadAlreadyExists,
    CustomUploadBadUmask,
    )
from lp.archivepublisher.uefi import UefiUpload
from lp.services.osutils import write_file
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.testing import TestCase
from lp.testing.fakemethod import FakeMethod


class FakeConfig:
    """A fake publisher configuration."""
    def __init__(self, archiveroot, uefiroot):
        self.archiveroot = archiveroot
        self.uefiroot = uefiroot


class TestUefi(TestCase):

    def setUp(self):
        super(TestUefi, self).setUp()
        self.temp_dir = self.makeTemporaryDirectory()
        self.uefi_dir = self.makeTemporaryDirectory()
        self.pubconf = FakeConfig(self.temp_dir, self.uefi_dir)
        self.suite = "distroseries"
        # CustomUpload.installFiles requires a umask of 022.
        old_umask = os.umask(022)
        self.addCleanup(os.umask, old_umask)

    def setUpKeyAndCert(self):
        self.key = os.path.join(self.uefi_dir, "uefi.key")
        self.cert = os.path.join(self.uefi_dir, "uefi.crt")
        write_file(self.key, "")
        write_file(self.cert, "")

    def openArchive(self, loader_type, version, arch):
        self.path = os.path.join(
            self.temp_dir, "%s_%s_%s.tar.gz" % (loader_type, version, arch))
        self.buffer = open(self.path, "wb")
        self.archive = LaunchpadWriteTarFile(self.buffer)

    def process(self):
        self.archive.close()
        self.buffer.close()
        upload = UefiUpload()
        upload.sign = FakeMethod()
        upload.process(self.pubconf, self.path, self.suite)
        return upload

    def getUefiPath(self, loader_type, arch):
        return os.path.join(
            self.temp_dir, "dists", self.suite, "main", "uefi",
            "%s-%s" % (loader_type, arch))

    def test_unconfigured(self):
        # If there is no key/cert configuration, processing succeeds but
        # nothing is signed.
        self.pubconf = FakeConfig(self.temp_dir, None)
        self.openArchive("test", "1.0", "amd64")
        self.archive.add_file("1.0/empty.efi", "")
        upload = self.process()
        self.assertEqual(0, upload.sign.call_count)

    def test_missing_key_and_cert(self):
        # If the configured key/cert are missing, processing succeeds but
        # nothing is signed.
        self.openArchive("test", "1.0", "amd64")
        self.archive.add_file("1.0/empty.efi", "")
        upload = self.process()
        self.assertEqual(0, upload.sign.call_count)

    def test_no_efi_files(self):
        # Tarballs containing no *.efi files are extracted without complaint.
        self.setUpKeyAndCert()
        self.openArchive("empty", "1.0", "amd64")
        self.archive.add_file("1.0/hello", "world")
        self.process()
        self.assertTrue(os.path.exists(os.path.join(
            self.getUefiPath("empty", "amd64"), "1.0", "hello")))

    def test_already_exists(self):
        # If the target directory already exists, processing fails.
        self.setUpKeyAndCert()
        self.openArchive("test", "1.0", "amd64")
        self.archive.add_file("1.0/empty.efi", "")
        os.makedirs(os.path.join(self.getUefiPath("test", "amd64"), "1.0"))
        self.assertRaises(CustomUploadAlreadyExists, self.process)

    def test_bad_umask(self):
        # The umask must be 022 to avoid incorrect permissions.
        self.setUpKeyAndCert()
        self.openArchive("test", "1.0", "amd64")
        self.archive.add_file("1.0/dir/file.efi", "foo")
        os.umask(002)  # cleanup already handled by setUp
        self.assertRaises(CustomUploadBadUmask, self.process)

    def test_correct_signing_command(self):
        # getSigningCommand returns the correct command.
        self.setUpKeyAndCert()
        upload = UefiUpload()
        upload.setTargetDirectory(
            self.pubconf, "test_1.0_amd64.tar.gz", "distroseries")
        expected_command = [
            "sbsign", "--key", self.key, "--cert", self.cert, "t.efi"]
        self.assertEqual(expected_command, upload.getSigningCommand("t.efi"))

    def test_signs_image(self):
        # Each image in the tarball is signed.
        self.setUpKeyAndCert()
        self.openArchive("test", "1.0", "amd64")
        self.archive.add_file("1.0/empty.efi", "")
        upload = self.process()
        self.assertEqual(1, upload.sign.call_count)
        self.assertEqual(1, len(upload.sign.calls[0][0]))
        self.assertEqual(
            "empty.efi", os.path.basename(upload.sign.calls[0][0][0]))

    def test_installed(self):
        # Files in the tarball are installed correctly.
        self.setUpKeyAndCert()
        self.openArchive("test", "1.0", "amd64")
        self.archive.add_file("1.0/empty.efi", "")
        self.process()
        self.assertTrue(os.path.exists(os.path.join(
            self.getUefiPath("test", "amd64"), "1.0", "empty.efi")))
