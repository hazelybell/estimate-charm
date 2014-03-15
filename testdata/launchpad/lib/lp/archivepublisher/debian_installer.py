# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The processing of debian installer tarballs."""

# This code is mostly owned by Colin Watson and is partly refactored by
# Daniel Silverstone who should be the first point of contact for it.

__metaclass__ = type

__all__ = [
    'DebianInstallerUpload',
    'process_debian_installer',
    ]

import os
import shutil

from lp.archivepublisher.customupload import CustomUpload


class DebianInstallerUpload(CustomUpload):
    """ Debian Installer custom upload.

    The debian-installer filename must be of the form:

        <BASE>_<VERSION>_<ARCH>.tar.gz

    where:

      * BASE: base name (usually 'debian-installer-images');
      * VERSION: encoded version (something like '20061102ubuntu14');
      * ARCH: targeted architecture tag ('i386', 'amd64', etc);

    The contents are extracted in the archive in the following path:

         <ARCHIVE>/dists/<SUITE>/main/installer-<ARCH>/<VERSION>

    A 'current' symbolic link points to the most recent version.
    """
    custom_type = "installer"

    @staticmethod
    def parsePath(tarfile_path):
        tarfile_base = os.path.basename(tarfile_path)
        bits = tarfile_base.split("_")
        if len(bits) != 3:
            raise ValueError("%s is not BASE_VERSION_ARCH" % tarfile_base)
        return bits[0], bits[1], bits[2].split(".")[0]

    def setComponents(self, tarfile_path):
        _, self.version, self.arch = self.parsePath(tarfile_path)

    def setTargetDirectory(self, pubconf, tarfile_path, distroseries):
        self.setComponents(tarfile_path)
        self.targetdir = os.path.join(
            pubconf.archiveroot, 'dists', distroseries, 'main',
            'installer-%s' % self.arch)

    @classmethod
    def getSeriesKey(cls, tarfile_path):
        try:
            return cls.parsePath(tarfile_path)[2]
        except ValueError:
            return None

    def extract(self):
        CustomUpload.extract(self)
        # We now have a valid unpacked installer directory, but it's one level
        # deeper than it should be. Move it up and remove the debris.
        unpack_dir = 'installer-%s' % self.arch
        os.rename(os.path.join(self.tmpdir, unpack_dir, self.version),
                  os.path.join(self.tmpdir, self.version))
        shutil.rmtree(os.path.join(self.tmpdir, unpack_dir))

    def shouldInstall(self, filename):
        return filename.startswith('%s/' % self.version)


def process_debian_installer(pubconf, tarfile_path, distroseries, logger=None):
    """Process a raw-installer tarfile.

    Unpacking it into the given archive for the given distroseries.
    Raises CustomUploadError (or some subclass thereof) if anything goes
    wrong.
    """
    upload = DebianInstallerUpload(logger=logger)
    upload.process(pubconf, tarfile_path, distroseries)
