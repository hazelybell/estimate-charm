# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The processing of translated packages descriptions (ddtp) tarballs.

DDTP (Debian Descripton Translation Project) aims to offer the description
of all supported packages translated in several languages.

DDTP-TARBALL is a custom format upload supported by Launchpad infrastructure
to enable developers to publish indexes of DDTP contents.
"""

__metaclass__ = type

__all__ = [
    'DdtpTarballUpload',
    'process_ddtp_tarball',
    ]

import os

from lp.archivepublisher.customupload import CustomUpload


class DdtpTarballUpload(CustomUpload):
    """DDTP (Debian Description Translation Project) tarball upload

    The tarball filename must be of the form:

     <NAME>_<COMPONENT>_<VERSION>.tar.gz

    where:

     * NAME: anything reasonable (ddtp-tarball);
     * COMPONENT: LP component (main, universe, etc);
     * VERSION: debian-like version token.

    It is consisted of a tarball containing all the supported indexes
    files for the DDTP system (under 'i18n' directory) contents driven
    by component.

    Results will be published (installed in archive) under:

       <ARCHIVE>dists/<SUITE>/<COMPONENT>/i18n

    Old contents will be preserved.
    """
    custom_type = "ddtp-tarball"

    @staticmethod
    def parsePath(tarfile_path):
        tarfile_base = os.path.basename(tarfile_path)
        bits = tarfile_base.split("_")
        if len(bits) != 3:
            raise ValueError("%s is not NAME_COMPONENT_VERSION" % tarfile_base)
        return tuple(bits)

    def setComponents(self, tarfile_path):
        _, self.component, self.version = self.parsePath(tarfile_path)
        self.arch = None

    def setTargetDirectory(self, pubconf, tarfile_path, distroseries):
        self.setComponents(tarfile_path)
        self.targetdir = os.path.join(
            pubconf.archiveroot, 'dists', distroseries, self.component)

    @classmethod
    def getSeriesKey(cls, tarfile_path):
        try:
            return cls.parsePath(tarfile_path)[1]
        except ValueError:
            return None

    def checkForConflicts(self):
        # We just overwrite older files, so no conflicts are possible.
        pass

    def shouldInstall(self, filename):
        # Ignore files outside of the i18n subdirectory
        return filename.startswith('i18n/')

    def fixCurrentSymlink(self):
        # There is no symlink to fix up for DDTP uploads
        pass


def process_ddtp_tarball(pubconf, tarfile_path, distroseries, logger=None):
    """Process a raw-ddtp-tarball tarfile.

    Unpacking it into the given archive for the given distroseries.
    Raises CustomUploadError (or some subclass thereof) if
    anything goes wrong.
    """
    upload = DdtpTarballUpload(logger=logger)
    upload.process(pubconf, tarfile_path, distroseries)
