#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script to save list of country mirrors for in text files.

For each country in our database, this script will create a text file,
named like cc.txt (where cc is the two letter country code),
containing the archive mirrors for that country.
"""

import _pythonpath

import os
import shutil
import tempfile

from zope.component import getUtility

from lp.registry.interfaces.distributionmirror import (
    IDistributionMirrorSet,
    MirrorContent,
    )
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.services.worlddata.interfaces.country import ICountrySet


class CacheCountryMirrors(LaunchpadScript):

    usage = '%prog <target-directory>'

    def main(self):
        if len(self.args) != 1:
            raise LaunchpadScriptFailure(
                "You must specify the full path of the directory where the "
                "files will be stored.")

        mirror_set = getUtility(IDistributionMirrorSet)
        [dir_name] = self.args
        if not os.path.isdir(dir_name):
            raise LaunchpadScriptFailure(
                "'%s' is not a directory." % dir_name)

        for country in getUtility(ICountrySet):
            mirrors = mirror_set.getBestMirrorsForCountry(
                country, MirrorContent.ARCHIVE)
            # Write the content to a temporary file first, to avoid problems
            # if the script is killed or something like that.
            fd, tmpfile = tempfile.mkstemp()
            mirrors_file = os.fdopen(fd, 'w')
            mirrors_file.write(
                "\n".join(mirror.base_url for mirror in mirrors))
            mirrors_file.close()
            filename = os.path.join(dir_name, '%s.txt' % country.iso3166code2)
            shutil.move(tmpfile, filename)
            os.chmod(filename, 0644)


if __name__ == '__main__':
    CacheCountryMirrors('cache-country-mirrors').lock_and_run()

