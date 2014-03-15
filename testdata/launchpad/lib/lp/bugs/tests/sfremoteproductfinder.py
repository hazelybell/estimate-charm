# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing helpers for sfremoteproductfinder."""

__metaclass__ = type
__all__ = ['TestSFRemoteProductFinder']

import os
import re
from urllib2 import HTTPError

from lp.bugs.scripts.sfremoteproductfinder import (
    SourceForgeRemoteProductFinder,
    )


class TestSFRemoteProductFinder(SourceForgeRemoteProductFinder):

    def _getPage(self, page):
        self.logger.debug("Getting page %s" % page)

        project_re = re.compile('projects/([a-z]+)')
        tracker_re = re.compile('/?tracker/\?group_id=([0-9]+)')

        project_match = project_re.match(page)
        tracker_match = tracker_re.match(page)

        if project_match is not None:
            project = project_match.groups()[0]
            file_path = os.path.join(
                os.path.dirname(__file__), 'testfiles',
                'sourceforge-project-%s.html' % project)
        elif tracker_match is not None:
            group_id = tracker_match.groups()[0]
            file_path = os.path.join(
                os.path.dirname(__file__), 'testfiles',
                'sourceforge-tracker-%s.html' % group_id)
        else:
            raise AssertionError(
                "The requested page '%s' isn't a project or tracker page."
                % page)

        return open(file_path, 'r').read()


class TestBrokenSFRemoteProductFinder(SourceForgeRemoteProductFinder):

    def _getPage(self, page):
        raise HTTPError(page, 500, "This is an error", None, None)
