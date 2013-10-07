# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers to work with tar files more easily."""

__metaclass__ = type

__all__ = [
    'LaunchpadWriteTarFile',
    ]

import os
from StringIO import StringIO
import tarfile
import tempfile
import time

# A note about tarballs, StringIO and unicode. SQLObject returns unicode
# values for columns which are declared as StringCol. We have to be careful
# not to pass unicode instances to the tarfile module, because when the
# tarfile's filehandle is a StringIO object, the StringIO object gets upset
# later when we ask it for its value and it tries to join together its
# buffers. This is why the tarball code is sprinkled with ".encode('ascii')".
# If we get separate StringCol and UnicodeCol column types, we won't need this
# any longer.
# -- Dafydd Harries, 2005-04-07.


class LaunchpadWriteTarFile:
    """Convenience wrapper around the tarfile module.

    This class makes it convenient to generate tar files in various ways.
    """

    def __init__(self, stream):
        self.tarfile = tarfile.open('', 'w:gz', stream)
        self.closed = False

    @classmethod
    def files_to_stream(cls, files):
        """Turn a dictionary of files into a data stream."""
        buffer = tempfile.TemporaryFile()
        archive = cls(buffer)
        archive.add_files(files)
        archive.close()
        buffer.seek(0)
        return buffer

    @classmethod
    def files_to_string(cls, files):
        """Turn a dictionary of files into a data string."""
        return cls.files_to_stream(files).read()

    @classmethod
    def files_to_tarfile(cls, files):
        """Turn a dictionary of files into a tarfile object."""
        return tarfile.open('', 'r', cls.files_to_stream(files))

    def close(self):
        """Close the archive.

        After the archive is closed, the data written to the filehandle will
        be complete. The archive may not be appended to after it has been
        closed.
        """

        self.tarfile.close()
        self.closed = True

    def _make_skeleton_tarinfo(self, path, now):
        """Make a basic TarInfo object to be fleshed out by the caller."""
        tarinfo = tarfile.TarInfo(path)
        tarinfo.mtime = now
        tarinfo.uname = 'launchpad'
        tarinfo.gname = 'launchpad'
        return tarinfo

    def _ensure_directories(self, path, now):
        """Ensure that all the directories in the path are present."""
        path_bits = path.split(os.path.sep)

        for i in range(1, len(path_bits)):
            joined_path = os.path.join(*path_bits[:i])

            try:
                self.tarfile.getmember(joined_path)
            except KeyError:
                tarinfo = self._make_skeleton_tarinfo(joined_path, now)
                tarinfo.type = tarfile.DIRTYPE
                tarinfo.mode = 0755
                self.tarfile.addfile(tarinfo)

    def add_directory(self, path):
        """Add a directory to the archive."""
        assert not self.closed, "Can't add a directory to a closed archive"

        now = int(time.time())
        self._ensure_directories(os.path.join(path, "."), now)

    def add_file(self, path, contents):
        """Add a file to the archive."""
        assert not self.closed, "Can't add a file to a closed archive"

        now = int(time.time())
        self._ensure_directories(path, now)

        tarinfo = self._make_skeleton_tarinfo(path, now)
        tarinfo.mode = 0644
        tarinfo.size = len(contents)
        self.tarfile.addfile(tarinfo, StringIO(contents))

    def add_files(self, files):
        """Add a number of files to the archive.

        :param files: A dictionary mapping file names to file contents.
        """

        for filename in sorted(files.keys()):
            self.add_file(filename, files[filename])

    def add_symlink(self, path, target):
        """Add a symbolic link to the archive."""
        assert not self.closed, "Can't add a symlink to a closed archive"

        now = int(time.time())
        self._ensure_directories(path, now)

        tarinfo = self._make_skeleton_tarinfo(path, now)
        tarinfo.type = tarfile.SYMTYPE
        tarinfo.linkname = target
        self.tarfile.addfile(tarinfo)
