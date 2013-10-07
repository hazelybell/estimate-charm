# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""External bugtrackers."""

__metaclass__ = type
__all__ = [
    'BATCH_SIZE_UNLIMITED',
    'BugNotFound',
    'BugTrackerAuthenticationError',
    'BugTrackerConnectError',
    'BugWatchUpdateError',
    'BugWatchUpdateWarning',
    'ExternalBugTracker',
    'InvalidBugId',
    'LookupTree',
    'PrivateRemoteBug',
    'UnknownBugTrackerTypeError',
    'UnknownRemoteImportanceError',
    'UnknownRemoteStatusError',
    'UnknownRemoteValueError',
    'UnparsableBugData',
    'UnparsableBugTrackerVersion',
    'UnsupportedBugTrackerVersion',
    ]


import urllib
import urllib2
from urlparse import urlparse

from zope.interface import implements

from lp.bugs.adapters import treelookup
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.interfaces.externalbugtracker import (
    IExternalBugTracker,
    ISupportsBackLinking,
    ISupportsCommentImport,
    ISupportsCommentPushing,
    )
from lp.services.config import config
from lp.services.database.isolation import ensure_no_transaction

# The user agent we send in our requests
LP_USER_AGENT = "Launchpad Bugscraper/0.2 (https://bugs.launchpad.net/)"

# To signify that all bug watches should be checked in a single run.
BATCH_SIZE_UNLIMITED = 0


class BugWatchUpdateError(Exception):
    """Base exception for when we fail to update watches for a tracker."""


class UnknownBugTrackerTypeError(BugWatchUpdateError):
    """Exception class to catch systems we don't have a class for yet."""

    def __init__(self, bugtrackertypename, bugtrackername):
        BugWatchUpdateError.__init__(self)
        self.bugtrackertypename = bugtrackertypename
        self.bugtrackername = bugtrackername

    def __str__(self):
        return self.bugtrackertypename


class UnsupportedBugTrackerVersion(BugWatchUpdateError):
    """The bug tracker version is not supported."""


class UnparsableBugTrackerVersion(BugWatchUpdateError):
    """The bug tracker version could not be parsed."""


class UnparsableBugData(BugWatchUpdateError):
    """The bug tracker provided bug data that could not be parsed."""


class BugTrackerConnectError(BugWatchUpdateError):
    """Exception class to catch misc errors contacting a bugtracker."""

    def __init__(self, url, error):
        BugWatchUpdateError.__init__(self)
        self.url = url
        self.error = str(error)

    def __str__(self):
        return "%s: %s" % (self.url, self.error)


class BugTrackerAuthenticationError(BugTrackerConnectError):
    """Launchpad couldn't authenticate with the remote bugtracker."""


class BugWatchUpdateWarning(Exception):
    """An exception representing a warning.

    This is a flag exception for the benefit of the OOPS machinery.
    """

    def __init__(self, message, *args):
        # Require a message.
        Exception.__init__(self, message, *args)


class InvalidBugId(BugWatchUpdateWarning):
    """The bug id wasn't in the format the bug tracker expected.

    For example, Bugzilla and debbugs expect the bug id to be an
    integer.
    """


class BugNotFound(BugWatchUpdateWarning):
    """The bug was not found in the external bug tracker."""


class UnknownRemoteValueError(BugWatchUpdateWarning):
    """A matching Launchpad value could not be found for the remote value."""


class UnknownRemoteImportanceError(UnknownRemoteValueError):
    """The remote bug's importance isn't mapped to a `BugTaskImportance`."""
    field_name = 'importance'


class UnknownRemoteStatusError(UnknownRemoteValueError):
    """The remote bug's status isn't mapped to a `BugTaskStatus`."""
    field_name = 'status'


class PrivateRemoteBug(BugWatchUpdateWarning):
    """Raised when a bug is marked private on the remote bugtracker."""


class ExternalBugTracker:
    """Base class for an external bug tracker."""

    implements(IExternalBugTracker)

    batch_size = None
    batch_query_threshold = config.checkwatches.batch_query_threshold
    timeout = config.checkwatches.default_socket_timeout
    comment_template = 'default_remotecomment_template.txt'
    url_opener = None

    def __init__(self, baseurl):
        self.baseurl = baseurl.rstrip('/')
        self.basehost = urlparse(baseurl).netloc
        self.sync_comments = (
            config.checkwatches.sync_comments and (
                ISupportsCommentPushing.providedBy(self) or
                ISupportsCommentImport.providedBy(self) or
                ISupportsBackLinking.providedBy(self)))

    @ensure_no_transaction
    def urlopen(self, request, data=None):
        if self.url_opener:
            func = self.url_opener.open
        else:
            func = urllib2.urlopen
        return func(request, data, self.timeout)

    def getExternalBugTrackerToUse(self):
        """See `IExternalBugTracker`."""
        return self

    def getCurrentDBTime(self):
        """See `IExternalBugTracker`."""
        # Returning None means that we don't know that the time is,
        # which is a good default.
        return None

    def getModifiedRemoteBugs(self, bug_ids, last_accessed):
        """See `IExternalBugTracker`."""
        # Return all bugs, since we don't know which have been modified.
        return list(bug_ids)

    def initializeRemoteBugDB(self, bug_ids):
        """See `IExternalBugTracker`."""
        self.bugs = {}
        if len(bug_ids) > self.batch_query_threshold:
            self.bugs = self.getRemoteBugBatch(bug_ids)
        else:
            for bug_id in bug_ids:
                bug_id, remote_bug = self.getRemoteBug(bug_id)
                if bug_id is not None:
                    self.bugs[bug_id] = remote_bug

    def getRemoteBug(self, bug_id):
        """Retrieve and return a single bug from the remote database.

        The bug is returned as a tuple in the form (id, bug). This ensures
        that bug ids are formatted correctly for the current
        ExternalBugTracker. If no data can be found for bug_id, (None,
        None) will be returned.

        A BugTrackerConnectError will be raised if anything goes wrong.
        """
        raise NotImplementedError(self.getRemoteBug)

    def getRemoteBugBatch(self, bug_ids):
        """Retrieve and return a set of bugs from the remote database.

        A BugTrackerConnectError will be raised if anything goes wrong.
        """
        raise NotImplementedError(self.getRemoteBugBatch)

    def getRemoteImportance(self, bug_id):
        """Return the remote importance for the given bug id.

        Raise BugNotFound if the bug can't be found.
        Raise InvalidBugId if the bug id has an unexpected format.
        Raise UnparsableBugData if the bug data cannot be parsed.
        """
        # This method should be overridden by subclasses, so we raise a
        # NotImplementedError if this version of it gets called for some
        # reason.
        raise NotImplementedError(self.getRemoteImportance)

    def getRemoteStatus(self, bug_id):
        """Return the remote status for the given bug id.

        Raise BugNotFound if the bug can't be found.
        Raise InvalidBugId if the bug id has an unexpected format.
        """
        raise NotImplementedError(self.getRemoteStatus)

    def getRemoteProduct(self, remote_bug):
        """Return the remote product for a given bug.

        See `IExternalBugTracker`.
        """
        return None

    def _getHeaders(self):
        # For some reason, bugs.kde.org doesn't allow the regular urllib
        # user-agent string (Python-urllib/2.x) to access their bugzilla.
        return {'User-agent': LP_USER_AGENT, 'Host': self.basehost}

    def _fetchPage(self, page, data=None):
        """Fetch a page from the remote server.

        A BugTrackerConnectError will be raised if anything goes wrong.
        """
        if not isinstance(page, urllib2.Request):
            page = urllib2.Request(page, headers=self._getHeaders())
        try:
            return self.urlopen(page, data)
        except (urllib2.HTTPError, urllib2.URLError) as val:
            raise BugTrackerConnectError(self.baseurl, val)

    def _getPage(self, page):
        """GET the specified page on the remote HTTP server."""
        request = urllib2.Request(
            "%s/%s" % (self.baseurl, page), headers=self._getHeaders())
        return self._fetchPage(request).read()

    def _post(self, url, data):
        """Post to a given URL."""
        request = urllib2.Request(url, headers=self._getHeaders())
        return self._fetchPage(request, data=data)

    def _postPage(self, page, form, repost_on_redirect=False):
        """POST to the specified page and form.

        :param form: is a dict of form variables being POSTed.
        :param repost_on_redirect: override RFC-compliant redirect handling.
            By default, if the POST receives a redirect response, the
            request to the redirection's target URL will be a GET.  If
            `repost_on_redirect` is True, this method will do a second POST
            instead.  Do this only if you are sure that repeated POST to
            this page is safe, as is usually the case with search forms.
        """
        url = "%s/%s" % (self.baseurl, page)
        post_data = urllib.urlencode(form)
        response = self._post(url, data=post_data)

        if repost_on_redirect and response.url != url:
            response = self._post(response.url, data=post_data)

        return response.read()


class LookupBranch(treelookup.LookupBranch):
    """A lookup branch customised for documenting external bug trackers."""

    def _verify(self):
        """Check the validity of the branch.

        The branch result must be a member of `BugTaskStatus`, or
        another `LookupTree`.

        :raises TypeError: If the branch is invalid.
        """
        if (not isinstance(self.result, treelookup.LookupTree) and
            self.result not in BugTaskStatus):
            raise TypeError(
                'Result is not a member of BugTaskStatus: %r' % (
                    self.result))
        super(LookupBranch, self)._verify()

    def _describe_result(self, result):
        """See `treelookup.LookupBranch._describe_result`."""
        # `result` should be a member of `BugTaskStatus`.
        return result.title


class LookupTree(treelookup.LookupTree):
    """A lookup tree customised for documenting external bug trackers."""

    # See `treelookup.LookupTree`.
    _branch_factory = LookupBranch

    def moinmoin_table(self, titles=None):
        """Return lines of a MoinMoin table that documents self."""
        max_depth = self.max_depth

        def line(columns):
            return '|| %s ||' % ' || '.join(columns)

        if titles is not None:
            if len(titles) != (max_depth + 1):
                raise ValueError(
                    "Table of %d columns needs %d titles, but %d given." % (
                        (max_depth + 1), (max_depth + 1), len(titles)))
            yield line("'''%s'''" % (title) for title in titles)

        def diff(last, now):
            """Yields elements from `now` when different to those in `last`.

            When the elements are the same, this yields the empty
            string.

            Once a difference has been found, all subsequent elements
            in `now` are returned.

            This results in a good looking and readable mapping table;
            it gives a good balance between being explicit and
            avoiding repetition.
            """
            all = False
            for elem_last, elem_now in zip(last, now):
                if all:
                    yield elem_now
                elif elem_last == elem_now:
                    yield ''
                else:
                    # We found a difference. Force the return of all
                    # subsequent elements in `now`.
                    all = True
                    yield elem_now

        last_columns = None
        for elems in self.flatten():
            path, result = elems[:-1], elems[-1]
            columns = []
            for branch in path:
                if branch.is_default:
                    columns.append("* (''any'')")
                else:
                    columns.append(
                        " '''or''' ".join(str(key) for key in branch.keys))
            columns.extend(["- (''ignored'')"] * (max_depth - len(path)))
            columns.append(result.title)
            if last_columns is None:
                yield line(columns)
            else:
                yield line(list(diff(last_columns, columns)))
            last_columns = columns
