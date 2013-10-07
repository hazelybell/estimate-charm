#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parse librarian apache logs to find out download counts for each file.

Thanks to the *huge* number of different LibraryFileAlias objects this script
will fetch when parsing multiple log files from scratch and the fact that we
overwrite storm's cache with something that caches *everything*, this script
may end up eating all your RAM. That shouldn't happen in general as we run
it multiple times a day, but if we ever fail to run it for more than a week,
we may need to add a hack (store._cache.clear()) to clear the cache after
updating the counts of every LFA, in order to get through the backlog.
"""

__metaclass__ = type

import _pythonpath

from storm.sqlobject import SQLObjectNotFound
from zope.component import getUtility

from lp.services.apachelogparser.script import ParseApacheLogs
from lp.services.config import config
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarianserver.apachelogparser import (
    DBUSER,
    get_library_file_id,
    )


class ParseLibrarianApacheLogs(ParseApacheLogs):
    """An Apache log parser for LibraryFileAlias downloads."""

    def setUpUtilities(self):
        """See `ParseApacheLogs`."""
        self.libraryfilealias_set = getUtility(ILibraryFileAliasSet)

    @property
    def root(self):
        """See `ParseApacheLogs`."""
        return config.librarianlogparser.logs_root

    def getDownloadKey(self, path):
        """See `ParseApacheLogs`."""
        return get_library_file_id(path)

    def getDownloadCountUpdater(self, file_id):
        """See `ParseApacheLogs`."""
        try:
            return self.libraryfilealias_set[file_id].updateDownloadCount
        except SQLObjectNotFound:
            # This file has been deleted from the librarian, so don't
            # try to store download counters for it.
            return None


if __name__ == '__main__':
    script = ParseLibrarianApacheLogs('parse-librarian-apache-logs', DBUSER)
    script.lock_and_run()
