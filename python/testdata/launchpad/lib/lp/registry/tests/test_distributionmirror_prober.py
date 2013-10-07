# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""distributionmirror-prober tests."""

__metaclass__ = type


from datetime import datetime
import httplib
import logging
import os
from StringIO import StringIO

from lazr.uri import URI
from sqlobject import SQLObjectNotFound
from twisted.internet import (
    defer,
    reactor,
    )
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase as TrialTestCase
from twisted.web import server
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.distributionmirror import DistributionMirror
from lp.registry.scripts import distributionmirror_prober
from lp.registry.scripts.distributionmirror_prober import (
    _build_request_for_cdimage_file_list,
    ArchiveMirrorProberCallbacks,
    BadResponseCode,
    ConnectionSkipped,
    InfiniteLoopDetected,
    LoggingMixin,
    MAX_REDIRECTS,
    MIN_REQUEST_TIMEOUT_RATIO,
    MIN_REQUESTS_TO_CONSIDER_RATIO,
    MirrorCDImageProberCallbacks,
    MultiLock,
    OVERALL_REQUESTS,
    PER_HOST_REQUESTS,
    probe_archive_mirror,
    probe_cdimage_mirror,
    ProberFactory,
    ProberTimeout,
    RedirectAwareProberFactory,
    RedirectAwareProberProtocol,
    RedirectToDifferentFile,
    RequestManager,
    restore_http_proxy,
    should_skip_host,
    UnknownURLSchemeAfterRedirect,
    )
from lp.registry.tests.distributionmirror_http_server import (
    DistributionMirrorTestHTTPServer,
    )
from lp.services.config import config
from lp.services.daemons.tachandler import TacTestSetup
from lp.testing import (
    clean_up_reactor,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    TwistedLayer,
    ZopelessDatabaseLayer,
    )


class HTTPServerTestSetup(TacTestSetup):

    def setUpRoot(self):
        pass

    @property
    def root(self):
        return '/var/tmp'

    @property
    def tacfile(self):
        return os.path.join(
            self.daemon_directory, 'distributionmirror_http_server.tac')

    @property
    def pidfile(self):
        return os.path.join(self.root, 'distributionmirror_http_server.pid')

    @property
    def logfile(self):
        return os.path.join(self.root, 'distributionmirror_http_server.log')


class TestProberProtocolAndFactory(TrialTestCase):

    layer = TwistedLayer

    def setUp(self):
        self.orig_proxy = os.getenv('http_proxy')
        root = DistributionMirrorTestHTTPServer()
        site = server.Site(root)
        site.displayTracebacks = False
        self.listening_port = reactor.listenTCP(0, site)
        self.port = self.listening_port.getHost().port
        self.urls = {'timeout': u'http://localhost:%s/timeout' % self.port,
                     '200': u'http://localhost:%s/valid-mirror' % self.port,
                     '500': u'http://localhost:%s/error' % self.port,
                     '404': u'http://localhost:%s/invalid-mirror' % self.port}

    def tearDown(self):
        restore_http_proxy(self.orig_proxy)
        return self.listening_port.stopListening()

    def _createProberAndProbe(self, url):
        prober = ProberFactory(url)
        return prober.probe()

    def test_environment_http_proxy_is_handled_correctly(self):
        os.environ['http_proxy'] = 'http://squid.internal:3128'
        prober = ProberFactory(self.urls['200'])
        self.failUnlessEqual(prober.request_host, 'localhost')
        self.failUnlessEqual(prober.request_port, self.port)
        self.failUnlessEqual(prober.request_path, '/valid-mirror')
        self.failUnlessEqual(prober.connect_host, 'squid.internal')
        self.failUnlessEqual(prober.connect_port, 3128)
        self.failUnlessEqual(prober.connect_path, self.urls['200'])

    def test_connect_cancels_existing_timeout_call(self):
        prober = ProberFactory(self.urls['200'])
        prober.timeoutCall = reactor.callLater(
            30, prober.failWithTimeoutError)
        old_timeout_call = prober.timeoutCall
        self.failUnless(old_timeout_call.active())
        prober.connect()
        self.failIf(old_timeout_call.active())
        self.failUnless(prober.timeoutCall.active())
        return prober._deferred

    def _test_connect_to_host(self, url, host):
        """Check that a ProberFactory created with the given url will actually
        connect to the given host.
        """
        prober = ProberFactory(url)

        def fakeConnect(host, port, factory):
            factory.connecting_to = host
            factory.succeeded('200')

        prober.connecting_to = None
        orig_connect = reactor.connectTCP
        reactor.connectTCP = fakeConnect

        def restore_connect(result, orig_connect):
            self.failUnlessEqual(prober.connecting_to, host)
            reactor.connectTCP = orig_connect
            return None

        deferred = prober.probe()
        return deferred.addCallback(restore_connect, orig_connect)

    def test_connect_to_proxy_when_http_proxy_exists(self):
        os.environ['http_proxy'] = 'http://squid.internal:3128'
        self._test_connect_to_host(self.urls['200'], 'squid.internal')

    def test_connect_to_host_when_http_proxy_does_not_exist(self):
        try:
            del os.environ['http_proxy']
        except KeyError:
            pass
        self._test_connect_to_host(self.urls['200'], 'localhost')

    def test_probe_sets_up_timeout_call(self):
        prober = ProberFactory(self.urls['200'])
        self.failUnless(getattr(prober, 'timeoutCall', None) is None)
        deferred = prober.probe()
        self.failUnless(getattr(prober, 'timeoutCall', None) is not None)
        return deferred

    def test_RedirectAwareProber_follows_http_redirect(self):
        url = 'http://localhost:%s/redirect-to-valid-mirror/file' % self.port
        prober = RedirectAwareProberFactory(url)
        self.failUnless(prober.redirection_count == 0)
        self.failUnless(prober.url == url)
        deferred = prober.probe()

        def got_result(result):
            self.failUnless(prober.redirection_count == 1)
            new_url = 'http://localhost:%s/valid-mirror/file' % self.port
            self.failUnless(prober.url == new_url)
            self.failUnless(result == str(httplib.OK))

        return deferred.addCallback(got_result)

    def test_redirectawareprober_detects_infinite_loop(self):
        prober = RedirectAwareProberFactory(
            'http://localhost:%s/redirect-infinite-loop' % self.port)
        deferred = prober.probe()
        return self.assertFailure(deferred, InfiniteLoopDetected)

    def test_redirectawareprober_fail_on_unknown_scheme(self):
        prober = RedirectAwareProberFactory(
            'http://localhost:%s/redirect-unknown-url-scheme' % self.port)
        deferred = prober.probe()
        return self.assertFailure(deferred, UnknownURLSchemeAfterRedirect)

    def test_200(self):
        d = self._createProberAndProbe(self.urls['200'])

        def got_result(result):
            self.failUnless(
                result == str(httplib.OK),
                "Expected a '200' status but got '%s'" % result)

        return d.addCallback(got_result)

    def test_success_cancel_timeout_call(self):
        prober = ProberFactory(self.urls['200'])
        deferred = prober.probe()
        self.failUnless(prober.timeoutCall.active())

        def check_timeout_call(result):
            self.failIf(prober.timeoutCall.active())

        return deferred.addCallback(check_timeout_call)

    def test_failure_cancel_timeout_call(self):
        prober = ProberFactory(self.urls['500'])
        deferred = prober.probe()
        self.failUnless(prober.timeoutCall.active())

        def check_timeout_call(result):
            self.failIf(prober.timeoutCall.active())

        return deferred.addErrback(check_timeout_call)

    def test_notfound(self):
        d = self._createProberAndProbe(self.urls['404'])
        return self.assertFailure(d, BadResponseCode)

    def test_500(self):
        d = self._createProberAndProbe(self.urls['500'])
        return self.assertFailure(d, BadResponseCode)

    def test_timeout(self):
        d = self._createProberAndProbe(self.urls['timeout'])
        return self.assertFailure(d, ProberTimeout)

    def test_prober_user_agent(self):
        protocol = RedirectAwareProberProtocol()

        orig_sendHeader = protocol.sendHeader
        headers = {}

        def mySendHeader(header, value):
            orig_sendHeader(header, value)
            headers[header] = value

        protocol.sendHeader = mySendHeader

        protocol.factory = FakeFactory('http://foo.bar/')
        protocol.makeConnection(FakeTransport())
        self.assertEquals(
            'Launchpad Mirror Prober ( https://launchpad.net/ )',
            headers['User-Agent'])


class FakeTimeOutCall:
    resetCalled = False

    def reset(self, seconds):
        self.resetCalled = True


class FakeTransport:
    disconnecting = False

    def loseConnection(self):
        self.disconnecting = True

    def write(self, text):
        pass

    def writeSequence(self, text):
        pass


class FakeFactory(RedirectAwareProberFactory):
    redirectedTo = None

    def redirect(self, url):
        self.redirectedTo = url


class TestProberFactoryRequestTimeoutRatioWithoutTwisted(TestCase):
    """Tests to ensure we stop issuing requests on a given host if the
    requests/timeouts ratio on that host is too low.

    The tests here will stub the prober's connect() method, so that we can
    easily check whether it was called or not without actually issuing any
    connections.
    """

    host = 'foo.bar'

    def setUp(self):
        super(TestProberFactoryRequestTimeoutRatioWithoutTwisted, self).setUp()
        self.orig_host_requests = dict(
            distributionmirror_prober.host_requests)
        self.orig_host_timeouts = dict(
            distributionmirror_prober.host_timeouts)

    def tearDown(self):
        # Restore the globals that our tests fiddle with.
        distributionmirror_prober.host_requests = self.orig_host_requests
        distributionmirror_prober.host_timeouts = self.orig_host_timeouts
        # We need to remove any DelayedCalls that didn't actually get called.
        clean_up_reactor()
        super(
            TestProberFactoryRequestTimeoutRatioWithoutTwisted,
            self).tearDown()

    def _createProberStubConnectAndProbe(self, requests, timeouts):
        """Create a ProberFactory object with a URL inside self.host and call
        its probe() method.

        Before the prober.probe() method is called, we stub the connect
        method, because all we want is to check whether that method was called
        or not --we don't want to actually connect.
        """
        def connect():
            prober.connectCalled = True
        distributionmirror_prober.host_requests = {self.host: requests}
        distributionmirror_prober.host_timeouts = {self.host: timeouts}
        prober = ProberFactory('http://%s/baz' % self.host)
        prober.connectCalled = False
        prober.failed = lambda error: None
        prober.connect = connect
        prober.probe()
        return prober

    def test_connect_is_called_if_not_enough_requests(self):
        """Test that only a small ratio is not enough to cause a host to be
        skipped; we also need to have a considerable number of requests.
        """
        requests = MIN_REQUESTS_TO_CONSIDER_RATIO - 1
        timeouts = requests
        prober = self._createProberStubConnectAndProbe(requests, timeouts)
        self.failUnless(prober.connectCalled)
        # Ensure the number of requests and timeouts we're using should
        # _NOT_ cause a given host to be skipped.
        self.failIf(should_skip_host(self.host))

    def test_connect_is_not_called_after_too_many_timeouts(self):
        """If we get a small requests/timeouts ratio on a given host, we'll
        stop issuing requests on that host.
        """
        # If the ratio is small enough and we have a considerable number of
        # requests, we won't issue more connections on that host.
        requests = MIN_REQUESTS_TO_CONSIDER_RATIO
        timeouts = (
            (MIN_REQUESTS_TO_CONSIDER_RATIO / MIN_REQUEST_TIMEOUT_RATIO) + 2)
        prober = self._createProberStubConnectAndProbe(requests, timeouts)
        self.failIf(prober.connectCalled)
        # Ensure the number of requests and timeouts we're using should
        # actually cause a given host to be skipped.
        self.failUnless(should_skip_host(self.host))

    def test_connect_is_called_if_not_many_timeouts(self):
        # If the ratio is not too small we consider it's safe to keep
        # issuing connections on that host.
        requests = MIN_REQUESTS_TO_CONSIDER_RATIO
        timeouts = (
            (MIN_REQUESTS_TO_CONSIDER_RATIO / MIN_REQUEST_TIMEOUT_RATIO) - 2)
        prober = self._createProberStubConnectAndProbe(requests, timeouts)
        self.failUnless(prober.connectCalled)
        # Ensure the number of requests and timeouts we're using should
        # _NOT_ cause a given host to be skipped.
        self.failIf(should_skip_host(self.host))


class TestProberFactoryRequestTimeoutRatioWithTwisted(TrialTestCase):
    """Tests to ensure we stop issuing requests on a given host if the
    requests/timeouts ratio on that host is too low.

    The tests here will check that we'll record a timeout whenever we get a
    ProberTimeout from twisted, as well as checking that twisted raises
    ConnectionSkipped when it finds a URL that should not be probed. This
    means that we need a test HTTP server as well as the twisted magic to
    actually connect to the server.
    """

    layer = TwistedLayer

    def setUp(self):
        self.orig_host_requests = dict(
            distributionmirror_prober.host_requests)
        self.orig_host_timeouts = dict(
            distributionmirror_prober.host_timeouts)
        distributionmirror_prober.host_requests = {}
        distributionmirror_prober.host_timeouts = {}
        root = DistributionMirrorTestHTTPServer()
        site = server.Site(root)
        site.displayTracebacks = False
        self.listening_port = reactor.listenTCP(0, site)
        self.port = self.listening_port.getHost().port

    def tearDown(self):
        # Restore the globals that our tests fiddle with.
        distributionmirror_prober.host_requests = self.orig_host_requests
        distributionmirror_prober.host_timeouts = self.orig_host_timeouts
        return self.listening_port.stopListening()

    def _createProberAndProbe(self, url):
        prober = ProberFactory(url)
        return prober.probe()

    def test_timeout_is_recorded(self):
        host = 'localhost'
        d = self._createProberAndProbe(
            u'http://%s:%s/timeout' % (host, self.port))

        def got_error(error):
            self.failUnlessEqual(
                {host: 1}, distributionmirror_prober.host_requests)
            self.failUnlessEqual(
                {host: 1}, distributionmirror_prober.host_timeouts)

        return d.addErrback(got_error)

    def test_non_timeout_is_recorded(self):
        host = 'localhost'
        d = self._createProberAndProbe(
            u'http://%s:%s/valid-mirror' % (host, self.port))

        def got_result(result):
            self.failUnlessEqual(
                {host: 1}, distributionmirror_prober.host_requests)
            self.failUnlessEqual(
                {host: 0}, distributionmirror_prober.host_timeouts)

        return d.addCallback(got_result)

    def test_failure_after_too_many_timeouts(self):
        host = 'foo.bar'
        requests = MIN_REQUESTS_TO_CONSIDER_RATIO
        timeouts = (
            (MIN_REQUESTS_TO_CONSIDER_RATIO / MIN_REQUEST_TIMEOUT_RATIO) + 2)
        distributionmirror_prober.host_requests = {host: requests}
        distributionmirror_prober.host_timeouts = {host: timeouts}
        # Ensure the number of requests and timeouts we're using should
        # cause a given host to be skipped.
        self.failUnless(should_skip_host(host))

        d = self._createProberAndProbe(
            u'http://%s:%s/timeout' % (host, self.port))
        return self.assertFailure(d, ConnectionSkipped)


class TestMultiLock(TestCase):

    def setUp(self):
        super(TestMultiLock, self).setUp()
        self.lock_one = defer.DeferredLock()
        self.lock_two = defer.DeferredLock()
        self.multi_lock = MultiLock(self.lock_one, self.lock_two)
        self.count = 0

    def callback(self):
        self.count += 1

    def test_run_does_not_wait_when_there_is_no_need_to(self):
        """Multilock.run will run any given task if it's not locked and
        there's no task currently running.
        """
        self.multi_lock.run(self.callback)
        self.assertEquals(self.count, 1, "self.callback should have run.")

        self.multi_lock.run(self.callback)
        self.assertEquals(
            self.count, 2, "self.callback should have run twice.")

    def test_run_waits_for_first_lock(self):
        """MultiLock.run acquires the first lock before running a function."""
        # Keep lock_one busy.
        deferred = defer.Deferred()
        self.lock_one.run(lambda: deferred)

        # Run self.callback when self.multi_lock is acquired.
        self.multi_lock.run(self.callback)
        self.assertEquals(
            self.count, 0, "self.callback should not have run yet.")

        # Release lock_one.
        deferred.callback(None)

        # multi_lock will now have been able to acquire both semaphores, and
        # so it will have run its task.
        self.assertEquals(self.count, 1, "self.callback should have run.")

    def test_run_waits_for_second_lock(self):
        """MultiLock.run acquires the second lock before running functions."""
        # Keep lock_two busy.
        deferred = defer.Deferred()
        self.lock_two.run(lambda: deferred)

        # Run self.callback when self.multi_lock is acquired.
        self.multi_lock.run(self.callback)
        self.assertEquals(
            self.count, 0, "self.callback should not have run yet.")

        # Release lock_two.
        deferred.callback(None)

        # multi_lock will now have been able to acquire both semaphores, and
        # so it will have run its task.
        self.assertEquals(self.count, 1, "self.callback should have run.")

    def test_run_waits_for_current_task(self):
        """MultiLock.run waits the end of the current task before running the
        next.
        """
        # Keep multi_lock busy.
        deferred = defer.Deferred()
        self.multi_lock.run(lambda: deferred)

        # Run self.callback when self.multi_lock is acquired.
        self.multi_lock.run(self.callback)
        self.assertEquals(
            self.count, 0, "self.callback should not have run yet.")

        # Release lock_one.
        deferred.callback(None)

        # multi_lock will now have been able to acquire both semaphores, and
        # so it will have run its task.
        self.assertEquals(self.count, 1, "self.callback should have run.")


class TestRedirectAwareProberFactoryAndProtocol(TestCase):

    def tearDown(self):
        # We need to remove any DelayedCalls that didn't actually get called.
        clean_up_reactor()
        super(TestRedirectAwareProberFactoryAndProtocol, self).tearDown()

    def test_redirect_resets_timeout(self):
        prober = RedirectAwareProberFactory('http://foo.bar')
        prober.timeoutCall = FakeTimeOutCall()
        prober.connect = lambda: None
        self.failIf(prober.timeoutCall.resetCalled)
        prober.redirect('http://bar.foo')
        self.failUnless(prober.timeoutCall.resetCalled)

    def _createFactoryAndStubConnectAndTimeoutCall(self, url=None):
        if url is None:
            url = 'http://foo.bar'
        prober = RedirectAwareProberFactory(url)
        prober.timeoutCall = FakeTimeOutCall()
        prober.connectCalled = False

        def connect():
            prober.connectCalled = True

        prober.connect = connect
        return prober

    def test_raises_error_if_redirected_to_different_file(self):
        prober = self._createFactoryAndStubConnectAndTimeoutCall(
            'http://foo.bar/baz/boo/package.deb')

        def failed(error):
            prober.has_failed = True

        prober.failed = failed
        prober.redirect('http://foo.bar/baz/boo/notfound?file=package.deb')
        self.failUnless(prober.has_failed)

    def test_does_not_raise_if_redirected_to_reencoded_file(self):
        prober = self._createFactoryAndStubConnectAndTimeoutCall(
            'http://foo.bar/baz/boo/package+foo.deb')

        def failed(error):
            prober.has_failed = True

        prober.failed = failed
        prober.redirect('http://foo.bar/baz/boo/package%2Bfoo.deb')
        self.assertFalse(hasattr(prober, 'has_failed'))

    def test_connect_depends_on_localhost_only_config(self):
        # If localhost_only is True and the host to which we would connect is
        # not localhost, the connect() method is not called.
        localhost_only_conf = """
            [distributionmirrorprober]
            localhost_only: True
            """
        config.push('localhost_only_conf', localhost_only_conf)
        prober = self._createFactoryAndStubConnectAndTimeoutCall()
        self.failUnless(prober.connect_host != 'localhost')
        prober.probe()
        self.failIf(prober.connectCalled)
        # Restore the config.
        config.pop('localhost_only_conf')

        # If localhost_only is False, then it doesn't matter the host to which
        # we'll connect to --the connect() method will be called.
        remote_conf = """
            [distributionmirrorprober]
            localhost_only: False
            """
        config.push('remote_conf', remote_conf)
        prober = self._createFactoryAndStubConnectAndTimeoutCall()
        prober.probe()
        self.failUnless(prober.connectCalled)
        # Restore the config.
        config.pop('remote_conf')

    def test_noconnection_is_made_when_infiniteloop_detected(self):
        prober = self._createFactoryAndStubConnectAndTimeoutCall()
        prober.failed = lambda error: None
        prober.redirection_count = MAX_REDIRECTS
        prober.redirect('http://bar.foo')
        self.failIf(prober.connectCalled)

    def test_noconnection_is_made_when_url_scheme_is_not_http_or_ftp(self):
        prober = self._createFactoryAndStubConnectAndTimeoutCall()
        prober.failed = lambda error: None
        prober.redirect('ssh://bar.foo')
        self.failIf(prober.connectCalled)

    def test_connection_is_made_on_successful_redirect(self):
        prober = self._createFactoryAndStubConnectAndTimeoutCall()
        prober.redirect('http://bar.foo')
        self.failUnless(prober.connectCalled)

    def test_connection_is_closed_on_redirect(self):
        protocol = RedirectAwareProberProtocol()
        protocol.factory = FakeFactory('http://foo.bar/')
        protocol.makeConnection(FakeTransport())
        protocol.dataReceived(
            "HTTP/1.1 301 Moved Permanently\r\n"
            "Location: http://foo.baz/\r\n"
            "Length: 0\r\n"
            "\r\n")
        self.assertEqual('http://foo.baz/', protocol.factory.redirectedTo)
        self.failUnless(protocol.transport.disconnecting)


class TestMirrorCDImageProberCallbacks(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def makeMirrorProberCallbacks(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries = removeSecurityProxy(
            self.factory.makeDistroSeries(distribution=ubuntu))
        mirror = removeSecurityProxy(
            self.factory.makeMirror(distroseries.distribution))
        callbacks = MirrorCDImageProberCallbacks(
            mirror, distroseries, 'ubuntu', StringIO())
        return callbacks

    def getLogger(self):
        logger = logging.getLogger('distributionmirror-prober')
        logger.errorCalled = False

        def error(msg):
            logger.errorCalled = True

        logger.error = error
        return logger

    def test_mirrorcdimageseries_creation_and_deletion_all_success(self):
        callbacks = self.makeMirrorProberCallbacks()
        all_success = [(defer.SUCCESS, '200'), (defer.SUCCESS, '200')]
        mirror_cdimage_series = callbacks.ensureOrDeleteMirrorCDImageSeries(
             all_success)
        self.assertIsNot(
            mirror_cdimage_series, None,
            "If the prober gets a list of 200 Okay statuses, a new "
            "MirrorCDImageSeries should be created.")

    def test_mirrorcdimageseries_creation_and_deletion_some_404s(self):
        not_all_success = [
            (defer.FAILURE, Failure(BadResponseCode(str(httplib.NOT_FOUND)))),
            (defer.SUCCESS, '200')]
        callbacks = self.makeMirrorProberCallbacks()
        all_success = [(defer.SUCCESS, '200'), (defer.SUCCESS, '200')]
        mirror_cdimage_series = callbacks.ensureOrDeleteMirrorCDImageSeries(
             all_success)
        callbacks.ensureOrDeleteMirrorCDImageSeries(not_all_success)
        # If the prober gets at least one 404 status, we need to make sure
        # there's no MirrorCDImageSeries for that series and flavour.
        self.assertRaises(
            SQLObjectNotFound, mirror_cdimage_series.get,
            mirror_cdimage_series.id)

    def test_expected_failures_are_ignored(self):
        # Any errors included in callbacks.expected_failures are simply
        # ignored by ensureOrDeleteMirrorCDImageSeries() because they've been
        # logged by logMissingURL() already and they're expected to happen
        # some times.
        logger = self.getLogger()
        callbacks = self.makeMirrorProberCallbacks()
        self.assertEqual(
            set(callbacks.expected_failures),
            set([
                BadResponseCode,
                ProberTimeout,
                ConnectionSkipped,
                RedirectToDifferentFile,
                UnknownURLSchemeAfterRedirect,
                ]))
        exceptions = [BadResponseCode(str(httplib.NOT_FOUND)),
                      ProberTimeout('http://localhost/', 5),
                      ConnectionSkipped(),
                      RedirectToDifferentFile('/foo', '/bar'),
                      UnknownURLSchemeAfterRedirect('https://localhost')]
        for exception in exceptions:
            failure = callbacks.ensureOrDeleteMirrorCDImageSeries(
                [(defer.FAILURE, Failure(exception))])
            # Twisted callbacks may raise or return a failure; that's why we
            # check the return value.
            self.failIf(isinstance(failure, Failure))
            # Also, these failures are not logged to stdout/stderr since
            # they're expected to happen.
            self.failIf(logger.errorCalled)

    def test_unexpected_failures_are_logged_but_not_raised(self):
        # Errors which are not expected as logged using the
        # prober's logger to make sure people see it while still alowing other
        # mirrors to be probed.
        logger = self.getLogger()
        callbacks = self.makeMirrorProberCallbacks()
        failure = callbacks.ensureOrDeleteMirrorCDImageSeries(
            [(defer.FAILURE, Failure(ZeroDivisionError()))])
        # Twisted callbacks may raise or return a failure; that's why we
        # check the return value.
        self.failIf(isinstance(failure, Failure))
        # Unlike the expected failures, these ones must be logged as errors to
        # stdout/stderr.
        self.failUnless(logger.errorCalled)


class TestArchiveMirrorProberCallbacks(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def makeMirrorProberCallbacks(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        distroseries = removeSecurityProxy(
            self.factory.makeDistroSeries(distribution=ubuntu))
        mirror = removeSecurityProxy(
            self.factory.makeMirror(distroseries.distribution))
        component = self.factory.makeComponent()
        callbacks = ArchiveMirrorProberCallbacks(
            mirror, distroseries, PackagePublishingPocket.RELEASE,
            component, 'foo', StringIO())
        return callbacks

    def test_failure_propagation(self):
        # Make sure that deleteMirrorSeries() does not propagate
        # ProberTimeout, BadResponseCode or ConnectionSkipped failures.
        callbacks = self.makeMirrorProberCallbacks()
        try:
            callbacks.deleteMirrorSeries(
                Failure(ProberTimeout('http://localhost/', 5)))
        except Exception as e:
            self.fail("A timeout shouldn't be propagated. Got %s" % e)
        try:
            callbacks.deleteMirrorSeries(
                Failure(BadResponseCode(str(httplib.INTERNAL_SERVER_ERROR))))
        except Exception as e:
            self.fail(
                "A bad response code shouldn't be propagated. Got %s" % e)
        try:
            callbacks.deleteMirrorSeries(Failure(ConnectionSkipped()))
        except Exception as e:
            self.fail("A ConnectionSkipped exception shouldn't be "
                      "propagated. Got %s" % e)

        # Make sure that deleteMirrorSeries() propagate any failure that is
        # not a ProberTimeout, a BadResponseCode or a ConnectionSkipped.
        d = defer.Deferred()
        d.addErrback(callbacks.deleteMirrorSeries)
        ok = []

        def got_result(result):
            self.fail(
                "Any failure that's not a timeout/bad-response/skipped "
                "should be propagated.")

        def got_failure(failure):
            ok.append(1)

        d.addCallbacks(got_result, got_failure)
        d.errback(Failure(ZeroDivisionError()))
        self.assertEqual([1], ok)

    def test_mirrorseries_creation_and_deletion(self):
        callbacks = self.makeMirrorProberCallbacks()
        mirror_distro_series_source = callbacks.ensureMirrorSeries(
             str(httplib.OK))
        self.assertIsNot(
            mirror_distro_series_source, None,
            "If the prober gets a 200 Okay status, a new "
            "MirrorDistroSeriesSource/MirrorDistroArchSeries should be "
            "created.")

        callbacks.deleteMirrorSeries(
            Failure(BadResponseCode(str(httplib.NOT_FOUND))))
        # If the prober gets a 404 status, we need to make sure there's no
        # MirrorDistroSeriesSource/MirrorDistroArchSeries referent to
        # that url
        self.assertRaises(
            SQLObjectNotFound, mirror_distro_series_source.get,
            mirror_distro_series_source.id)


class TestProbeFunctionSemaphores(TestCase):
    """Make sure we use one DeferredSemaphore for each hostname when probing
    mirrors.
    """
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestProbeFunctionSemaphores, self).setUp()
        self.logger = None
        # RequestManager uses a mutable class attribute (host_locks) to ensure
        # all of its instances share the same locks. We don't want our tests
        # to interfere with each other, though, so we'll clean
        # RequestManager.host_locks here.
        RequestManager.host_locks.clear()

    def tearDown(self):
        # We need to remove any DelayedCalls that didn't actually get called.
        clean_up_reactor()
        super(TestProbeFunctionSemaphores, self).tearDown()

    def test_MirrorCDImageSeries_records_are_deleted_before_probing(self):
        mirror = DistributionMirror.byName('releases-mirror2')
        self.failUnless(not mirror.cdimage_series.is_empty())
        # Note that calling this function won't actually probe any mirrors; we
        # need to call reactor.run() to actually start the probing.
        probe_cdimage_mirror(mirror, StringIO(), [], logging)
        self.failUnless(mirror.cdimage_series.is_empty())

    def test_archive_mirror_probe_function(self):
        mirror1 = DistributionMirror.byName('archive-mirror')
        mirror2 = DistributionMirror.byName('archive-mirror2')
        mirror3 = DistributionMirror.byName('canonical-archive')
        self._test_one_semaphore_for_each_host(
            mirror1, mirror2, mirror3, probe_archive_mirror)

    def test_cdimage_mirror_probe_function(self):
        mirror1 = DistributionMirror.byName('releases-mirror')
        mirror2 = DistributionMirror.byName('releases-mirror2')
        mirror3 = DistributionMirror.byName('canonical-releases')
        self._test_one_semaphore_for_each_host(
            mirror1, mirror2, mirror3, probe_cdimage_mirror)

    def _test_one_semaphore_for_each_host(
            self, mirror1, mirror2, mirror3, probe_function):
        """Check that we create one semaphore per host when probing the given
        mirrors using the given probe_function.

        mirror1.base_url and mirror2.base_url must be on the same host while
        mirror3.base_url must be on a different one.

        The given probe_function must be either probe_cdimage_mirror or
        probe_archive_mirror.
        """
        request_manager = RequestManager()
        mirror1_host = URI(mirror1.base_url).host
        mirror2_host = URI(mirror2.base_url).host
        mirror3_host = URI(mirror3.base_url).host

        probe_function(mirror1, StringIO(), [], logging)
        # Since we have a single mirror to probe we need to have a single
        # DeferredSemaphore with a limit of PER_HOST_REQUESTS, to ensure we
        # don't issue too many simultaneous connections on that host.
        self.assertEquals(len(request_manager.host_locks), 1)
        multi_lock = request_manager.host_locks[mirror1_host]
        self.assertEquals(multi_lock.host_lock.limit, PER_HOST_REQUESTS)
        # Note that our multi_lock contains another semaphore to control the
        # overall number of requests.
        self.assertEquals(multi_lock.overall_lock.limit, OVERALL_REQUESTS)

        probe_function(mirror2, StringIO(), [], logging)
        # Now we have two mirrors to probe, but they have the same hostname,
        # so we'll still have a single semaphore in host_semaphores.
        self.assertEquals(mirror2_host, mirror1_host)
        self.assertEquals(len(request_manager.host_locks), 1)
        multi_lock = request_manager.host_locks[mirror2_host]
        self.assertEquals(multi_lock.host_lock.limit, PER_HOST_REQUESTS)

        probe_function(mirror3, StringIO(), [], logging)
        # This third mirror is on a separate host, so we'll have a second
        # semaphore added to host_semaphores.
        self.failUnless(mirror3_host != mirror1_host)
        self.assertEquals(len(request_manager.host_locks), 2)
        multi_lock = request_manager.host_locks[mirror3_host]
        self.assertEquals(multi_lock.host_lock.limit, PER_HOST_REQUESTS)

        # When using an http_proxy, even though we'll actually connect to the
        # proxy, we'll use the mirror's host as the key to find the semaphore
        # that should be used
        orig_proxy = os.getenv('http_proxy')
        os.environ['http_proxy'] = 'http://squid.internal:3128/'
        probe_function(mirror3, StringIO(), [], logging)
        self.assertEquals(len(request_manager.host_locks), 2)
        restore_http_proxy(orig_proxy)


class TestCDImageFileListFetching(TestCase):

    def test_no_cache(self):
        url = 'http://releases.ubuntu.com/.manifest'
        request = _build_request_for_cdimage_file_list(url)
        self.failUnlessEqual(request.headers['Pragma'], 'no-cache')
        self.failUnlessEqual(request.headers['Cache-control'], 'no-cache')


class TestLoggingMixin(TestCase):

    def tearDown(self):
        # We need to remove any DelayedCalls that didn't actually get called.
        clean_up_reactor()
        super(TestLoggingMixin, self).tearDown()

    def _fake_gettime(self):
        # Fake the current time.
        fake_time = datetime(2004, 10, 20, 12, 00, 00, 000000)
        return fake_time

    def test_logMessage_output(self):
        logger = LoggingMixin()
        logger.log_file = StringIO()
        logger._getTime = self._fake_gettime
        logger.logMessage("Ubuntu Warty Released")
        logger.log_file.seek(0)
        message = logger.log_file.read()
        self.failUnlessEqual(
            'Wed Oct 20 12:00:00 2004: Ubuntu Warty Released',
            message)

    def test_logMessage_integration(self):
        logger = LoggingMixin()
        logger.log_file = StringIO()
        logger.logMessage("Probing...")
        logger.log_file.seek(0)
        message = logger.log_file.read()
        self.assertNotEqual(None, message)
