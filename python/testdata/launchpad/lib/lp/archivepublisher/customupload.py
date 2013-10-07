# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Infrastructure for handling custom uploads.

Custom uploads are uploaded to Soyuz as special tarballs that must be
extracted to a particular location in the archive.  This module
contains code common to the different custom upload types.

Custom uploads include Debian installer packages, dist upgraders and
DDTP (Debian Description Translation Project) tarballs.
"""

__metaclass__ = type

__all__ = ['CustomUpload', 'CustomUploadError']

import os
import shutil
import tarfile
import tempfile

from lp.archivepublisher.debversion import (
    Version as make_version,
    VersionError,
    )


class CustomUploadError(Exception):
    """Base class for all errors associated with publishing custom uploads."""


class CustomUploadTarballTarError(CustomUploadError):
    """The tarfile module raised an exception."""
    def __init__(self, tarfile_path, tar_error):
        message = 'Problem reading tarfile %s: %s' % (tarfile_path, tar_error)
        CustomUploadError.__init__(self, message)


class CustomUploadTarballInvalidTarfile(CustomUploadError):
    """The supplied tarfile did not contain the expected elements."""
    def __init__(self, tarfile_path, expected_dir):
        message = ('Tarfile %s did not contain expected file %s' %
                   (tarfile_path, expected_dir))
        CustomUploadError.__init__(self, message)


class CustomUploadBadUmask(CustomUploadError):
    """The environment's umask was incorrect."""
    def __init__(self, expected_umask, got_umask):
        message = 'Bad umask; expected %03o, got %03o' % (
            expected_umask, got_umask)
        CustomUploadError.__init__(self, message)


class CustomUploadTarballInvalidFileType(CustomUploadError):
    """A file of type other than regular or symlink was found."""
    def __init__(self, tarfile_path, file_name):
        message = ("Tarfile %s has file %s which is not a regular file, "
                   "directory or a symlink" % (tarfile_path, file_name))
        CustomUploadError.__init__(self, message)


class CustomUploadTarballBadSymLink(CustomUploadError):
    """A symlink was found whose target points outside the immediate tree."""
    def __init__(self, tarfile_path, symlink_name, target):
        message = "Tarfile %s has a symlink %s whose target %s is illegal" % (
            tarfile_path, symlink_name, target)
        CustomUploadError.__init__(self, message)


class CustomUploadTarballBadFile(CustomUploadError):
    """A file was found which resolves outside the immediate tree.

    This can happen if someone embeds ../file in the tar, for example.
    """
    def __init__(self, tarfile_path, file_name):
        message = "Tarfile %s has a file %s which is illegal" % (
            tarfile_path, file_name)
        CustomUploadError.__init__(self, message)


class CustomUploadAlreadyExists(CustomUploadError):
    """A build for this type, architecture, and version already exists."""
    def __init__(self, custom_type, arch, version):
        message = ('%s build %s for architecture %s already exists' %
                   (custom_type, arch, version))
        CustomUploadError.__init__(self, message)


class CustomUpload:
    """Base class for custom upload handlers"""

    # This should be set as a class property on each subclass.
    custom_type = None

    def __init__(self, logger=None):
        self.targetdir = None
        self.version = None
        self.arch = None

        self.tmpdir = None
        self.logger = logger

    def process(self, pubconf, tarfile_path, distroseries):
        """Process the upload and install it into the archive."""
        self.tarfile_path = tarfile_path
        try:
            self.setTargetDirectory(pubconf, tarfile_path, distroseries)
            self.checkForConflicts()
            self.extract()
            self.installFiles()
            self.fixCurrentSymlink()
        finally:
            self.cleanup()

    @staticmethod
    def parsePath(tarfile_path):
        """Parse tarfile_path, returning its useful components.

        :raises ValueError: If tarfile_path is incorrectly formed.
        """
        raise NotImplementedError

    def setComponents(tarfile_path):
        """Set instance variables based on decomposing the filename."""
        raise NotImplementedError

    def setTargetDirectory(self, pubconf, tarfile_path, distroseries):
        """Set self.targetdir based on parameters.

        This should also set self.version and self.arch (if applicable) as a
        side-effect.
        """
        raise NotImplementedError

    @classmethod
    def getSeriesKey(cls, tarfile_path):
        """Get a unique key for instances of this custom upload type.

        The key should differ for any uploads that may be published
        simultaneously, but should be identical for (e.g.) different
        versions of the same type of upload on the same architecture in the
        same series.  Returns None on failure to parse tarfile_path.
        """
        raise NotImplementedError

    def checkForConflicts(self):
        """Check for conflicts with existing publications in the archive."""
        if os.path.exists(os.path.join(self.targetdir, self.version)):
            raise CustomUploadAlreadyExists(
                self.custom_type, self.arch, self.version)

    def verifyBeforeExtracting(self, tar):
        """Verify the tarball before extracting it.

        Extracting tarballs from untrusted sources is extremely dangerous
        as it's trivial to overwrite any part of the filesystem that the
        user running this process has access to.

        Here, we make sure that the file will extract to somewhere under
        the tmp dir, that the file is a directory, regular file or a symlink
        only, and that symlinks only resolve to stuff under the tmp dir.
        """
        for member in tar.getmembers():
            # member is a TarInfo object.

            if not (member.isreg() or member.issym() or member.isdir()):
                raise CustomUploadTarballInvalidFileType(
                    self.tarfile_path, member.name)

            # Append os.sep to stop attacks like /var/tmp/../tmpBOGUS
            # This is unlikely since someone would need to guess what
            # mkdtemp returned, but still ...
            tmpdir_with_sep = self.tmpdir + os.sep

            member_path = os.path.join(self.tmpdir, member.name)
            member_realpath = os.path.realpath(member_path)

            # The path can either be the tmpdir (without a trailing
            # separator) or have the tmpdir plus a trailing separator
            # as a prefix.
            if (member_realpath != self.tmpdir and
                not member_realpath.startswith(tmpdir_with_sep)):
                raise CustomUploadTarballBadFile(
                    self.tarfile_path, member.name)

            if member.issym():
                # This is a bit tricky.  We need to take the dirname of
                # the link's name which is where the link's target is
                # relative to, and prepend the extraction directory to
                # get an absolute path for the link target.
                rel_link_file_location = os.path.dirname(member.name)
                abs_link_file_location = os.path.join(
                    self.tmpdir, rel_link_file_location)
                target_path = os.path.join(
                    abs_link_file_location, member.linkname)
                target_realpath = os.path.realpath(target_path)

                # The same rules apply here as for member_realpath
                # above.
                if (target_realpath != self.tmpdir and
                    not target_realpath.startswith(tmpdir_with_sep)):
                    raise CustomUploadTarballBadSymLink(
                        self.tarfile_path, member.name, member.linkname)

        return True

    def extract(self):
        """Extract the custom upload to a temporary directory."""
        assert self.tmpdir is None, "Have already extracted tarfile"
        self.tmpdir = tempfile.mkdtemp(prefix='customupload_')
        try:
            tar = tarfile.open(self.tarfile_path)
            self.verifyBeforeExtracting(tar)
            tar.ignore_zeros = True
            try:
                for tarinfo in tar:
                    tar.extract(tarinfo, self.tmpdir)
            finally:
                tar.close()
        except tarfile.TarError as exc:
            raise CustomUploadTarballTarError(self.tarfile_path, exc)

    def shouldInstall(self, filename):
        """Returns True if the given filename should be installed."""
        raise NotImplementedError

    def _buildInstallPaths(self, basename, dirname):
        """Build and return paths used to install files.

        Return a triple containing: (sourcepath, basepath, destpath)
        Where:
         * sourcepath is the absolute path to the extracted location.
         * basepath is the relative path inside the target location.
         * destpath is the absolute path to the target location.
        """
        sourcepath = os.path.join(dirname, basename)
        assert sourcepath.startswith(self.tmpdir), (
            "Source path must refer to the extracted location.")
        basepath = sourcepath[len(self.tmpdir):].lstrip(os.path.sep)
        destpath = os.path.join(self.targetdir, basepath)

        return sourcepath, basepath, destpath

    def ensurePath(self, path):
        """Ensure the parent directory exists."""
        parentdir = os.path.dirname(path)
        if not os.path.isdir(parentdir):
            os.makedirs(parentdir, 0755)

    def installFiles(self):
        """Install the files from the custom upload to the archive."""
        assert self.tmpdir is not None, "Must extract tarfile first"
        extracted = False
        for dirpath, dirnames, filenames in os.walk(self.tmpdir):

            # Create symbolic links to directories.
            for dirname in dirnames:
                sourcepath, basepath, destpath = self._buildInstallPaths(
                    dirname, dirpath)

                if not self.shouldInstall(basepath):
                    continue

                self.ensurePath(destpath)
                # Also, ensure that the process has the expected umask.
                old_mask = os.umask(0)
                try:
                    if old_mask != 022:
                        raise CustomUploadBadUmask(022, old_mask)
                finally:
                    os.umask(old_mask)
                if os.path.islink(sourcepath):
                    os.symlink(os.readlink(sourcepath), destpath)

                # XXX cprov 2007-03-27: We don't want to create empty
                # directories, some custom formats rely on this, DDTP,
                # for instance. We may end up with broken links
                # but that's more an uploader fault than anything else.

            # Create/Copy files.
            for filename in filenames:
                sourcepath, basepath, destpath = self._buildInstallPaths(
                    filename, dirpath)

                if not self.shouldInstall(basepath):
                    continue

                self.ensurePath(destpath)
                # Remove any previous file, to avoid hard link problems
                if os.path.exists(destpath):
                    os.remove(destpath)
                # Copy the file or symlink
                if os.path.islink(sourcepath):
                    os.symlink(os.readlink(sourcepath), destpath)
                else:
                    shutil.copy(sourcepath, destpath)
                    os.chmod(destpath, 0644)

                extracted = True

        if not extracted:
            raise CustomUploadTarballInvalidTarfile(
                self.tarfile_path, self.targetdir)

    def fixCurrentSymlink(self):
        """Update the 'current' symlink and prune old entries.

        The 'current' symbolic link will point to the latest version present
        in 'targetdir' and only the latest 3 valid entries will be kept.

        Entries named as invalid versions, for instance 'alpha-X', will be
        ignored and left alone. That's because they were probably copied
        manually into this location, they should remain in place.

        See `DebVersion` for more information about version validation.
        """
        # Get an appropriately-sorted list of the valid installer directories
        # now present in the target. Deliberately skip 'broken' versions
        # because they can't be sorted anyway.
        versions = []
        for inst in os.listdir(self.targetdir):
            # Skip the symlink.
            if inst == 'current':
                continue
            # Skip broken versions.
            try:
                make_version(inst)
            except VersionError:
                continue
            # Append the valid versions to the list.
            versions.append(inst)
        versions.sort(key=make_version, reverse=True)

        # Make sure the 'current' symlink points to the most recent version
        # The most recent version is in versions[0]
        current = os.path.join(self.targetdir, 'current')
        os.symlink(versions[0], '%s.new' % current)
        os.rename('%s.new' % current, current)

        # There may be some other unpacked installer directories in
        # the target already. We only keep the three with the highest
        # version (plus the one we just extracted, if for some reason
        # it's lower).
        for oldversion in versions[3:]:
            if oldversion != self.version:
                shutil.rmtree(os.path.join(self.targetdir, oldversion))

    def cleanup(self):
        """Clean up the temporary directory"""
        if self.tmpdir is not None:
            shutil.rmtree(self.tmpdir, ignore_errors=True)
            self.tmpdir = None
