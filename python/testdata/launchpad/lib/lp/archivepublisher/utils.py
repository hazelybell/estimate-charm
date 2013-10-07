# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Miscellaneous functions for publisher."""

__metaclass__ = type

__all__ = [
    'RepositoryIndexFile',
    'get_ppa_reference',
    ]


import bz2
import gzip
from operator import itemgetter
import os
import stat
import tempfile

from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.archive import default_name_by_purpose


def get_ppa_reference(ppa):
    """Return a text reference for the given PPA.

    * '<owner_name>' for default PPAs (the ones named 'ppa');
    * '<owner_name>-<ppa_name>' for named-PPAs.
    """
    assert ppa.purpose == ArchivePurpose.PPA, (
        'Only PPAs can use reference name.')

    if ppa.name != default_name_by_purpose.get(ArchivePurpose.PPA):
        return '%s-%s' % (ppa.owner.name, ppa.name)

    return ppa.owner.name


def count_alive(store, logger):
    """Print counts of how many alive objects the store knows about."""
    counts = {}
    for obj_info in store._iter_alive():
        name = obj_info.cls_info.cls.__name__
        counts[name] = counts.get(name, 0) + 1

    sorted_items = sorted(counts.items(), key=itemgetter(0), reverse=True)
    for (name, count) in sorted_items:
        logger.debug('%-20s %d' % (name, count))


class PlainTempFile:

    # Filename suffix.
    suffix = ''
    # File path built on initialization.
    path = None

    def __init__(self, temp_root, filename):
        self.filename = filename + self.suffix

        fd, self.path = tempfile.mkstemp(
            dir=temp_root, prefix='%s_' % filename)

        self._fd = self._buildFile(fd)

    def _buildFile(self, fd):
        return os.fdopen(fd, 'wb')

    def write(self, content):
        self._fd.write(content)

    def close(self):
        self._fd.close()

    def __del__(self):
        """Remove temporary file if it was left behind. """
        if self.path is not None and os.path.exists(self.path):
            os.remove(self.path)


class GzipTempFile(PlainTempFile):
    suffix = '.gz'

    def _buildFile(self, fd):
        return gzip.GzipFile(fileobj=os.fdopen(fd, "wb"))


class Bzip2TempFile(PlainTempFile):
    suffix = '.bz2'

    def _buildFile(self, fd):
        os.close(fd)
        return bz2.BZ2File(self.path, mode='wb')


class RepositoryIndexFile:
    """Facilitates the publication of repository index files.

    It allows callsites to publish index files in different medias
    (plain, gzip and bzip2) transparently and atomically.
    """

    def __init__(self, path, temp_root):
        """Store repositories destinations and filename.

        The given 'temp_root' needs to exist; on the other hand, the
        directory containing 'path' will be created on `close` if it doesn't
        exist.

        Additionally creates the needed temporary files in the given
        'temp_root'.
        """
        self.root, filename = os.path.split(path)
        assert os.path.exists(temp_root), 'Temporary root does not exist.'

        self.index_files = (
            PlainTempFile(temp_root, filename),
            GzipTempFile(temp_root, filename),
            Bzip2TempFile(temp_root, filename),
            )

    def write(self, content):
        """Write contents to all target medias."""
        for index_file in self.index_files:
            index_file.write(content)

    def close(self):
        """Close temporary media and atomically publish them.

        If necessary the given 'root' destination is created at this point.

        It also fixes the final files permissions making them readable and
        writable by their group and readable by others.
        """
        if os.path.exists(self.root):
            assert os.access(
                self.root, os.W_OK), "%s not writeable!" % self.root
        else:
            os.makedirs(self.root)

        for index_file in self.index_files:
            index_file.close()
            root_path = os.path.join(self.root, index_file.filename)
            os.rename(index_file.path, root_path)
            # XXX julian 2007-10-03
            # This is kinda papering over a problem somewhere that causes the
            # files to get created with permissions that don't allow
            # group/world read access.
            # See https://bugs.launchpad.net/soyuz/+bug/148471
            mode = stat.S_IMODE(os.stat(root_path).st_mode)
            os.chmod(root_path,
                     mode | stat.S_IWGRP | stat.S_IRGRP | stat.S_IROTH)
