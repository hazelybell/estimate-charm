# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['ParseApacheLogs']

import glob
import os

from lazr.restful.utils import safe_hasattr
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.services.apachelogparser.base import (
    create_or_update_parsedlog_entry,
    get_files_to_parse,
    parse_file,
    )
from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript
from lp.services.worlddata.interfaces.country import ICountrySet


class ParseApacheLogs(LaunchpadCronScript):
    """An abstract Apache log parser, finding download counts for each file.

    This does the heavy lifting to turn a directory of Apache log files
    into a structure mapping files to days to countries to download counts.

    Subclasses should override root, getDownloadKey, getDownloadCountUpdater,
    and optionally setUpUtilities.
    """

    # Glob to restrict filenames that are parsed.
    log_file_glob = '*'

    def setUpUtilities(self):
        """Prepare any utilities that might be used many times."""
        pass

    @property
    def root(self):
        """Root directory in which to find the logs."""
        raise NotImplementedError

    def getDownloadKey(self, path):
        """Generate a value to use as a key in the download dict.

        This will be called for every log line, so it should be very cheap.
        It's probably best not to return any complex objects, as there will
        be lots and lots and lots of these results sitting around for quite
        some time.

        :param path: The requested path.
        :return: A hashable object identifying the object at the path, or
            None if a request with this path should be ignored.
        """
        raise NotImplementedError

    def getDownloadCountUpdater(self, file_id):
        """Return a function which updates the download count of the object.

        :param file_id: The download key as calculated by getDownloadKey.
        :return: A count updating function, called as f(day, country, count),
            or None if the count should not be updated (eg. target deleted).
        """
        raise NotImplementedError

    def main(self):
        self.setUpUtilities()

        # Materialize the list of files to parse. It is better to do the
        # checks now, rather than potentially hours later when the
        # generator gets around to it, because there is a reasonable
        # chance log rotation will have kicked in and removed our oldest
        # files. Note that we still error if a file we want to parse
        # disappears before we get around to parsing it, which is
        # desirable behavior.
        files_to_parse = list(get_files_to_parse(
            glob.glob(os.path.join(self.root, self.log_file_glob))))

        country_set = getUtility(ICountrySet)
        parsed_lines = 0
        max_parsed_lines = getattr(
            config.launchpad, 'logparser_max_parsed_lines', None)
        max_is_set = max_parsed_lines is not None
        for fd, position in files_to_parse:
            # If we've used up our budget of lines to process, stop.
            if (max_is_set and parsed_lines >= max_parsed_lines):
                break
            downloads, parsed_bytes, parsed_lines = parse_file(
                fd, position, self.logger, self.getDownloadKey)
            # Use a while loop here because we want to pop items from the dict
            # in order to free some memory as we go along. This is a good
            # thing here because the downloads dict may get really huge.
            while downloads:
                file_id, daily_downloads = downloads.popitem()
                update_download_count = self.getDownloadCountUpdater(file_id)

                # The object couldn't be retrieved (maybe it was deleted).
                # Don't bother counting downloads for it.
                if update_download_count is None:
                    continue

                for day, country_downloads in daily_downloads.items():
                    for country_code, count in country_downloads.items():
                        try:
                            country = country_set[country_code]
                        except NotFoundError:
                            # We don't know the country for the IP address
                            # where this request originated.
                            country = None
                        update_download_count(day, country, count)
            fd.seek(0)
            first_line = fd.readline()
            fd.close()
            create_or_update_parsedlog_entry(first_line, parsed_bytes)
            self.txn.commit()
            if safe_hasattr(fd, 'name'):
                name = fd.name
            else:
                name = fd
            self.logger.info('Finished parsing %s' % name)

        self.logger.info('Done parsing apache log files')
