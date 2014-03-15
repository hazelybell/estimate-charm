# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""URL filter.

This module implements the URL filtering to identify which glob each
filename matches, or whether it is a file outside of any known pattern.
"""

__metaclass__ = type
__all__ = [
    'Filter',
    'FilterPattern',
    ]

import fnmatch
import itertools
import re

from lp.registry.scripts.productreleasefinder import log


class Filter:
    """URL filter.

    The filters argument is a sequence of filter patterns.  Each
    filter pattern is an object with a match() method used to check if
    the pattern matches the URL.
    """

    def __init__(self, filters=(), log_parent=None):
        self.log = log.get_logger("Filter", log_parent)
        self.filters = list(filters)

    def check(self, url):
        """Check a URL against the filters.

        Checks each of the registered patterns against the given URL,
        and returns the 'key' attribute of the first pattern that
        matches.
        """
        self.log.debug("Checking %s", url)
        for pattern in self.filters:
            if pattern.match(url):
                self.log.info("%s matches %s glob (%s)",
                              url, pattern.key, pattern.urlglob)
                return pattern.key
        else:
            self.log.debug("No matches")
            return None

    def isPossibleParent(self, url):
        """Check if any filters could match children of a URL."""
        self.log.debug("Checking if %s is a possible parent", url)
        for pattern in self.filters:
            if pattern.containedBy(url):
                self.log.info("%s could contain matches for %s glob (%s)",
                              url, pattern.key, pattern.urlglob)
                return True
        else:
            return False


class FilterPattern:
    """A filter pattern.

    Instances of FilterPattern are intended to be used with a Filter
    instance.
    """

    def __init__(self, key, urlglob):
        self.key = key
        self.urlglob = urlglob

        parts = self.urlglob.split('/')
        # construct a base URL by taking components up til the first
        # one containing a glob pattern:
        self.base_url = '/'.join(itertools.takewhile(
            lambda part: '*' not in part and '?' not in part, parts))
        if not self.base_url.endswith('/'):
            self.base_url += '/'

        self.patterns = [re.compile(fnmatch.translate(part)) for part in parts]

    def match(self, url):
        """Returns true if this filter pattern matches the URL."""
        parts = url.split('/')
        # If the length of list of slash separated parts of the URL
        # differs from the number of patterns, then they can't match.
        if len(parts) != len(self.patterns):
            return False
        for (part, pattern) in zip(parts, self.patterns):
            if not pattern.match(part):
                return False
        # Everything matches ...
        return True

    def containedBy(self, url):
        """Returns true if this pattern could match children of the URL."""
        url = url.rstrip('/')
        parts = url.split('/')
        # If the URL contains greater than or equal the number of
        # parts as the number of patterns we have, then it couldn't
        # contain any children that match this pattern.
        if len(parts) >= len(self.patterns):
            return False
        for (part, pattern) in zip(parts, self.patterns):
            if not pattern.match(part):
                return False
        # Everything else matches ...
        return True
