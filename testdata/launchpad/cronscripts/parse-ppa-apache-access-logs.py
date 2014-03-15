#!/usr/bin/python -S
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parse PPA apache logs to find out download counts for each file."""

__metaclass__ = type

import _pythonpath

import functools

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.services.apachelogparser.script import ParseApacheLogs
from lp.services.config import config
from lp.soyuz.interfaces.archive import NoSuchPPA
from lp.soyuz.scripts.ppa_apache_log_parser import (
    DBUSER,
    get_ppa_file_key,
    )


class ParsePPAApacheLogs(ParseApacheLogs):
    """An Apache log parser for PPA downloads."""

    def setUpUtilities(self):
        """See `ParseApacheLogs`."""
        self.person_set = getUtility(IPersonSet)

    @property
    def root(self):
        """See `ParseApacheLogs`."""
        return config.ppa_apache_log_parser.logs_root

    @property
    def log_file_glob(self):
        return config.ppa_apache_log_parser.log_file_glob

    def getDownloadKey(self, path):
        """See `ParseApacheLogs`."""
        return get_ppa_file_key(path)

    def getDownloadCountUpdater(self, file_id):
        """See `ParseApacheLogs`."""
        person = self.person_set.getByName(file_id[0])
        if person is None:
            return
        try:
            archive = person.getPPAByName(file_id[1])
        except NoSuchPPA:
            return None
        # file_id[2] (distro) isn't used yet, since getPPAByName
        # hardcodes Ubuntu.
        bpr = archive.getBinaryPackageReleaseByFileName(file_id[3])
        if bpr is None:
            return None

        return functools.partial(archive.updatePackageDownloadCount, bpr)


if __name__ == '__main__':
    script = ParsePPAApacheLogs('parse-ppa-apache-logs', DBUSER)
    script.lock_and_run()
