# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Client code for the branch filesystem endpoint.

This code talks to the internal XML-RPC server for the branch filesystem.
"""

__metaclass__ = type
__all__ = [
    'BranchFileSystemClient',
    'NotInCache',
    ]

import time

from twisted.internet import defer

from lp.code.interfaces.codehosting import BRANCH_TRANSPORT
from lp.services.twistedsupport import no_traceback_failures


class NotInCache(Exception):
    """Raised when we try to get a path from the cache that's not present."""


class BranchFileSystemClient:
    """Wrapper for some methods of the codehosting endpoint.

    Instances of this class wrap the methods of the codehosting endpoint
    required by the VFS code, specialized for a particular user.

    The wrapper also caches the results of calls to translatePath in order to
    avoid a large number of roundtrips. In the normal course of operation, our
    Bazaar transport translates virtual paths to real paths on disk using this
    client. It does this many, many times for a single Bazaar operation, so we
    cache the results here.
    """

    def __init__(self, codehosting_endpoint, user_id, expiry_time=None,
                 seen_new_branch_hook=None, _now=time.time):
        """Construct a caching codehosting_endpoint.

        :param codehosting_endpoint: An XML-RPC proxy that implements
            callRemote and returns Deferreds.
        :param user_id: The database ID of the user who will be making these
            requests. An integer.
        :param expiry_time: If supplied, only cache the results of
            translatePath for this many seconds.  If not supplied, cache the
            results of translatePath for as long as this instance exists.
        :param seen_new_branch_hook: A callable that will be called with the
            unique_name of each new branch that is accessed.
        """
        self._codehosting_endpoint = codehosting_endpoint
        self._cache = {}
        self._user_id = user_id
        self.expiry_time = expiry_time
        self._now = _now
        self.seen_new_branch_hook = seen_new_branch_hook

    def _getMatchedPart(self, path, transport_tuple):
        """Return the part of 'path' that the endpoint actually matched."""
        trailing_length = len(transport_tuple[2])
        if trailing_length == 0:
            matched_part = path
        else:
            matched_part = path[:-trailing_length]
        return matched_part.rstrip('/')

    def _addToCache(self, transport_tuple, path):
        """Cache the given 'transport_tuple' results for 'path'.

        :return: the 'transport_tuple' as given, so we can use this as a
            callback.
        """
        (transport_type, data, trailing_path) = transport_tuple
        matched_part = self._getMatchedPart(path, transport_tuple)
        if transport_type == BRANCH_TRANSPORT:
            if self.seen_new_branch_hook:
                self.seen_new_branch_hook(matched_part.strip('/'))
            self._cache[matched_part] = (transport_type, data, self._now())
        return transport_tuple

    def _getFromCache(self, path):
        """Get the cached 'transport_tuple' for 'path'."""
        split_path = path.strip('/').split('/')
        for object_path, value in self._cache.iteritems():
            transport_type, data, inserted_time = value
            split_object_path = object_path.strip('/').split('/')
            # Do a segment-by-segment comparison. Python sucks, lists should
            # also have startswith.
            if split_path[:len(split_object_path)] == split_object_path:
                if (self.expiry_time is not None
                    and self._now() > inserted_time + self.expiry_time):
                    del self._cache[object_path]
                    break
                trailing_path = '/'.join(split_path[len(split_object_path):])
                return (transport_type, data, trailing_path)
        raise NotInCache(path)

    def createBranch(self, branch_path):
        """Create a Launchpad `IBranch` in the database.

        This raises any Faults that might be raised by the
        codehosting_endpoint's `createBranch` method, so for more information
        see `IBranchFileSystem.createBranch`.

        :param branch_path: The path to the branch to create.
        :return: A `Deferred` that fires the ID of the created branch.
        """
        return self._codehosting_endpoint.callRemote(
            'createBranch', self._user_id, branch_path)

    def branchChanged(self, branch_id, stacked_on_url, last_revision_id,
                      control_string, branch_string, repository_string):
        """Mark a branch as needing to be mirrored.

        :param branch_id: The database ID of the branch.
        """
        return self._codehosting_endpoint.callRemote(
            'branchChanged', self._user_id, branch_id, stacked_on_url,
            last_revision_id, control_string, branch_string,
            repository_string)

    def translatePath(self, path):
        """Translate 'path'."""
        try:
            return defer.succeed(self._getFromCache(path))
        except NotInCache:
            deferred = self._codehosting_endpoint.callRemote(
                'translatePath', self._user_id, path)
            deferred.addCallback(no_traceback_failures(self._addToCache), path)
            return deferred
