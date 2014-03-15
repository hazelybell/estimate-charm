# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation of the dynamic RewriteMap used to serve branches over HTTP.
"""

import time

from bzrlib import urlutils
from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.codehosting import BRANCH_ID_ALIAS_PREFIX
from lp.codehosting.vfs import branch_id_to_path
from lp.services.config import config
from lp.services.utils import iter_split
from lp.services.webapp.adapter import (
    clear_request_started,
    set_request_started,
    )


__all__ = ['BranchRewriter']


class BranchRewriter:

    def __init__(self, logger, _now=None):
        """

        :param logger: Logger that messages about what the rewriter is doing
            will be sent to.
        :param proxy: A blocking proxy for a branchfilesystem endpoint.
        """
        if _now is None:
            self._now = time.time
        else:
            self._now = _now
        self.logger = logger
        self._cache = {}

    def _codebrowse_url(self, path):
        return urlutils.join(
            config.codehosting.internal_codebrowse_root,
            path)

    def _getBranchIdAndTrailingPath(self, location):
        """Return the branch id and trailing path for 'location'.

        In addition this method returns whether the answer can from the cache
        or from the database.
        """
        for first, second in iter_split(location[1:], '/'):
            if first in self._cache:
                branch_id, inserted_time = self._cache[first]
                if (self._now() < inserted_time +
                    config.codehosting.branch_rewrite_cache_lifetime):
                    return branch_id, second, "HIT"
        lookup = getUtility(IBranchLookup)
        branch, trailing = lookup.getByHostingPath(location.lstrip('/'))
        if branch is not None:
            try:
                branch_id = branch.id
            except Unauthorized:
                pass
            else:
                unique_name = location[1:-len(trailing)]
                self._cache[unique_name] = (branch_id, self._now())
                return branch_id, trailing, "MISS"
        return None, None, "MISS"

    def rewriteLine(self, resource_location):
        """Rewrite 'resource_location' to a more concrete location.

        We use the 'translatePath' BranchFileSystemClient method.  There are
        three cases:

         (1) The request is for something within the .bzr directory of a
             branch.

             In this case we rewrite the request to the location from which
             branches are served by ID.

         (2) The request is for something within a branch, but not the .bzr
             directory.

             In this case, we hand the request off to codebrowse.

         (3) The branch is not found.  Two sub-cases: the request is for a
             product control directory or the we don't know how to translate
             the path.

             In both these cases we return 'NULL' which indicates to Apache
             that we don't know how to rewrite the request (and so it should
             go on to generate a 404 response).

        Other errors are allowed to propagate, on the assumption that the
        caller will catch and log them.
        """
        # Codebrowse generates references to its images and stylesheets
        # starting with "/static", so pass them on unthinkingly.
        T = time.time()
        # Tell the webapp adapter that we are in a request, so that DB
        # statement timeouts will be applied.
        set_request_started()
        try:
            cached = None
            if resource_location.startswith('/static/'):
                r = self._codebrowse_url(resource_location)
                cached = 'N/A'
            else:
                branch_id, trailing, cached = self._getBranchIdAndTrailingPath(
                    resource_location)
                if branch_id is None:
                    if resource_location.startswith(
                            '/' + BRANCH_ID_ALIAS_PREFIX):
                        r = 'NULL'
                    else:
                        r = self._codebrowse_url(resource_location)
                else:
                    if trailing.startswith('/.bzr'):
                        r = urlutils.join(
                            config.codehosting.internal_branch_by_id_root,
                            branch_id_to_path(branch_id), trailing[1:])
                    else:
                        r = self._codebrowse_url(resource_location)
        finally:
            clear_request_started()
        self.logger.info(
            "%r -> %r (%fs, cache: %s)",
            resource_location, r, time.time() - T, cached)
        return r
