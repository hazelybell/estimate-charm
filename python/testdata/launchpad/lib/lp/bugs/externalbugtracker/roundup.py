# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Round ExternalBugTracker utility."""

__metaclass__ = type
__all__ = ['Roundup']

import csv
from urllib import quote_plus

from lazr.uri import URI

from lp.bugs.externalbugtracker import (
    BugNotFound,
    ExternalBugTracker,
    InvalidBugId,
    LookupTree,
    UnknownRemoteStatusError,
    UnparsableBugData,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.externalbugtracker import UNKNOWN_REMOTE_IMPORTANCE


PYTHON_BUGS_HOSTNAME = 'bugs.python.org'
MPLAYERHQ_BUGS_HOSTNAME = 'roundup.mplayerhq.hu'


def create_query_string(items):
    """Join the items to form a valid URL query string.

    There is urllib.urlencode that does a similar job, but you can't
    specify the safe characters. Roundup likes URLs with @s in them,
    and they work just fine unquoted.
    """
    return '&'.join(
        '%s=%s' % (quote_plus(key, '@'), quote_plus(value))
        for (key, value) in items)


class Roundup(ExternalBugTracker):
    """An ExternalBugTracker descendant for handling Roundup bug trackers."""

    _status_fields_map = {
        PYTHON_BUGS_HOSTNAME: ('status', 'resolution'),
        MPLAYERHQ_BUGS_HOSTNAME: ('status', 'substatus'),
        }

    # Our mapping of Roundup => Launchpad statuses. Roundup statuses
    # are integer-only and highly configurable.  Therefore we map the
    # statuses available by default.
    _status_lookup_standard = LookupTree(
        (1, BugTaskStatus.NEW),          # Roundup status 'unread'
        (2, BugTaskStatus.CONFIRMED),    # Roundup status 'deferred'
        (3, BugTaskStatus.INCOMPLETE),   # Roundup status 'chatting'
        (4, BugTaskStatus.INCOMPLETE),   # Roundup status 'need-eg'
        (5, BugTaskStatus.INPROGRESS),   # Roundup status 'in-progress'
        (6, BugTaskStatus.INPROGRESS),   # Roundup status 'testing'
        (7, BugTaskStatus.FIXCOMMITTED), # Roundup status 'done-cbb'
        (8, BugTaskStatus.FIXRELEASED),  # Roundup status 'resolved'
        )

    # Python bugtracker statuses come in two parts: status and
    # resolution. Both of these are integer values.
    _status_lookup_python_1 = LookupTree(
        # Open issues (status=1). We also use this as a fallback for
        # statuses 2 and 3, for which the mappings are different only
        # in a few instances.
        (None, BugTaskStatus.NEW),       # No resolution
        (1, BugTaskStatus.CONFIRMED),    # Resolution: accepted
        (2, BugTaskStatus.CONFIRMED),    # Resolution: duplicate
        (3, BugTaskStatus.FIXCOMMITTED), # Resolution: fixed
        (4, BugTaskStatus.INVALID),      # Resolution: invalid
        (5, BugTaskStatus.CONFIRMED),    # Resolution: later
        (6, BugTaskStatus.INVALID),      # Resolution: out-of-date
        (7, BugTaskStatus.CONFIRMED),    # Resolution: postponed
        (8, BugTaskStatus.WONTFIX),      # Resolution: rejected
        (9, BugTaskStatus.CONFIRMED),    # Resolution: remind
        (10, BugTaskStatus.WONTFIX),     # Resolution: wontfix
        (11, BugTaskStatus.INVALID),     # Resolution: works for me
        )
    _status_lookup_python = LookupTree(
        (1, _status_lookup_python_1),
        (2, LookupTree(
            (None, BugTaskStatus.WONTFIX),   # No resolution
            (1, BugTaskStatus.FIXCOMMITTED), # Resolution: accepted
            (3, BugTaskStatus.FIXRELEASED),  # Resolution: fixed
            (7, BugTaskStatus.WONTFIX),      # Resolution: postponed
            _status_lookup_python_1)),       # Failback
        (3, LookupTree(
            (None, BugTaskStatus.INCOMPLETE),# No resolution
            (7, BugTaskStatus.WONTFIX),      # Resolution: postponed
            _status_lookup_python_1)),       # Failback
        )

    # Status tree for roundup.mplayerhq.hu Roundup instances. This is
    # a mapping of all statuses that have ever been used (as of
    # December 2008) in the Mplayer Roundup instance, not a
    # comprehensive mapping of all /possible/ statuses. Appropriate
    # mappings have been guessed at by looking at example bugs for
    # each combination found.
    #
    # If new combinations are used, we will see OOPSes, and we should
    # then see what they have used that combination to mean before
    # adding them to this lookup tree.
    #
    _status_lookup_mplayerhq = LookupTree(
        # status (new)
        (1, LookupTree(
                # substatus (new, open)
                (1, 2, BugTaskStatus.NEW),
                # substatus (analyzed)
                (4, BugTaskStatus.TRIAGED),
                )),
        # status (open)
        (2, LookupTree(
                # substatus (open)
                (2, BugTaskStatus.NEW),
                # substatus (reproduced)
                (3, BugTaskStatus.CONFIRMED),
                # substatus (analyzed, approved)
                (4, 6, 7, BugTaskStatus.TRIAGED),
                # substatus (needs_more_info)
                (5, BugTaskStatus.INCOMPLETE),
                # substatus (fixed)
                (10, BugTaskStatus.FIXCOMMITTED),
                # substatus (implemented)
                (13, BugTaskStatus.INPROGRESS),
                )),
        # status (closed)
        (3, LookupTree(
                # substatus (analyzed, needs_more_info, approved,
                #            duplicate, invalid, works_for_me, reject)
                (4, 5, 6, 8, 9, 12, BugTaskStatus.INVALID),
                # substatus (fixed, implemented, applied)
                (10, 13, 15, BugTaskStatus.FIXRELEASED),
                # substatus (wont_fix, wont_implement, reject)
                (11, 14, 16, BugTaskStatus.WONTFIX),
                )),
        )

    # Combine custom mappings with the standard mappings, using the
    # remote host as the first key into the tree.
    _status_lookup_titles = (
        'Remote host', 'Roundup status', 'Roundup resolution')
    _status_lookup = LookupTree(
        (PYTHON_BUGS_HOSTNAME, _status_lookup_python),
        (MPLAYERHQ_BUGS_HOSTNAME, _status_lookup_mplayerhq),
        (_status_lookup_standard,), # Default
        )

    def __init__(self, baseurl):
        """Create a new Roundup instance.

        :baseurl: The starting URL for accessing the remote Roundup
            bug tracker.

        The fields/columns to fetch from the remote bug tracker are
        derived based on the host part of the baseurl.
        """
        super(Roundup, self).__init__(baseurl)
        self.host = URI(self.baseurl).host

        self._status_fields = (
            self._status_fields_map.get(self.host, ('status',)))
        fields = ('title', 'id', 'activity') + self._status_fields

        # Roundup is quite particular about URLs, so although several
        # of the parameters below seem redundant or irrelevant, they
        # are needed for compatibility with the broadest range of
        # Roundup instances in the wild. Test before changing them!
        self.query_base = [
            ("@action", "export_csv"),
            ("@columns", ",".join(fields)),
            ("@sort", "id"),
            ("@group", "priority"),
            ("@filter", "id"),
            ("@pagesize", "50"),
            ("@startwith", "0"),
            ]

    def getSingleBugExportURL(self, bug_id):
        """Return the URL for single bug CSV export."""
        query = list(self.query_base)
        query.append(('id', str(bug_id)))
        return "%s/issue?%s" % (self.baseurl, create_query_string(query))

    def getBatchBugExportURL(self):
        """Return the URL for batch (all bugs) CSV export."""
        query = self.query_base
        return "%s/issue?%s" % (self.baseurl, create_query_string(query))

    def _getBug(self, bug_id):
        """Return the bug with the ID bug_id from the internal bug list.

        :param bug_id: The ID of the remote bug to return.
        :type bug_id: int

        BugNotFound will be raised if the bug does not exist.
        InvalidBugId will be raised if bug_id is not of a valid format.
        """
        try:
            bug_id = int(bug_id)
        except ValueError:
            raise InvalidBugId(
                "bug_id must be an integer: %s." % str(bug_id))

        try:
            return self.bugs[bug_id]
        except KeyError:
            raise BugNotFound(bug_id)

    def getRemoteBug(self, bug_id):
        """See `ExternalBugTracker`."""
        bug_id = int(bug_id)
        query_url = self.getSingleBugExportURL(bug_id)
        reader = csv.DictReader(self._fetchPage(query_url))
        return (bug_id, reader.next())

    def getRemoteBugBatch(self, bug_ids):
        """See `ExternalBugTracker`"""
        # XXX: Graham Binns 2007-08-28 bug=135317:
        #      At present, Roundup does not support exporting only a
        #      subset of bug ids as a batch (launchpad bug 135317). When
        #      this bug is fixed we need to change this method to only
        #      export the bug ids needed rather than hitting the remote
        #      tracker for a potentially massive number of bugs.
        query_url = self.getBatchBugExportURL()
        remote_bugs = csv.DictReader(self._fetchPage(query_url))
        bugs = {}
        for remote_bug in remote_bugs:
            # We're only interested in the bug if it's one of the ones in
            # bug_ids.
            if remote_bug['id'] not in bug_ids:
                continue

            bugs[int(remote_bug['id'])] = remote_bug

        return bugs

    def getRemoteImportance(self, bug_id):
        """See `ExternalBugTracker`.

        This method is implemented here as a stub to ensure that
        existing functionality is preserved. As a result,
        UNKNOWN_REMOTE_IMPORTANCE will always be returned.
        """
        return UNKNOWN_REMOTE_IMPORTANCE

    def getRemoteStatus(self, bug_id):
        """See `ExternalBugTracker`."""
        remote_bug = self._getBug(bug_id)

        # This could be done in a single list comprehension, but it's
        # done the long way so that we can raise a more useful error
        # if a field value is missing.
        field_values = []
        for field in self._status_fields:
            if field in remote_bug:
                field_values.append(remote_bug[field])
            else:
                raise UnparsableBugData(
                    "Remote bug %s does not define a value for %s." % (
                        bug_id, field))

        return ':'.join(field_values)

    def convertRemoteImportance(self, remote_importance):
        """See `ExternalBugTracker`.

        This method is implemented here as a stub to ensure that
        existing functionality is preserved. As a result,
        BugTaskImportance.UNKNOWN will always be returned.
        """
        return BugTaskImportance.UNKNOWN

    def convertRemoteStatus(self, remote_status):
        """See `IExternalBugTracker`."""
        fields = self._status_fields
        field_values = remote_status.split(':')

        if len(field_values) != len(fields):
            raise UnknownRemoteStatusError(
                "%d field(s) expected, got %d: %s" % (
                    len(fields), len(field_values), remote_status))

        for index, field_value in enumerate(field_values):
            if field_value == "None":
                field_values[index] = None
            elif field_value.isdigit():
                field_values[index] = int(field_value)
            else:
                raise UnknownRemoteStatusError(
                    "Unrecognized value for field %d (%s): %s" % (
                        (index + 1), fields[index], field_value))

        try:
            return self._status_lookup.find(self.host, *field_values)
        except KeyError:
            raise UnknownRemoteStatusError(remote_status)
