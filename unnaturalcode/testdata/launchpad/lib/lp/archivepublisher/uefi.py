# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The processing of UEFI boot loader images.

UEFI Secure Boot requires boot loader images to be signed, and we want to
have signed images in the archive so that they can be used for upgrades.
This cannot be done on the build daemons because they are insufficiently
secure to hold signing keys, so we sign them as a custom upload instead.
"""

__metaclass__ = type

__all__ = [
    "process_uefi",
    "UefiUpload",
    ]

import os
import subprocess

from lp.archivepublisher.customupload import CustomUpload
from lp.services.osutils import remove_if_exists


class UefiUpload(CustomUpload):
    """UEFI boot loader custom upload.

    The filename must be of the form:

        <TYPE>_<VERSION>_<ARCH>.tar.gz

    where:

      * TYPE: loader type (e.g. 'efilinux');
      * VERSION: encoded version;
      * ARCH: targeted architecture tag (e.g. 'amd64').

    The contents are extracted in the archive in the following path:

        <ARCHIVE>/dists/<SUITE>/main/uefi/<TYPE>-<ARCH>/<VERSION>

    A 'current' symbolic link points to the most recent version.  The
    tarfile must contain at least one file matching the wildcard *.efi, and
    any such files are signed using the archive's UEFI signing key.

    Signing keys may be installed in the "uefiroot" directory specified in
    publisher configuration.  In this directory, the private key is
    "uefi.key" and the certificate is "uefi.crt".
    """
    custom_type = "UEFI"

    @staticmethod
    def parsePath(tarfile_path):
        tarfile_base = os.path.basename(tarfile_path)
        bits = tarfile_base.split("_")
        if len(bits) != 3:
            raise ValueError("%s is not TYPE_VERSION_ARCH" % tarfile_base)
        return bits[0], bits[1], bits[2].split(".")[0]

    def setComponents(self, tarfile_path):
        self.loader_type, self.version, self.arch = self.parsePath(
            tarfile_path)

    def setTargetDirectory(self, pubconf, tarfile_path, distroseries):
        if pubconf.uefiroot is None:
            if self.logger is not None:
                self.logger.warning("No UEFI root configured for this archive")
            self.key = None
            self.cert = None
        else:
            self.key = os.path.join(pubconf.uefiroot, "uefi.key")
            self.cert = os.path.join(pubconf.uefiroot, "uefi.crt")
            if not os.access(self.key, os.R_OK):
                if self.logger is not None:
                    self.logger.warning(
                        "UEFI private key %s not readable" % self.key)
                self.key = None
            if not os.access(self.cert, os.R_OK):
                if self.logger is not None:
                    self.logger.warning(
                        "UEFI certificate %s not readable" % self.cert)
                self.cert = None

        self.setComponents(tarfile_path)
        self.targetdir = os.path.join(
            pubconf.archiveroot, "dists", distroseries, "main", "uefi",
            "%s-%s" % (self.loader_type, self.arch))

    @classmethod
    def getSeriesKey(cls, tarfile_path):
        try:
            loader_type, _, arch = cls.parsePath(tarfile_path)
            return loader_type, arch
        except ValueError:
            return None

    def findEfiFilenames(self):
        """Find all the *.efi files in an extracted tarball."""
        for dirpath, dirnames, filenames in os.walk(self.tmpdir):
            for filename in filenames:
                if filename.endswith(".efi"):
                    yield os.path.join(dirpath, filename)

    def getSigningCommand(self, image):
        """Return the command used to sign an image."""
        return ["sbsign", "--key", self.key, "--cert", self.cert, image]

    def sign(self, image):
        """Sign an image."""
        if subprocess.call(self.getSigningCommand(image)) != 0:
            # Just log this rather than failing, since custom upload errors
            # tend to make the publisher rather upset.
            if self.logger is not None:
                self.logger.warning("Failed to sign %s" % image)

    def extract(self):
        """Copy the custom upload to a temporary directory, and sign it.

        No actual extraction is required.
        """
        super(UefiUpload, self).extract()
        if self.key is not None and self.cert is not None:
            efi_filenames = list(self.findEfiFilenames())
            for efi_filename in efi_filenames:
                remove_if_exists("%s.signed" % efi_filename)
                self.sign(efi_filename)

    def shouldInstall(self, filename):
        return filename.startswith("%s/" % self.version)


def process_uefi(pubconf, tarfile_path, distroseries, logger=None):
    """Process a raw-uefi tarfile.

    Unpacking it into the given archive for the given distroseries.
    Raises CustomUploadError (or some subclass thereof) if anything goes
    wrong.
    """
    upload = UefiUpload(logger=logger)
    upload.process(pubconf, tarfile_path, distroseries)
