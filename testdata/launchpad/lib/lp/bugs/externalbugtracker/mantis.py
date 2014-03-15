# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mantis ExternalBugTracker utility."""

__metaclass__ = type
__all__ = ['Mantis', 'MantisLoginHandler']

import cgi
import csv
import logging
import urllib
import urllib2
from urlparse import urlunparse

from BeautifulSoup import (
    BeautifulSoup,
    Comment,
    SoupStrainer,
    )

from lp.bugs.externalbugtracker import (
    BugNotFound,
    BugTrackerConnectError,
    BugWatchUpdateError,
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
from lp.services.propertycache import cachedproperty
from lp.services.webapp.url import urlparse


class MantisLoginHandler(urllib2.HTTPRedirectHandler):
    """Handler for urllib2.build_opener to automatically log-in
    to Mantis anonymously if needed.

    The ALSA bug tracker is the only tested Mantis installation that
    actually needs this. For ALSA bugs, the dance is like so:

      1. We request bug 3301 ('jack sensing problem'):
           https://bugtrack.alsa-project.org/alsa-bug/view.php?id=3301

      2. Mantis redirects us to:
           .../alsa-bug/login_page.php?
                 return=%2Falsa-bug%2Fview.php%3Fid%3D3301

      3. We notice this, rewrite the query, and skip to login.php:
           .../alsa-bug/login.php?
                 return=%2Falsa-bug%2Fview.php%3Fid%3D3301&
                 username=guest&password=guest

      4. Mantis accepts our credentials then redirects us to the bug
         view page via a cookie test page (login_cookie_test.php)
    """

    def rewrite_url(self, url):
        scheme, host, path, params, query, fragment = urlparse(url)

        # If we can, skip the login page and submit credentials
        # directly. The query should contain a 'return' parameter
        # which, if our credentials are accepted, means we'll be
        # redirected back from whence we came. In other words, we'll
        # end up back at the bug page we first requested.
        login_page = '/login_page.php'
        if path.endswith(login_page):
            path = path[:-len(login_page)] + '/login.php'
            query = cgi.parse_qs(query, True)
            query['username'] = query['password'] = ['guest']
            if 'return' not in query:
                raise BugTrackerConnectError(
                    url, ("Mantis redirected us to the login page "
                          "but did not set a return path."))

            query = urllib.urlencode(query, True)
            url = urlunparse(
                (scheme, host, path, params, query, fragment))

        # Previous versions of the Mantis external bug tracker fetched
        # login_anon.php in addition to the login.php method above, but none
        # of the Mantis installations tested actually needed this. For
        # example, the ALSA bugtracker actually issues an error "Your account
        # may be disabled" when accessing this page. For now it's better to
        # *not* try this page because we may end up annoying admins with
        # spurious login attempts.

        return url

    def redirect_request(self, request, fp, code, msg, hdrs, new_url):
        return urllib2.HTTPRedirectHandler.redirect_request(
            self, request, fp, code, msg, hdrs, self.rewrite_url(new_url))


class MantisBugBatchParser:
    """A class that parses the batch of bug data.

    Using the CSV reader is pretty much essential since the data that comes
    back can include title text which can in turn contain field separators.
    You don't want to handle the unquoting yourself.
    """

    def __init__(self, csv_data, logger):
        # Clean out stray, unquoted newlines inside csv_data to avoid the CSV
        # module blowing up.  IDEA: perhaps if the size of csv_data is large
        # in the future, this could be moved into a generator.
        csv_data = [s.replace("\r", "") for s in csv_data]
        csv_data = [s.replace("\n", "") for s in csv_data]
        self.reader = csv.reader(csv_data)
        self.logger = logger

    def processCSVBugLine(self, bug_line, headers):
        """Processes a single line of the CSV."""
        bug = {}
        for index, header in enumerate(headers):
            try:
                data = bug_line[index]
            except IndexError:
                self.logger.warning("Line %r incomplete." % bug_line)
                return None
            bug[header] = data
        try:
            bug['id'] = int(bug['id'])
        except ValueError:
            self.logger.warning("Encountered invalid bug ID: %r." % bug['id'])
            return None
        return bug

    def parseHeaderLine(self, reader):
        # The first line of the CSV file is the header. We need to read
        # it because different Mantis instances have different header
        # ordering and even different columns in the export.
        try:
            headers = [h.lower() for h in reader.next()]
        except StopIteration:
            raise UnparsableBugData("Missing header line")
        missing_headers = [
            name for name in ('id', 'status', 'resolution')
            if name not in headers]
        if missing_headers:
            raise UnparsableBugData(
                "CSV header %r missing fields: %r" % (
                    headers, missing_headers))
        return headers

    def getBugs(self):
        headers = self.parseHeaderLine(self.reader)
        bugs = {}
        try:
            for bug_line in self.reader:
                bug = self.processCSVBugLine(bug_line, headers)
                if bug is not None:
                    bugs[bug['id']] = bug
            return bugs
        except csv.Error as error:
            raise UnparsableBugData("Exception parsing CSV file: %s." % error)


class Mantis(ExternalBugTracker):
    """An `ExternalBugTracker` for dealing with Mantis instances.

    For a list of tested Mantis instances and their behaviour when
    exported from, see:

        https://dev.launchpad.net/Bugs/ExternalBugTrackers/Mantis
    """

    def __init__(self, baseurl):
        super(Mantis, self).__init__(baseurl)
        # Custom cookie aware opener that automatically sends anonymous
        # credentials to Mantis if (and only if) needed.
        self._cookie_handler = urllib2.HTTPCookieProcessor()
        self.url_opener = urllib2.build_opener(
            self._cookie_handler, MantisLoginHandler())
        self._logger = logging.getLogger()

    @cachedproperty
    def csv_data(self):
        """Attempt to retrieve a CSV export from the remote server.

        If the export fails (i.e. the response is 0-length), None will
        be returned.
        """
        return self._csv_data()

    def _csv_data(self):
        """See `csv_data()."""
        # Next step is getting our query filter cookie set up; we need
        # to do this weird submit in order to get the closed bugs
        # included in the results; the default Mantis filter excludes
        # them. It's unlikely that all these parameters are actually
        # necessary, but it's easy to prepare the complete set from a
        # view_all_bugs.php form dump so let's keep it complete.
        data = {
           'type': '1',
           'page_number': '1',
           'view_type': 'simple',
           'reporter_id[]': '0',
           'user_monitor[]': '0',
           'handler_id[]': '0',
           'show_category[]': '0',
           'show_severity[]': '0',
           'show_resolution[]': '0',
           'show_profile[]': '0',
           'show_status[]': '0',
           # Some of the more modern Mantis trackers use
           # a value of 'hide_status[]': '-2' here but it appears that
           # [none] works. Oops, older Mantis uses 'none' here. Gross!
           'hide_status[]': '[none]',
           'show_build[]': '0',
           'show_version[]': '0',
           'fixed_in_version[]': '0',
           'show_priority[]': '0',
           'per_page': '50',
           'view_state': '0',
           'sticky_issues': 'on',
           'highlight_changed': '6',
           'relationship_type': '-1',
           'relationship_bug': '0',
           # Hack around the fact that the sorting parameter has
           # changed over time.
           'sort': 'last_updated',
           'sort_0': 'last_updated',
           'dir': 'DESC',
           'dir_0': 'DESC',
           'search': '',
           'filter': 'Apply Filter',
        }
        try:
            self._postPage("view_all_set.php?f=3", data)
        except BugTrackerConnectError:
            return None

        # Finally grab the full CSV export, which uses the
        # MANTIS_VIEW_ALL_COOKIE set in the previous step to specify
        # what's being viewed.
        try:
            csv_data = self._getPage("csv_export.php")
        except BugTrackerConnectError as value:
            # Some Mantis installations simply return a 500 error
            # when the csv_export.php page is accessed. Since the
            # bug data may be nevertheless available from ordinary
            # web pages, we simply ignore this error.
            if value.error.startswith('HTTP Error 500'):
                return None
            raise

        if not csv_data:
            return None
        else:
            return csv_data

    def canUseCSVExports(self):
        """Return True if a Mantis instance supports CSV exports.

        If the Mantis instance cannot or does not support CSV exports,
        False will be returned.
        """
        return self.csv_data is not None

    def initializeRemoteBugDB(self, bug_ids):
        """See `ExternalBugTracker`.

        This method is overridden so that it can take into account the
        fact that not all Mantis instances support CSV exports. In
        those cases all bugs will be imported individually, regardless
        of how many there are.
        """
        self.bugs = {}

        if (len(bug_ids) > self.batch_query_threshold and
            self.canUseCSVExports()):
            # We only query for batches of bugs if the remote Mantis
            # instance supports CSV exports, otherwise we default to
            # screen-scraping on a per bug basis regardless of how many bugs
            # there are to retrieve.
            self.bugs = self.getRemoteBugBatch(bug_ids)
        else:
            for bug_id in bug_ids:
                bug_id, remote_bug = self.getRemoteBug(bug_id)

                if bug_id is not None:
                    self.bugs[bug_id] = remote_bug

    def getRemoteBug(self, bug_id):
        """See `ExternalBugTracker`."""
        # Only parse tables to save time and memory. If we didn't have
        # to check for application errors in the page (using
        # _checkForApplicationError) then we could be much more
        # specific than this.
        bug_page = BeautifulSoup(
            self._getPage('view.php?id=%s' % bug_id),
            convertEntities=BeautifulSoup.HTML_ENTITIES,
            parseOnlyThese=SoupStrainer('table'))

        app_error = self._checkForApplicationError(bug_page)
        if app_error:
            app_error_code, app_error_message = app_error
            # 1100 is ERROR_BUG_NOT_FOUND in Mantis (see
            # mantisbt/core/constant_inc.php).
            if app_error_code == '1100':
                return None, None
            else:
                raise BugWatchUpdateError(
                    "Mantis APPLICATION ERROR #%s: %s" % (
                    app_error_code, app_error_message))

        bug = {
            'id': bug_id,
            'status': self._findValueRightOfKey(bug_page, 'Status'),
            'resolution': self._findValueRightOfKey(bug_page, 'Resolution')}

        return int(bug_id), bug

    def getRemoteBugBatch(self, bug_ids):
        """See `ExternalBugTracker`."""
        # XXX: Gavin Panella 2007-09-06 bug=137780:
        # You may find this zero in "\r\n0" funny. Well I don't. This is
        # to work around the fact that Mantis' CSV export doesn't cope
        # with the fact that the bug summary can contain embedded "\r\n"
        # characters! I don't see a better way to handle this short of
        # not using the CSV module and forcing all lines to have the
        # same number as fields as the header.
        csv_data = self.csv_data.strip().split("\r\n0")

        if not csv_data:
            raise UnparsableBugData("Empty CSV for %s" % self.baseurl)

        parser = MantisBugBatchParser(csv_data, self._logger)
        return parser.getBugs()

    def _checkForApplicationError(self, page_soup):
        """If Mantis does not find the bug it still returns a 200 OK
        response, so we need to look into the page to figure it out.

        If there is no error, None is returned.

        If there is an error, a 2-tuple of (code, message) is
        returned, both unicode strings.
        """
        app_error = page_soup.find(
            text=lambda node: (node.startswith('APPLICATION ERROR ')
                               and node.parent['class'] == 'form-title'
                               and not isinstance(node, Comment)))
        if app_error:
            app_error_code = ''.join(c for c in app_error if c.isdigit())
            app_error_message = app_error.findNext('p')
            if app_error_message is not None:
                app_error_message = app_error_message.string
            return app_error_code, app_error_message

        return None

    def _findValueRightOfKey(self, page_soup, key):
        """Scrape a value from a Mantis bug view page where the value
        is displayed to the right of the key.

        The Mantis bug view page uses HTML tables for both layout and
        representing tabular data, often within the same table. This
        method assumes that the key and value are on the same row,
        adjacent to one another, with the key preceding the value:

        ...
        <td>Key</td>
        <td>Value</td>
        ...

        This method does not compensate for colspan or rowspan.
        """
        key_node = page_soup.find(
            text=lambda node: (node.strip() == key
                               and not isinstance(node, Comment)))
        if key_node is None:
            raise UnparsableBugData("Key %r not found." % (key,))

        value_cell = key_node.findNext('td')
        if value_cell is None:
            raise UnparsableBugData(
                "Value cell for key %r not found." % (key,))

        value_node = value_cell.string
        if value_node is None:
            raise UnparsableBugData("Value for key %r not found." % (key,))

        return value_node.strip()

    def _findValueBelowKey(self, page_soup, key):
        """Scrape a value from a Mantis bug view page where the value
        is displayed directly below the key.

        The Mantis bug view page uses HTML tables for both layout and
        representing tabular data, often within the same table. This
        method assumes that the key and value are within the same
        column on adjacent rows, with the key preceding the value:

        ...
        <tr>...<td>Key</td>...</tr>
        <tr>...<td>Value</td>...</tr>
        ...

        This method does not compensate for colspan or rowspan.
        """
        key_node = page_soup.find(
            text=lambda node: (node.strip() == key
                               and not isinstance(node, Comment)))
        if key_node is None:
            raise UnparsableBugData("Key %r not found." % (key,))

        key_cell = key_node.parent
        if key_cell is None:
            raise UnparsableBugData("Cell for key %r not found." % (key,))

        key_row = key_cell.parent
        if key_row is None:
            raise UnparsableBugData("Row for key %r not found." % (key,))

        try:
            key_pos = key_row.findAll('td').index(key_cell)
        except ValueError:
            raise UnparsableBugData(
                "Key cell in row for key %r not found." % (key,))

        value_row = key_row.findNextSibling('tr')
        if value_row is None:
            raise UnparsableBugData(
                "Value row for key %r not found." % (key,))

        value_cell = value_row.findAll('td')[key_pos]
        if value_cell is None:
            raise UnparsableBugData(
                "Value cell for key %r not found." % (key,))

        value_node = value_cell.string
        if value_node is None:
            raise UnparsableBugData("Value for key %r not found." % (key,))

        return value_node.strip()

    def getRemoteImportance(self, bug_id):
        """See `ExternalBugTracker`.

        This method is implemented here as a stub to ensure that
        existing functionality is preserved. As a result,
        UNKNOWN_REMOTE_IMPORTANCE will always be returned.
        """
        return UNKNOWN_REMOTE_IMPORTANCE

    def getRemoteStatus(self, bug_id):
        if not bug_id.isdigit():
            raise InvalidBugId(
                "Mantis (%s) bug number not an integer: %s" % (
                    self.baseurl, bug_id))

        try:
            bug = self.bugs[int(bug_id)]
        except KeyError:
            raise BugNotFound(bug_id)

        # Use a colon and a space to join status and resolution because
        # there is a chance that statuses contain spaces, and because
        # it makes display of the data nicer.
        return "%(status)s: %(resolution)s" % bug

    def convertRemoteImportance(self, remote_importance):
        """See `ExternalBugTracker`.

        This method is implemented here as a stub to ensure that
        existing functionality is preserved. As a result,
        BugTaskImportance.UNKNOWN will always be returned.
        """
        return BugTaskImportance.UNKNOWN

    _status_lookup_titles = 'Mantis status', 'Mantis resolution'
    _status_lookup = (
        LookupTree(
            ('assigned', BugTaskStatus.INPROGRESS),
            ('feedback', BugTaskStatus.INCOMPLETE),
            ('new', BugTaskStatus.NEW),
            ('confirmed', 'ackowledged', BugTaskStatus.CONFIRMED),
            ('resolved', 'closed',
                LookupTree(
                    ('reopened', BugTaskStatus.NEW),
                    ('fixed', 'open', 'no change required',
                     BugTaskStatus.FIXRELEASED),
                    ('unable to reproduce', 'not fixable', 'suspended',
                     'duplicate', BugTaskStatus.INVALID),
                    ("won't fix", BugTaskStatus.WONTFIX))),
            )
        )

    def convertRemoteStatus(self, status_and_resolution):
        status, importance = status_and_resolution.split(": ", 1)
        try:
            return self._status_lookup.find(status, importance)
        except KeyError:
            raise UnknownRemoteStatusError(status_and_resolution)
