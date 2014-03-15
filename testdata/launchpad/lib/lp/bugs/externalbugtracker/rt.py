# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""RT ExternalBugTracker Utility."""

__metaclass__ = type
__all__ = ['RequestTracker']

import email
import urllib
import urllib2

from lp.bugs.externalbugtracker import (
    BugNotFound,
    BugTrackerConnectError,
    ExternalBugTracker,
    InvalidBugId,
    LookupTree,
    UnknownRemoteStatusError,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.externalbugtracker import UNKNOWN_REMOTE_IMPORTANCE
from lp.services.config import config
from lp.services.database.isolation import ensure_no_transaction
from lp.services.propertycache import cachedproperty
from lp.services.webapp.url import urlparse


class RequestTracker(ExternalBugTracker):
    """`ExternalBugTracker` subclass for handling RT imports."""

    ticket_url = 'REST/1.0/ticket/%s/show'
    batch_url = 'REST/1.0/search/ticket/'
    batch_query_threshold = 1

    @property
    def credentials(self):
        """Return the authentication credentials needed to log in.

        If there are specific credentials for the current RT instance,
        these will be returned. Otherwise the RT default guest
        credentials (username and password of 'guest') will be returned.
        """
        credentials_config = config['checkwatches.credentials']
        hostname = urlparse(self.baseurl)[1]
        try:
            username = credentials_config['%s.username' % hostname]
            password = credentials_config['%s.password' % hostname]
            return {'user': username, 'pass': password}
        except KeyError:
            return {'user': 'guest', 'pass': 'guest'}

    def _logIn(self, opener):
        """Attempt to log in to the remote RT service.

        :param opener: An instance of urllib2.OpenerDirector
            to be used to connect to the remote server.

        If HTTPError or URLErrors are encountered at any point in this
        process, they will be raised to be caught at the callsite.

        This method is separate from the _opener property so as to allow
        us to test the _opener property without having to connect to a
        remote server.
        """
        # To log in to an RT instance we must pass a username and
        # password to its login form, as a user would from the web.
        opener.open('%s/' % self.baseurl, urllib.urlencode(
            self.credentials))

    @cachedproperty
    def _opener(self):
        """Return a urllib2.OpenerDirector for the remote RT instance.

        An attempt will be made to log in to the remote instance before
        the opener is returned. If logging in is not successful a
        BugTrackerConnectError will be raised
        """
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())

        # Attempt to log in to the remote system. Raise an error if we
        # can't.
        try:
            self._logIn(opener)
        except (urllib2.HTTPError, urllib2.URLError) as error:
            raise BugTrackerConnectError('%s/' % self.baseurl,
                "Unable to authenticate with remote RT service: "
                "Could not submit login form: %s" % error)

        return opener

    @ensure_no_transaction
    def urlopen(self, request, data=None):
        """Return a handle to a remote resource.

        This method overrides that of `ExternalBugTracker` so that the
        custom URL opener for RequestTracker instances can be used.
        """
        # We create our own opener so as to handle the RT authentication
        # cookies that need to be passed around.
        return self._opener.open(request, data)

    def getRemoteBug(self, bug_id):
        """See `ExternalBugTracker`."""
        ticket_url = self.ticket_url % str(bug_id)
        query_url = '%s/%s' % (self.baseurl, ticket_url)
        try:
            bug_data = self.urlopen(query_url)
        except urllib2.HTTPError as error:
            raise BugTrackerConnectError(ticket_url, str(error))

        # We use the first line of the response to ensure that we've
        # made a successful request.
        firstline = bug_data.readline().strip().split(' ')
        if firstline[1] != '200':
            # If anything goes wrong we raise a BugTrackerConnectError.
            # We included in the error message the status code and error
            # message returned by the server.
            raise BugTrackerConnectError(
                query_url,
                "Unable to retrieve bug %s. The remote server returned the "
                "following error: %s." %
                (str(bug_id), " ".join(firstline[1:])))

        # RT's REST interface returns tickets in RFC822 format, so we
        # can use the email module to parse them.
        bug = email.message_from_string(bug_data.read().strip())
        if bug.get('id') is None:
            return None, None
        else:
            bug_id = bug['id'].replace('ticket/', '')
            return int(bug_id), bug

    def getRemoteBugBatch(self, bug_ids):
        """See `ExternalBugTracker`."""
        # We need to ensure that all the IDs are strings first.
        id_list = [str(id) for id in bug_ids]
        query = "id = " + "OR id = ".join(id_list)

        query_url = '%s/%s' % (self.baseurl, self.batch_url)
        request_params = {'query': query, 'format': 'l'}
        try:
            bug_data = self.urlopen(query_url, urllib.urlencode(
                request_params))
        except urllib2.HTTPError as error:
            raise BugTrackerConnectError(query_url, error.message)

        # We use the first line of the response to ensure that we've
        # made a successful request.
        firstline = bug_data.readline().strip().split(' ')
        if firstline[1] != '200':
            # If anything goes wrong we raise a BugTrackerConnectError.
            # We included in the error message the status code and error
            # message returned by the server.
            bug_id_string = ", ".join([str(bug_id) for bug_id in bug_ids])
            raise BugTrackerConnectError(
                query_url,
                "Unable to retrieve bugs %s. The remote server returned the "
                "following error:  %s." %
                (bug_id_string, " ".join(firstline[1:])))

        # Tickets returned in RT multiline format are separated by lines
        # containing only --\n.
        tickets = bug_data.read().split("--\n")
        bugs = {}
        for ticket in tickets:
            ticket = ticket.strip()

            # RT's REST interface returns tickets in RFC822 format, so we
            # can use the email module to parse them.
            bug = email.message_from_string(ticket)

            # We only bother adding the bug to the bugs dict if we
            # actually have some data worth adding.
            if bug.get('id') is not None:
                bug_id = bug['id'].replace('ticket/', '')
                bugs[int(bug_id)] = bug

        return bugs

    def getRemoteStatus(self, bug_id):
        """Return the remote status of a given bug.

        See `ExternalBugTracker`.
        """
        try:
            bug_id = int(bug_id)
        except ValueError:
            raise InvalidBugId(
                "RequestTracker bug ids must be integers (was passed %r)"
                % bug_id)

        if bug_id not in self.bugs:
            raise BugNotFound(bug_id)

        return self.bugs[bug_id]['status']

    def getRemoteImportance(self, bug_id):
        """See `IExternalBugTracker`."""
        return UNKNOWN_REMOTE_IMPORTANCE

    def convertRemoteImportance(self, remote_importance):
        """See `IExternalBugTracker`."""
        return BugTaskImportance.UNKNOWN

    _status_lookup_titles = 'RT status',
    _status_lookup = LookupTree(
        ('new', BugTaskStatus.NEW),
        ('open', BugTaskStatus.CONFIRMED),
        ('stalled', BugTaskStatus.CONFIRMED),
        ('rejected', BugTaskStatus.INVALID),
        ('resolved', BugTaskStatus.FIXRELEASED),
        )

    def convertRemoteStatus(self, remote_status):
        """Convert an RT status into a Launchpad BugTaskStatus."""
        try:
            return self._status_lookup.find(remote_status.lower())
        except KeyError:
            raise UnknownRemoteStatusError(remote_status)

    def getRemoteProduct(self, remote_bug):
        """Return the remote product for a remote bug.

        See `IExternalBugTracker`.
        """
        if remote_bug not in self.bugs:
            raise BugNotFound(remote_bug)

        return self.bugs[remote_bug].get('queue', None)
