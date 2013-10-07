# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test BuilderInteractor features."""

import os
import signal
import tempfile
import xmlrpclib

from lpbuildd.slave import BuilderStatus
from testtools.deferredruntest import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    AsynchronousDeferredRunTestForBrokenTwisted,
    SynchronousDeferredRunTest,
    )
from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.web.client import getPage
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interactor import (
    BuilderInteractor,
    BuilderSlave,
    extract_vitals_from_db,
    )
from lp.buildmaster.interfaces.builder import (
    CannotFetchFile,
    CannotResumeHost,
    )
from lp.buildmaster.tests.mock_slaves import (
    AbortingSlave,
    BuildingSlave,
    DeadProxy,
    LostBuildingBrokenSlave,
    MockBuilder,
    OkSlave,
    SlaveTestHelpers,
    WaitingSlave,
    )
from lp.services.config import config
from lp.services.log.logger import DevNullLogger
from lp.soyuz.model.binarypackagebuildbehavior import (
    BinaryPackageBuildBehavior,
    )
from lp.testing import (
    clean_up_reactor,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class TestBuilderInteractor(TestCase):

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=10)

    def test_extractBuildStatus_baseline(self):
        # extractBuildStatus picks the name of the build status out of a
        # dict describing the slave's status.
        slave_status = {'build_status': 'BuildStatus.BUILDING'}
        self.assertEqual(
            'BUILDING', BuilderInteractor.extractBuildStatus(slave_status))

    def test_extractBuildStatus_malformed(self):
        # extractBuildStatus errors out when the status string is not
        # of the form it expects.
        slave_status = {'build_status': 'BUILDING'}
        self.assertRaises(
            AssertionError, BuilderInteractor.extractBuildStatus, slave_status)

    def resumeSlaveHost(self, builder):
        vitals = extract_vitals_from_db(builder)
        return BuilderInteractor.resumeSlaveHost(
            vitals, BuilderInteractor.makeSlaveFromVitals(vitals))

    def test_resumeSlaveHost_nonvirtual(self):
        d = self.resumeSlaveHost(MockBuilder(virtualized=False))
        return assert_fails_with(d, CannotResumeHost)

    def test_resumeSlaveHost_no_vmhost(self):
        d = self.resumeSlaveHost(MockBuilder(virtualized=False, vm_host=None))
        return assert_fails_with(d, CannotResumeHost)

    def test_resumeSlaveHost_success(self):
        reset_config = """
            [builddmaster]
            vm_resume_command: /bin/echo -n snap %(buildd_name)s %(vm_host)s
            """
        config.push('reset', reset_config)
        self.addCleanup(config.pop, 'reset')

        d = self.resumeSlaveHost(MockBuilder(
            url="http://crackle.ppa/", virtualized=True, vm_host="pop"))

        def got_resume(output):
            self.assertEqual(('snap crackle pop', ''), output)
        return d.addCallback(got_resume)

    def test_resumeSlaveHost_command_failed(self):
        reset_fail_config = """
            [builddmaster]
            vm_resume_command: /bin/false"""
        config.push('reset fail', reset_fail_config)
        self.addCleanup(config.pop, 'reset fail')
        d = self.resumeSlaveHost(MockBuilder(virtualized=True, vm_host="pop"))
        return assert_fails_with(d, CannotResumeHost)

    def test_resetOrFail_resume_failure(self):
        reset_fail_config = """
            [builddmaster]
            vm_resume_command: /bin/false"""
        config.push('reset fail', reset_fail_config)
        self.addCleanup(config.pop, 'reset fail')
        builder = MockBuilder(virtualized=True, vm_host="pop", builderok=True)
        vitals = extract_vitals_from_db(builder)
        d = BuilderInteractor.resetOrFail(
            vitals, BuilderInteractor.makeSlaveFromVitals(vitals), builder,
            DevNullLogger(), Exception())
        return assert_fails_with(d, CannotResumeHost)

    @defer.inlineCallbacks
    def test_resetOrFail_nonvirtual(self):
        builder = MockBuilder(virtualized=False, builderok=True)
        vitals = extract_vitals_from_db(builder)
        yield BuilderInteractor().resetOrFail(
            vitals, None, builder, DevNullLogger(), Exception())
        self.assertFalse(builder.builderok)

    def test_makeSlaveFromVitals(self):
        # Builder.slave is a BuilderSlave that points at the actual Builder.
        # The Builder is only ever used in scripts that run outside of the
        # security context.
        builder = MockBuilder(virtualized=False)
        vitals = extract_vitals_from_db(builder)
        slave = BuilderInteractor.makeSlaveFromVitals(vitals)
        self.assertEqual(builder.url, slave.url)
        self.assertEqual(10, slave.timeout)

        builder = MockBuilder(virtualized=True)
        vitals = extract_vitals_from_db(builder)
        slave = BuilderInteractor.makeSlaveFromVitals(vitals)
        self.assertEqual(5, slave.timeout)

    def test_rescueIfLost_aborts_lost_and_broken_slave(self):
        # A slave that's 'lost' should be aborted; when the slave is
        # broken then abort() should also throw a fault.
        slave = LostBuildingBrokenSlave()
        d = BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), slave, 'trivial')

        def check_slave_status(failure):
            self.assertIn('abort', slave.call_log)
            # 'Fault' comes from the LostBuildingBrokenSlave, this is
            # just testing that the value is passed through.
            self.assertIsInstance(failure.value, xmlrpclib.Fault)

        return d.addBoth(check_slave_status)

    @defer.inlineCallbacks
    def test_recover_idle_slave(self):
        # An idle slave is not rescued, even if it's not meant to be
        # idle. SlaveScanner.scan() will clean up the DB side, because
        # we still report that it's lost.
        slave = OkSlave()
        lost = yield BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), slave, 'trivial')
        self.assertTrue(lost)
        self.assertEqual([], slave.call_log)

    @defer.inlineCallbacks
    def test_recover_ok_slave(self):
        # An idle slave that's meant to be idle is not rescued.
        slave = OkSlave()
        lost = yield BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), slave, None)
        self.assertFalse(lost)
        self.assertEqual([], slave.call_log)

    @defer.inlineCallbacks
    def test_recover_waiting_slave_with_good_id(self):
        # rescueIfLost does not attempt to abort or clean a builder that is
        # WAITING.
        waiting_slave = WaitingSlave(build_id='trivial')
        lost = yield BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), waiting_slave, 'trivial')
        self.assertFalse(lost)
        self.assertEqual(['status'], waiting_slave.call_log)

    @defer.inlineCallbacks
    def test_recover_waiting_slave_with_bad_id(self):
        # If a slave is WAITING with a build for us to get, and the build
        # cookie cannot be verified, which means we don't recognize the build,
        # then rescueBuilderIfLost should attempt to abort it, so that the
        # builder is reset for a new build, and the corrupt build is
        # discarded.
        waiting_slave = WaitingSlave(build_id='non-trivial')
        lost = yield BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), waiting_slave, 'trivial')
        self.assertTrue(lost)
        self.assertEqual(['status', 'clean'], waiting_slave.call_log)

    @defer.inlineCallbacks
    def test_recover_building_slave_with_good_id(self):
        # rescueIfLost does not attempt to abort or clean a builder that is
        # BUILDING.
        building_slave = BuildingSlave(build_id='trivial')
        lost = yield BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), building_slave, 'trivial')
        self.assertFalse(lost)
        self.assertEqual(['status'], building_slave.call_log)

    @defer.inlineCallbacks
    def test_recover_building_slave_with_bad_id(self):
        # If a slave is BUILDING with a build id we don't recognize, then we
        # abort the build, thus stopping it in its tracks.
        building_slave = BuildingSlave(build_id='non-trivial')
        lost = yield BuilderInteractor.rescueIfLost(
            extract_vitals_from_db(MockBuilder()), building_slave, 'trivial')
        self.assertTrue(lost)
        self.assertEqual(['status', 'abort'], building_slave.call_log)


class TestBuilderInteractorSlaveStatus(TestCase):
    # Verify what BuilderInteractor.slaveStatus returns with slaves in
    # different states.

    run_tests_with = AsynchronousDeferredRunTest

    @defer.inlineCallbacks
    def assertStatus(self, slave, builder_status=None,
                     build_status=None, logtail=False, filemap=None,
                     dependencies=None):
        statuses = yield BuilderInteractor.slaveStatus(slave)
        status_dict = statuses[1]

        expected = {}
        if builder_status is not None:
            expected["builder_status"] = builder_status
        if build_status is not None:
            expected["build_status"] = build_status
        if dependencies is not None:
            expected["dependencies"] = dependencies

        # We don't care so much about the content of the logtail,
        # just that it's there.
        if logtail:
            tail = status_dict.pop("logtail")
            self.assertIsInstance(tail, xmlrpclib.Binary)

        self.assertEqual(expected, status_dict)

    def test_slaveStatus_idle_slave(self):
        self.assertStatus(
            OkSlave(), builder_status='BuilderStatus.IDLE')

    def test_slaveStatus_building_slave(self):
        self.assertStatus(
            BuildingSlave(), builder_status='BuilderStatus.BUILDING',
            logtail=True)

    def test_slaveStatus_waiting_slave(self):
        self.assertStatus(
            WaitingSlave(), builder_status='BuilderStatus.WAITING',
            build_status='BuildStatus.OK', filemap={})

    def test_slaveStatus_aborting_slave(self):
        self.assertStatus(
            AbortingSlave(), builder_status='BuilderStatus.ABORTING')


class TestBuilderInteractorDB(TestCaseWithFactory):
    """BuilderInteractor tests that need a DB."""

    layer = ZopelessDatabaseLayer
    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=10)

    def test_getBuildBehavior_idle(self):
        """An idle builder has no build behavior."""
        self.assertIs(
            None,
            BuilderInteractor.getBuildBehavior(None, MockBuilder(), None))

    def test_getBuildBehavior_building(self):
        """The current behavior is set automatically from the current job."""
        # Set the builder attribute on the buildqueue record so that our
        # builder will think it has a current build.
        builder = self.factory.makeBuilder(name='builder')
        slave = BuildingSlave()
        build = self.factory.makeBinaryPackageBuild()
        bq = build.queueBuild()
        bq.markAsBuilding(builder)
        behavior = BuilderInteractor.getBuildBehavior(bq, builder, slave)
        self.assertIsInstance(behavior, BinaryPackageBuildBehavior)
        self.assertEqual(behavior._builder, builder)
        self.assertEqual(behavior._slave, slave)

    def _setupBuilder(self):
        processor = self.factory.makeProcessor(name="i386")
        builder = self.factory.makeBuilder(
            processor=processor, virtualized=True, vm_host="bladh")
        self.patch(BuilderSlave, 'makeBuilderSlave', FakeMethod(OkSlave()))
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="i386",
            processor=processor)
        chroot = self.factory.makeLibraryFileAlias(db_only=True)
        das.addOrUpdateChroot(chroot)
        distroseries.nominatedarchindep = das
        return builder, distroseries, das

    def _setupRecipeBuildAndBuilder(self):
        # Helper function to make a builder capable of building a
        # recipe, returning both.
        builder, distroseries, distroarchseries = self._setupBuilder()
        build = self.factory.makeSourcePackageRecipeBuild(
            distroseries=distroseries)
        return builder, build

    def _setupBinaryBuildAndBuilder(self):
        # Helper function to make a builder capable of building a
        # binary package, returning both.
        builder, distroseries, distroarchseries = self._setupBuilder()
        build = self.factory.makeBinaryPackageBuild(
            distroarchseries=distroarchseries, builder=builder)
        return builder, build

    def test_findAndStartJob_returns_candidate(self):
        # findAndStartJob finds the next queued job using _findBuildCandidate.
        # We don't care about the type of build at all.
        builder, build = self._setupRecipeBuildAndBuilder()
        candidate = build.queueBuild()
        # _findBuildCandidate is tested elsewhere, we just make sure that
        # findAndStartJob delegates to it.
        removeSecurityProxy(builder)._findBuildCandidate = FakeMethod(
            result=candidate)
        vitals = extract_vitals_from_db(builder)
        d = BuilderInteractor.findAndStartJob(vitals, builder, OkSlave())
        return d.addCallback(self.assertEqual, candidate)

    def test_findAndStartJob_starts_job(self):
        # findAndStartJob finds the next queued job using _findBuildCandidate
        # and then starts it.
        # We don't care about the type of build at all.
        builder, build = self._setupRecipeBuildAndBuilder()
        candidate = build.queueBuild()
        removeSecurityProxy(builder)._findBuildCandidate = FakeMethod(
            result=candidate)
        vitals = extract_vitals_from_db(builder)
        d = BuilderInteractor.findAndStartJob(vitals, builder, OkSlave())

        def check_build_started(candidate):
            self.assertEqual(candidate.builder, builder)
            self.assertEqual(BuildStatus.BUILDING, build.status)

        return d.addCallback(check_build_started)

    def test_virtual_job_dispatch_pings_before_building(self):
        # We need to send a ping to the builder to work around a bug
        # where sometimes the first network packet sent is dropped.
        builder, build = self._setupBinaryBuildAndBuilder()
        candidate = build.queueBuild()
        removeSecurityProxy(builder)._findBuildCandidate = FakeMethod(
            result=candidate)
        vitals = extract_vitals_from_db(builder)
        slave = OkSlave()
        d = BuilderInteractor.findAndStartJob(vitals, builder, slave)

        def check_build_started(candidate):
            self.assertIn(('echo', 'ping'), slave.call_log)

        return d.addCallback(check_build_started)


class TestSlave(TestCase):
    """
    Integration tests for BuilderSlave that verify how it works against a
    real slave server.
    """

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=10)

    def setUp(self):
        super(TestSlave, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())

    def test_abort(self):
        slave = self.slave_helper.getClientSlave()
        # We need to be in a BUILDING state before we can abort.
        d = self.slave_helper.triggerGoodBuild(slave)
        d.addCallback(lambda ignored: slave.abort())
        d.addCallback(self.assertEqual, BuilderStatus.ABORTING)
        return d

    def test_build(self):
        # Calling 'build' with an expected builder type, a good build id,
        # valid chroot & filemaps works and returns a BuilderStatus of
        # BUILDING.
        build_id = 'some-id'
        slave = self.slave_helper.getClientSlave()
        d = self.slave_helper.triggerGoodBuild(slave, build_id)
        return d.addCallback(
            self.assertEqual, [BuilderStatus.BUILDING, build_id])

    def test_clean(self):
        slave = self.slave_helper.getClientSlave()
        # XXX: JonathanLange 2010-09-21: Calling clean() on the slave requires
        # it to be in either the WAITING or ABORTED states, and both of these
        # states are very difficult to achieve in a test environment. For the
        # time being, we'll just assert that a clean attribute exists.
        self.assertNotEqual(getattr(slave, 'clean', None), None)

    def test_echo(self):
        # Calling 'echo' contacts the server which returns the arguments we
        # gave it.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.echo('foo', 'bar', 42)
        return d.addCallback(self.assertEqual, ['foo', 'bar', 42])

    def test_info(self):
        # Calling 'info' gets some information about the slave.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.info()
        # We're testing the hard-coded values, since the version is hard-coded
        # into the remote slave, the supported build managers are hard-coded
        # into the tac file for the remote slave and config is returned from
        # the configuration file.
        return d.addCallback(
            self.assertEqual,
            ['1.0',
             'i386',
             ['sourcepackagerecipe',
              'translation-templates', 'binarypackage', 'debian']])

    def test_initial_status(self):
        # Calling 'status' returns the current status of the slave. The
        # initial status is IDLE.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.status()
        return d.addCallback(self.assertEqual, [BuilderStatus.IDLE, ''])

    def test_status_after_build(self):
        # Calling 'status' returns the current status of the slave. After a
        # build has been triggered, the status is BUILDING.
        slave = self.slave_helper.getClientSlave()
        build_id = 'status-build-id'
        d = self.slave_helper.triggerGoodBuild(slave, build_id)
        d.addCallback(lambda ignored: slave.status())

        def check_status(status):
            self.assertEqual([BuilderStatus.BUILDING, build_id], status[:2])
            [log_file] = status[2:]
            self.assertIsInstance(log_file, xmlrpclib.Binary)

        return d.addCallback(check_status)

    def test_ensurepresent_not_there(self):
        # ensurepresent checks to see if a file is there.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.ensurepresent('blahblah', None, None, None)
        d.addCallback(self.assertEqual, [False, 'No URL'])
        return d

    def test_ensurepresent_actually_there(self):
        # ensurepresent checks to see if a file is there.
        tachandler = self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        self.slave_helper.makeCacheFile(tachandler, 'blahblah')
        d = slave.ensurepresent('blahblah', None, None, None)
        d.addCallback(self.assertEqual, [True, 'No URL'])
        return d

    def test_sendFileToSlave_not_there(self):
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.sendFileToSlave('blahblah', None, None, None)
        return assert_fails_with(d, CannotFetchFile)

    def test_sendFileToSlave_actually_there(self):
        tachandler = self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        self.slave_helper.makeCacheFile(tachandler, 'blahblah')
        d = slave.sendFileToSlave('blahblah', None, None, None)

        def check_present(ignored):
            d = slave.ensurepresent('blahblah', None, None, None)
            return d.addCallback(self.assertEqual, [True, 'No URL'])

        d.addCallback(check_present)
        return d

    def test_resumeHost_success(self):
        # On a successful resume resume() fires the returned deferred
        # callback with 'None'.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()

        # The configuration testing command-line.
        self.assertEqual(
            'echo %(vm_host)s', config.builddmaster.vm_resume_command)

        # On success the response is None.
        def check_resume_success(response):
            out, err, code = response
            self.assertEqual(os.EX_OK, code)
            # XXX: JonathanLange 2010-09-23: We should instead pass the
            # expected vm_host into the client slave. Not doing this now,
            # since the SlaveHelper is being moved around.
            self.assertEqual("%s\n" % slave._vm_host, out)
        d = slave.resume()
        d.addBoth(check_resume_success)
        return d

    def test_resumeHost_failure(self):
        # On a failed resume, 'resumeHost' fires the returned deferred
        # errorback with the `ProcessTerminated` failure.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()

        # Override the configuration command-line with one that will fail.
        failed_config = """
        [builddmaster]
        vm_resume_command: test "%(vm_host)s = 'no-sir'"
        """
        config.push('failed_resume_command', failed_config)
        self.addCleanup(config.pop, 'failed_resume_command')

        # On failures, the response is a twisted `Failure` object containing
        # a tuple.
        def check_resume_failure(failure):
            out, err, code = failure.value
            # The process will exit with a return code of "1".
            self.assertEqual(code, 1)
        d = slave.resume()
        d.addBoth(check_resume_failure)
        return d

    def test_resumeHost_timeout(self):
        # On a resume timeouts, 'resumeHost' fires the returned deferred
        # errorback with the `TimeoutError` failure.

        # Override the configuration command-line with one that will timeout.
        timeout_config = """
        [builddmaster]
        vm_resume_command: sleep 5
        socket_timeout: 1
        """
        config.push('timeout_resume_command', timeout_config)
        self.addCleanup(config.pop, 'timeout_resume_command')

        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()

        # On timeouts, the response is a twisted `Failure` object containing
        # a `TimeoutError` error.
        def check_resume_timeout(failure):
            self.assertIsInstance(failure, Failure)
            out, err, code = failure.value
            self.assertEqual(code, signal.SIGKILL)
        clock = Clock()
        d = slave.resume(clock=clock)
        # Move the clock beyond the socket_timeout but earlier than the
        # sleep 5.  This stops the test having to wait for the timeout.
        # Fast tests FTW!
        clock.advance(2)
        d.addBoth(check_resume_timeout)
        return d


class TestSlaveTimeouts(TestCase):
    # Testing that the methods that call callRemote() all time out
    # as required.

    run_tests_with = AsynchronousDeferredRunTestForBrokenTwisted

    def setUp(self):
        super(TestSlaveTimeouts, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())
        self.clock = Clock()
        self.proxy = DeadProxy("url")
        self.slave = self.slave_helper.getClientSlave(
            reactor=self.clock, proxy=self.proxy)

    def assertCancelled(self, d):
        self.clock.advance(config.builddmaster.socket_timeout + 1)
        return assert_fails_with(d, defer.CancelledError)

    def test_timeout_abort(self):
        return self.assertCancelled(self.slave.abort())

    def test_timeout_clean(self):
        return self.assertCancelled(self.slave.clean())

    def test_timeout_echo(self):
        return self.assertCancelled(self.slave.echo())

    def test_timeout_info(self):
        return self.assertCancelled(self.slave.info())

    def test_timeout_status(self):
        return self.assertCancelled(self.slave.status())

    def test_timeout_ensurepresent(self):
        return self.assertCancelled(
            self.slave.ensurepresent(None, None, None, None))

    def test_timeout_build(self):
        return self.assertCancelled(
            self.slave.build(None, None, None, None, None))


class TestSlaveConnectionTimeouts(TestCase):
    # Testing that we can override the default 30 second connection
    # timeout.

    run_test = SynchronousDeferredRunTest

    def setUp(self):
        super(TestSlaveConnectionTimeouts, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())
        self.clock = Clock()

    def tearDown(self):
        # We need to remove any DelayedCalls that didn't actually get called.
        clean_up_reactor()
        super(TestSlaveConnectionTimeouts, self).tearDown()

    def test_connection_timeout(self):
        # The default timeout of 30 seconds should not cause a timeout,
        # only the config value should.
        self.pushConfig('builddmaster', socket_timeout=180)

        slave = self.slave_helper.getClientSlave(reactor=self.clock)
        d = slave.echo()
        # Advance past the 30 second timeout.  The real reactor will
        # never call connectTCP() since we're not spinning it up.  This
        # avoids "connection refused" errors and simulates an
        # environment where the endpoint doesn't respond.
        self.clock.advance(31)
        self.assertFalse(d.called)

        self.clock.advance(config.builddmaster.socket_timeout + 1)
        self.assertTrue(d.called)
        return assert_fails_with(d, defer.CancelledError)


class TestSlaveWithLibrarian(TestCaseWithFactory):
    """Tests that need more of Launchpad to run."""

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=20)

    def setUp(self):
        super(TestSlaveWithLibrarian, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())

    def test_ensurepresent_librarian(self):
        # ensurepresent, when given an http URL for a file will download the
        # file from that URL and report that the file is present, and it was
        # downloaded.

        # Use the Librarian because it's a "convenient" web server.
        lf = self.factory.makeLibraryFileAlias(
            'HelloWorld.txt', content="Hello World")
        self.layer.txn.commit()
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.ensurepresent(
            lf.content.sha1, lf.http_url, "", "")
        d.addCallback(self.assertEqual, [True, 'Download'])
        return d

    def test_retrieve_files_from_filecache(self):
        # Files that are present on the slave can be downloaded with a
        # filename made from the sha1 of the content underneath the
        # 'filecache' directory.
        content = "Hello World"
        lf = self.factory.makeLibraryFileAlias(
            'HelloWorld.txt', content=content)
        self.layer.txn.commit()
        expected_url = '%s/filecache/%s' % (
            self.slave_helper.BASE_URL, lf.content.sha1)
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.ensurepresent(
            lf.content.sha1, lf.http_url, "", "")

        def check_file(ignored):
            d = getPage(expected_url.encode('utf8'))
            return d.addCallback(self.assertEqual, content)

        return d.addCallback(check_file)

    def test_getFiles(self):
        # Test BuilderSlave.getFiles().
        # It also implicitly tests getFile() - I don't want to test that
        # separately because it increases test run time and it's going
        # away at some point anyway, in favour of getFiles().
        contents = ["content1", "content2", "content3"]
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        filemap = {}
        content_map = {}

        def got_files(ignored):
            # Called back when getFiles finishes.  Make sure all the
            # content is as expected.
            for sha1 in filemap:
                local_file = filemap[sha1]
                file = open(local_file)
                self.assertEqual(content_map[sha1], file.read())
                file.close()

        def finished_uploading(ignored):
            d = slave.getFiles(filemap)
            return d.addCallback(got_files)

        # Set up some files on the builder and store details in
        # content_map so we can compare downloads later.
        dl = []
        for content in contents:
            filename = content + '.txt'
            lf = self.factory.makeLibraryFileAlias(filename, content=content)
            content_map[lf.content.sha1] = content
            fd, filemap[lf.content.sha1] = tempfile.mkstemp()
            self.addCleanup(os.remove, filemap[lf.content.sha1])
            self.layer.txn.commit()
            d = slave.ensurepresent(lf.content.sha1, lf.http_url, "", "")
            dl.append(d)

        return defer.DeferredList(dl).addCallback(finished_uploading)
