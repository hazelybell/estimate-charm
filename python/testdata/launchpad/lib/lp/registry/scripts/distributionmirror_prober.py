# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'DistroMirrorProber',
    ]

from datetime import datetime
import httplib
import itertools
import logging
import os
from StringIO import StringIO
import urllib
import urllib2
import urlparse

from twisted.internet import (
    defer,
    protocol,
    reactor,
    )
from twisted.internet.defer import DeferredSemaphore
from twisted.python.failure import Failure
from twisted.web.http import HTTPClient
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.distributionmirror import (
    IDistributionMirrorSet,
    MirrorContent,
    MirrorFreshness,
    UnableToFetchCDImageFileList,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.services.config import config
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.webapp import canonical_url
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries

# The requests/timeouts ratio has to be at least 3 for us to keep issuing
# requests on a given host. (This ratio is per run, rather than held long
# term)
# IMPORTANT: Changing these values can cause lots of false negatives when
# probing mirrors, so please don't change them unless you know what you're
# doing.
MIN_REQUEST_TIMEOUT_RATIO = 3
MIN_REQUESTS_TO_CONSIDER_RATIO = 30

# XXX Guilherme Salgado 2007-01-30 bug=82201:
# We need to get rid of these global dicts in this module.
host_requests = {}
host_timeouts = {}

MAX_REDIRECTS = 3

# Number of simultaneous requests we issue on a given host.
# IMPORTANT: Don't change this unless you really know what you're doing. Using
# a too big value can cause spurious failures on lots of mirrors and a too
# small one can cause the prober to run for hours.
PER_HOST_REQUESTS = 2

# We limit the overall number of simultaneous requests as well to prevent
# them from stalling and timing out before they even get a chance to
# start connecting.
OVERALL_REQUESTS = 100


class LoggingMixin:
    """Common logging class for archive and releases mirror messages."""

    def _getTime(self):
        """Return the current UTC time."""
        return datetime.utcnow()

    def logMessage(self, message):
        """Append a UTC timestamp to the message returned by the mirror
        prober.
        """
        timestamp = datetime.ctime(self._getTime())
        self.log_file.write(timestamp + ": " + message)


class RequestManager:

    overall_semaphore = DeferredSemaphore(OVERALL_REQUESTS)

    # Yes, I want a mutable class attribute because I want changes done in an
    # instance to be visible in other instances as well.
    host_locks = {}

    def run(self, host, probe_func):
        # Use a MultiLock with one semaphore limiting the overall
        # connections and another limiting the per-host connections.
        if host in self.host_locks:
            multi_lock = self.host_locks[host]
        else:
            multi_lock = MultiLock(
                self.overall_semaphore, DeferredSemaphore(PER_HOST_REQUESTS))
            self.host_locks[host] = multi_lock
        return multi_lock.run(probe_func)


class MultiLock(defer._ConcurrencyPrimitive):
    """Lock that acquires multiple underlying locks before it is acquired."""

    def __init__(self, overall_lock, host_lock):
        defer._ConcurrencyPrimitive.__init__(self)
        self.overall_lock = overall_lock
        self.host_lock = host_lock
        # host_lock will always be the scarcer resource, so it should be the
        # first to be acquired.
        self._locks = [host_lock, overall_lock]

    def acquire(self):
        return defer.gatherResults([lock.acquire() for lock in self._locks])

    def release(self):
        for lock in self._locks:
            lock.release()


class ProberProtocol(HTTPClient):
    """Simple HTTP client to probe path existence via HEAD."""

    def connectionMade(self):
        """Simply requests path presence."""
        self.makeRequest()
        self.headers = {}

    def makeRequest(self):
        """Request path presence via HTTP/1.1 using HEAD.

        Uses factory.connect_host and factory.connect_path
        """
        self.sendCommand('HEAD', self.factory.connect_path)
        self.sendHeader('HOST', self.factory.connect_host)
        self.sendHeader('User-Agent',
            'Launchpad Mirror Prober ( https://launchpad.net/ )')
        self.endHeaders()

    def handleStatus(self, version, status, message):
        # According to http://lists.debian.org/deity/2001/10/msg00046.html,
        # apt intentionally handles only '200 OK' responses, so we do the
        # same here.
        if status == str(httplib.OK):
            self.factory.succeeded(status)
        else:
            self.factory.failed(Failure(BadResponseCode(status)))
        self.transport.loseConnection()

    def handleResponse(self, response):
        # The status is all we need, so we don't need to do anything with
        # the response
        pass


class RedirectAwareProberProtocol(ProberProtocol):
    """A specialized version of ProberProtocol that follows HTTP redirects."""

    redirected_to_location = False

    # The different redirect statuses that I handle.
    handled_redirect_statuses = (
        httplib.MOVED_PERMANENTLY, httplib.FOUND, httplib.SEE_OTHER)

    def handleHeader(self, key, value):
        key = key.lower()
        l = self.headers.setdefault(key, [])
        l.append(value)

    def handleStatus(self, version, status, message):
        if int(status) in self.handled_redirect_statuses:
            # We need to redirect to the location specified in the headers.
            self.redirected_to_location = True
        else:
            # We have the result immediately.
            ProberProtocol.handleStatus(self, version, status, message)

    def handleEndHeaders(self):
        assert self.redirected_to_location, (
            'All headers received but failed to find a result.')

        # Server responded redirecting us to another location.
        location = self.headers.get('location')
        url = location[0]
        self.factory.redirect(url)
        self.transport.loseConnection()


class ProberFactory(protocol.ClientFactory):
    """Factory using ProberProtocol to probe single URL existence."""

    protocol = ProberProtocol

    # Details of the URL of the host in which we actually want to request the
    # confirmation from.
    request_scheme = None
    request_host = None
    request_port = None
    request_path = None

    # Details of the URL of the host in which we'll connect, which will only
    # be different from request_* in case we have an http_proxy environment
    # variable --in that case the scheme, host and port will be the ones
    # extracted from http_proxy and the path will be self.url
    connect_scheme = None
    connect_host = None
    connect_port = None
    connect_path = None

    def __init__(self, url, timeout=config.distributionmirrorprober.timeout):
        # We want the deferred to be a private attribute (_deferred) to make
        # sure our clients will only use the deferred returned by the probe()
        # method; this is to ensure self._cancelTimeout is always the first
        # callback in the chain.
        self._deferred = defer.Deferred()
        self.timeout = timeout
        self.timeoutCall = None
        self.setURL(url.encode('ascii'))

    def probe(self):
        logger = logging.getLogger('distributionmirror-prober')
        # NOTE: We don't want to issue connections to any outside host when
        # running the mirror prober in a development machine, so we do this
        # hack here.
        if (self.connect_host != 'localhost'
            and config.distributionmirrorprober.localhost_only):
            reactor.callLater(0, self.succeeded, '200')
            logger.debug("Forging a successful response on %s as we've been "
                         "told to probe only local URLs." % self.url)
            return self._deferred

        if should_skip_host(self.request_host):
            reactor.callLater(0, self.failed, ConnectionSkipped(self.url))
            logger.debug("Skipping %s as we've had too many timeouts on this "
                         "host already." % self.url)
            return self._deferred

        self.connect()
        logger.debug('Probing %s' % self.url)
        return self._deferred

    def connect(self):
        host_requests[self.request_host] += 1
        reactor.connectTCP(self.connect_host, self.connect_port, self)
        if self.timeoutCall is not None and self.timeoutCall.active():
            self._cancelTimeout(None)
        self.timeoutCall = reactor.callLater(
            self.timeout, self.failWithTimeoutError)
        self._deferred.addBoth(self._cancelTimeout)

    connector = None

    def failWithTimeoutError(self):
        host_timeouts[self.request_host] += 1
        self.failed(ProberTimeout(self.url, self.timeout))
        if self.connector is not None:
            self.connector.disconnect()

    def startedConnecting(self, connector):
        self.connector = connector

    def succeeded(self, status):
        self._deferred.callback(status)

    def failed(self, reason):
        self._deferred.errback(reason)

    def _cancelTimeout(self, result):
        if self.timeoutCall.active():
            self.timeoutCall.cancel()
        return result

    def setURL(self, url):
        self.url = url
        scheme, host, port, path = _parse(url)
        # XXX Guilherme Salgado 2006-09-19:
        # We don't actually know how to handle FTP responses, but we
        # expect to be behind a squid HTTP proxy with the patch at
        # http://www.squid-cache.org/bugs/show_bug.cgi?id=1758 applied. So, if
        # you encounter any problems with FTP URLs you'll probably have to nag
        # the sysadmins to fix squid for you.
        if scheme not in ('http', 'ftp'):
            raise UnknownURLScheme(url)

        if scheme and host:
            self.request_scheme = scheme
            self.request_host = host
            self.request_port = port
            self.request_path = path

        if self.request_host not in host_requests:
            host_requests[self.request_host] = 0
        if self.request_host not in host_timeouts:
            host_timeouts[self.request_host] = 0

        # If the http_proxy variable is set, we want to use it as the host
        # we're going to connect to.
        proxy = os.getenv('http_proxy')
        if proxy:
            scheme, host, port, dummy = _parse(proxy)
            path = url

        self.connect_scheme = scheme
        self.connect_host = host
        self.connect_port = port
        self.connect_path = path


class RedirectAwareProberFactory(ProberFactory):

    protocol = RedirectAwareProberProtocol
    redirection_count = 0

    def redirect(self, url):
        self.timeoutCall.reset(self.timeout)

        scheme, host, port, orig_path = _parse(self.url)
        scheme, host, port, new_path = _parse(url)
        if (urllib.unquote(orig_path.split('/')[-1])
            != urllib.unquote(new_path.split('/')[-1])):
            # Server redirected us to a file which doesn't seem to be what we
            # requested.  It's likely to be a stupid server which redirects
            # instead of 404ing (https://launchpad.net/bugs/204460).
            self.failed(Failure(RedirectToDifferentFile(orig_path, new_path)))
            return

        try:
            if self.redirection_count >= MAX_REDIRECTS:
                raise InfiniteLoopDetected()
            self.redirection_count += 1

            logger = logging.getLogger('distributionmirror-prober')
            logger.debug('Got redirected from %s to %s' % (self.url, url))
            # XXX Guilherme Salgado 2007-04-23 bug=109223:
            # We can't assume url to be absolute here.
            self.setURL(url)
        except UnknownURLScheme as e:
            # Since we've got the UnknownURLScheme after a redirect, we need
            # to raise it in a form that can be ignored in the layer above.
            self.failed(UnknownURLSchemeAfterRedirect(url))
        except InfiniteLoopDetected as e:
            self.failed(e)

        else:
            self.connect()


class ProberError(Exception):
    """A generic prober error.

    This class should be used as a base for more specific prober errors.
    """


class ProberTimeout(ProberError):
    """The initialized URL did not return in time."""

    def __init__(self, url, timeout, *args):
        self.url = url
        self.timeout = timeout
        ProberError.__init__(self, *args)

    def __str__(self):
        return ("HEAD request on %s took longer than %s seconds"
                % (self.url, self.timeout))


class BadResponseCode(ProberError):

    def __init__(self, status, *args):
        ProberError.__init__(self, *args)
        self.status = status

    def __str__(self):
        return "Bad response code: %s" % self.status


class RedirectToDifferentFile(ProberError):

    def __init__(self, orig_path, new_path, *args):
        ProberError.__init__(self, *args)
        self.orig_path = orig_path
        self.new_path = new_path

    def __str__(self):
        return ("Attempt to redirect to a different file; from %s to %s"
                % (self.orig_path, self.new_path))


class InfiniteLoopDetected(ProberError):

    def __str__(self):
        return "Infinite loop detected"


class ConnectionSkipped(ProberError):

    def __str__(self):
        return ("Connection skipped because of too many timeouts on this "
                "host. It will be retried on the next probing run.")


class UnknownURLScheme(ProberError):

    def __init__(self, url, *args):
        ProberError.__init__(self, *args)
        self.url = url

    def __str__(self):
        return ("The mirror prober doesn't know how to check this kind of "
                "URLs: %s" % self.url)


class UnknownURLSchemeAfterRedirect(UnknownURLScheme):

    def __str__(self):
        return ("The mirror prober was redirected to: %s. It doesn't know how"
                "to check this kind of URL." % self.url)


class ArchiveMirrorProberCallbacks(LoggingMixin):

    expected_failures = (BadResponseCode, ProberTimeout, ConnectionSkipped)

    def __init__(self, mirror, series, pocket, component, url, log_file):
        self.mirror = mirror
        self.series = series
        self.pocket = pocket
        self.component = component
        self.url = url
        self.log_file = log_file
        if IDistroArchSeries.providedBy(series):
            self.mirror_class_name = 'MirrorDistroArchSeries'
            self.deleteMethod = self.mirror.deleteMirrorDistroArchSeries
            self.ensureMethod = self.mirror.ensureMirrorDistroArchSeries
        elif IDistroSeries.providedBy(series):
            self.mirror_class_name = 'MirrorDistroSeries'
            self.deleteMethod = self.mirror.deleteMirrorDistroSeriesSource
            self.ensureMethod = self.mirror.ensureMirrorDistroSeriesSource
        else:
            raise AssertionError('series must provide either '
                                 'IDistroArchSeries or IDistroSeries.')

    def deleteMirrorSeries(self, failure):
        """Delete the mirror for self.series, self.pocket and self.component.

        If the failure we get from twisted is not a timeout, a bad response
        code or a connection skipped, then this failure is propagated.
        """
        self.deleteMethod(self.series, self.pocket, self.component)
        msg = ('Deleted %s of %s with url %s because: %s.\n'
               % (self.mirror_class_name,
                  self._getSeriesPocketAndComponentDescription(), self.url,
                  failure.getErrorMessage()))
        self.logMessage(msg)
        failure.trap(*self.expected_failures)

    def ensureMirrorSeries(self, http_status):
        """Make sure we have a mirror for self.series, self.pocket and
        self.component.
        """
        msg = ('Ensuring %s of %s with url %s exists in the database.\n'
               % (self.mirror_class_name,
                  self._getSeriesPocketAndComponentDescription(),
                  self.url))
        mirror = self.ensureMethod(
            self.series, self.pocket, self.component)

        self.logMessage(msg)
        return mirror

    def updateMirrorFreshness(self, arch_or_source_mirror):
        """Update the freshness of this MirrorDistro{ArchSeries,SeriesSource}.

        This is done by issuing HTTP HEAD requests on that mirror looking for
        some packages found in our publishing records. Then, knowing what
        packages the mirror contains and when these packages were published,
        we can have an idea of when that mirror was last updated.
        """
        # The errback that's one level before this callback in the chain will
        # return None if it gets any of self.expected_failures as the error,
        # so we need to check that here.
        if arch_or_source_mirror is None:
            return

        scheme, host, port, path = _parse(self.url)
        freshness_url_map = arch_or_source_mirror.getURLsToCheckUpdateness()
        if not freshness_url_map or should_skip_host(host):
            # Either we have no publishing records for self.series,
            # self.pocket and self.component or we got too may timeouts from
            # this host and thus should skip it, so it's better to delete this
            # MirrorDistroArchSeries/MirrorDistroSeriesSource than to keep
            # it with an UNKNOWN freshness.
            self.deleteMethod(self.series, self.pocket, self.component)
            return

        request_manager = RequestManager()
        deferredList = []
        # We start setting the freshness to unknown, and then we move on
        # trying to find one of the recently published packages mirrored
        # there.
        arch_or_source_mirror.freshness = MirrorFreshness.UNKNOWN
        for freshness, url in freshness_url_map.items():
            prober = ProberFactory(url)
            deferred = request_manager.run(prober.request_host, prober.probe)
            deferred.addCallback(
                self.setMirrorFreshness, arch_or_source_mirror, freshness,
                url)
            deferred.addErrback(self.logError, url)
            deferredList.append(deferred)
        return defer.DeferredList(deferredList)

    def setMirrorFreshness(
            self, http_status, arch_or_source_mirror, freshness, url):
        """Update the freshness of the given arch or source mirror.

        The freshness is changed only if the given freshness refers to a more
        recent date than the current one.
        """
        if freshness < arch_or_source_mirror.freshness:
            msg = ('Found that %s exists. Updating %s of %s freshness to '
                   '%s.\n' % (url, self.mirror_class_name,
                              self._getSeriesPocketAndComponentDescription(),
                              freshness.title))
            self.logMessage(msg)
            arch_or_source_mirror.freshness = freshness

    def _getSeriesPocketAndComponentDescription(self):
        """Return a string containing the name of the series, pocket and
        component.

        This is meant to be used in the logs, to help us identify if this is a
        MirrorDistroSeriesSource or a MirrorDistroArchSeries.
        """
        if IDistroArchSeries.providedBy(self.series):
            text = ("Series %s, Architecture %s" %
                    (self.series.distroseries.title,
                     self.series.architecturetag))
        else:
            text = "Series %s" % self.series.title
        text += (", Component %s and Pocket %s" %
                 (self.component.name, self.pocket.title))
        return text

    def logError(self, failure, url):
        msg = ("%s on %s of %s\n"
               % (failure.getErrorMessage(), url,
                  self._getSeriesPocketAndComponentDescription()))
        if failure.check(*self.expected_failures) is not None:
            self.logMessage(msg)
        else:
            # This is not an error we expect from an HTTP server, so we log it
            # using the cronscript's logger and wait for kiko to complain
            # about it.
            logger = logging.getLogger('distributionmirror-prober')
            logger.error(msg)
        return None


class MirrorCDImageProberCallbacks(LoggingMixin):

    expected_failures = (
        BadResponseCode,
        ConnectionSkipped,
        ProberTimeout,
        RedirectToDifferentFile,
        UnknownURLSchemeAfterRedirect,
        )

    def __init__(self, mirror, distroseries, flavour, log_file):
        self.mirror = mirror
        self.distroseries = distroseries
        self.flavour = flavour
        self.log_file = log_file

    def ensureOrDeleteMirrorCDImageSeries(self, result):
        """Check if the result of the deferredList contains only success and
        then ensure we have a MirrorCDImageSeries for self.distroseries and
        self.flavour.

        If result contains one or more failures, then we ensure that
        MirrorCDImageSeries is deleted.
        """
        for success_or_failure, response in result:
            if success_or_failure == defer.FAILURE:
                self.mirror.deleteMirrorCDImageSeries(
                    self.distroseries, self.flavour)
                if response.check(*self.expected_failures) is None:
                    msg = ("%s on mirror %s. Check its logfile for more "
                           "details.\n"
                           % (response.getErrorMessage(), self.mirror.name))
                    # This is not an error we expect from an HTTP server, so
                    # we log it using the cronscript's logger and wait for
                    # kiko to complain about it.
                    logger = logging.getLogger('distributionmirror-prober')
                    logger.error(msg)
                return None

        mirror = self.mirror.ensureMirrorCDImageSeries(
            self.distroseries, self.flavour)
        self.logMessage(
            "Found all ISO images for series %s and flavour %s.\n"
            % (self.distroseries.title, self.flavour))
        return mirror

    def logMissingURL(self, failure, url):
        self.logMessage(
            "Failed %s: %s\n" % (url, failure.getErrorMessage()))
        return failure


def _build_request_for_cdimage_file_list(url):
    headers = {'Pragma': 'no-cache', 'Cache-control': 'no-cache'}
    return urllib2.Request(url, headers=headers)


def _get_cdimage_file_list():
    url = config.distributionmirrorprober.cdimage_file_list_url
    try:
        return urllib2.urlopen(_build_request_for_cdimage_file_list(url))
    except urllib2.URLError as e:
        raise UnableToFetchCDImageFileList(
            'Unable to fetch %s: %s' % (url, e))


def restore_http_proxy(http_proxy):
    """Restore the http_proxy environment variable to the given value."""
    if http_proxy is None:
        try:
            del os.environ['http_proxy']
        except KeyError:
            pass
    else:
        os.environ['http_proxy'] = http_proxy


def get_expected_cdimage_paths():
    """Get all paths where we can find CD image files on a cdimage mirror.

    Return a list containing, for each Ubuntu DistroSeries and flavour, a
    list of CD image file paths for that DistroSeries and flavour.

    This list is read from a file located at http://releases.ubuntu.com,
    so if something goes wrong while reading that file, an
    UnableToFetchCDImageFileList exception will be raised.
    """
    d = {}
    for line in _get_cdimage_file_list().readlines():
        flavour, seriesname, path, size = line.split('\t')
        paths = d.setdefault((flavour, seriesname), [])
        paths.append(path)

    ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
    paths = []
    for key, value in sorted(d.items()):
        flavour, seriesname = key
        series = ubuntu.getSeries(seriesname)
        paths.append((series, flavour, value))
    return paths


def checkComplete(result, key, unchecked_keys):
    """Check if we finished probing all mirrors, and call reactor.stop()."""
    unchecked_keys.remove(key)
    if not len(unchecked_keys):
        reactor.callLater(0, reactor.stop)
    # This is added to the deferred with addBoth(), which means it'll be
    # called if something goes wrong in the end of the callback chain, and in
    # that case we shouldn't swallow the error.
    return result


def probe_archive_mirror(mirror, logfile, unchecked_keys, logger):
    """Probe an archive mirror for its contents and freshness.

    First we issue a set of HTTP HEAD requests on some key files to find out
    what is mirrored there, then we check if some packages that we know the
    publishing time are available on that mirror, giving us an idea of when it
    was last synced to the main archive.
    """
    packages_paths = mirror.getExpectedPackagesPaths()
    sources_paths = mirror.getExpectedSourcesPaths()
    all_paths = itertools.chain(packages_paths, sources_paths)
    request_manager = RequestManager()
    for series, pocket, component, path in all_paths:
        url = "%s/%s" % (mirror.base_url, path)
        callbacks = ArchiveMirrorProberCallbacks(
            mirror, series, pocket, component, url, logfile)
        unchecked_keys.append(url)
        prober = ProberFactory(url)

        deferred = request_manager.run(prober.request_host, prober.probe)
        deferred.addCallbacks(
            callbacks.ensureMirrorSeries, callbacks.deleteMirrorSeries)

        deferred.addCallback(callbacks.updateMirrorFreshness)
        deferred.addErrback(logger.error)

        deferred.addBoth(checkComplete, url, unchecked_keys)


def probe_cdimage_mirror(mirror, logfile, unchecked_keys, logger):
    """Probe a cdimage mirror for its contents.

    This is done by checking the list of files for each flavour and series
    returned by get_expected_cdimage_paths(). If a mirror contains all
    files for a given series and flavour, then we consider that mirror is
    actually mirroring that series and flavour.
    """
    # The list of files a mirror should contain will change over time and we
    # don't want to keep records for files a mirror doesn't need to have
    # anymore, so we delete all records before start probing. This also fixes
    # https://launchpad.net/bugs/46662
    mirror.deleteAllMirrorCDImageSeries()
    try:
        cdimage_paths = get_expected_cdimage_paths()
    except UnableToFetchCDImageFileList as e:
        logger.error(e)
        return

    for series, flavour, paths in cdimage_paths:
        callbacks = MirrorCDImageProberCallbacks(
            mirror, series, flavour, logfile)

        mirror_key = (series, flavour)
        unchecked_keys.append(mirror_key)
        deferredList = []
        request_manager = RequestManager()
        for path in paths:
            url = '%s/%s' % (mirror.base_url, path)
            # Use a RedirectAwareProberFactory because CD mirrors are allowed
            # to redirect, and we need to cope with that.
            prober = RedirectAwareProberFactory(url)
            deferred = request_manager.run(prober.request_host, prober.probe)
            deferred.addErrback(callbacks.logMissingURL, url)
            deferredList.append(deferred)

        deferredList = defer.DeferredList(deferredList, consumeErrors=True)
        deferredList.addCallback(callbacks.ensureOrDeleteMirrorCDImageSeries)
        deferredList.addCallback(checkComplete, mirror_key, unchecked_keys)


def should_skip_host(host):
    """Return True if the requests/timeouts ratio on this host is too low."""
    requests = host_requests[host]
    timeouts = host_timeouts[host]
    if timeouts == 0 or requests < MIN_REQUESTS_TO_CONSIDER_RATIO:
        return False
    else:
        ratio = float(requests) / timeouts
        return ratio < MIN_REQUEST_TIMEOUT_RATIO


def _parse(url, defaultPort=80):
    """Parse the given URL returning the scheme, host, port and path."""
    scheme, host, path, dummy, dummy, dummy = urlparse.urlparse(url)
    port = defaultPort
    if ':' in host:
        host, port = host.split(':')
        assert port.isdigit()
        port = int(port)
    return scheme, host, port, path


class DistroMirrorProber:
    """Main entry point for the distribution mirror prober."""

    def __init__(self, txn, logger):
        self.txn = txn
        self.logger = logger

    def _sanity_check_mirror(self, mirror):
        """Check that the given mirror is official and has an http_base_url.
        """
        assert mirror.isOfficial(), (
            'Non-official mirrors should not be probed')
        if mirror.base_url is None:
            self.logger.warning(
                "Mirror '%s' of distribution '%s' doesn't have a base URL; "
                "we can't probe it." % (
                    mirror.name, mirror.distribution.name))
            return False
        return True

    def _create_probe_record(self, mirror, logfile):
        """Create a probe record for the given mirror with the given logfile.
        """
        logfile.seek(0)
        filename = '%s-probe-logfile.txt' % mirror.name
        log_file = getUtility(ILibraryFileAliasSet).create(
            name=filename, size=len(logfile.getvalue()),
            file=logfile, contentType='text/plain')
        mirror.newProbeRecord(log_file)

    def probe(self, content_type, no_remote_hosts, ignore_last_probe,
              max_mirrors, notify_owner):
        """Probe distribution mirrors.

        :param content_type: The type of mirrored content, as a
            `MirrorContent`.
        :param no_remote_hosts: If True, restrict access to localhost.
        :param ignore_last_probe: If True, ignore the results of the last
            probe and probe again anyway.
        :param max_mirrors: The maximum number of mirrors to probe. If None,
            no maximum.
        :param notify_owner: Send failure notification to the owners of the
            mirrors.
        """
        if content_type == MirrorContent.ARCHIVE:
            probe_function = probe_archive_mirror
        elif content_type == MirrorContent.RELEASE:
            probe_function = probe_cdimage_mirror
        else:
            raise ValueError(
                "Unrecognized content_type: %s" % (content_type,))

        self.txn.begin()

        # To me this seems better than passing the no_remote_hosts value
        # through a lot of method/function calls, until it reaches the probe()
        # method. (salgado)
        if no_remote_hosts:
            localhost_only_conf = """
                [distributionmirrorprober]
                localhost_only: True
                """
            config.push('localhost_only_conf', localhost_only_conf)

        self.logger.info('Probing %s Mirrors' % content_type.title)

        mirror_set = getUtility(IDistributionMirrorSet)
        results = mirror_set.getMirrorsToProbe(
            content_type, ignore_last_probe=ignore_last_probe,
            limit=max_mirrors)
        mirror_ids = [mirror.id for mirror in results]
        unchecked_keys = []
        logfiles = {}
        probed_mirrors = []

        for mirror_id in mirror_ids:
            mirror = mirror_set[mirror_id]
            if not self._sanity_check_mirror(mirror):
                continue

            # XXX: salgado 2006-05-26:
            # Some people registered mirrors on distros other than Ubuntu back
            # in the old times, so now we need to do this small hack here.
            if not mirror.distribution.full_functionality:
                self.logger.debug(
                    "Mirror '%s' of distribution '%s' can't be probed --we "
                    "only probe Ubuntu mirrors."
                    % (mirror.name, mirror.distribution.name))
                continue

            probed_mirrors.append(mirror)
            logfile = StringIO()
            logfiles[mirror_id] = logfile
            probe_function(mirror, logfile, unchecked_keys, self.logger)

        if probed_mirrors:
            reactor.run()
            self.logger.info('Probed %d mirrors.' % len(probed_mirrors))
        else:
            self.logger.info('No mirrors to probe.')

        disabled_mirrors = []
        reenabled_mirrors = []
        # Now that we finished probing all mirrors, we check if any of these
        # mirrors appear to have no content mirrored, and, if so, mark them as
        # disabled and notify their owners.
        expected_iso_images_count = len(get_expected_cdimage_paths())
        for mirror in probed_mirrors:
            log = logfiles[mirror.id]
            self._create_probe_record(mirror, log)
            if mirror.shouldDisable(expected_iso_images_count):
                if mirror.enabled:
                    log.seek(0)
                    mirror.disable(notify_owner, log.getvalue())
                    disabled_mirrors.append(canonical_url(mirror))
            else:
                # Ensure the mirror is enabled, so that it shows up on public
                # mirror listings.
                if not mirror.enabled:
                    mirror.enabled = True
                    reenabled_mirrors.append(canonical_url(mirror))

        if disabled_mirrors:
            self.logger.info(
                'Disabling %s mirror(s): %s'
                % (len(disabled_mirrors), ", ".join(disabled_mirrors)))
        if reenabled_mirrors:
            self.logger.info(
                'Re-enabling %s mirror(s): %s'
                % (len(reenabled_mirrors), ", ".join(reenabled_mirrors)))
        # XXX: salgado 2007-04-03:
        # This should be done in LaunchpadScript.lock_and_run() when
        # the isolation used is ISOLATION_LEVEL_AUTOCOMMIT. Also note
        # that replacing this with a flush_database_updates() doesn't
        # have the same effect, it seems.
        self.txn.commit()

        self.logger.info('Done.')
