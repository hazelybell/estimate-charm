# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The processing of dist-upgrader tarballs."""

__metaclass__ = type

__all__ = [
    'DistUpgraderUpload',
    'process_dist_upgrader',
    ]

import os

from lp.archivepublisher.customupload import (
    CustomUpload,
    CustomUploadError,
    )
from lp.archivepublisher.debversion import (
    BadUpstreamError,
    Version as make_version,
    )


class DistUpgraderBadVersion(CustomUploadError):
    def __init__(self, tarfile_path, exc):
        message = "bad version found in '%s': %s" % (tarfile_path, str(exc))
        CustomUploadError.__init__(self, message)


class DistUpgraderUpload(CustomUpload):
    """Dist Upgrader custom upload processor.

    Dist-Upgrader is a tarball containing files for performing automatic
    distroseries upgrades, driven by architecture.

    The tarball filename must be of the form:

      <NAME>_<VERSION>_<ARCH>.tar.gz

    where:

     * NAME: can be anything reasonable like 'dist-upgrader', it's not used;
     * VERSION: debian-like version token;
     * ARCH: debian-like architecture tag.

    and should contain:

     * ReleaseAnnouncement text file;
     * <distroseries>.tar.gz file.

    Dist-Upgrader versions are published under:

    <ARCHIVE>/dists/<SUITE>/main/dist-upgrader-<ARCH>/<VERSION>/

    A 'current' symbolic link points to the most recent version.
    """
    custom_type = "dist-upgrader"

    @staticmethod
    def parsePath(tarfile_path):
        tarfile_base = os.path.basename(tarfile_path)
        bits = tarfile_base.split("_")
        if len(bits) != 3:
            raise ValueError("%s is not NAME_VERSION_ARCH" % tarfile_base)
        return bits[0], bits[1], bits[2].split(".")[0]

    def setComponents(self, tarfile_path):
        _, self.version, self.arch = self.parsePath(tarfile_path)

    def setTargetDirectory(self, pubconf, tarfile_path, distroseries):
        self.setComponents(tarfile_path)
        self.targetdir = os.path.join(
            pubconf.archiveroot, 'dists', distroseries, 'main',
            'dist-upgrader-%s' % self.arch)

    @classmethod
    def getSeriesKey(cls, tarfile_path):
        try:
            return cls.parsePath(tarfile_path)[2]
        except ValueError:
            return None

    def shouldInstall(self, filename):
        """ Install files from a dist-upgrader tarball.

        It raises DistUpgraderBadVersion if if finds a directory name that
        could not be treated as a valid Debian version.

        It returns False for extracted contents of a directory named
        'current' (since it would obviously conflict with the symbolic
        link in the archive).

        Return True for contents of 'versionable' directories.
        """
        # Only the first path part (directory name) must be *versionable*
        # and we may allow subdirectories.
        directory_name = filename.split(os.path.sep)[0]
        try:
            version = make_version(directory_name)
        except BadUpstreamError as exc:
            raise DistUpgraderBadVersion(self.tarfile_path, exc)
        return version and not filename.startswith('current')


def process_dist_upgrader(pubconf, tarfile_path, distroseries, logger=None):
    """Process a raw-dist-upgrader tarfile.

    Unpacking it into the given archive for the given distroseries.
    Raises CustomUploadError (or some subclass thereof) if anything goes
    wrong.
    """
    upload = DistUpgraderUpload(logger=logger)
    upload.process(pubconf, tarfile_path, distroseries)
