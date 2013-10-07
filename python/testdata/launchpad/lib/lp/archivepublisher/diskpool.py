# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = ['DiskPoolEntry', 'DiskPool', 'poolify', 'unpoolify']

import os
import tempfile

from lp.archivepublisher import HARDCODED_COMPONENT_ORDER
from lp.services.librarian.utils import (
    copy_and_close,
    sha1_from_path,
    )
from lp.services.propertycache import cachedproperty
from lp.soyuz.interfaces.publishing import (
    MissingSymlinkInPool,
    NotInPool,
    PoolFileOverwriteError,
    )


def poolify(source, component):
    """Poolify a given source and component name."""
    if source.startswith("lib"):
        return os.path.join(component, source[:4], source)
    else:
        return os.path.join(component, source[:1], source)


def unpoolify(self, path):
    """Take a path and unpoolify it.

    Return a tuple of component, source, filename
    """
    p = path.split("/")
    if len(p) < 3 or len(p) > 4:
        raise ValueError("Path %s is not in a valid pool form" % path)
    if len(p) == 4:
        return p[0], p[2], p[3]
    return p[0], p[2], None


def relative_symlink(src_path, dst_path):
    """os.symlink replacement that creates relative symbolic links."""
    path_sep = os.path.sep
    src_path = os.path.normpath(src_path)
    dst_path = os.path.normpath(dst_path)
    src_path_elems = src_path.split(path_sep)
    dst_path_elems = dst_path.split(path_sep)
    if os.path.isabs(src_path):
        if not os.path.isabs(dst_path):
            dst_path = os.path.abspath(dst_path)
        common_prefix = os.path.commonprefix([src_path_elems, dst_path_elems])
        backward_elems = ['..'] * (len(dst_path_elems)-len(common_prefix)-1)
        forward_elems = src_path_elems[len(common_prefix):]
        src_path = path_sep.join(backward_elems + forward_elems)
    os.symlink(src_path, dst_path)


class FileAddActionEnum:
    """Possible actions taken when adding a file.

    FILE_ADDED: we added the actual file to the disk
    SYMLINK_ADDED: we created a symlink to another copy of the same file
    NONE: no action was necessary or taken.
    """
    FILE_ADDED = "file_added"
    SYMLINK_ADDED = "symlink_added"
    NONE = "none"


class _diskpool_atomicfile:
    """Simple file-like object used by the pool to atomically move into place
    a file after downloading from the librarian.

    This class is designed to solve a very specific problem encountered in
    the publisher. Namely that should the publisher crash during the process
    of publishing a file to the pool, an empty or incomplete file would be
    present in the pool. Its mere presence would fool the publisher into
    believing it had already downloaded that file to the pool, resulting
    in failures in the apt-ftparchive stage.

    By performing a rename() when the file is guaranteed to have been
    fully written to disk (after the fd.close()) we can be sure that if
    the filename is present in the pool, it is definitely complete.
    """

    def __init__(self, targetfilename, mode, rootpath="/tmp"):
        # atomicfile implements the file object interface, but it is only
        # really used (or useful) for writing binary files, which is why we
        # keep the mode constructor argument but assert it's sane below.
        if mode == "w":
            mode = "wb"
        assert mode == "wb"

        assert not os.path.exists(targetfilename)

        self.targetfilename = targetfilename
        fd, name = tempfile.mkstemp(prefix="temp-download.", dir=rootpath)
        self.fd = os.fdopen(fd, mode)
        self.tempname = name
        self.write = self.fd.write

    def close(self):
        """Make the atomic move into place having closed the temp file."""
        self.fd.close()
        os.chmod(self.tempname, 0644)
        # Note that this will fail if the target and the temp dirs are on
        # different filesystems.
        os.rename(self.tempname, self.targetfilename)


class DiskPoolEntry:
    """Represents a single file in the pool, across all components.

    Creating a DiskPoolEntry performs disk reads, so don't create an
    instance of this class unless you need to know what's already on
    the disk for this file.

    'tempath' must be in the same filesystem as 'rootpath', it will be
    used to store the instalation candidate while it is being downloaded
    from the Librarian.

    Remaining files in the 'temppath' indicated installation failures and
    require manual removal after further investigation.
    """
    def __init__(self, rootpath, temppath, source, filename, logger):
        self.rootpath = rootpath
        self.temppath = temppath
        self.source = source
        self.filename = filename
        self.logger = logger

        self.file_component = None
        self.symlink_components = set()

        for component in HARDCODED_COMPONENT_ORDER:
            path = self.pathFor(component)
            if os.path.islink(path):
                self.symlink_components.add(component)
            elif os.path.isfile(path):
                assert not self.file_component
                self.file_component = component
        if self.symlink_components:
            assert self.file_component

    def debug(self, *args, **kwargs):
        self.logger.debug(*args, **kwargs)

    def pathFor(self, component):
        """Return the path for this file in the given component."""
        return os.path.join(self.rootpath,
                            poolify(self.source, component),
                            self.filename)

    def preferredComponent(self, add=None, remove=None):
        """Return the appropriate component for the real file.

        If add is passed, add it to the list before calculating.
        If remove is passed, remove it before calculating.
        Thus, we can calcuate which component should contain the main file
        after the addition or removal we are working on.
        """
        components = set()
        if self.file_component:
            components.add(self.file_component)
        components = components.union(self.symlink_components)
        if add is not None:
            components.add(add)
        if remove is not None and remove in components:
            components.remove(remove)

        for component in HARDCODED_COMPONENT_ORDER:
            if component in components:
                return component

    @cachedproperty
    def file_hash(self):
        """Return the SHA1 sum of this file."""
        targetpath = self.pathFor(self.file_component)
        return sha1_from_path(targetpath)

    def addFile(self, component, sha1, contents):
        """See DiskPool.addFile."""
        assert component in HARDCODED_COMPONENT_ORDER

        targetpath = self.pathFor(component)
        if not os.path.exists(os.path.dirname(targetpath)):
            os.makedirs(os.path.dirname(targetpath))

        if self.file_component:
            # There's something on disk. Check hash.
            if sha1 != self.file_hash:
                raise PoolFileOverwriteError('%s != %s for %s' %
                    (sha1, self.file_hash,
                     self.pathFor(self.file_component)))

            if (component == self.file_component
                or component in self.symlink_components):
                # The file is already here
                return FileAddActionEnum.NONE
            else:
                # The file is present in a different component,
                # make a symlink.
                relative_symlink(
                    self.pathFor(self.file_component), targetpath)
                self.symlink_components.add(component)
                # Then fix to ensure the right component is linked.
                self._sanitiseLinks()

                return FileAddActionEnum.SYMLINK_ADDED

        # If we get to here, we want to write the file.
        assert not os.path.exists(targetpath)

        self.debug("Making new file in %s for %s/%s" %
                   (component, self.source, self.filename))

        file_to_write = _diskpool_atomicfile(
            targetpath, "wb", rootpath=self.temppath)
        contents.open()
        copy_and_close(contents, file_to_write)
        self.file_component = component
        return FileAddActionEnum.FILE_ADDED

    def removeFile(self, component):
        """Remove a file from a given component; return bytes freed.

        This method handles three situations:

        1) Remove a symlink

        2) Remove the main file and there are no symlinks left.

        3) Remove the main file and there are symlinks left.
        """
        if not self.file_component:
            raise NotInPool(
                "File for removing %s %s/%s is not in pool, skipping." %
                (component, self.source, self.filename))


        # Okay, it's there, if it's a symlink then we need to remove
        # it simply.
        if component in self.symlink_components:
            self.debug("Removing %s %s/%s as it is a symlink"
                       % (component, self.source, self.filename))
            # ensure we are removing a symbolic link and
            # it is published in one or more components
            link_path = self.pathFor(component)
            assert os.path.islink(link_path)
            return self._reallyRemove(component)

        if component != self.file_component:
            raise MissingSymlinkInPool(
                "Symlink for %s/%s in %s is missing, skipping." %
                (self.source, self.filename, component))

        # It's not a symlink, this means we need to check whether we
        # have symlinks or not.
        if len(self.symlink_components) == 0:
            self.debug("Removing %s/%s from %s" %
                       (self.source, self.filename, component))
        else:
            # The target for removal is the real file, and there are symlinks
            # pointing to it. In order to avoid breakage, we need to first
            # shuffle the symlinks, so that the one we want to delete will
            # just be one of the links, and becomes safe.
            targetcomponent = self.preferredComponent(remove=component)
            self._shufflesymlinks(targetcomponent)

        return self._reallyRemove(component)

    def _reallyRemove(self, component):
        """Remove file and return file size.

        Remove the file from the filesystem and from our data
        structures.
        """
        fullpath = self.pathFor(component)
        assert os.path.exists(fullpath)

        if component == self.file_component:
            # Deleting the master file is only allowed if there
            # are no symlinks left.
            assert not self.symlink_components
            self.file_component = None
        elif component in self.symlink_components:
            self.symlink_components.remove(component)

        size = os.lstat(fullpath).st_size
        os.remove(fullpath)
        return size

    def _shufflesymlinks(self, targetcomponent):
        """Shuffle the symlinks for filename so that targetcomponent contains
        the real file and the rest are symlinks to the right place..."""
        if targetcomponent == self.file_component:
            # We're already in the right place.
            return

        if targetcomponent not in self.symlink_components:
            raise ValueError(
                "Target component '%s' is not a symlink for %s" %
                             (targetcomponent, self.filename))

        self.debug("Shuffling symlinks so primary for %s is in %s" %
                   (self.filename, targetcomponent))

        # Okay, so first up, we unlink the targetcomponent symlink.
        targetpath = self.pathFor(targetcomponent)
        os.remove(targetpath)

        # Now we rename the source file into the target component.
        sourcepath = self.pathFor(self.file_component)

        # XXX cprov 2006-05-26: if it fails the symlinks are severely broken
        # or maybe we are writing them wrong. It needs manual fix !
        # Nonetheless, we carry on checking other candidates.
        # Use 'find -L . -type l' on pool to find out broken symlinks
        # Normally they only can be fixed by remove the broken links and
        # run a careful (-C) publication.

        # ensure targetpath doesn't exists and  the sourcepath exists
        # before rename them.
        assert not os.path.exists(targetpath)
        assert os.path.exists(sourcepath)
        os.rename(sourcepath, targetpath)

        # XXX cprov 2006-06-12: it may cause problems to the database, since
        # ZTM isn't handled properly in scripts/publish-distro.py. Things are
        # commited mid-procedure & bare exception is caught.

        # Update the data structures.
        self.symlink_components.add(self.file_component)
        self.symlink_components.remove(targetcomponent)
        self.file_component = targetcomponent

        # Now we make the symlinks on the filesystem.
        for comp in self.symlink_components:
            newpath = self.pathFor(comp)
            try:
                os.remove(newpath)
            except OSError:
                # Do nothing because it's almost certainly a not found.
                pass
            relative_symlink(targetpath, newpath)

    def _sanitiseLinks(self):
        """Ensure the real file is in the most preferred component.

        If this file is in more than one component, ensure the real
        file is in the most preferred component and the other components
        use symlinks.

        It's important that the real file be in the most preferred
        component because partial mirrors may only take a subset of
        components, and these partial mirrors must not have broken
        symlinks where they should have working files.
        """
        component = self.preferredComponent()
        if not self.file_component == component:
            self._shufflesymlinks(component)


class DiskPool:
    """Scan a pool on the filesystem and record information about it.

    Its constructor receives 'rootpath', which is the pool path where the
    files will be installed, and the 'temppath', which is a temporary
    directory used to store the installation candidate from librarian.

    'rootpath' and 'temppath' must be in the same filesystem, see
    DiskPoolEntry for further information.
    """
    results = FileAddActionEnum

    def __init__(self, rootpath, temppath, logger):
        self.rootpath = rootpath
        if not rootpath.endswith("/"):
            self.rootpath += "/"

        self.temppath = temppath
        if not temppath.endswith("/"):
            self.temppath += "/"

        self.entries = {}
        self.logger = logger

    def _getEntry(self, sourcename, file):
        """Return a new DiskPoolEntry for the given sourcename and file."""
        return DiskPoolEntry(
            self.rootpath, self.temppath, sourcename, file, self.logger)

    def pathFor(self, comp, source, file=None):
        """Return the path for the given pool folder or file.

        If file is none, the path to the folder containing all packages
        for the given component and source package name will be returned.

        If file is specified, the path to the specific package file will
        be returned.
        """
        path = os.path.join(
            self.rootpath, poolify(source, comp))
        if file:
            return os.path.join(path, file)
        return path

    def addFile(self, component, sourcename, filename, sha1, contents):
        """Add a file with the given contents to the pool.

        Component, sourcename and filename are used to calculate the
        on-disk location.

        sha1 is used to compare with the existing file's checksum, if
        a file already exists for any component.

        contents is a file-like object containing the contents we want
        to write.

        There are four possible outcomes:
        - If the file doesn't exist in the pool for any component, it will
        be written from the given contents and results.ADDED_FILE will be
        returned.

        - If the file already exists in the pool, in this or any other
        component, the checksum of the file on disk will be calculated and
        compared with the checksum provided. If they fail to match,
        PoolFileOverwriteError will be raised.

        - If the file already exists but not in this component, and the
        checksum test above passes, a symlink will be added, and
        results.SYMLINK_ADDED will be returned. Also, the symlinks will be
        checked and sanitised, to ensure the real copy of the file is in the
        most preferred component, according to HARDCODED_COMPONENT_ORDER.

        - If the file already exists and is already in this component,
        either as a file or a symlink, and the checksum check passes,
        results.NONE will be returned and nothing will be done.
        """
        entry = self._getEntry(sourcename, filename)
        return entry.addFile(component, sha1, contents)

    def removeFile(self, component, sourcename, filename):
        """Remove the specified file from the pool.

        There are three possible outcomes:
        - If the specified file does not exist, NotInPool will be raised.

        - If the specified file exists and is a symlink, or is the only
        copy of the file in the pool, it will simply be deleted, and its
        size will be returned.

        - If the specified file is a real file and there are symlinks
        referencing it, the symlink in the next most preferred component
        will be deleted, and the file will be moved to replace it. The
        size of the deleted symlink will be returned.
        """
        entry = self._getEntry(sourcename, filename)
        return entry.removeFile(component)
