# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Layers used by Launchpad tests.

Layers are the mechanism used by the Zope3 test runner to efficiently
provide environments for tests and are documented in the lib/zope/testing.

Note that every Layer should define all of setUp, tearDown, testSetUp
and testTearDown. If you don't do this, a base class' method will be called
instead probably breaking something.

Preferred style is to not use the 'cls' argument to Layer class methods,
as this is unambguious.

TODO: Make the Zope3 test runner handle multiple layers per test instead
of one, forcing us to attempt to make some sort of layer tree.
-- StuartBishop 20060619
"""

__metaclass__ = type
__all__ = [
    'AppServerLayer',
    'AuditorLayer',
    'BaseLayer',
    'DatabaseFunctionalLayer',
    'DatabaseLayer',
    'FunctionalLayer',
    'GoogleLaunchpadFunctionalLayer',
    'GoogleServiceLayer',
    'LaunchpadFunctionalLayer',
    'LaunchpadLayer',
    'LaunchpadScriptLayer',
    'LaunchpadTestSetup',
    'LaunchpadZopelessLayer',
    'LayerInvariantError',
    'LayerIsolationError',
    'LibrarianLayer',
    'PageTestLayer',
    'RabbitMQLayer',
    'SwiftLayer',
    'TwistedAppServerLayer',
    'TwistedLaunchpadZopelessLayer',
    'TwistedLayer',
    'YUITestLayer',
    'YUIAppServerLayer',
    'ZopelessAppServerLayer',
    'ZopelessDatabaseLayer',
    'ZopelessLayer',
    'disconnect_stores',
    'reconnect_stores',
    'wsgi_application',
    ]

from cProfile import Profile
import datetime
import errno
import gc
import logging
import os
import signal
import socket
import subprocess
import sys
import tempfile
from textwrap import dedent
import threading
import time
from unittest import (
    TestCase,
    TestResult,
    )
from urllib import urlopen

from fixtures import (
    Fixture,
    MonkeyPatch,
    )
import psycopg2
from storm.zope.interfaces import IZStorm
import transaction
import wsgi_intercept
from wsgi_intercept import httplib2_intercept
from zope.app.publication.httpfactory import chooseClasses
import zope.app.testing.functional
from zope.app.testing.functional import (
    FunctionalTestSetup,
    ZopePublication,
    )
from zope.component import (
    getUtility,
    globalregistry,
    provideUtility,
    )
from zope.component.interfaces import ComponentLookupError
import zope.publisher.publish
from zope.security.management import (
    endInteraction,
    getSecurityPolicy,
    )
from zope.server.logger.pythonlogger import PythonLogger

from lp.services import pidfile
from lp.services.auditor.server import AuditorServer
from lp.services.config import (
    config,
    dbconfig,
    LaunchpadConfig,
    )
from lp.services.config.fixture import (
    ConfigFixture,
    ConfigUseFixture,
    )
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import session_store
from lp.services.googlesearch.tests.googleserviceharness import (
    GoogleServiceTestSetup,
    )
from lp.services.job.tests import celeryd
from lp.services.librarian.model import LibraryFileAlias
from lp.services.librarianserver.testing.server import LibrarianServerFixture
from lp.services.mail.mailbox import (
    IMailBox,
    TestMailBox,
    )
from lp.services.mail.sendmail import set_immediate_mail_delivery
import lp.services.mail.stub
from lp.services.memcache.client import memcache_client_factory
from lp.services.osutils import kill_by_pidfile
from lp.services.rabbit.server import RabbitServer
from lp.services.scripts import execute_zcml_for_scripts
from lp.services.testing.profiled import profiled
from lp.services.timeout import (
    get_default_timeout_function,
    set_default_timeout_function,
    )
from lp.services.webapp.authorization import LaunchpadPermissiveSecurityPolicy
from lp.services.webapp.interfaces import IOpenLaunchBag
from lp.services.webapp.servers import (
    LaunchpadAccessLogger,
    register_launchpad_request_publication_factories,
    )
import lp.services.webapp.session
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    reset_logging,
    )
from lp.testing.pgsql import PgTestSetup
from lp.testing.swift.fixture import SwiftFixture
from lp.testing.smtpd import SMTPController


orig__call__ = zope.app.testing.functional.HTTPCaller.__call__
COMMA = ','
WAIT_INTERVAL = datetime.timedelta(seconds=180)


def set_up_functional_test():
    return FunctionalTestSetup('zcml/ftesting.zcml')


class LayerError(Exception):
    pass


class LayerInvariantError(LayerError):
    """Layer self checks have detected a fault. Invariant has been violated.

    This indicates the Layer infrastructure has messed up. The test run
    should be aborted.
    """
    pass


class LayerIsolationError(LayerError):
    """Test isolation has been broken, probably by the test we just ran.

    This generally indicates a test has screwed up by not resetting
    something correctly to the default state.

    The test suite should abort if it cannot clean up the mess as further
    test failures may well be spurious.
    """


def is_ca_available():
    """Returns true if the component architecture has been loaded"""
    try:
        getUtility(IOpenLaunchBag)
    except ComponentLookupError:
        return False
    else:
        return True


def disconnect_stores():
    """Disconnect Storm stores."""
    zstorm = getUtility(IZStorm)
    stores = [
        store for name, store in zstorm.iterstores() if name != 'session']

    # If we have any stores, abort the transaction and close them.
    if stores:
        for store in stores:
            zstorm.remove(store)
        transaction.abort()
        for store in stores:
            store.close()


def reconnect_stores(reset=False):
    """Reconnect Storm stores, resetting the dbconfig to its defaults.

    After reconnecting, the database revision will be checked to make
    sure the right data is available.
    """
    disconnect_stores()
    if reset:
        dbconfig.reset()

    main_store = IStore(LibraryFileAlias)
    assert main_store is not None, 'Failed to reconnect'

    # Confirm that SQLOS is again talking to the database (it connects
    # as soon as SQLBase._connection is accessed
    r = main_store.execute('SELECT count(*) FROM LaunchpadDatabaseRevision')
    assert r.get_one()[0] > 0, 'Storm is not talking to the database'
    assert session_store() is not None, 'Failed to reconnect'


def wait_children(seconds=120):
    """Wait for all children to exit.

    :param seconds: Maximum number of seconds to wait.  If None, wait
        forever.
    """
    now = datetime.datetime.now
    if seconds is None:
        until = None
    else:
        until = now() + datetime.timedelta(seconds=seconds)
    while True:
        try:
            os.waitpid(-1, os.WNOHANG)
        except OSError as error:
            if error.errno != errno.ECHILD:
                raise
            break
        if until is not None and now() > until:
            break


class MockRootFolder:
    """Implement the minimum functionality required by Z3 ZODB dependencies

    Installed as part of FunctionalLayer.testSetUp() to allow the http()
    method (zope.app.testing.functional.HTTPCaller) to work.
    """
    @property
    def _p_jar(self):
        return self

    def sync(self):
        pass


class BaseLayer:
    """Base layer.

    All our layers should subclass Base, as this is where we will put
    test isolation checks to ensure that tests to not leave global
    resources in a mess.

    XXX: StuartBishop 2006-07-12: Unit tests (tests with no layer) will not
    get these checks. The Z3 test runner should be updated so that a layer
    can be specified to use for unit tests.
    """
    # Set to True when we are running tests in this layer.
    isSetUp = False

    # The name of this test - this is the same output that the testrunner
    # displays. It is probably unique, but not guaranteed to be so.
    test_name = None

    # A flag to disable a check for threads still running after test
    # completion.  This is hopefully a temporary measure; see the comment
    # in tearTestDown.
    disable_thread_check = False

    # A flag to make services like Librarian and Memcached to persist
    # between test runs. This flag is set in setUp() by looking at the
    # LP_PERSISTENT_TEST_SERVICES environment variable.
    persist_test_services = False

    # Things we need to cleanup.
    fixture = None

    # ConfigFixtures for the configs generated for this layer. Set to None
    # if the layer is not setUp, or if persistent tests services are in use.
    config_fixture = None
    appserver_config_fixture = None

    # The config names that are generated for this layer. Set to None when
    # the layer is not setUp.
    config_name = None
    appserver_config_name = None

    @classmethod
    def make_config(cls, config_name, clone_from, attr_name):
        """Create a temporary config and link it into the layer cleanup."""
        cfg_fixture = ConfigFixture(config_name, clone_from)
        cls.fixture.addCleanup(cfg_fixture.cleanUp)
        cfg_fixture.setUp()
        cls.fixture.addCleanup(setattr, cls, attr_name, None)
        setattr(cls, attr_name, cfg_fixture)

    @classmethod
    @profiled
    def setUp(cls):
        # Set the default appserver config instance name.
        # May be changed as required eg when running parallel tests.
        cls.appserver_config_name = 'testrunner-appserver'
        BaseLayer.isSetUp = True
        cls.fixture = Fixture()
        cls.fixture.setUp()
        cls.fixture.addCleanup(setattr, cls, 'fixture', None)
        BaseLayer.persist_test_services = (
            os.environ.get('LP_PERSISTENT_TEST_SERVICES') is not None)
        # We can only do unique test allocation and parallelisation if
        # LP_PERSISTENT_TEST_SERVICES is off.
        if not BaseLayer.persist_test_services:
            test_instance = str(os.getpid())
            os.environ['LP_TEST_INSTANCE'] = test_instance
            cls.fixture.addCleanup(os.environ.pop, 'LP_TEST_INSTANCE', '')
            # Kill any Memcached or Librarian left running from a previous
            # test run, or from the parent test process if the current
            # layer is being run in a subprocess. No need to be polite
            # about killing memcached - just do it quickly.
            kill_by_pidfile(MemcachedLayer.getPidFile(), num_polls=0)
            config_name = 'testrunner_%s' % test_instance
            cls.make_config(config_name, 'testrunner', 'config_fixture')
            app_config_name = 'testrunner-appserver_%s' % test_instance
            cls.make_config(
                app_config_name, 'testrunner-appserver',
                'appserver_config_fixture')
            cls.appserver_config_name = app_config_name
        else:
            config_name = 'testrunner'
            app_config_name = 'testrunner-appserver'
        cls.config_name = config_name
        cls.fixture.addCleanup(setattr, cls, 'config_name', None)
        cls.appserver_config_name = app_config_name
        cls.fixture.addCleanup(setattr, cls, 'appserver_config_name', None)
        use_fixture = ConfigUseFixture(config_name)
        cls.fixture.addCleanup(use_fixture.cleanUp)
        use_fixture.setUp()
        # Kill any database left lying around from a previous test run.
        db_fixture = LaunchpadTestSetup()
        try:
            db_fixture.connect().close()
        except psycopg2.Error:
            # We assume this means 'no test database exists.'
            pass
        else:
            db_fixture.dropDb()

    @classmethod
    @profiled
    def tearDown(cls):
        cls.fixture.cleanUp()
        BaseLayer.isSetUp = False

    @classmethod
    @profiled
    def testSetUp(cls):
        # Store currently running threads so we can detect if a test
        # leaves new threads running.
        BaseLayer._threads = threading.enumerate()
        BaseLayer.check()
        BaseLayer.original_working_directory = os.getcwd()

        # Tests and test infrastruture sometimes needs to know the test
        # name.  The testrunner doesn't provide this, so we have to do
        # some snooping.
        import inspect
        frame = inspect.currentframe()
        try:
            while frame.f_code.co_name != 'startTest':
                frame = frame.f_back
            BaseLayer.test_name = str(frame.f_locals['test'])
        finally:
            del frame  # As per no-leak stack inspection in Python reference.

    @classmethod
    @profiled
    def testTearDown(cls):
        # Get our current working directory, handling the case where it no
        # longer exists (!).
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = None

        # Handle a changed working directory. If the test succeeded,
        # add an error. Then restore the working directory so the test
        # run can continue.
        if cwd != BaseLayer.original_working_directory:
            BaseLayer.flagTestIsolationFailure(
                    "Test failed to restore working directory.")
            os.chdir(BaseLayer.original_working_directory)

        BaseLayer.original_working_directory = None
        reset_logging()
        del lp.services.mail.stub.test_emails[:]
        BaseLayer.test_name = None
        BaseLayer.check()

        def new_live_threads():
            return [
                thread for thread in threading.enumerate()
                    if thread not in BaseLayer._threads and thread.isAlive()]

        if BaseLayer.disable_thread_check:
            new_threads = None
        else:
            for loop in range(0, 100):
                # Check for tests that leave live threads around early.
                # A live thread may be the cause of other failures, such as
                # uncollectable garbage.
                new_threads = new_live_threads()
                has_live_threads = False
                for new_thread in new_threads:
                    new_thread.join(0.1)
                    if new_thread.isAlive():
                        has_live_threads = True
                if has_live_threads:
                    # Trigger full garbage collection that might be
                    # blocking threads from exiting.
                    gc.collect()
                else:
                    break
            new_threads = new_live_threads()

        if new_threads:
            # BaseLayer.disable_thread_check is a mechanism to stop
            # tests that leave threads behind from failing. Its use
            # should only ever be temporary.
            if BaseLayer.disable_thread_check:
                print (
                    "ERROR DISABLED: "
                    "Test left new live threads: %s") % repr(new_threads)
            else:
                BaseLayer.flagTestIsolationFailure(
                    "Test left new live threads: %s" % repr(new_threads))

        BaseLayer.disable_thread_check = False
        del BaseLayer._threads

        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            BaseLayer.flagTestIsolationFailure(
                "Test left SIGCHLD handler.")

        # Objects with __del__ methods cannot participate in refence cycles.
        # Fail tests with memory leaks now rather than when Launchpad crashes
        # due to a leak because someone ignored the warnings.
        if gc.garbage:
            del gc.garbage[:]
            gc.collect()  # Expensive, so only do if there might be garbage.
            if gc.garbage:
                BaseLayer.flagTestIsolationFailure(
                        "Test left uncollectable garbage\n"
                        "%s (referenced from %s)"
                        % (gc.garbage, gc.get_referrers(*gc.garbage)))

    @classmethod
    @profiled
    def check(cls):
        """Check that the environment is working as expected.

        We check here so we can detect tests that, for example,
        initialize the Zopeless or Functional environments and
        are using the incorrect layer.
        """
        if FunctionalLayer.isSetUp and ZopelessLayer.isSetUp:
            raise LayerInvariantError(
                "Both Zopefull and Zopeless CA environments setup")

        # Detect a test that causes the component architecture to be loaded.
        # This breaks test isolation, as it cannot be torn down.
        if (is_ca_available()
            and not FunctionalLayer.isSetUp
            and not ZopelessLayer.isSetUp):
            raise LayerIsolationError(
                "Component architecture should not be loaded by tests. "
                "This should only be loaded by the Layer.")

        # Detect a test that forgot to reset the default socket timeout.
        # This safety belt is cheap and protects us from very nasty
        # intermittent test failures: see bug #140068 for an example.
        if socket.getdefaulttimeout() is not None:
            raise LayerIsolationError(
                "Test didn't reset the socket default timeout.")

    @classmethod
    def flagTestIsolationFailure(cls, message):
        """Handle a breakdown in test isolation.

        If the test that broke isolation thinks it succeeded,
        add an error. If the test failed, don't add a notification
        as the isolation breakdown is probably just fallout.

        The layer that detected the isolation failure still needs to
        repair the damage, or in the worst case abort the test run.
        """
        test_result = BaseLayer.getCurrentTestResult()
        if test_result.wasSuccessful():
            test_case = BaseLayer.getCurrentTestCase()
            try:
                raise LayerIsolationError(message)
            except LayerIsolationError:
                test_result.addError(test_case, sys.exc_info())

    @classmethod
    def getCurrentTestResult(cls):
        """Return the TestResult currently in play."""
        import inspect
        frame = inspect.currentframe()
        try:
            while True:
                f_self = frame.f_locals.get('self', None)
                if isinstance(f_self, TestResult):
                    return frame.f_locals['self']
                frame = frame.f_back
        finally:
            del frame  # As per no-leak stack inspection in Python reference.

    @classmethod
    def getCurrentTestCase(cls):
        """Return the test currently in play."""
        import inspect
        frame = inspect.currentframe()
        try:
            while True:
                f_self = frame.f_locals.get('self', None)
                if isinstance(f_self, TestCase):
                    return f_self
                f_test = frame.f_locals.get('test', None)
                if isinstance(f_test, TestCase):
                    return f_test
                frame = frame.f_back
            return frame.f_locals['test']
        finally:
            del frame  # As per no-leak stack inspection in Python reference.

    @classmethod
    def appserver_config(cls):
        """Return a config suitable for AppServer tests."""
        return LaunchpadConfig(cls.appserver_config_name)

    @classmethod
    def appserver_root_url(cls, facet='mainsite', ensureSlash=False):
        """Return the correct app server root url for the given facet."""
        return cls.appserver_config().appserver_root_url(
                facet, ensureSlash)


class MemcachedLayer(BaseLayer):
    """Provides tests access to a memcached.

    Most tests needing memcache access will actually need to use
    ZopelessLayer, FunctionalLayer or sublayer as they will be accessing
    memcached using a utility.
    """

    # A memcache.Client instance.
    client = None

    # A subprocess.Popen instance if this process spawned the test
    # memcached.
    _memcached_process = None

    _is_setup = False

    @classmethod
    @profiled
    def setUp(cls):
        cls._is_setup = True
        # Create a client
        MemcachedLayer.client = memcache_client_factory()
        if (BaseLayer.persist_test_services and
            os.path.exists(MemcachedLayer.getPidFile())):
            return

        # First, check to see if there is a memcached already running.
        # This happens when new layers are run as a subprocess.
        test_key = "MemcachedLayer__live_test"
        if MemcachedLayer.client.set(test_key, "live"):
            return

        cmd = [
            'memcached',
            '-m', str(config.memcached.memory_size),
            '-l', str(config.memcached.address),
            '-p', str(config.memcached.port),
            '-U', str(config.memcached.port),
            ]
        if config.memcached.verbose:
            cmd.append('-vv')
            stdout = sys.stdout
            stderr = sys.stderr
        else:
            stdout = tempfile.NamedTemporaryFile()
            stderr = tempfile.NamedTemporaryFile()
        MemcachedLayer._memcached_process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
        MemcachedLayer._memcached_process.stdin.close()

        # Wait for the memcached to become operational.
        while not MemcachedLayer.client.set(test_key, "live"):
            if MemcachedLayer._memcached_process.returncode is not None:
                raise LayerInvariantError(
                    "memcached never started or has died.",
                    MemcachedLayer._memcached_process.stdout.read())
            MemcachedLayer.client.forget_dead_hosts()
            time.sleep(0.1)

        # Store the pidfile for other processes to kill.
        pid_file = MemcachedLayer.getPidFile()
        open(pid_file, 'w').write(str(MemcachedLayer._memcached_process.pid))

    @classmethod
    @profiled
    def tearDown(cls):
        if not cls._is_setup:
            return
        cls._is_setup = False
        MemcachedLayer.client.disconnect_all()
        MemcachedLayer.client = None
        if not BaseLayer.persist_test_services:
            # Kill our memcached, and there is no reason to be nice about it.
            kill_by_pidfile(MemcachedLayer.getPidFile())
            MemcachedLayer._memcached_process = None

    @classmethod
    @profiled
    def testSetUp(cls):
        MemcachedLayer.client.forget_dead_hosts()
        MemcachedLayer.client.flush_all()

    @classmethod
    @profiled
    def testTearDown(cls):
        pass

    @classmethod
    def getPidFile(cls):
        return os.path.join(config.root, '.memcache.pid')

    @classmethod
    def purge(cls):
        "Purge everything from our memcached."
        MemcachedLayer.client.flush_all()  # Only do this in tests!


class RabbitMQLayer(BaseLayer):
    """Provides tests access to a rabbitMQ instance."""

    rabbit = RabbitServer()

    _is_setup = False

    @classmethod
    @profiled
    def setUp(cls):
        cls.rabbit.setUp()
        cls.config_fixture.add_section(
            cls.rabbit.config.service_config)
        cls.appserver_config_fixture.add_section(
            cls.rabbit.config.service_config)
        cls._is_setup = True

    @classmethod
    @profiled
    def tearDown(cls):
        if not cls._is_setup:
            return
        cls.rabbit.cleanUp()
        cls._is_setup = False
        # Can't pop the config above, so bail here and let the test runner
        # start a sub-process.
        raise NotImplementedError

    @classmethod
    @profiled
    def testSetUp(cls):
        pass

    @classmethod
    @profiled
    def testTearDown(cls):
        pass


# We store a reference to the DB-API connect method here when we
# put a proxy in its place.
_org_connect = None


class DatabaseLayer(BaseLayer):
    """Provides tests access to the Launchpad sample database."""

    _is_setup = False
    _db_fixture = None
    # For parallel testing, we allocate a temporary template to prevent worker
    # contention.
    _db_template_fixture = None

    @classmethod
    @profiled
    def setUp(cls):
        cls._is_setup = True
        # Read the sequences we'll need from the test template database.
        reset_sequences_sql = LaunchpadTestSetup(
            dbname='launchpad_ftest_template').generateResetSequencesSQL()
        # Allocate a template for this test instance
        if os.environ.get('LP_TEST_INSTANCE'):
            template_name = '_'.join([LaunchpadTestSetup.template,
                os.environ.get('LP_TEST_INSTANCE')])
            cls._db_template_fixture = LaunchpadTestSetup(
                dbname=template_name, reset_sequences_sql=reset_sequences_sql)
            cls._db_template_fixture.setUp()
        else:
            template_name = LaunchpadTestSetup.template
        cls._db_fixture = LaunchpadTestSetup(template=template_name,
            reset_sequences_sql=reset_sequences_sql)
        cls.force_dirty_database()
        # Nuke any existing DB (for persistent-test-services) [though they
        # prevent this !?]
        cls._db_fixture.tearDown()
        # Force a db creation for unique db names - needed at layer init
        # because appserver using layers run things at layer setup, not
        # test setup.
        cls._db_fixture.setUp()
        # And take it 'down' again to be in the right state for testSetUp
        # - note that this conflicts in principle with layers whose setUp
        # needs the db working, but this is a conceptually cleaner starting
        # point for addressing that mismatch.
        cls._db_fixture.tearDown()
        # Bring up the db, so that it is available for other layers.
        cls._ensure_db()

    @classmethod
    @profiled
    def tearDown(cls):
        if not cls._is_setup:
            return
        cls._is_setup = False
        # Don't leave the DB lying around or it might break tests
        # that depend on it not being there on startup, such as found
        # in test_layers.py
        cls.force_dirty_database()
        cls._db_fixture.tearDown()
        cls._db_fixture = None
        if os.environ.get('LP_TEST_INSTANCE'):
            cls._db_template_fixture.tearDown()
            cls._db_template_fixture = None

    @classmethod
    @profiled
    def testSetUp(cls):
        pass

    @classmethod
    def _ensure_db(cls):
        cls._db_fixture.setUp()
        # Ensure that the database is connectable. Because we might have
        # just created it, keep trying for a few seconds incase PostgreSQL
        # is taking its time getting its house in order.
        attempts = 60
        for count in range(0, attempts):
            try:
                cls.connect().close()
            except psycopg2.Error:
                if count == attempts - 1:
                    raise
                time.sleep(0.5)
            else:
                break

    @classmethod
    @profiled
    def testTearDown(cls):
        # Ensure that the database is connectable
        cls.connect().close()

        cls._db_fixture.tearDown()

        # Fail tests that forget to uninstall their database policies.
        from lp.services.webapp.adapter import StoreSelector
        while StoreSelector.get_current() is not None:
            BaseLayer.flagTestIsolationFailure(
                "Database policy %s still installed"
                % repr(StoreSelector.pop()))
        # Reset/bring up the db - makes it available for either the next test,
        # or a subordinate layer which builds on the db. This wastes one setup
        # per db layer teardown per run, but thats tolerable.
        cls._ensure_db()

    @classmethod
    @profiled
    def force_dirty_database(cls):
        cls._db_fixture.force_dirty_database()

    @classmethod
    @profiled
    def connect(cls):
        return cls._db_fixture.connect()

    @classmethod
    @profiled
    def _dropDb(cls):
        return cls._db_fixture.dropDb()


class SwiftLayer(BaseLayer):
    @classmethod
    @profiled
    def setUp(cls):
        cls.swift_fixture = SwiftFixture()
        cls.swift_fixture.setUp()

    @classmethod
    @profiled
    def tearDown(cls):
        swift = cls.swift_fixture
        if swift is not None:
            cls.swift_fixture = None
            swift.cleanUp()


class LibrarianLayer(DatabaseLayer):
    """Provides tests access to a Librarian instance.

    Calls to the Librarian will fail unless there is also a Launchpad
    database available.
    """

    librarian_fixture = None

    @classmethod
    @profiled
    def setUp(cls):
        cls.librarian_fixture = LibrarianServerFixture(
            BaseLayer.config_fixture)
        cls.librarian_fixture.setUp()
        cls._check_and_reset()

        # Make sure things using the appserver config know the
        # correct Librarian port numbers.
        cls.appserver_config_fixture.add_section(
            cls.librarian_fixture.service_config)

    @classmethod
    @profiled
    def tearDown(cls):
        # Permit multiple teardowns while we sort out the layering
        # responsibilities : not desirable though.
        if cls.librarian_fixture is None:
            return
        try:
            cls._check_and_reset()
        finally:
            librarian = cls.librarian_fixture
            cls.librarian_fixture = None
            librarian.cleanUp()

    @classmethod
    @profiled
    def _check_and_reset(cls):
        """Raise an exception if the Librarian has been killed, else reset."""
        try:
            f = urlopen(config.librarian.download_url)
            f.read()
        except Exception as e:
            raise LayerIsolationError(
                    "Librarian has been killed or has hung."
                    "Tests should use LibrarianLayer.hide() and "
                    "LibrarianLayer.reveal() where possible, and ensure "
                    "the Librarian is restarted if it absolutely must be "
                    "shutdown: " + str(e))
        else:
            cls.librarian_fixture.reset()

    @classmethod
    @profiled
    def testSetUp(cls):
        cls._check_and_reset()

    @classmethod
    @profiled
    def testTearDown(cls):
        if cls._hidden:
            cls.reveal()
        cls._check_and_reset()

    # Flag maintaining state of hide()/reveal() calls
    _hidden = False

    # Fake upload socket used when the librarian is hidden
    _fake_upload_socket = None

    @classmethod
    @profiled
    def hide(cls):
        """Hide the Librarian so nothing can find it. We don't want to
        actually shut it down because starting it up again is expensive.

        We do this by altering the configuration so the Librarian client
        looks for the Librarian server on the wrong port.
        """
        cls._hidden = True
        if cls._fake_upload_socket is None:
            # Bind to a socket, but don't listen to it.  This way we
            # guarantee that connections to the given port will fail.
            cls._fake_upload_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            assert config.librarian.upload_host == 'localhost', (
                'Can only hide librarian if it is running locally')
            cls._fake_upload_socket.bind(('127.0.0.1', 0))

        host, port = cls._fake_upload_socket.getsockname()
        librarian_data = dedent("""
            [librarian]
            upload_port: %s
            """ % port)
        config.push('hide_librarian', librarian_data)

    @classmethod
    @profiled
    def reveal(cls):
        """Reveal a hidden Librarian.

        This just involves restoring the config to the original value.
        """
        cls._hidden = False
        config.pop('hide_librarian')


def test_default_timeout():
    """Don't timeout by default in tests."""
    return None


class LaunchpadLayer(LibrarianLayer, MemcachedLayer, RabbitMQLayer):
    """Provides access to the Launchpad database and daemons.

    We need to ensure that the database setup runs before the daemon
    setup, or the database setup will fail because the daemons are
    already connected to the database.

    This layer is mainly used by tests that call initZopeless() themselves.
    Most tests will use a sublayer such as LaunchpadFunctionalLayer that
    provides access to the Component Architecture.
    """

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def tearDown(cls):
        pass

    @classmethod
    @profiled
    def testSetUp(cls):
        # By default, don't make external service tests timeout.
        if get_default_timeout_function() is not None:
            raise LayerIsolationError(
                "Global default timeout function should be None.")
        set_default_timeout_function(test_default_timeout)

    @classmethod
    @profiled
    def testTearDown(cls):
        if get_default_timeout_function() is not test_default_timeout:
            raise LayerIsolationError(
                "Test didn't reset default timeout function.")
        set_default_timeout_function(None)

    # A database connection to the session database, created by the first
    # call to resetSessionDb.
    _raw_sessiondb_connection = None

    @classmethod
    @profiled
    def resetSessionDb(cls):
        """Reset the session database.

        Layers that need session database isolation call this explicitly
        in the testSetUp().
        """
        if LaunchpadLayer._raw_sessiondb_connection is None:
            from storm.uri import URI
            from lp.services.webapp.adapter import (
                LaunchpadSessionDatabase)
            launchpad_session_database = LaunchpadSessionDatabase(
                URI('launchpad-session:'))
            LaunchpadLayer._raw_sessiondb_connection = (
                launchpad_session_database.raw_connect())
        LaunchpadLayer._raw_sessiondb_connection.cursor().execute(
            "DELETE FROM SessionData")


def wsgi_application(environ, start_response):
    """This is a wsgi application for Zope functional testing.

    We use it with wsgi_intercept, which is itself mostly interesting
    for our webservice (lazr.restful) tests.
    """
    # Committing work done up to now is a convenience that the Zope
    # zope.app.testing.functional.HTTPCaller does.  We're replacing that bit,
    # so it is easiest to follow that lead, even if it feels a little loose.
    transaction.commit()
    # Let's support post-mortem debugging.
    if environ.pop('HTTP_X_ZOPE_HANDLE_ERRORS', 'True') == 'False':
        environ['wsgi.handleErrors'] = False
    handle_errors = environ.get('wsgi.handleErrors', True)

    # Make sure the request method is something Launchpad will
    # recognize. httplib2 usually takes care of this, but we've
    # bypassed that code in our test environment.
    environ['REQUEST_METHOD'] = environ['REQUEST_METHOD'].upper()
    # Now we do the proper dance to get the desired request.  This is an
    # almalgam of code from zope.app.testing.functional.HTTPCaller and
    # zope.publisher.paste.Application.
    request_cls, publication_cls = chooseClasses(
        environ['REQUEST_METHOD'], environ)
    publication = publication_cls(set_up_functional_test().db)
    request = request_cls(environ['wsgi.input'], environ)
    request.setPublication(publication)
    # The rest of this function is an amalgam of
    # zope.publisher.paste.Application.__call__ and van.testing.layers.
    request = zope.publisher.publish.publish(
        request, handle_errors=handle_errors)
    response = request.response
    # We sort these, and then put the status first, because
    # zope.testbrowser.testing does--and because it makes it easier to write
    # reliable tests.
    headers = sorted(response.getHeaders())
    status = response.getStatusString()
    headers.insert(0, ('Status', status))
    # Start the WSGI server response.
    start_response(status, headers)
    # Return the result body iterable.
    return response.consumeBodyIter()


class FunctionalLayer(BaseLayer):
    """Loads the Zope3 component architecture in appserver mode."""

    # Set to True if tests using the Functional layer are currently being run.
    isSetUp = False

    @classmethod
    @profiled
    def setUp(cls):
        FunctionalLayer.isSetUp = True
        set_up_functional_test().setUp()

        # Assert that set_up_functional_test did what it says it does
        if not is_ca_available():
            raise LayerInvariantError("Component architecture failed to load")

        # Access the cookie manager's secret to get the cache populated.
        # If we don't, it may issue extra queries depending on test order.
        lp.services.webapp.session.idmanager.secret
        # If our request publication factories were defined using ZCML,
        # they'd be set up by set_up_functional_test().setUp(). Since
        # they're defined by Python code, we need to call that code
        # here.
        register_launchpad_request_publication_factories()
        wsgi_intercept.add_wsgi_intercept(
            'localhost', 80, lambda: wsgi_application)
        wsgi_intercept.add_wsgi_intercept(
            'api.launchpad.dev', 80, lambda: wsgi_application)
        httplib2_intercept.install()

    @classmethod
    @profiled
    def tearDown(cls):
        FunctionalLayer.isSetUp = False
        wsgi_intercept.remove_wsgi_intercept('localhost', 80)
        wsgi_intercept.remove_wsgi_intercept('api.launchpad.dev', 80)
        httplib2_intercept.uninstall()
        # Signal Layer cannot be torn down fully
        raise NotImplementedError

    @classmethod
    @profiled
    def testSetUp(cls):
        transaction.abort()
        transaction.begin()

        # Fake a root folder to keep Z3 ZODB dependencies happy.
        fs = set_up_functional_test()
        if not fs.connection:
            fs.connection = fs.db.open()
        root = fs.connection.root()
        root[ZopePublication.root_name] = MockRootFolder()

        # Should be impossible, as the CA cannot be unloaded. Something
        # mighty nasty has happened if this is triggered.
        if not is_ca_available():
            raise LayerInvariantError(
                "Component architecture not loaded or totally screwed")

    @classmethod
    @profiled
    def testTearDown(cls):
        # Should be impossible, as the CA cannot be unloaded. Something
        # mighty nasty has happened if this is triggered.
        if not is_ca_available():
            raise LayerInvariantError(
                "Component architecture not loaded or totally screwed")

        transaction.abort()


class ZopelessLayer(BaseLayer):
    """Layer for tests that need the Zopeless component architecture
    loaded using execute_zcml_for_scripts().
    """

    # Set to True if tests in the Zopeless layer are currently being run.
    isSetUp = False

    @classmethod
    @profiled
    def setUp(cls):
        ZopelessLayer.isSetUp = True
        execute_zcml_for_scripts()

        # Assert that execute_zcml_for_scripts did what it says it does.
        if not is_ca_available():
            raise LayerInvariantError(
                "Component architecture not loaded by "
                "execute_zcml_for_scripts")

        # If our request publication factories were defined using
        # ZCML, they'd be set up by execute_zcml_for_scripts(). Since
        # they're defined by Python code, we need to call that code
        # here.
        register_launchpad_request_publication_factories()

    @classmethod
    @profiled
    def tearDown(cls):
        ZopelessLayer.isSetUp = False
        # Signal Layer cannot be torn down fully
        raise NotImplementedError

    @classmethod
    @profiled
    def testSetUp(cls):
        # Should be impossible, as the CA cannot be unloaded. Something
        # mighty nasty has happened if this is triggered.
        if not is_ca_available():
            raise LayerInvariantError(
                "Component architecture not loaded or totally screwed")
        # This should not happen here, it should be caught by the
        # testTearDown() method. If it does, something very nasty
        # happened.
        if getSecurityPolicy() != LaunchpadPermissiveSecurityPolicy:
            raise LayerInvariantError(
                "Previous test removed the LaunchpadPermissiveSecurityPolicy."
                )

        # execute_zcml_for_scripts() sets up an interaction for the
        # anonymous user. A previous script may have changed or removed
        # the interaction, so set it up again
        login(ANONYMOUS)

    @classmethod
    @profiled
    def testTearDown(cls):
        # Should be impossible, as the CA cannot be unloaded. Something
        # mighty nasty has happened if this is triggered.
        if not is_ca_available():
            raise LayerInvariantError(
                "Component architecture not loaded or totally screwed")
        # Make sure that a test that changed the security policy, reset it
        # back to its default value.
        if getSecurityPolicy() != LaunchpadPermissiveSecurityPolicy:
            raise LayerInvariantError(
                "This test removed the LaunchpadPermissiveSecurityPolicy and "
                "didn't restore it.")
        logout()


class TwistedLayer(BaseLayer):
    """A layer for cleaning up the Twisted thread pool."""

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def tearDown(cls):
        pass

    @classmethod
    def _save_signals(cls):
        """Save the current signal handlers."""
        TwistedLayer._original_sigint = signal.getsignal(signal.SIGINT)
        TwistedLayer._original_sigterm = signal.getsignal(signal.SIGTERM)
        TwistedLayer._original_sigchld = signal.getsignal(signal.SIGCHLD)
        # XXX MichaelHudson, 2009-07-14, bug=399118: If a test case in this
        # layer launches a process with spawnProcess, there should really be a
        # SIGCHLD handler installed to avoid PotentialZombieWarnings.  But
        # some tests in this layer use tachandler and it is fragile when a
        # SIGCHLD handler is installed.  tachandler needs to be fixed.
        # from twisted.internet import reactor
        # signal.signal(signal.SIGCHLD, reactor._handleSigchld)

    @classmethod
    def _restore_signals(cls):
        """Restore the signal handlers."""
        signal.signal(signal.SIGINT, TwistedLayer._original_sigint)
        signal.signal(signal.SIGTERM, TwistedLayer._original_sigterm)
        signal.signal(signal.SIGCHLD, TwistedLayer._original_sigchld)

    @classmethod
    @profiled
    def testSetUp(cls):
        TwistedLayer._save_signals()
        from twisted.internet import interfaces, reactor
        from twisted.python import threadpool
        # zope.exception demands more of frame objects than
        # twisted.python.failure provides in its fake frames.  This is enough
        # to make it work with them as of 2009-09-16.  See
        # https://bugs.launchpad.net/bugs/425113.
        cls._patch = MonkeyPatch(
            'twisted.python.failure._Frame.f_locals',
            property(lambda self: {}))
        cls._patch.setUp()
        if interfaces.IReactorThreads.providedBy(reactor):
            pool = getattr(reactor, 'threadpool', None)
            # If the Twisted threadpool has been obliterated (probably by
            # testTearDown), then re-build it using the values that Twisted
            # uses.
            if pool is None:
                reactor.threadpool = threadpool.ThreadPool(0, 10)
                reactor.threadpool.start()

    @classmethod
    @profiled
    def testTearDown(cls):
        # Shutdown and obliterate the Twisted threadpool, to plug up leaking
        # threads.
        from twisted.internet import interfaces, reactor
        if interfaces.IReactorThreads.providedBy(reactor):
            reactor.suggestThreadPoolSize(0)
            pool = getattr(reactor, 'threadpool', None)
            if pool is not None:
                reactor.threadpool.stop()
                reactor.threadpool = None
        cls._patch.cleanUp()
        TwistedLayer._restore_signals()


class GoogleServiceLayer(BaseLayer):
    """Tests for Google web service integration."""

    @classmethod
    def setUp(cls):
        google = GoogleServiceTestSetup()
        google.setUp()

    @classmethod
    def tearDown(cls):
        GoogleServiceTestSetup().tearDown()

    @classmethod
    def testSetUp(self):
        # We need to override BaseLayer.testSetUp(), or else we will
        # get a LayerIsolationError.
        pass

    @classmethod
    def testTearDown(self):
        # We need to override BaseLayer.testTearDown(), or else we will
        # get a LayerIsolationError.
        pass


class DatabaseFunctionalLayer(DatabaseLayer, FunctionalLayer):
    """Provides the database and the Zope3 application server environment."""

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def tearDown(cls):
        pass

    @classmethod
    @profiled
    def testSetUp(cls):
        # Connect Storm
        reconnect_stores(reset=True)

    @classmethod
    @profiled
    def testTearDown(cls):
        getUtility(IOpenLaunchBag).clear()

        endInteraction()

        # Disconnect Storm so it doesn't get in the way of database resets
        disconnect_stores()


class LaunchpadFunctionalLayer(LaunchpadLayer, FunctionalLayer):
    """Provides the Launchpad Zope3 application server environment."""

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def testSetUp(cls):
        # Reset any statistics
        from lp.services.webapp.opstats import OpStats
        OpStats.resetStats()

        # Connect Storm
        reconnect_stores(reset=True)

    @classmethod
    @profiled
    def testTearDown(cls):
        getUtility(IOpenLaunchBag).clear()

        endInteraction()

        # Reset any statistics
        from lp.services.webapp.opstats import OpStats
        OpStats.resetStats()

        # Disconnect Storm so it doesn't get in the way of database resets
        disconnect_stores()


class AuditorLayer(LaunchpadFunctionalLayer):

    auditor = AuditorServer()

    _is_setup = False

    @classmethod
    @profiled
    def setUp(cls):
        cls.auditor.setUp()
        cls.config_fixture.add_section(cls.auditor.service_config)
        cls.appserver_config_fixture.add_section(cls.auditor.service_config)
        cls._is_setup = True

    @classmethod
    @profiled
    def tearDown(cls):
        if not cls._is_setup:
            return
        cls.auditor.cleanUp()
        cls._is_setup = False
        # Can't pop the config above, so bail here and let the test runner
        # start a sub-process.
        raise NotImplementedError

    @classmethod
    @profiled
    def testSetUp(cls):
        pass

    @classmethod
    @profiled
    def testTearDown(cls):
        pass


class GoogleLaunchpadFunctionalLayer(LaunchpadFunctionalLayer,
                                     GoogleServiceLayer):
    """Provides Google service in addition to LaunchpadFunctionalLayer."""

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def tearDown(cls):
        pass

    @classmethod
    @profiled
    def testSetUp(cls):
        pass

    @classmethod
    @profiled
    def testTearDown(cls):
        pass


class ZopelessDatabaseLayer(ZopelessLayer, DatabaseLayer):
    """Testing layer for unit tests with no need for librarian.

    Can be used wherever you're accustomed to using LaunchpadZopeless
    or LaunchpadScript layers, but there is no need for librarian.
    """

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def tearDown(cls):
        # Signal Layer cannot be torn down fully
        raise NotImplementedError

    @classmethod
    @profiled
    def testSetUp(cls):
        # LaunchpadZopelessLayer takes care of reconnecting the stores
        if not LaunchpadZopelessLayer.isSetUp:
            reconnect_stores(reset=True)

    @classmethod
    @profiled
    def testTearDown(cls):
        disconnect_stores()


class LaunchpadScriptLayer(ZopelessLayer, LaunchpadLayer):
    """Testing layer for scripts using the main Launchpad database adapter"""

    @classmethod
    @profiled
    def setUp(cls):
        # Make a TestMailBox available
        # This is registered via ZCML in the LaunchpadFunctionalLayer
        # XXX flacoste 2006-10-25 bug=68189: This should be configured from
        # ZCML but execute_zcml_for_scripts() doesn't cannot support a
        # different testing configuration.
        cls._mailbox = TestMailBox()
        provideUtility(cls._mailbox, IMailBox)

    @classmethod
    @profiled
    def tearDown(cls):
        if not globalregistry.base.unregisterUtility(cls._mailbox):
            raise NotImplementedError('failed to unregister mailbox')

    @classmethod
    @profiled
    def testSetUp(cls):
        # LaunchpadZopelessLayer takes care of reconnecting the stores
        if not LaunchpadZopelessLayer.isSetUp:
            reconnect_stores(reset=True)

    @classmethod
    @profiled
    def testTearDown(cls):
        disconnect_stores()


class LaunchpadTestSetup(PgTestSetup):
    template = 'launchpad_ftest_template'
    dbuser = 'launchpad'
    host = 'localhost'


class LaunchpadZopelessLayer(LaunchpadScriptLayer):
    """Full Zopeless environment including Component Architecture and
    database connections initialized.
    """

    isSetUp = False
    txn = transaction

    @classmethod
    @profiled
    def setUp(cls):
        LaunchpadZopelessLayer.isSetUp = True

    @classmethod
    @profiled
    def tearDown(cls):
        LaunchpadZopelessLayer.isSetUp = False

    @classmethod
    @profiled
    def testSetUp(cls):
        dbconfig.override(isolation_level='read_committed')
        # XXX wgrant 2011-09-24 bug=29744: initZopeless used to do this.
        # Tests that still need it should eventually set this directly,
        # so the whole layer is not polluted.
        set_immediate_mail_delivery(True)

        # Connect Storm
        reconnect_stores()

    @classmethod
    @profiled
    def testTearDown(cls):
        dbconfig.reset()
        # LaunchpadScriptLayer will disconnect the stores for us.

        # XXX wgrant 2011-09-24 bug=29744: uninstall used to do this.
        # Tests that still need immediate delivery should eventually do
        # this directly.
        set_immediate_mail_delivery(False)

    @classmethod
    @profiled
    def commit(cls):
        transaction.commit()

    @classmethod
    @profiled
    def abort(cls):
        transaction.abort()


class MockHTTPTask:

    class MockHTTPRequestParser:
        headers = None
        first_line = None

    class MockHTTPServerChannel:
        # This is not important to us, so we can hardcode it here.
        addr = ['127.0.0.88', 80]

    request_data = MockHTTPRequestParser()
    channel = MockHTTPServerChannel()

    def __init__(self, response, first_line):
        self.request = response._request
        # We have no way of knowing when the task started, so we use
        # the current time here. That shouldn't be a problem since we don't
        # care about that for our tests anyway.
        self.start_time = time.time()
        self.status = response.getStatus()
        # When streaming files (see lib/zope/publisher/httpresults.txt)
        # the 'Content-Length' header is missing. When it happens we set
        # 'bytes_written' to an obviously invalid value. This variable is
        # used for logging purposes, see webapp/servers.py.
        content_length = response.getHeader('Content-Length')
        if content_length is not None:
            self.bytes_written = int(content_length)
        else:
            self.bytes_written = -1
        self.request_data.headers = self.request.headers
        self.request_data.first_line = first_line

    def getCGIEnvironment(self):
        return self.request._orig_env


class PageTestLayer(LaunchpadFunctionalLayer, GoogleServiceLayer):
    """Environment for page tests.
    """

    @classmethod
    @profiled
    def setUp(cls):
        if os.environ.get('PROFILE_PAGETESTS_REQUESTS'):
            PageTestLayer.profiler = Profile()
        else:
            PageTestLayer.profiler = None
        file_handler = logging.FileHandler('logs/pagetests-access.log', 'w')
        file_handler.setFormatter(logging.Formatter())
        logger = PythonLogger('pagetests-access')
        logger.logger.addHandler(file_handler)
        logger.logger.setLevel(logging.INFO)
        access_logger = LaunchpadAccessLogger(logger)

        def my__call__(obj, request_string, handle_errors=True, form=None):
            """Call HTTPCaller.__call__ and log the page hit."""
            if PageTestLayer.profiler:
                response = PageTestLayer.profiler.runcall(
                    orig__call__, obj, request_string,
                    handle_errors=handle_errors, form=form)
            else:
                response = orig__call__(
                    obj, request_string, handle_errors=handle_errors,
                    form=form)
            first_line = request_string.strip().splitlines()[0]
            access_logger.log(MockHTTPTask(response._response, first_line))
            return response

        PageTestLayer.orig__call__ = (
                zope.app.testing.functional.HTTPCaller.__call__)
        zope.app.testing.functional.HTTPCaller.__call__ = my__call__

    @classmethod
    @profiled
    def tearDown(cls):
        zope.app.testing.functional.HTTPCaller.__call__ = (
                PageTestLayer.orig__call__)
        if PageTestLayer.profiler:
            PageTestLayer.profiler.dump_stats(
                os.environ.get('PROFILE_PAGETESTS_REQUESTS'))

    @classmethod
    @profiled
    def testSetUp(cls):
        LaunchpadLayer.resetSessionDb()

    @classmethod
    @profiled
    def testTearDown(cls):
        pass


class TwistedLaunchpadZopelessLayer(TwistedLayer, LaunchpadZopelessLayer):
    """A layer for cleaning up the Twisted thread pool."""

    @classmethod
    @profiled
    def setUp(cls):
        pass

    @classmethod
    @profiled
    def tearDown(cls):
        pass

    @classmethod
    @profiled
    def testSetUp(cls):
        pass

    @classmethod
    @profiled
    def testTearDown(cls):
        # XXX 2008-06-11 jamesh bug=239086:
        # Due to bugs in the transaction module's thread local
        # storage, transactions may be reused by new threads in future
        # tests.  Therefore we do some cleanup before the pool is
        # destroyed by TwistedLayer.testTearDown().
        from twisted.internet import interfaces, reactor
        if interfaces.IReactorThreads.providedBy(reactor):
            pool = getattr(reactor, 'threadpool', None)
            if pool is not None and pool.workers > 0:

                def cleanup_thread_stores(event):
                    disconnect_stores()
                    # Don't exit until the event fires.  This ensures
                    # that our thread doesn't get added to
                    # pool.waiters until all threads are processed.
                    event.wait()

                event = threading.Event()
                # Ensure that the pool doesn't grow, and issue one
                # cleanup job for each thread in the pool.
                pool.adjustPoolsize(0, pool.workers)
                for i in range(pool.workers):
                    pool.callInThread(cleanup_thread_stores, event)
                event.set()


class LayerProcessController:
    """Controller for starting and stopping subprocesses.

    Layers which need to start and stop a child process appserver or smtp
    server should call the methods in this class, but should NOT inherit from
    this class.
    """

    # Holds the Popen instance of the spawned app server.
    appserver = None

    # The config used by the spawned app server.
    appserver_config = None

    # The SMTP server for layer tests.  See
    # configs/testrunner-appserver/mail-configure.zcml
    smtp_controller = None

    @classmethod
    def setConfig(cls):
        """Stash a config for use."""
        cls.appserver_config = LaunchpadConfig(
            BaseLayer.appserver_config_name, 'runlaunchpad')

    @classmethod
    def setUp(cls):
        cls.setConfig()
        cls.startSMTPServer()
        cls.startAppServer()

    @classmethod
    @profiled
    def startSMTPServer(cls):
        """Start the SMTP server if it hasn't already been started."""
        if cls.smtp_controller is not None:
            raise LayerInvariantError('SMTP server already running')
        # Ensure that the SMTP server does proper logging.
        log = logging.getLogger('lazr.smtptest')
        log_file = os.path.join(config.mailman.build_var_dir, 'logs', 'smtpd')
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter(
            fmt='%(asctime)s (%(process)d) %(message)s',
            datefmt='%b %d %H:%M:%S %Y')
        handler.setFormatter(formatter)
        log.setLevel(logging.DEBUG)
        log.addHandler(handler)
        log.propagate = False
        cls.smtp_controller = SMTPController('localhost', 9025)
        cls.smtp_controller.start()

    @classmethod
    @profiled
    def startAppServer(cls, run_name='run'):
        """Start the app server if it hasn't already been started."""
        if cls.appserver is not None:
            raise LayerInvariantError('App server already running')
        cls._cleanUpStaleAppServer()
        cls._runAppServer(run_name)
        cls._waitUntilAppServerIsReady()

    @classmethod
    @profiled
    def stopSMTPServer(cls):
        """Kill the SMTP server and wait until it's exited."""
        if cls.smtp_controller is not None:
            cls.smtp_controller.reset()
            cls.smtp_controller.stop()
            cls.smtp_controller = None

    @classmethod
    def _kill(cls, sig):
        """Kill the appserver with `sig`.

        :param sig: the signal to kill with
        :type sig: int
        :return: True if the signal was delivered, otherwise False.
        :rtype: bool
        """
        try:
            os.kill(cls.appserver.pid, sig)
        except OSError as error:
            if error.errno == errno.ESRCH:
                # The child process doesn't exist.  Maybe it went away by the
                # time we got here.
                cls.appserver = None
                return False
            else:
                # Something else went wrong.
                raise
        else:
            return True

    @classmethod
    @profiled
    def stopAppServer(cls):
        """Kill the appserver and wait until it's exited."""
        if cls.appserver is not None:
            # Unfortunately, Popen.wait() does not support a timeout, so poll
            # for a little while, then SIGKILL the process if it refuses to
            # exit.  test_on_merge.py will barf if we hang here for too long.
            until = datetime.datetime.now() + WAIT_INTERVAL
            last_chance = False
            if not cls._kill(signal.SIGTERM):
                # The process is already gone.
                return
            while True:
                # Sleep and poll for process exit.
                if cls.appserver.poll() is not None:
                    break
                time.sleep(0.5)
                # If we slept long enough, send a harder kill and wait again.
                # If we already had our last chance, raise an exception.
                if datetime.datetime.now() > until:
                    if last_chance:
                        raise RuntimeError("The appserver just wouldn't die")
                    last_chance = True
                    if not cls._kill(signal.SIGKILL):
                        # The process is already gone.
                        return
                    until = datetime.datetime.now() + WAIT_INTERVAL
            cls.appserver = None

    @classmethod
    @profiled
    def postTestInvariants(cls):
        """Enforce some invariants after each test.

        Must be called in your layer class's `testTearDown()`.
        """
        if cls.appserver.poll() is not None:
            raise LayerIsolationError(
                "App server died in this test (status=%s):\n%s" % (
                    cls.appserver.returncode, cls.appserver.stdout.read()))
        DatabaseLayer.force_dirty_database()

    @classmethod
    def _cleanUpStaleAppServer(cls):
        """Kill any stale app server or pid file."""
        pid = pidfile.get_pid('launchpad', cls.appserver_config)
        if pid is not None:
            # Don't worry if the process no longer exists.
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError as error:
                if error.errno != errno.ESRCH:
                    raise
            pidfile.remove_pidfile('launchpad', cls.appserver_config)

    @classmethod
    def _runAppServer(cls, run_name):
        """Start the app server using runlaunchpad.py"""
        _config = cls.appserver_config
        cmd = [
            os.path.join(_config.root, 'bin', run_name),
            '-C', 'configs/%s/launchpad.conf' % _config.instance_name]
        environ = dict(os.environ)
        environ['LPCONFIG'] = _config.instance_name
        cls.appserver = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environ, cwd=_config.root)

    @classmethod
    def appserver_root_url(cls):
        return cls.appserver_config.vhost.mainsite.rooturl

    @classmethod
    def _waitUntilAppServerIsReady(cls):
        """Wait until the app server accepts connection."""
        assert cls.appserver is not None, "App server isn't started."
        root_url = cls.appserver_root_url()
        until = datetime.datetime.now() + WAIT_INTERVAL
        while until > datetime.datetime.now():
            try:
                connection = urlopen(root_url)
                connection.read()
            except IOError as error:
                # We are interested in a wrapped socket.error.
                # urlopen() really sucks here.
                if len(error.args) <= 1:
                    raise
                if not isinstance(error.args[1], socket.error):
                    raise
                if error.args[1].args[0] != errno.ECONNREFUSED:
                    raise
                returncode = cls.appserver.poll()
                if returncode is not None:
                    raise RuntimeError(
                        'App server failed to start (status=%d):\n%s' % (
                            returncode, cls.appserver.stdout.read()))
                time.sleep(0.5)
            else:
                connection.close()
                break
        else:
            os.kill(cls.appserver.pid, signal.SIGTERM)
            cls.appserver = None
            # Go no further.
            raise AssertionError('App server startup timed out.')


class AppServerLayer(LaunchpadFunctionalLayer):
    """Layer for tests that run in the webapp environment with an app server.
    """

    @classmethod
    @profiled
    def setUp(cls):
        LayerProcessController.setUp()

    @classmethod
    @profiled
    def tearDown(cls):
        LayerProcessController.stopAppServer()
        LayerProcessController.stopSMTPServer()

    @classmethod
    @profiled
    def testSetUp(cls):
        LaunchpadLayer.resetSessionDb()

    @classmethod
    @profiled
    def testTearDown(cls):
        LayerProcessController.postTestInvariants()


class CeleryJobLayer(AppServerLayer):
    """Layer for tests that run jobs via Celery."""

    celeryd = None

    @classmethod
    @profiled
    def setUp(cls):
        cls.celeryd = celeryd('launchpad_job')
        cls.celeryd.__enter__()

    @classmethod
    @profiled
    def tearDown(cls):
        cls.celeryd.__exit__(None, None, None)
        cls.celeryd = None


class CeleryBzrsyncdJobLayer(AppServerLayer):
    """Layer for tests that run jobs that read from branches via Celery."""

    celeryd = None

    @classmethod
    @profiled
    def setUp(cls):
        cls.celeryd = celeryd('bzrsyncd_job')
        cls.celeryd.__enter__()

    @classmethod
    @profiled
    def tearDown(cls):
        cls.celeryd.__exit__(None, None, None)
        cls.celeryd = None


class CeleryBranchWriteJobLayer(AppServerLayer):
    """Layer for tests that run jobs which write to branches via Celery."""

    celeryd = None

    @classmethod
    @profiled
    def setUp(cls):
        cls.celeryd = celeryd('branch_write_job')
        cls.celeryd.__enter__()

    @classmethod
    @profiled
    def tearDown(cls):
        cls.celeryd.__exit__(None, None, None)
        cls.celeryd = None


class ZopelessAppServerLayer(LaunchpadZopelessLayer):
    """Layer for tests that run in the zopeless environment with an appserver.
    """

    @classmethod
    @profiled
    def setUp(cls):
        LayerProcessController.setUp()

    @classmethod
    @profiled
    def tearDown(cls):
        LayerProcessController.stopAppServer()
        LayerProcessController.stopSMTPServer()

    @classmethod
    @profiled
    def testSetUp(cls):
        LaunchpadLayer.resetSessionDb()

    @classmethod
    @profiled
    def testTearDown(cls):
        LayerProcessController.postTestInvariants()


class TwistedAppServerLayer(TwistedLaunchpadZopelessLayer):
    """Layer for twisted-using zopeless tests that need a running app server.
    """

    @classmethod
    @profiled
    def setUp(cls):
        LayerProcessController.setUp()

    @classmethod
    @profiled
    def tearDown(cls):
        LayerProcessController.stopAppServer()
        LayerProcessController.stopSMTPServer()

    @classmethod
    @profiled
    def testSetUp(cls):
        LaunchpadLayer.resetSessionDb()

    @classmethod
    @profiled
    def testTearDown(cls):
        LayerProcessController.postTestInvariants()


class YUITestLayer(FunctionalLayer):
    """The layer for all YUITests cases."""


class YUIAppServerLayer(MemcachedLayer):
    """The layer for all YUIAppServer test cases."""

    @classmethod
    @profiled
    def setUp(cls):
        LayerProcessController.setConfig()
        LayerProcessController.startAppServer('run-testapp')

    @classmethod
    @profiled
    def tearDown(cls):
        LayerProcessController.stopAppServer()

    @classmethod
    @profiled
    def testSetUp(cls):
        LaunchpadLayer.resetSessionDb()
