# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bugs support for the scanner."""

__metaclass__ = type
__all__ = [
    'BugBranchLinker',
    ]

import urlparse

from bzrlib.errors import InvalidBugStatus
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bug import IBugSet


class BugBranchLinker:
    """Links branches to bugs based on revision metadata."""

    def __init__(self, db_branch):
        self.db_branch = db_branch

    def _getBugFromUrl(self, url):
        protocol, host, path, ignored, ignored = urlparse.urlsplit(url)

        # Skip URLs that don't point to Launchpad.
        if host != 'launchpad.net':
            return None

        # Remove empty path segments.
        segments = [
            segment for segment in path.split('/') if len(segment) > 0]
        # Don't allow Launchpad URLs that aren't /bugs/<integer>.
        try:
            bug_segment, bug_id = segments
        except ValueError:
            return None
        if bug_segment != 'bugs':
            return None
        try:
            return int(bug_id)
        except ValueError:
            return None

    def _getBugStatus(self, bzr_status):
        # Make sure the status is acceptable.
        valid_statuses = {'fixed': 'fixed'}
        return valid_statuses.get(bzr_status.lower(), None)

    def extractBugInfo(self, bzr_revision):
        """Parse bug information out of the given revision property.

        :param bug_status_prop: A string containing lines of
            '<bug_url> <status>'.
        :return: dict mapping bug IDs to BugBranchStatuses.
        """
        bug_statuses = {}
        for url, status in bzr_revision.iter_bugs():
            bug = self._getBugFromUrl(url)
            status = self._getBugStatus(status)
            if bug is None or status is None:
                continue
            bug_statuses[bug] = status
        return bug_statuses

    def createBugBranchLinksForRevision(self, bzr_revision):
        """Create bug-branch links for a revision.

        This looks inside the 'bugs' property of the given Bazaar revision and
        creates a BugBranch record for each bug mentioned.
        """
        try:
            bug_info = self.extractBugInfo(bzr_revision)
        except InvalidBugStatus:
            return
        bug_set = getUtility(IBugSet)
        for bug_id, status in bug_info.iteritems():
            try:
                bug = bug_set.get(bug_id)
            except NotFoundError:
                pass
            else:
                bug.linkBranch(
                    branch=self.db_branch,
                    registrant=getUtility(ILaunchpadCelebrities).janitor)


def got_new_mainline_revisions(new_mainline_revisions):
    linker = BugBranchLinker(new_mainline_revisions.db_branch)
    for bzr_revision in new_mainline_revisions.bzr_revisions:
        linker.createBugBranchLinksForRevision(bzr_revision)
