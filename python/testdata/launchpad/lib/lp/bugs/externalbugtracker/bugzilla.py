# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bugzilla ExternalBugTracker utility."""

__metaclass__ = type
__all__ = [
    'Bugzilla',
    'BugzillaAPI',
    'BugzillaLPPlugin',
    'needs_authentication',
    ]

from email.Utils import parseaddr
from httplib import BadStatusLine
import re
import string
from urllib2 import URLError
from xml.dom import minidom
import xml.parsers.expat
import xmlrpclib

import pytz
from zope.component import getUtility
from zope.interface import implements

from lp.bugs.externalbugtracker.base import (
    BugNotFound,
    BugTrackerAuthenticationError,
    BugTrackerConnectError,
    ExternalBugTracker,
    InvalidBugId,
    LookupTree,
    UnknownRemoteImportanceError,
    UnknownRemoteStatusError,
    UnparsableBugData,
    UnparsableBugTrackerVersion,
    )
from lp.bugs.externalbugtracker.xmlrpc import UrlLib2Transport
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.externalbugtracker import (
    ISupportsBackLinking,
    ISupportsCommentImport,
    ISupportsCommentPushing,
    UNKNOWN_REMOTE_IMPORTANCE,
    )
from lp.services import encoding
from lp.services.config import config
from lp.services.database.isolation import ensure_no_transaction
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.url import (
    urlappend,
    urlparse,
    )


class Bugzilla(ExternalBugTracker):
    """An ExternalBugTrack for dealing with remote Bugzilla systems."""

    batch_query_threshold = 0  # Always use the batch method.
    _test_xmlrpc_proxy = None

    def __init__(self, baseurl, version=None):
        super(Bugzilla, self).__init__(baseurl)
        self.version = self._parseVersion(version)
        self.is_issuezilla = False
        self.remote_bug_status = {}
        self.remote_bug_importance = {}
        self.remote_bug_product = {}

    @ensure_no_transaction
    def _remoteSystemHasBugzillaAPI(self):
        """Return True if the remote host offers the Bugzilla API.

        :return: True if the remote host offers an XML-RPC API and its
            version is > 3.4. Return False otherwise.
        """
        api = BugzillaAPI(self.baseurl)
        if self._test_xmlrpc_proxy is not None:
            proxy = self._test_xmlrpc_proxy
        else:
            proxy = api.xmlrpc_proxy

        try:
            # We try calling Bugzilla.version() on the remote
            # server because it's the most lightweight method there is.
            remote_version = proxy.Bugzilla.version()
        except xmlrpclib.Fault as fault:
            # 'Client' is a hangover. Either Bugzilla or the Perl
            # XML-RPC lib in use returned it as faultCode. It's wrong,
            # but it's known wrongness, so we recognize it here.
            if fault.faultCode in (xmlrpclib.METHOD_NOT_FOUND, 'Client'):
                return False
            else:
                raise
        except xmlrpclib.ProtocolError as error:
            # We catch 404s, which occur when xmlrpc.cgi doesn't exist
            # on the remote server, and 500s, which sometimes occur when
            # an invalid request is made to the remote server. We allow
            # any other error types to propagate upward.
            if error.errcode in (404, 500):
                return False
            else:
                raise
        except (xmlrpclib.ResponseError, xml.parsers.expat.ExpatError):
            # The server returned an unparsable response.
            return False
        else:
            # Older versions of the Bugzilla API return tuples. We
            # consider anything other than a mapping to be unsupported.
            if isinstance(remote_version, dict):
                if remote_version['version'] >= '3.4':
                    return True
            return False

    @ensure_no_transaction
    def _remoteSystemHasPluginAPI(self):
        """Return True if the remote host has the Launchpad plugin installed.
        """
        plugin = BugzillaLPPlugin(self.baseurl)
        if self._test_xmlrpc_proxy is not None:
            proxy = self._test_xmlrpc_proxy
        else:
            proxy = plugin.xmlrpc_proxy

        try:
            # We try calling Launchpad.plugin_version() on the remote
            # server because it's the most lightweight method there is.
            proxy.Launchpad.plugin_version()
        except xmlrpclib.Fault as fault:
            # 'Client' is a hangover. Either Bugzilla or the Perl
            # XML-RPC lib in use returned it as faultCode. It's wrong,
            # but it's known wrongness, so we recognize it here.
            if fault.faultCode in (xmlrpclib.METHOD_NOT_FOUND, 'Client'):
                return False
            else:
                raise
        except xmlrpclib.ProtocolError as error:
            # We catch 404s, which occur when xmlrpc.cgi doesn't exist
            # on the remote server, and 500s, which sometimes occur when
            # the Launchpad Plugin isn't installed. Everything else we
            # can consider to be a problem, so we let it travel up the
            # stack for the error log.
            if error.errcode in (404, 500):
                return False
            else:
                raise
        except (xmlrpclib.ResponseError, xml.parsers.expat.ExpatError):
            # The server returned an unparsable response.
            return False
        else:
            return True

    def getExternalBugTrackerToUse(self):
        """Return the correct `Bugzilla` subclass for the current bugtracker.

        See `IExternalBugTracker`.
        """
        # checkwatches isn't set up to handle errors here, so we supress
        # known connection issues. They'll be handled and logged later on when
        # further requests are attempted.
        try:
            if self._remoteSystemHasPluginAPI():
                return BugzillaLPPlugin(self.baseurl)
            elif self._remoteSystemHasBugzillaAPI():
                return BugzillaAPI(self.baseurl)
        except (xmlrpclib.ProtocolError, URLError, BadStatusLine):
            pass
        return self

    def _parseDOMString(self, contents):
        """Return a minidom instance representing the XML contents supplied"""
        # Some Bugzilla sites will return pages with content that has
        # broken encoding. It's unfortunate but we need to guess the
        # encoding that page is in, and then encode() it into the utf-8
        # that minidom requires.
        contents = encoding.guess(contents).encode("utf-8")
        # Since the string is utf-8 encoded and utf-8 encoded string have the
        # high bit set for non-ASCII characters, we can now strip out any
        # ASCII control characters without touching encoded Unicode
        # characters.
        bad_chars = ''.join(chr(i) for i in range(0, 32))
        for char in '\n\r\t':
            bad_chars = bad_chars.replace(char, '')
        trans_map = string.maketrans(bad_chars, ' ' * len(bad_chars))
        contents = contents.translate(trans_map)
        return minidom.parseString(contents)

    def _probe_version(self):
        """Retrieve and return a remote bugzilla version.

        If the version cannot be parsed from the remote server
        `UnparsableBugTrackerVersion` will be raised. If the remote
        server cannot be reached `BugTrackerConnectError` will be
        raised.
        """
        version_xml = self._getPage('xml.cgi?id=1')
        try:
            document = self._parseDOMString(version_xml)
        except xml.parsers.expat.ExpatError as e:
            raise BugTrackerConnectError(self.baseurl,
                "Failed to parse output when probing for version: %s" % e)
        bugzilla = document.getElementsByTagName("bugzilla")
        if not bugzilla:
            # Welcome to Disneyland. The Issuezilla tracker replaces
            # "bugzilla" with "issuezilla".
            bugzilla = document.getElementsByTagName("issuezilla")
            if bugzilla:
                self.is_issuezilla = True
            else:
                raise UnparsableBugTrackerVersion(
                    'Failed to parse version from xml.cgi for %s: could '
                    'not find top-level bugzilla element'
                    % self.baseurl)
        version = bugzilla[0].getAttribute("version")
        return self._parseVersion(version)

    def _parseVersion(self, version):
        """Return a Bugzilla version parsed into a tuple.

        A typical tuple will be in the form (major_version,
        minor_version), so the version string '2.15' would be returned
        as (2, 15).

        If the passed version is None, None will be returned.
        If the version cannot be parsed `UnparsableBugTrackerVersion`
        will be raised.
        """
        if version is None:
            return None

        version_numbers = re.findall('[0-9]+', version)
        if len(version_numbers) == 0:
            raise UnparsableBugTrackerVersion(
                'Failed to parse version %r for %s' %
                (version, self.baseurl))

        return tuple(int(number) for number in version_numbers)

    _importance_lookup = {
        'blocker': BugTaskImportance.CRITICAL,
        'critical': BugTaskImportance.CRITICAL,
        'immediate': BugTaskImportance.CRITICAL,
        'urgent': BugTaskImportance.CRITICAL,
        'p5': BugTaskImportance.CRITICAL,
        'crash': BugTaskImportance.HIGH,
        'grave': BugTaskImportance.HIGH,
        'major': BugTaskImportance.HIGH,
        'high': BugTaskImportance.HIGH,
        'p4': BugTaskImportance.HIGH,
        'nor': BugTaskImportance.MEDIUM,
        'normal': BugTaskImportance.MEDIUM,
        'medium': BugTaskImportance.MEDIUM,
        'p3': BugTaskImportance.MEDIUM,
        'minor': BugTaskImportance.LOW,
        'low': BugTaskImportance.LOW,
        'trivial': BugTaskImportance.LOW,
        'p2': BugTaskImportance.LOW,
        'p1': BugTaskImportance.LOW,
        'enhancement': BugTaskImportance.WISHLIST,
        'wishlist': BugTaskImportance.WISHLIST,
        }

    def convertRemoteImportance(self, remote_importance):
        """See `ExternalBugTracker`."""
        words = remote_importance.lower().split()
        try:
            return self._importance_lookup[words.pop()]
        except KeyError:
            raise UnknownRemoteImportanceError(remote_importance)
        except IndexError:
            return BugTaskImportance.UNKNOWN

        return BugTaskImportance.UNKNOWN

    _status_lookup_titles = 'Bugzilla status', 'Bugzilla resolution'
    _status_lookup = LookupTree(
        ('ASSIGNED', 'ON_DEV', 'FAILS_QA', 'STARTED',
         BugTaskStatus.INPROGRESS),
        ('NEEDINFO', 'NEEDINFO_REPORTER', 'NEEDSINFO', 'WAITING', 'SUSPENDED',
         'PLEASETEST',
         BugTaskStatus.INCOMPLETE),
        ('PENDINGUPLOAD', 'MODIFIED', 'RELEASE_PENDING', 'ON_QA',
         BugTaskStatus.FIXCOMMITTED),
        ('REJECTED', BugTaskStatus.INVALID),
        ('RESOLVED', 'VERIFIED', 'CLOSED',
            LookupTree(
                ('CODE_FIX', 'CURRENTRELEASE', 'ERRATA', 'NEXTRELEASE',
                 'PATCH_ALREADY_AVAILABLE', 'FIXED', 'RAWHIDE',
                 'DOCUMENTED',
                 BugTaskStatus.FIXRELEASED),
                ('WONTFIX', 'WILL_NOT_FIX', 'NOTOURBUG', 'UPSTREAM',
                 BugTaskStatus.WONTFIX),
                ('OBSOLETE', 'INSUFFICIENT_DATA', 'INCOMPLETE', 'EXPIRED',
                 BugTaskStatus.EXPIRED),
                ('INVALID', 'WORKSFORME', 'NOTABUG', 'CANTFIX',
                 'UNREPRODUCIBLE', 'DUPLICATE',
                 BugTaskStatus.INVALID))),
        ('REOPENED', 'NEW', 'UPSTREAM', 'DEFERRED',
         BugTaskStatus.CONFIRMED),
        ('UNCONFIRMED', BugTaskStatus.NEW),
        )

    def convertRemoteStatus(self, remote_status):
        """See `IExternalBugTracker`.

        Bugzilla status consist of two parts separated by space, where
        the last part is the resolution. The resolution is optional.
        """
        try:
            return self._status_lookup.find(*remote_status.split())
        except KeyError:
            raise UnknownRemoteStatusError(remote_status)

    def initializeRemoteBugDB(self, bug_ids):
        """See `ExternalBugTracker`.

        This method is overridden so that Bugzilla version issues can be
        accounted for.
        """
        if self.version is None:
            self.version = self._probe_version()

        super(Bugzilla, self).initializeRemoteBugDB(bug_ids)

    def getRemoteBug(self, bug_id):
        """See `ExternalBugTracker`."""
        return (bug_id, self.getRemoteBugBatch([bug_id]))

    def _checkBugSearchResult(self, document):
        """Does `document` appear to be a bug search result page?

        :param document: An `xml.dom.Document` built from a bug search result
            on the bugzilla instance.
        :raise UnparsableBugData: If `document` does not appear to be a bug
            search result.
        """
        root = document.documentElement
        if root.tagName == 'html':
            raise UnparsableBugData(
                "Bug search on %s returned a <%s> instead of an RDF page." % (
                    self.baseurl, root.tagName))

    def getRemoteBugBatch(self, bug_ids):
        """See `ExternalBugTracker`."""
        # XXX: GavinPanella 2007-10-25 bug=153532: The modification of
        # self.remote_bug_status later on is a side-effect that should
        # really not be in this method, but for the fact that
        # getRemoteStatus needs it at other times. Perhaps
        # getRemoteBug and getRemoteBugBatch could return RemoteBug
        # objects which have status properties that would replace
        # getRemoteStatus.
        if self.is_issuezilla:
            buglist_page = 'xml.cgi'
            data = {
                'download_type': 'browser',
                'output_configured': 'true',
                'include_attachments': 'false',
                'include_dtd': 'true',
                'id': ','.join(bug_ids),
                }
            bug_tag = 'issue'
            id_tag = 'issue_id'
            status_tag = 'issue_status'
            resolution_tag = 'resolution'
            priority_tag = 'priority'
            severity_tag = None
        elif self.version < (2, 16):
            buglist_page = 'xml.cgi'
            data = {'id': ','.join(bug_ids)}
            bug_tag = 'bug'
            id_tag = 'bug_id'
            status_tag = 'bug_status'
            resolution_tag = 'resolution'
            priority_tag = 'priority'
            severity_tag = 'bug_severity'
        else:
            buglist_page = 'buglist.cgi'
            data = {
                'form_name': 'buglist.cgi',
                'columnlist':
                    ('id,product,bug_status,resolution,'
                     'priority,bug_severity'),
                'bug_id': ','.join(bug_ids),
                }
            if self.version < (2, 17, 1):
                data['format'] = 'rdf'
            else:
                data['ctype'] = 'rdf'
            if self.version >= (3, 6, 0):
                data['bugidtype'] = 'include'
            else:
                data['bug_id_type'] = 'include'
            bug_tag = 'bz:bug'
            id_tag = 'bz:id'
            status_tag = 'bz:bug_status'
            resolution_tag = 'bz:resolution'
            priority_tag = 'bz:priority'
            severity_tag = 'bz:bug_severity'

        buglist_xml = self._postPage(
            buglist_page, data, repost_on_redirect=True)

        try:
            document = self._parseDOMString(buglist_xml)
        except xml.parsers.expat.ExpatError as e:
            raise UnparsableBugData(
                "Failed to parse XML description for %s bugs %s: %s"
                % (self.baseurl, bug_ids, e))
        self._checkBugSearchResult(document)

        bug_nodes = document.getElementsByTagName(bug_tag)
        for bug_node in bug_nodes:
            # We use manual iteration to pick up id_tags instead of
            # getElementsByTagName because the latter does a recursive
            # search, and in some documents we've found the id_tag to
            # appear under other elements (such as "has_duplicates") in
            # the document hierarchy.
            bug_id_nodes = [node for node in bug_node.childNodes if
                            node.nodeName == id_tag]
            if not bug_id_nodes:
                # Something in the output is really weird; this will
                # show up as a bug not found, but we can catch that
                # later in the error logs.
                continue
            bug_id_node = bug_id_nodes[0]
            assert len(bug_id_node.childNodes) == 1, (
                "id node should contain a non-empty text string.")
            bug_id = str(bug_id_node.childNodes[0].data)
            # This assertion comes in late so we can at least tell what
            # bug caused this crash.
            assert len(bug_id_nodes) == 1, ("Should be only one id node, "
                "but %s had %s." % (bug_id, len(bug_id_nodes)))

            status_nodes = bug_node.getElementsByTagName(status_tag)
            if not status_nodes:
                # Older versions of bugzilla used bz:status; this was
                # later changed to bz:bug_status. For robustness, and
                # because there is practically no risk of reading wrong
                # data here, just try the older format as well.
                status_nodes = bug_node.getElementsByTagName("bz:status")
            assert len(status_nodes) == 1, ("Couldn't find a status "
                                            "node for bug %s." % bug_id)
            bug_status_node = status_nodes[0]
            assert len(bug_status_node.childNodes) == 1, (
                "status node for bug %s should contain a non-empty "
                "text string." % bug_id)
            status = bug_status_node.childNodes[0].data

            resolution_nodes = bug_node.getElementsByTagName(resolution_tag)
            assert len(resolution_nodes) <= 1, (
                "Should be only one resolution node for bug %s." % bug_id)
            if resolution_nodes:
                assert len(resolution_nodes[0].childNodes) <= 1, (
                    "Resolution for bug %s should just contain "
                    "a string." % bug_id)
                if resolution_nodes[0].childNodes:
                    resolution = resolution_nodes[0].childNodes[0].data
                    status += ' %s' % resolution
            self.remote_bug_status[bug_id] = status

            # Priority (for Importance)
            priority = ''
            priority_nodes = bug_node.getElementsByTagName(priority_tag)
            assert len(priority_nodes) <= 1, (
                "Should only be one priority node for bug %s" % bug_id)
            if priority_nodes:
                bug_priority_node = priority_nodes[0]
                assert len(bug_priority_node.childNodes) == 1, (
                    "priority node for bug %s should contain a non-empty "
                    "text string." % bug_id)
                priority = bug_priority_node.childNodes[0].data

            # Severity (for Importance)
            if severity_tag:
                severity_nodes = bug_node.getElementsByTagName(severity_tag)
                assert len(severity_nodes) <= 1, (
                    "Should only be one severity node for bug %s." % bug_id)
                if severity_nodes:
                    assert len(severity_nodes[0].childNodes) <= 1, (
                        "Severity for bug %s should just contain "
                        "a string." % bug_id)
                    if severity_nodes[0].childNodes:
                        severity = severity_nodes[0].childNodes[0].data
                        priority += ' %s' % severity
            self.remote_bug_importance[bug_id] = priority

            # Product
            product_nodes = bug_node.getElementsByTagName('bz:product')
            assert len(product_nodes) <= 1, (
                "Should be at most one product node for bug %s." % bug_id)
            if len(product_nodes) == 0:
                self.remote_bug_product[bug_id] = None
            else:
                product_node = product_nodes[0]
                self.remote_bug_product[bug_id] = (
                    product_node.childNodes[0].data)

    def getRemoteImportance(self, bug_id):
        """See `ExternalBugTracker`."""
        try:
            if bug_id not in self.remote_bug_importance:
                return "Bug %s is not in remote_bug_importance" % bug_id
            return self.remote_bug_importance[bug_id]
        except:
            return UNKNOWN_REMOTE_IMPORTANCE

    def getRemoteStatus(self, bug_id):
        """See ExternalBugTracker."""
        if not bug_id.isdigit():
            raise InvalidBugId(
                "Bugzilla (%s) bug number not an integer: %s" % (
                    self.baseurl, bug_id))
        try:
            return self.remote_bug_status[bug_id]
        except KeyError:
            raise BugNotFound(bug_id)

    def getRemoteProduct(self, remote_bug):
        """See `IExternalBugTracker`."""
        if remote_bug not in self.remote_bug_product:
            raise BugNotFound(remote_bug)
        return self.remote_bug_product[remote_bug]


def needs_authentication(func):
    """Decorator for automatically authenticating if needed.

    If an `xmlrpclib.Fault` with error code 410 is raised by the
    function, we'll try to authenticate and call the function again.
    """

    def decorator(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except xmlrpclib.Fault as fault:
            # Catch authentication errors only.
            if fault.faultCode != 410:
                raise

            self._authenticate()
            return func(self, *args, **kwargs)
    return decorator


class BugzillaAPI(Bugzilla):
    """An `ExternalBugTracker` to handle Bugzillas that offer an API."""

    implements(
        ISupportsBackLinking, ISupportsCommentImport, ISupportsCommentPushing)

    def __init__(self, baseurl, xmlrpc_transport=None,
                 internal_xmlrpc_transport=None):
        super(BugzillaAPI, self).__init__(baseurl)
        self._bugs = {}
        self._bug_aliases = {}

        self.xmlrpc_endpoint = urlappend(self.baseurl, 'xmlrpc.cgi')

        self.internal_xmlrpc_transport = internal_xmlrpc_transport
        if xmlrpc_transport is None:
            self.xmlrpc_transport = UrlLib2Transport(self.xmlrpc_endpoint)
        else:
            self.xmlrpc_transport = xmlrpc_transport

    def getExternalBugTrackerToUse(self):
        """The Bugzilla API has been chosen, so return self."""
        return self

    @property
    def xmlrpc_proxy(self):
        """Return an `xmlrpclib.ServerProxy` to self.xmlrpc_endpoint."""
        return xmlrpclib.ServerProxy(
            self.xmlrpc_endpoint, transport=self.xmlrpc_transport)

    @property
    def credentials(self):
        credentials_config = config['checkwatches.credentials']

        # Extract the hostname from the current base url using urlparse.
        hostname = urlparse(self.baseurl)[1]
        try:
            # XXX gmb 2009-08-19 bug=391131
            #     We shouldn't be using this here. Ideally we'd be able
            #     to get the credentials from the BugTracker object.
            #     If you find yourself adding credentials for, for
            #     example, www.password.username.pirateninjah4x0rz.org,
            #     think about fixing the above bug instead.
            username = credentials_config['%s.username' % hostname]
            password = credentials_config['%s.password' % hostname]
            return {'login': username, 'password': password}
        except KeyError:
            raise BugTrackerAuthenticationError(
                self.baseurl, "No credentials found.")

    @ensure_no_transaction
    def _authenticate(self):
        """Authenticate with the remote Bugzilla instance.

        The native Bugzilla API uses a standard (username, password)
        paradigm for authentication. If the username and password are
        correct, Bugzilla will send back a login cookie which we can use
        to re-authenticate with each subsequent method call.
        """
        try:
            self.xmlrpc_proxy.User.login(self.credentials)
        except xmlrpclib.Fault as fault:
            raise BugTrackerAuthenticationError(
                self.baseurl,
                "Fault %s: %s" % (fault.faultCode, fault.faultString))

    def _storeBugs(self, remote_bugs):
        """Store remote bugs in the local `bugs` dict."""
        for remote_bug in remote_bugs:
            self._bugs[remote_bug['id']] = remote_bug

            # The bug_aliases dict is a mapping between aliases and bug
            # IDs. We use the aliases dict to look up the correct ID for
            # a bug. This allows us to reference a bug by either ID or
            # alias.
            if remote_bug.get('alias', '') != '':
                self._bug_aliases[remote_bug['alias']] = remote_bug['id']

    @ensure_no_transaction
    def getCurrentDBTime(self):
        """See `IExternalBugTracker`."""
        time_dict = self.xmlrpc_proxy.Bugzilla.time()

        # The server's DB time is the one that we want to use. However,
        # this may not be in UTC, so we need to convert it. Since we
        # can't guarantee that the timezone data returned by the server
        # is sane, we work out the server's offset from UTC by looking
        # at the difference between the web_time and the web_time_utc
        # values.
        server_web_datetime = time_dict['web_time']
        server_web_datetime_utc = time_dict['web_time_utc']
        server_utc_offset = server_web_datetime - server_web_datetime_utc
        server_db_datetime = time_dict['db_time']
        server_utc_datetime = server_db_datetime - server_utc_offset
        return server_utc_datetime.replace(tzinfo=pytz.timezone('UTC'))

    def _getActualBugId(self, bug_id):
        """Return the actual bug id for an alias or id."""
        # See if bug_id is actually an alias.
        actual_bug_id = self._bug_aliases.get(bug_id)

        # bug_id isn't an alias, so try turning it into an int and
        # looking the bug up by ID.
        if actual_bug_id is not None:
            return actual_bug_id
        else:
            try:
                actual_bug_id = int(bug_id)
            except ValueError:
                # If bug_id can't be int()'d then it's likely an alias
                # that doesn't exist, so raise BugNotFound.
                raise BugNotFound(bug_id)

            # Check that the bug does actually exist. That way we're
            # treating integer bug IDs and aliases in the same way.
            if actual_bug_id not in self._bugs:
                raise BugNotFound(bug_id)

            return actual_bug_id

    def _getBugIdsToRetrieve(self, bug_ids):
        """For a set of bug IDs, return those for which we have no data."""
        bug_ids_to_retrieve = []
        for bug_id in bug_ids:
            try:
                self._getActualBugId(bug_id)
            except BugNotFound:
                bug_ids_to_retrieve.append(bug_id)

        return bug_ids_to_retrieve

    @ensure_no_transaction
    def initializeRemoteBugDB(self, bug_ids):
        """See `IExternalBugTracker`."""
        # First, discard all those bug IDs about which we already have
        # data.
        bug_ids_to_retrieve = self._getBugIdsToRetrieve(bug_ids)

        # Pull the bug data from the remote server. permissive=True here
        # prevents Bugzilla from erroring if we ask for a bug it doesn't
        # have.
        response_dict = self.xmlrpc_proxy.Bug.get({
            'ids': bug_ids_to_retrieve,
            'permissive': True,
            })
        remote_bugs = response_dict['bugs']

        self._storeBugs(remote_bugs)

    def getRemoteStatus(self, bug_id):
        """See `IExternalBugTracker`."""
        actual_bug_id = self._getActualBugId(bug_id)

        # Attempt to get the status and resolution from the bug. If
        # we don't have the data for either of them, raise an error.
        try:
            status = self._bugs[actual_bug_id]['status']
            resolution = self._bugs[actual_bug_id]['resolution']
        except KeyError:
            raise UnparsableBugData(
                "No status or resolution defined for bug %i" % (bug_id))

        if resolution != '':
            return "%s %s" % (status, resolution)
        else:
            return status

    def getRemoteImportance(self, bug_id):
        """See `IExternalBugTracker`."""
        actual_bug_id = self._getActualBugId(bug_id)

        # Attempt to get the priority and severity from the bug.
        # If we don't have the data for either, raise an error.
        try:
            priority = self._bugs[actual_bug_id]['priority']
            severity = self._bugs[actual_bug_id]['severity']
        except KeyError:
            raise UnparsableBugData(
                "No priority or severity defined for bug %i" % bug_id)

        if severity != '':
            return "%s %s" % (priority, severity)
        else:
            return priority

    @ensure_no_transaction
    def getModifiedRemoteBugs(self, bug_ids, last_checked):
        """See `IExternalBugTracker`."""
        response_dict = self.xmlrpc_proxy.Bug.search(
            {'id': bug_ids, 'last_change_time': last_checked})
        remote_bugs = response_dict['bugs']
        # Store the bugs we've imported and return only their IDs.
        self._storeBugs(remote_bugs)
        # Marshal the bug IDs into strings before returning them since
        # the remote Bugzilla may return ints rather than strings.
        return [str(remote_bug['id']) for remote_bug in remote_bugs]

    def getRemoteProduct(self, remote_bug):
        """See `IExternalBugTracker`."""
        actual_bug_id = self._getActualBugId(remote_bug)
        return self._bugs[actual_bug_id]['product']

    def getProductsForRemoteBugs(self, bug_ids):
        """Return the products to which a set of remote bugs belong.

        :param bug_ids: A list of bug IDs or aliases.
        :returns: A dict of (bug_id_or_alias, product) mappings. If a
            bug ID specified in `bug_ids` is invalid, it will be ignored.
        """
        # Fetch from the server those bugs that we haven't already
        # fetched.
        self.initializeRemoteBugDB(bug_ids)

        bug_products = {}
        for bug_id in bug_ids:
            # If one of the bugs we're trying to get the product for
            # doesn't exist, just skip it.
            try:
                actual_bug_id = self._getActualBugId(bug_id)
            except BugNotFound:
                continue

            bug_dict = self._bugs[actual_bug_id]
            bug_products[bug_id] = bug_dict['product']

        return bug_products

    def getCommentIds(self, remote_bug_id):
        """See `ISupportsCommentImport`."""
        actual_bug_id = self._getActualBugId(remote_bug_id)

        # Check that the bug exists, first.
        if actual_bug_id not in self._bugs:
            raise BugNotFound(remote_bug_id)

        # Get only the remote comment IDs and store them in the
        # 'comments' field of the bug.
        return_dict = self.xmlrpc_proxy.Bug.comments({
            'ids': [actual_bug_id],
            'include_fields': ['id'],
            })

        # We need to convert bug and comment ids to strings (see bugs
        # 248662 amd 248938).
        bug_comments_dict = return_dict['bugs']
        bug_comments = bug_comments_dict[str(actual_bug_id)]['comments']

        return [str(comment['id']) for comment in bug_comments]

    @ensure_no_transaction
    def fetchComments(self, remote_bug_id, comment_ids):
        """See `ISupportsCommentImport`."""
        actual_bug_id = self._getActualBugId(remote_bug_id)

        # We need to cast comment_ids to integers, since
        # CheckwatchesMaster.importBugComments() will pass us a list of
        # strings (see bug 248938).
        comment_ids = [int(comment_id) for comment_id in comment_ids]

        # Fetch the comments we want.
        return_dict = self.xmlrpc_proxy.Bug.comments({
            'comment_ids': comment_ids,
            })
        comments = return_dict['comments']

        # As a sanity check, drop any comments that don't belong to the
        # bug in remote_bug_id.
        for comment_id, comment in comments.items():
            if int(comment['bug_id']) != actual_bug_id:
                del comments[comment_id]

        # Ensure that comment IDs are converted to ints.
        comments_with_int_ids = dict(
            (int(id), comments[id]) for id in comments)
        self._bugs[actual_bug_id]['comments'] = comments_with_int_ids

    def getPosterForComment(self, remote_bug_id, comment_id):
        """See `ISupportsCommentImport`."""
        actual_bug_id = self._getActualBugId(remote_bug_id)

        # We need to cast comment_id to integers, since
        # CheckwatchesMaster.importBugComments() will pass us a string (see
        # bug 248938).
        comment_id = int(comment_id)

        comment = self._bugs[actual_bug_id]['comments'][comment_id]
        display_name, email = parseaddr(comment['author'])

        # If the name is empty then we return None so that
        # IPersonSet.ensurePerson() can actually do something with it.
        if not display_name:
            display_name = None

        return (display_name, email)

    def getMessageForComment(self, remote_bug_id, comment_id, poster):
        """See `ISupportsCommentImport`."""
        actual_bug_id = self._getActualBugId(remote_bug_id)

        # We need to cast comment_id to integers, since
        # CheckwatchesMaster.importBugComments() will pass us a string (see
        # bug 248938).
        comment_id = int(comment_id)
        comment = self._bugs[actual_bug_id]['comments'][comment_id]
        return getUtility(IMessageSet).fromText(
            owner=poster, subject='', content=comment['text'],
            datecreated=comment['time'].replace(tzinfo=pytz.timezone('UTC')))

    @ensure_no_transaction
    @needs_authentication
    def addRemoteComment(self, remote_bug, comment_body, rfc822msgid):
        """Add a comment to the remote bugtracker.

        See `ISupportsCommentPushing`.
        """
        actual_bug_id = self._getActualBugId(remote_bug)

        request_params = {
            'id': actual_bug_id,
            'comment': comment_body,
            }
        return_dict = self.xmlrpc_proxy.Bug.add_comment(request_params)

        # We cast the return value to string, since that's what
        # CheckwatchesMaster will expect (see bug 248938).
        return str(return_dict['id'])

    def getLaunchpadBugId(self, remote_bug):
        """Return the Launchpad bug ID for the remote bug.

        See `ISupportsBackLinking`.
        """
        # XXX gmb 2009-11-30 bug=490267
        #     In fact, this method always returns None due to bug
        #     490267. Once the bug is fixed in Bugzilla we should update
        #     this method.
        return None

    @ensure_no_transaction
    @needs_authentication
    def setLaunchpadBugId(self, remote_bug, launchpad_bug_id,
                          launchpad_bug_url):
        """Set the Launchpad bug for a given remote bug.

        See `ISupportsBackLinking`.
        """
        actual_bug_id = self._getActualBugId(remote_bug)

        request_params = {
            'ids': [actual_bug_id],
            'add': [launchpad_bug_url],
            }

        self.xmlrpc_proxy.Bug.update_see_also(request_params)


class BugzillaLPPlugin(BugzillaAPI):
    """An `ExternalBugTracker` to handle Bugzillas using the LP Plugin."""

    implements(
        ISupportsBackLinking, ISupportsCommentImport,
        ISupportsCommentPushing)

    def getExternalBugTrackerToUse(self):
        """The Bugzilla LP Plugin has been chosen, so return self."""
        return self

    @ensure_no_transaction
    def _authenticate(self):
        """Authenticate with the remote Bugzilla instance.

        Authentication works by means of using a LoginToken of type
        BUGTRACKER. We send the token text to the remote server as a
        parameter to Launchpad.login(), which verifies it using the
        standard launchpad.net/token/$token/+bugtracker-handshake URL.

        If the token is valid, Bugzilla will send us a user ID as a
        return value for the call to Launchpad.login() and will set two
        cookies in the response header, Bugzilla_login and
        Bugzilla_logincookie, which we can then use to re-authenticate
        ourselves for each subsequent method call.
        """
        internal_xmlrpc_server = xmlrpclib.ServerProxy(
            config.checkwatches.xmlrpc_url,
            transport=self.internal_xmlrpc_transport)

        token_text = internal_xmlrpc_server.newBugTrackerToken()

        try:
            self.xmlrpc_proxy.Launchpad.login(
                {'token': token_text})
        except xmlrpclib.Fault as fault:
            message = 'XML-RPC Fault: %s "%s"' % (
                fault.faultCode, fault.faultString)
            raise BugTrackerAuthenticationError(
                self.baseurl, message)
        except xmlrpclib.ProtocolError as error:
            message = 'Protocol error: %s "%s"' % (
                error.errcode, error.errmsg)
            raise BugTrackerAuthenticationError(
                self.baseurl, message)

    @ensure_no_transaction
    def getModifiedRemoteBugs(self, bug_ids, last_checked):
        """See `IExternalBugTracker`."""
        # We pass permissive=True to ensure that Bugzilla won't error
        # if we ask for a bug that doesn't exist.
        response_dict = self.xmlrpc_proxy.Launchpad.get_bugs({
            'ids': bug_ids,
            'changed_since': last_checked,
            'permissive': True,
            })
        remote_bugs = response_dict['bugs']
        # Store the bugs we've imported and return only their IDs.
        self._storeBugs(remote_bugs)
        return [remote_bug['id'] for remote_bug in remote_bugs]

    @ensure_no_transaction
    def initializeRemoteBugDB(self, bug_ids, products=None):
        """See `IExternalBugTracker`."""
        # First, discard all those bug IDs about which we already have
        # data.
        bug_ids_to_retrieve = self._getBugIdsToRetrieve(bug_ids)

        # Next, grab the bugs we still need from the remote server.
        # We pass permissive=True to ensure that Bugzilla won't error if
        # we ask for a bug that doesn't exist.
        request_args = {
            'ids': bug_ids_to_retrieve,
            'permissive': True,
            }

        if products is not None:
            request_args['products'] = products

        response_dict = self.xmlrpc_proxy.Launchpad.get_bugs(request_args)
        remote_bugs = response_dict['bugs']

        self._storeBugs(remote_bugs)

    @ensure_no_transaction
    def getCurrentDBTime(self):
        """See `IExternalBugTracker`."""
        time_dict = self.xmlrpc_proxy.Launchpad.time()

        # Return the UTC time sent by the server so that we don't have
        # to care about timezones.
        server_utc_time = time_dict['utc_time']
        return server_utc_time.replace(tzinfo=pytz.timezone('UTC'))

    @ensure_no_transaction
    def getCommentIds(self, remote_bug_id):
        """See `ISupportsCommentImport`."""
        actual_bug_id = self._getActualBugId(remote_bug_id)

        # Check that the bug exists, first.
        if actual_bug_id not in self._bugs:
            raise BugNotFound(remote_bug_id)

        # Get only the remote comment IDs and store them in the
        # 'comments' field of the bug.
        request_params = {
            'bug_ids': [actual_bug_id],
            'include_fields': ['id'],
            }
        bug_comments_dict = self.xmlrpc_proxy.Launchpad.comments(
            request_params)

        # We need to convert actual_bug_id to a string due to a quirk
        # with XML-RPC (see bug 248662).
        bug_comments = bug_comments_dict['bugs'][str(actual_bug_id)]

        # We also need to convert each comment ID to a string, since
        # that's what CheckwatchesMaster.importBugComments() expects (see
        # bug 248938).
        return [str(comment['id']) for comment in bug_comments]

    @ensure_no_transaction
    def fetchComments(self, remote_bug_id, comment_ids):
        """See `ISupportsCommentImport`."""
        actual_bug_id = self._getActualBugId(remote_bug_id)

        # We need to cast comment_ids to integers, since
        # CheckwatchesMaster.importBugComments() will pass us a list of
        # strings (see bug 248938).
        comment_ids = [int(comment_id) for comment_id in comment_ids]

        # Fetch the comments we want.
        request_params = {
            'bug_ids': [actual_bug_id],
            'ids': comment_ids,
            }
        bug_comments_dict = self.xmlrpc_proxy.Launchpad.comments(
            request_params)

        # We need to convert actual_bug_id to a string here due to a
        # quirk with XML-RPC (see bug 248662).
        comment_list = bug_comments_dict['bugs'][str(actual_bug_id)]

        # Transfer the comment list into a dict.
        bug_comments = dict(
            (comment['id'], comment) for comment in comment_list)

        self._bugs[actual_bug_id]['comments'] = bug_comments

    @ensure_no_transaction
    @needs_authentication
    def addRemoteComment(self, remote_bug, comment_body, rfc822msgid):
        """Add a comment to the remote bugtracker.

        See `ISupportsCommentPushing`.
        """
        actual_bug_id = self._getActualBugId(remote_bug)

        request_params = {
            'id': actual_bug_id,
            'comment': comment_body,
            }
        return_dict = self.xmlrpc_proxy.Launchpad.add_comment(request_params)

        # We cast the return value to string, since that's what
        # CheckwatchesMaster will expect (see bug 248938).
        return str(return_dict['comment_id'])

    def getLaunchpadBugId(self, remote_bug):
        """Return the current Launchpad bug ID for a given remote bug.

        See `ISupportsBackLinking`.
        """
        actual_bug_id = self._getActualBugId(remote_bug)

        # Grab the internals dict from the bug, if there is one. If
        # there isn't, return None, since there's no Launchpad bug ID to
        # be had.
        internals = self._bugs[actual_bug_id].get('internals', None)
        if internals is None:
            return None

        # Extract the Launchpad bug ID and return it. Return None if
        # there isn't one or it's set to an empty string.
        launchpad_bug_id = internals.get('launchpad_id', None)
        if launchpad_bug_id == '':
            launchpad_bug_id = None

        return launchpad_bug_id

    @ensure_no_transaction
    @needs_authentication
    def setLaunchpadBugId(self, remote_bug, launchpad_bug_id,
                          launchpad_bug_url):
        """Set the Launchpad bug for a given remote bug.

        See `ISupportsBackLinking`.
        """
        actual_bug_id = self._getActualBugId(remote_bug)

        request_params = {
            'id': actual_bug_id,
            'launchpad_id': launchpad_bug_id,
            }

        self.xmlrpc_proxy.Launchpad.set_link(request_params)
