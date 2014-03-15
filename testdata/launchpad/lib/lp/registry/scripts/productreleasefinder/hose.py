# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Identifies files for download.

This module uses the walker and filter modules to identify files for
download.
"""

__metaclass__ = type
__all__ = [
    'Hose',
    ]

from lp.registry.scripts.productreleasefinder import log
from lp.registry.scripts.productreleasefinder.filter import Filter
from lp.registry.scripts.productreleasefinder.walker import (
    combine_url,
    walk,
    )


class Hose:
    """Hose.

    This class should be instantiated with a dictionary of url and glob pairs,
    it will use a walker to recursively decend each URL and map each URL
    to a file.

    It can be used as an iterator to yield (key, url) for each URL where
    key is one of the dictionary keys or None if none matched.
    """

    def __init__(self, filters=(), log_parent=None):
        self.log = log.get_logger("Hose", log_parent)
        self.filter = Filter(filters, log_parent=self.log)
        self.urls = self.reduceWork([pattern.base_url for pattern in filters])

    def reduceWork(self, url_list):
        """Simplify URL list to remove children of other elements.

        Reduces the amount of work we need to do by removing any URL from
        the list whose parent also appears in the list.  Returns the
        reduced list.
        """
        self.log.info("Reducing URL list.")
        urls = []
        url_list = list(url_list)
        while len(url_list):
            url = url_list.pop(0)
            for check_url in urls + url_list:
                if url.startswith(check_url):
                    self.log.debug("Discarding %s as have %s", url, check_url)
                    break
            else:
                urls.append(url)

        return urls

    def run(self):
        """Run over the URL list."""
        self.log.info("Identifying URLs")
        for base_url in self.urls:
            for dirpath, dirnames, filenames in walk(base_url, self.log):
                for filename in filenames:
                    url = combine_url(base_url, dirpath, filename)
                    key = self.filter.check(url)
                    yield (key, url)
                # To affect which directories the walker descends
                # into, we must update the dirnames list in place.
                i = 0
                while i < len(dirnames):
                    url = combine_url(base_url, dirpath, dirnames[i])
                    if self.filter.isPossibleParent(url):
                        i += 1
                    else:
                        self.log.info('Skipping %s', url)
                        del dirnames[i]

    __iter__ = run
