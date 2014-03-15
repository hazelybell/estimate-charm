# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from __future__ import absolute_import


__metaclass__ = type
__all__ = [
    'AbstractYUITestCase',
    'ANONYMOUS',
    'admin_logged_in',
    'anonymous_logged_in',
    'api_url',
    'BrowserTestCase',
    'build_yui_unittest_suite',
    'celebrity_logged_in',
    'clean_up_reactor',
    'ExpectedException',
    'extract_lp_cache',
    'FakeAdapterMixin',
    'FakeLaunchpadRequest',
    'FakeTime',
    'launchpadlib_credentials_for',
    'launchpadlib_for',
    'login',
    'login_as',
    'login_celebrity',
    'login_person',
    'login_team',
    'logout',
    'map_branch_contents',
    'normalize_whitespace',
    'nonblocking_readline',
    'oauth_access_token_for',
    'person_logged_in',
    'record_statements',
    'reset_logging',
    'run_process',
    'run_script',
    'run_with_login',
    'run_with_storm_debug',
    'StormStatementRecorder',
    'test_tales',
    'TestCase',
    'TestCaseWithFactory',
    'time_counter',
    'unlink_source_packages',
    'validate_mock_class',
    'verifyObject',
    'with_anonymous_login',
    'with_celebrity_logged_in',
    'with_person_logged_in',
    'ws_object',
    'YUIUnitTestCase',
    'ZopeTestInSubProcess',
    ]

from contextlib import contextmanager
from cStringIO import StringIO
from datetime import (
    datetime,
    timedelta,
    )
from fnmatch import fnmatchcase
from functools import partial
from inspect import (
    getargspec,
    getmro,
    isclass,
    ismethod,
    )
import logging
import os
import re
from select import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from bzrlib import trace
from bzrlib.bzrdir import (
    BzrDir,
    format_registry,
    )
from bzrlib.transport import get_transport
import fixtures
from lazr.restful.testing.tales import test_tales
from lazr.restful.testing.webservice import FakeRequest
import lp_sitecustomize
import oops_datedir_repo.serializer_rfc822
import pytz
import simplejson
from storm.store import Store
import subunit
import testtools
from testtools.content import Content
from testtools.content_type import UTF8_TEXT
from testtools.matchers import (
    Equals,
    MatchesRegex,
    MatchesSetwise,
    )
from testtools.testcase import ExpectedException as TTExpectedException
import transaction
from zope.component import (
    ComponentLookupError,
    getMultiAdapter,
    getSiteManager,
    getUtility,
    )
import zope.event
from zope.interface import Interface
from zope.interface.verify import (
    verifyClass,
    verifyObject as zope_verifyObject,
    )
from zope.publisher.interfaces.browser import IBrowserRequest
from zope.security.management import queryInteraction
from zope.security.proxy import (
    isinstance as zope_isinstance,
    removeSecurityProxy,
    )
from zope.testing.testrunner.runner import TestResult as ZopeTestResult

from lp.app.interfaces.security import IAuthorization
from lp.codehosting.vfs import (
    branch_id_to_path,
    get_rw_server,
    )
from lp.registry.interfaces.packaging import IPackagingUtil
from lp.services import features
from lp.services.config import config
from lp.services.database.sqlbase import flush_database_caches
from lp.services.features.flags import FeatureController
from lp.services.features.model import (
    FeatureFlag,
    getFeatureStore,
    )
from lp.services.features.webapp import ScopesFromRequest
from lp.services.osutils import override_environ
from lp.services.webapp import canonical_url
from lp.services.webapp.adapter import (
    print_queries,
    start_sql_logging,
    stop_sql_logging,
    )
from lp.services.webapp.authorization import (
    clear_cache as clear_permission_cache,
    )
from lp.services.webapp.interaction import ANONYMOUS
from lp.services.webapp.servers import (
    LaunchpadTestRequest,
    StepsToGo,
    WebServiceTestRequest,
    )
# Import the login helper functions here as it is a much better
# place to import them from in tests.
from lp.testing._login import (
    admin_logged_in,
    anonymous_logged_in,
    celebrity_logged_in,
    login,
    login_as,
    login_celebrity,
    login_person,
    login_team,
    logout,
    person_logged_in,
    run_with_login,
    with_anonymous_login,
    with_celebrity_logged_in,
    with_person_logged_in,
    )
from lp.testing._webservice import (
    api_url,
    launchpadlib_credentials_for,
    launchpadlib_for,
    oauth_access_token_for,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.fixture import CaptureOops
from lp.testing.karma import KarmaRecorder

# The following names have been imported for the purpose of being
# exported. They are referred to here to silence lint warnings.
admin_logged_in
anonymous_logged_in
api_url
celebrity_logged_in
launchpadlib_credentials_for
launchpadlib_for
login_as
login_celebrity
login_person
login_team
oauth_access_token_for
person_logged_in
run_with_login
test_tales
with_anonymous_login
with_celebrity_logged_in
with_person_logged_in


def reset_logging():
    """Reset the logging system back to defaults

    Currently, defaults means 'the way the Z3 testrunner sets it up'
    plus customizations made in lp_sitecustomize
    """
    # Remove all handlers from non-root loggers, and remove the loggers too.
    loggerDict = logging.Logger.manager.loggerDict
    for name, logger in list(loggerDict.items()):
        if name == 'pagetests-access':
            # Don't reset the hit logger used by the test infrastructure.
            continue
        if not isinstance(logger, logging.PlaceHolder):
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
        del loggerDict[name]

    # Remove all handlers from the root logger
    root = logging.getLogger('')
    for handler in root.handlers:
        root.removeHandler(handler)

    # Set the root logger's log level back to the default level: WARNING.
    root.setLevel(logging.WARNING)

    # Clean out the guts of the logging module. We don't want handlers that
    # have already been closed hanging around for the atexit handler to barf
    # on, for example.
    del logging._handlerList[:]
    logging._handlers.clear()

    # Reset the setup
    from zope.testing.testrunner.runner import Runner
    from zope.testing.testrunner.logsupport import Logging
    Logging(Runner()).global_setup()
    lp_sitecustomize.customize_logger()


class FakeTime:
    """Provides a controllable implementation of time.time().

    You can either advance the time manually using advance() or have it done
    automatically using next_now(). The amount of seconds to advance the
    time by is set during initialization but can also be changed for single
    calls of advance() or next_now().

    >>> faketime = FakeTime(1000)
    >>> print faketime.now()
    1000
    >>> print faketime.now()
    1000
    >>> faketime.advance(10)
    >>> print faketime.now()
    1010
    >>> print faketime.next_now()
    1011
    >>> print faketime.next_now(100)
    1111
    >>> faketime = FakeTime(1000, 5)
    >>> print faketime.next_now()
    1005
    >>> print faketime.next_now()
    1010
    """

    def __init__(self, start=None, advance=1):
        """Set up the instance.

        :param start: The value that will initially be returned by `now()`.
            If None, the current time will be used.
        :param advance: The value in secounds to advance the clock by by
            default.
        """
        if start is not None:
            self._now = start
        else:
            self._now = time.time()
        self._advance = advance

    def advance(self, amount=None):
        """Advance the value that will be returned by `now()`.

        :param amount: The amount of seconds to advance the value by.
            If None, the configured default value will be used.
        """
        if amount is None:
            self._now += self._advance
        else:
            self._now += amount

    def now(self):
        """Use this bound method instead of time.time in tests."""
        return self._now

    def next_now(self, amount=None):
        """Read the current time and advance it.

        Calls advance() and returns the current value of now().
        :param amount: The amount of seconds to advance the value by.
            If None, the configured default value will be used.
        """
        self.advance(amount)
        return self.now()


class StormStatementRecorder:
    """A storm tracer to count queries.

    This exposes the count and queries as
    lp.testing._webservice.QueryCollector does permitting its use with the
    HasQueryCount matcher.

    It also meets the context manager protocol, so you can gather queries
    easily:
    with StormStatementRecorder() as recorder:
        do somestuff
    self.assertThat(recorder, HasQueryCount(LessThan(42)))

    This also can be useful for investigation, such as in make harness.
    Try printing it after you have collected some queries.  You can
    even collect tracebacks, passing True to "tracebacks_if" for tracebacks
    of every SQL query, or a callable that takes the SQL query string and
    returns a boolean decision as to whether a traceback is desired.
    """
    # Note that tests for this are in lp.services.webapp.tests.
    # test_statementtracer, because this is really just a small wrapper of
    # the functionality found there.

    def __init__(self, tracebacks_if=False):
        self.tracebacks_if = tracebacks_if
        self.query_data = []

    @property
    def queries(self):
        return [record['sql'] for record in self.query_data]

    @property
    def count(self):
        return len(self.query_data)

    @property
    def statements(self):
        return [record['sql'][3] for record in self.query_data]

    def __enter__(self):
        self.query_data = start_sql_logging(self.tracebacks_if)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        stop_sql_logging()

    def __str__(self):
        out = StringIO()
        print_queries(self.query_data, file=out)
        return out.getvalue()


def record_statements(function, *args, **kwargs):
    """Run the function and record the sql statements that are executed.

    :return: a tuple containing the return value of the function,
        and a list of sql statements.
    """
    with StormStatementRecorder() as recorder:
        ret = function(*args, **kwargs)
    return (ret, recorder.statements)


def record_two_runs(tested_method, item_creator, first_round_number,
                    second_round_number=None):
    """A helper that returns the two storm statement recorders
    obtained when running tested_method after having run the
    method {item_creator} {first_round_number} times and then
    again after having run the same method {second_round_number}
    times.

    :return: a tuple containing the two recorders obtained by the successive
        runs.
    """
    for i in range(first_round_number):
        item_creator()
    # Record how many queries are issued when {tested_method} is
    # called after {item_creator} has been run {first_round_number}
    # times.
    flush_database_caches()
    if queryInteraction() is not None:
        clear_permission_cache()
    with StormStatementRecorder() as recorder1:
        tested_method()
    # Run {item_creator} {second_round_number} more times.
    if second_round_number is None:
        second_round_number = first_round_number
    for i in range(second_round_number):
        item_creator()
    # Record again the number of queries issued.
    flush_database_caches()
    if queryInteraction() is not None:
        clear_permission_cache()
    with StormStatementRecorder() as recorder2:
        tested_method()
    return recorder1, recorder2


def run_with_storm_debug(function, *args, **kwargs):
    """A helper function to run a function with storm debug tracing on."""
    from storm.tracer import debug
    debug(True)
    try:
        return function(*args, **kwargs)
    finally:
        debug(False)


class TestCase(testtools.TestCase, fixtures.TestWithFixtures):
    """Provide Launchpad-specific test facilities."""

    def becomeDbUser(self, dbuser):
        """Commit, then log into the database as `dbuser`.

        For this to work, the test must run in a layer.

        Try to test every code path at least once under a realistic db
        user, or you'll hit privilege violations later on.
        """
        assert self.layer, "becomeDbUser requires a layer."
        switch_dbuser(dbuser)

    def __str__(self):
        """The string representation of a test is its id.

        The most descriptive way of writing down a test is to write down its
        id. It is usually the fully-qualified Python name, which is pretty
        handy.
        """
        return self.id()

    def useContext(self, context):
        """Use the supplied context in this test.

        The context will be cleaned via addCleanup.
        """
        retval = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return retval

    def makeTemporaryDirectory(self):
        """Create a temporary directory, and return its path."""
        return self.useFixture(fixtures.TempDir()).path

    def installKarmaRecorder(self, *args, **kwargs):
        """Set up and return a `KarmaRecorder`.

        Registers the karma recorder immediately, and ensures that it is
        unregistered after the test.
        """
        recorder = KarmaRecorder(*args, **kwargs)
        recorder.register_listener()
        self.addCleanup(recorder.unregister_listener)
        return recorder

    def assertProvides(self, obj, interface):
        """Assert 'obj' correctly provides 'interface'."""
        from lp.testing.matchers import Provides
        self.assertThat(obj, Provides(interface))

    def assertClassImplements(self, cls, interface):
        """Assert 'cls' may correctly implement 'interface'."""
        self.assertTrue(
            verifyClass(interface, cls),
            "%r does not correctly implement %r." % (cls, interface))

    def assertNotifies(self, event_types, callable_obj, *args, **kwargs):
        """Assert that a callable performs a given notification.

        :param event_type: One or more event types that notification is
            expected for.
        :param callable_obj: The callable to call.
        :param *args: The arguments to pass to the callable.
        :param **kwargs: The keyword arguments to pass to the callable.
        :return: (result, event), where result was the return value of the
            callable, and event is the event emitted by the callable.
        """
        if not isinstance(event_types, (list, tuple)):
            event_types = [event_types]
        with EventRecorder() as recorder:
            result = callable_obj(*args, **kwargs)
        if len(recorder.events) == 0:
            raise AssertionError('No notification was performed.')
        self.assertEqual(len(event_types), len(recorder.events))
        for event, expected_type in zip(recorder.events, event_types):
            self.assertIsInstance(event, expected_type)
        return result, recorder.events

    def assertNoNotification(self, callable_obj, *args, **kwargs):
        """Assert that no notifications are generated by the callable.

        :param callable_obj: The callable to call.
        :param *args: The arguments to pass to the callable.
        :param **kwargs: The keyword arguments to pass to the callable.
        """
        with EventRecorder() as recorder:
            result = callable_obj(*args, **kwargs)
        if len(recorder.events) == 1:
            raise AssertionError(
                'An event was generated: %r.' % recorder.events[0])
        elif len(recorder.events) > 1:
            event_list = ', '.join(
                [repr(event) for event in recorder.events])
            raise AssertionError(
                'Events were generated: %s.' % event_list)
        return result

    def assertSqlAttributeEqualsDate(self, sql_object, attribute_name, date):
        """Fail unless the value of the attribute is equal to the date.

        Use this method to test that date value that may be UTC_NOW is equal
        to another date value. Trickery is required because SQLBuilder truth
        semantics cause UTC_NOW to appear equal to all dates.

        :param sql_object: a security-proxied SQLObject instance.
        :param attribute_name: the name of a database column in the table
            associated to this object.
        :param date: `datetime.datetime` object or `UTC_NOW`.
        """
        # XXX: Aaron Bentley 2008-04-14: Probably does not belong here, but
        # better location not clear. Used primarily for testing ORM objects,
        # which ought to use factory.
        sql_object = removeSecurityProxy(sql_object)
        sql_class = type(sql_object)
        store = Store.of(sql_object)
        found_object = store.find(
            sql_class, **({'id': sql_object.id, attribute_name: date})).one()
        if found_object is None:
            self.fail(
                "Expected %s to be %s, but it was %s."
                % (attribute_name, date, getattr(sql_object, attribute_name)))

    def assertTextMatchesExpressionIgnoreWhitespace(self,
                                                    regular_expression_txt,
                                                    text):

        def normalise_whitespace(text):
            return ' '.join(text.split())
        pattern = re.compile(
            normalise_whitespace(regular_expression_txt), re.S)
        self.assertIsNot(
            None, pattern.search(normalise_whitespace(text)), text)

    def assertIsInstance(self, instance, assert_class):
        """Assert that an instance is an instance of assert_class.

        instance and assert_class have the same semantics as the parameters
        to isinstance.
        """
        self.assertTrue(zope_isinstance(instance, assert_class),
            '%r is not an instance of %r' % (instance, assert_class))

    def assertIsNot(self, expected, observed, msg=None):
        """Assert that `expected` is not the same object as `observed`."""
        if msg is None:
            msg = "%r is %r" % (expected, observed)
        self.assertTrue(expected is not observed, msg)

    def assertContentEqual(self, iter1, iter2):
        """Assert that 'iter1' has the same content as 'iter2'."""
        self.assertThat(iter1, MatchesSetwise(*(map(Equals, iter2))))

    def assertRaisesWithContent(self, exception, exception_content,
                                func, *args, **kwargs):
        """Check if the given exception is raised with given content.

        If the exception isn't raised or the exception_content doesn't
        match what was raised an AssertionError is raised.
        """
        err = self.assertRaises(exception, func, *args, **kwargs)
        self.assertEqual(exception_content, str(err))

    def assertBetween(self, lower_bound, variable, upper_bound):
        """Assert that 'variable' is strictly between two boundaries."""
        self.assertTrue(
            lower_bound < variable < upper_bound,
            "%r < %r < %r" % (lower_bound, variable, upper_bound))

    def assertVectorEqual(self, *args):
        """Apply assertEqual to all given pairs in one go.

        Takes any number of (expected, observed) tuples and asserts each
        equality in one operation, thus making sure all tests are performed.
        If any of the tuples mismatches, AssertionError is raised.
        """
        expected_vector, observed_vector = zip(*args)
        return self.assertEqual(expected_vector, observed_vector)

    @contextmanager
    def expectedLog(self, regex):
        """Expect a log to be written that matches the regex."""
        output = StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger()
        logger.addHandler(handler)
        try:
            yield
        finally:
            logger.removeHandler(handler)
        self.assertThat(output.getvalue(), MatchesRegex(regex))

    def pushConfig(self, section, **kwargs):
        """Push some key-value pairs into a section of the config.

        The config values will be restored during test tearDown.
        """
        name = self.factory.getUniqueString()
        body = '\n'.join("%s: %s" % (k, v) for k, v in kwargs.iteritems())
        config.push(name, "\n[%s]\n%s\n" % (section, body))
        self.addCleanup(config.pop, name)

    def attachOopses(self):
        if len(self.oopses) > 0:
            for (i, report) in enumerate(self.oopses):
                content = Content(UTF8_TEXT,
                    partial(oops_datedir_repo.serializer_rfc822.to_chunks,
                    report))
                self.addDetail("oops-%d" % i, content)

    def attachLibrarianLog(self, fixture):
        """Include the logChunks from fixture in the test details."""
        # Evaluate the log when called, not later, to permit the librarian to
        # be shutdown before the detail is rendered.
        chunks = fixture.getLogChunks()
        content = Content(UTF8_TEXT, lambda: chunks)
        self.addDetail('librarian-log', content)

    def setUp(self):
        super(TestCase, self).setUp()
        # Circular imports.
        from lp.testing.factory import ObjectFactory
        from lp.testing.layers import LibrarianLayer
        self.factory = ObjectFactory()
        # Record the oopses generated during the test run.
        # You can call self.oops_capture.sync() to collect oopses from
        # subprocesses over amqp.
        self.oops_capture = self.useFixture(CaptureOops())
        self.oopses = self.oops_capture.oopses
        self.addCleanup(self.attachOopses)
        if LibrarianLayer.librarian_fixture is not None:
            self.addCleanup(
                self.attachLibrarianLog,
                LibrarianLayer.librarian_fixture)
        # Remove all log handlers, tests should not depend on global logging
        # config but should make their own config instead.
        logger = logging.getLogger()
        for handler in list(logger.handlers):
            logger.removeHandler(handler)

    def assertStatementCount(self, expected_count, function, *args, **kwargs):
        """Assert that the expected number of SQL statements occurred.

        :return: Returns the result of calling the function.
        """
        ret, statements = record_statements(function, *args, **kwargs)
        if len(statements) != expected_count:
            self.fail(
                "Expected %d statements, got %d:\n%s"
                % (expected_count, len(statements), "\n".join(statements)))
        return ret

    def useTempDir(self):
        """Use a temporary directory for this test."""
        tempdir = self.makeTemporaryDirectory()
        cwd = os.getcwd()
        os.chdir(tempdir)
        self.addCleanup(os.chdir, cwd)
        return tempdir

    def _unfoldEmailHeader(self, header):
        """Unfold a multiline e-mail header."""
        header = ''.join(header.splitlines())
        return header.replace('\t', ' ')

    def assertEmailHeadersEqual(self, expected, observed):
        """Assert that two e-mail headers are equal.

        The headers are unfolded before being compared.
        """
        return self.assertEqual(
            self._unfoldEmailHeader(expected),
            self._unfoldEmailHeader(observed))

    def assertStartsWith(self, s, prefix):
        if not s.startswith(prefix):
            raise AssertionError(
                'string %r does not start with %r' % (s, prefix))

    def assertEndsWith(self, s, suffix):
        """Asserts that s ends with suffix."""
        if not s.endswith(suffix):
            raise AssertionError(
                'string %r does not end with %r' % (s, suffix))

    def checkPermissions(self, expected_permissions, used_permissions,
                          type_):
        """Check if the used_permissions match expected_permissions.

        :param expected_permissions: A dictionary mapping a permission
            to a set of attribute names.
        :param used_permissions: The property get_permissions or
            set_permissions of getChecker(security_proxied_object).
        :param type_: The string "set" or "get".
        """
        expected = set(expected_permissions.keys())
        self.assertEqual(
            expected, set(used_permissions.values()),
            'Unexpected %s permissions' % type_)
        for permission in expected_permissions:
            attribute_names = set(
                name for name, value in used_permissions.items()
                if value == permission)
            self.assertEqual(
                expected_permissions[permission], attribute_names,
                'Unexpected set of attributes with %s permission %s:\n'
                'Defined but not expected: %s\n'
                'Expected but not defined: %s'
                % (
                    type_, permission,
                    sorted(
                        attribute_names - expected_permissions[permission]),
                    sorted(
                        expected_permissions[permission] - attribute_names)))


class TestCaseWithFactory(TestCase):

    def setUp(self, user=ANONYMOUS):
        super(TestCaseWithFactory, self).setUp()
        login(user)
        self.addCleanup(logout)
        from lp.testing.factory import LaunchpadObjectFactory
        self.factory = LaunchpadObjectFactory()
        self.direct_database_server = False
        self._use_bzr_branch_called = False
        # XXX: JonathanLange 2010-12-24 bug=694140: Because of Launchpad's
        # messing with global log state (see
        # lp.services.scripts.logger), trace._bzr_logger does not
        # necessarily equal logging.getLogger('bzr'), so we have to explicitly
        # make it so in order to avoid "No handlers for "bzr" logger'
        # messages.
        trace._bzr_logger = logging.getLogger('bzr')

    def getUserBrowser(self, url=None, user=None):
        """Return a Browser logged in as a fresh user, maybe opened at `url`.

        :param user: The user to open a browser for.
        """
        # Do the import here to avoid issues with import cycles.
        from lp.testing.pages import setupBrowserForUser
        login(ANONYMOUS)
        if user is None:
            user = self.factory.makePerson()
        browser = setupBrowserForUser(user)
        if url is not None:
            browser.open(url)
        return browser

    def createBranchAtURL(self, branch_url, format=None):
        """Create a branch at the supplied URL.

        The branch will be scheduled for deletion when the test terminates.
        :param branch_url: The URL to create the branch at.
        :param format: The format of branch to create.
        """
        if format is not None and isinstance(format, basestring):
            format = format_registry.get(format)()
        return BzrDir.create_branch_convenience(
            branch_url, format=format)

    def create_branch_and_tree(self, tree_location=None, product=None,
                               db_branch=None, format=None,
                               **kwargs):
        """Create a database branch, bzr branch and bzr checkout.

        :param tree_location: The path on disk to create the tree at.
        :param product: The product to associate with the branch.
        :param db_branch: If supplied, the database branch to use.
        :param format: Override the default bzrdir format to create.
        :return: a `Branch` and a workingtree.
        """
        if db_branch is None:
            if product is None:
                db_branch = self.factory.makeAnyBranch(**kwargs)
            else:
                db_branch = self.factory.makeProductBranch(product, **kwargs)
        branch_url = 'lp-internal:///' + db_branch.unique_name
        if not self.direct_database_server:
            transaction.commit()
        bzr_branch = self.createBranchAtURL(branch_url, format=format)
        if tree_location is None:
            tree_location = tempfile.mkdtemp()
            self.addCleanup(lambda: shutil.rmtree(tree_location))
        return db_branch, bzr_branch.create_checkout(
            tree_location, lightweight=True)

    def createBzrBranch(self, db_branch, parent=None):
        """Create a bzr branch for a database branch.

        :param db_branch: The database branch to create the branch for.
        :param parent: If supplied, the bzr branch to use as a parent.
        """
        bzr_branch = self.createBranchAtURL(db_branch.getInternalBzrUrl())
        if parent:
            bzr_branch.pull(parent)
            naked_branch = removeSecurityProxy(db_branch)
            naked_branch.last_scanned_id = bzr_branch.last_revision()
        return bzr_branch

    @staticmethod
    def getBranchPath(branch, base):
        """Return the path of the branch in the mirrored area.

        This always uses the configured mirrored area, ignoring whatever
        server might be providing lp-mirrored: urls.
        """
        # XXX gary 2009-5-28 bug 381325
        # This is a work-around for some failures on PQM, arguably caused by
        # relying on test set-up that is happening in the Makefile rather than
        # the actual test set-up.
        get_transport(base).create_prefix()
        return os.path.join(base, branch_id_to_path(branch.id))

    def useTempBzrHome(self):
        self.useTempDir()
        # Avoid leaking local user configuration into tests.
        self.useContext(override_environ(
            BZR_HOME=os.getcwd(), BZR_EMAIL=None, EMAIL=None,
            ))

    def useBzrBranches(self, direct_database=False):
        """Prepare for using bzr branches.

        This sets up support for lp-internal URLs, changes to a temp
        directory, and overrides the bzr home directory.

        :param direct_database: If true, translate branch locations by
            directly querying the database, not the internal XML-RPC server.
            If the test is in an AppServerLayer, you probably want to pass
            direct_database=False and if not you probably want to pass
            direct_database=True.
        """
        if self._use_bzr_branch_called:
            if direct_database != self.direct_database_server:
                raise AssertionError(
                    "useBzrBranches called with inconsistent values for "
                    "direct_database")
            return
        self._use_bzr_branch_called = True
        self.useTempBzrHome()
        self.direct_database_server = direct_database
        server = get_rw_server(direct_database=direct_database)
        server.start_server()
        self.addCleanup(server.destroy)


class BrowserTestCase(TestCaseWithFactory):
    """A TestCase class for browser tests.

    This testcase provides an API similar to page tests, and can be used for
    cases when one wants a unit test and not a frakking pagetest.
    """

    def setUp(self):
        """Provide useful defaults."""
        super(BrowserTestCase, self).setUp()
        self.user = self.factory.makePerson()

    def getViewBrowser(self, context, view_name=None, no_login=False,
                       rootsite=None, user=None):
        # Make sure that there is a user interaction in order to generate the
        # canonical url for the context object.
        if no_login:
            login(ANONYMOUS)
        else:
            if user is None:
                user = self.user
            login_person(user)
        url = canonical_url(context, view_name=view_name, rootsite=rootsite)
        logout()
        if no_login:
            from lp.testing.pages import setupBrowser
            browser = setupBrowser()
            browser.open(url)
            return browser
        else:
            return self.getUserBrowser(url, user)

    def getMainContent(self, context, view_name=None, rootsite=None,
                       no_login=False, user=None):
        """Beautiful soup of the main content area of context's page."""
        from lp.testing.pages import find_main_content
        browser = self.getViewBrowser(
            context, view_name, rootsite=rootsite, no_login=no_login,
            user=user)
        return find_main_content(browser.contents)

    def getMainText(self, context, view_name=None, rootsite=None,
                    no_login=False, user=None):
        """Return the main text of a context's page."""
        from lp.testing.pages import extract_text
        return extract_text(
            self.getMainContent(context, view_name, rootsite, no_login, user))


class WebServiceTestCase(TestCaseWithFactory):
    """Test case optimized for testing the web service using launchpadlib."""

    @property
    def layer(self):
        # XXX wgrant 2011-03-09 bug=505913:
        # TestTwistedJobRunner.test_timeout fails if this is at the
        # module level. There is probably some hidden circular import.
        from lp.testing.layers import AppServerLayer
        return AppServerLayer

    def setUp(self):
        super(WebServiceTestCase, self).setUp()
        self.ws_version = 'devel'
        self.service = self.factory.makeLaunchpadService(
            version=self.ws_version)

    def wsObject(self, obj, user=None):
        """Return the launchpadlib version of the supplied object.

        :param obj: The object to find the launchpadlib equivalent of.
        :param user: The user to use for accessing the object over
            launchpadlib.  Defaults to an arbitrary logged-in user.
        """
        if user is not None:
            service = self.factory.makeLaunchpadService(
                user, version=self.ws_version)
        else:
            service = self.service
        return ws_object(service, obj)


class AbstractYUITestCase(TestCase):

    layer = None
    suite_name = ''
    # 30 seconds for the suite.
    suite_timeout = 30000
    # By default we do not restrict per-test or times.  yuixhr tests do.
    incremental_timeout = None
    initial_timeout = None
    html_uri = None
    test_path = None

    TIMEOUT = object()
    MISSING_REPORT = object()

    _yui_results = None

    def __init__(self, methodName=None):
        """Create a new test case without a choice of test method name.

        Preventing the choice of test method ensures that we can safely
        provide a test ID based on the file path.
        """
        if methodName is None:
            methodName = self._testMethodName
        else:
            assert methodName == self._testMethodName
        super(AbstractYUITestCase, self).__init__(methodName)

    def id(self):
        """Return an ID for this test based on the file path."""
        return os.path.relpath(self.test_path, config.root)

    def setUp(self):
        super(AbstractYUITestCase, self).setUp()
        # html5browser imports from the gir/pygtk stack which causes
        # twisted tests to break because of gtk's initialize.
        import html5browser
        client = html5browser.Browser()
        page = client.load_page(self.html_uri,
                                timeout=self.suite_timeout,
                                initial_timeout=self.initial_timeout,
                                incremental_timeout=self.incremental_timeout)
        report = None
        if page.content:
            report = simplejson.loads(page.content)
        if page.return_code == page.CODE_FAIL:
            self._yui_results = self.TIMEOUT
            self._last_test_info = report
            return
        # Data['type'] is complete (an event).
        # Data['results'] is a dict (type=report)
        # with 1 or more dicts (type=testcase)
        # with 1 for more dicts (type=test).
        if report.get('type', None) != 'complete':
            # Did not get a report back.
            self._yui_results = self.MISSING_REPORT
            return
        self._yui_results = {}
        for key, value in report['results'].items():
            if isinstance(value, dict) and value['type'] == 'testcase':
                testcase_name = key
                test_case = value
                for key, value in test_case.items():
                    if isinstance(value, dict) and value['type'] == 'test':
                        test_name = '%s.%s' % (testcase_name, key)
                        test = value
                        self._yui_results[test_name] = dict(
                            result=test['result'], message=test['message'])

    def checkResults(self):
        """Check the results.

        The tests are run during `setUp()`, but failures need to be reported
        from here.
        """
        if self._yui_results == self.TIMEOUT:
            msg = 'JS timed out.'
            if self._last_test_info is not None:
                try:
                    msg += ('  The last test that ran to '
                            'completion before timing out was '
                            '%(testCase)s:%(testName)s.  The test %(type)sed.'
                            % self._last_test_info)
                except (KeyError, TypeError):
                    msg += ('  The test runner received an unexpected error '
                            'when trying to show information about the last '
                            'test to run.  The data it received was %r.'
                            % (self._last_test_info,))
            elif (self.incremental_timeout is not None or
                  self.initial_timeout is not None):
                msg += '  The test may never have started.'
            self.fail(msg)
        elif self._yui_results == self.MISSING_REPORT:
            self.fail("The data returned by js is not a test report.")
        elif self._yui_results is None or len(self._yui_results) == 0:
            self.fail("Test harness or js report format changed.")
        failures = []
        for test_name in self._yui_results:
            result = self._yui_results[test_name]
            if result['result'] not in ('pass', 'ignore'):
                failures.append(
                    'Failure in %s.%s: %s' % (
                    self.test_path, test_name, result['message']))
        self.assertEqual([], failures, '\n'.join(failures))


class YUIUnitTestCase(AbstractYUITestCase):

    _testMethodName = 'checkResults'

    def initialize(self, test_path):
        # The path is a .html file.
        self.test_path = test_path
        self.html_uri = 'file://%s' % os.path.join(
            config.root, 'lib', self.test_path)


def build_yui_unittest_suite(app_testing_path, yui_test_class):
    suite = unittest.TestSuite()
    testing_path = os.path.join(config.root, 'lib', app_testing_path)
    unit_test_names = _harvest_yui_test_files(testing_path)
    for unit_test_path in unit_test_names:
        test_case = yui_test_class()
        test_case.initialize(unit_test_path)
        suite.addTest(test_case)
    return suite


def _harvest_yui_test_files(file_path):
    for dirpath, dirnames, filenames in os.walk(file_path):
        for filename in filenames:
            if fnmatchcase(filename, "test_*.html"):
                yield os.path.join(dirpath, filename)


class ZopeTestInSubProcess:
    """Run tests in a sub-process, respecting Zope idiosyncrasies.

    Use this as a mixin with an interesting `TestCase` to isolate
    tests with side-effects. Each and every test *method* in the test
    case is run in a new, forked, sub-process. This will slow down
    your tests, so use it sparingly. However, when you need to, for
    example, start the Twisted reactor (which cannot currently be
    safely stopped and restarted in process) it is invaluable.

    This is basically a reimplementation of subunit's
    `IsolatedTestCase` or `IsolatedTestSuite`, but adjusted to work
    with Zope. In particular, Zope's TestResult object is responsible
    for calling testSetUp() and testTearDown() on the selected layer.
    """

    def run(self, result):
        # The result must be an instance of Zope's TestResult because
        # we construct a super() of it later on. Other result classes
        # could be supported with a more general approach, but it's
        # unlikely that any one approach is going to work for every
        # class. It's better to fail early and draw attention here.
        assert isinstance(result, ZopeTestResult), (
            "result must be a Zope result object, not %r." % (result, ))
        pread, pwrite = os.pipe()
        # We flush __stdout__ and __stderr__ at this point in order to avoid
        # bug 986429; they get copied in full when we fork, which means that
        # we end up with repeated output, resulting in repeated subunit
        # output.
        # Why not sys.stdout and sys.stderr instead?  Because when generating
        # subunit output we replace stdout and stderr with do-nothing objects
        # and direct the subunit stream to __stdout__ instead.  Therefore we
        # need to flush __stdout__ to be sure duplicate lines are not
        # generated.
        sys.__stdout__.flush()
        sys.__stderr__.flush()
        pid = os.fork()
        if pid == 0:
            # Child.
            os.close(pread)
            fdwrite = os.fdopen(pwrite, 'wb', 1)
            # Send results to both the Zope result object (so that
            # layer setup and teardown are done properly, etc.) and to
            # the subunit stream client so that the parent process can
            # obtain the result.
            result = testtools.MultiTestResult(
                result, subunit.TestProtocolClient(fdwrite))
            super(ZopeTestInSubProcess, self).run(result)
            fdwrite.flush()
            # See note above about flushing.
            sys.__stdout__.flush()
            sys.__stderr__.flush()
            # Exit hard to avoid running onexit handlers and to avoid
            # anything that could suppress SystemExit; this exit must
            # not be prevented.
            os._exit(0)
        else:
            # Parent.
            os.close(pwrite)
            fdread = os.fdopen(pread, 'rb')
            # Skip all the Zope-specific result stuff by using a
            # super() of the result. This is because the Zope result
            # object calls testSetUp() and testTearDown() on the
            # layer, and handles post-mortem debugging. These things
            # do not make sense in the parent process. More
            # immediately, it also means that the results are not
            # reported twice; they are reported on stdout by the child
            # process, so they need to be suppressed here.
            result = super(ZopeTestResult, result)
            # Accept the result from the child process.
            protocol = subunit.TestProtocolServer(result)
            protocol.readFrom(fdread)
            fdread.close()
            os.waitpid(pid, 0)


class EventRecorder:
    """Intercept and record Zope events.

    This prevents the events from propagating to their normal subscribers.
    The recorded events can be accessed via the 'events' list.
    """

    def __init__(self):
        self.events = []
        self.old_subscribers = None

    def __enter__(self):
        self.old_subscribers = zope.event.subscribers[:]
        zope.event.subscribers[:] = [self.events.append]
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        assert zope.event.subscribers == [self.events.append], (
            'Subscriber list has been changed while running!')
        zope.event.subscribers[:] = self.old_subscribers


@contextmanager
def feature_flags():
    """Provide a context in which feature flags work."""
    empty_request = LaunchpadTestRequest()
    old_features = features.get_relevant_feature_controller()
    features.install_feature_controller(FeatureController(
        ScopesFromRequest(empty_request).lookup))
    try:
        yield
    finally:
        features.install_feature_controller(old_features)


def time_counter(origin=None, delta=timedelta(seconds=5)):
    """A generator for yielding datetime values.

    Each time the generator yields a value, the origin is incremented
    by the delta.

    >>> now = time_counter(datetime(2007, 12, 1), timedelta(days=1))
    >>> now.next()
    datetime.datetime(2007, 12, 1, 0, 0)
    >>> now.next()
    datetime.datetime(2007, 12, 2, 0, 0)
    >>> now.next()
    datetime.datetime(2007, 12, 3, 0, 0)
    """
    if origin is None:
        origin = datetime.now(pytz.UTC)
    now = origin
    while True:
        yield now
        now += delta


def run_script(cmd_line, env=None, cwd=None):
    """Run the given command line as a subprocess.

    :param cmd_line: A command line suitable for passing to
        `subprocess.Popen`.
    :param env: An optional environment dict.  If none is given, the
        script will get a copy of your present environment.  Either way,
        PYTHONPATH will be removed from it because it will break the
        script.
    :return: A 3-tuple of stdout, stderr, and the process' return code.
    """
    if env is None:
        env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    process = subprocess.Popen(
        cmd_line, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env, cwd=cwd)
    (out, err) = process.communicate()
    return out, err, process.returncode


def run_process(cmd, env=None):
    """Run the given command as a subprocess.

    This differs from `run_script` in that it does not execute via a shell and
    it explicitly connects stdin to /dev/null so that processes will not be
    able to hang, waiting for user input.

    :param cmd_line: A command suitable for passing to `subprocess.Popen`.
    :param env: An optional environment dict. If none is given, the script
        will get a copy of your present environment. Either way, PYTHONPATH
        will be removed from it because it will break the script.
    :return: A 3-tuple of stdout, stderr, and the process' return code.
    """
    if env is None:
        env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    with open(os.devnull, "rb") as devnull:
        process = subprocess.Popen(
            cmd, stdin=devnull, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
        stdout, stderr = process.communicate()
        return stdout, stderr, process.returncode


def normalize_whitespace(string):
    """Replace all sequences of whitespace with a single space."""
    # In Python 2.4, splitting and joining a string to normalize
    # whitespace is roughly 6 times faster than using an uncompiled
    # regex (for the expression \s+), and 4 times faster than a
    # compiled regex.
    return " ".join(string.split())


def map_branch_contents(branch):
    """Return all files in branch at `branch_url`.

    :param branch_url: the URL for an accessible branch.
    :return: a dict mapping file paths to file contents.  Only regular
        files are included.
    """
    # XXX: This doesn't seem to be a generically useful testing function.
    # Perhaps it should go into a sub-module? -- jml
    contents = {}
    tree = branch.basis_tree()
    tree.lock_read()
    try:
        for dir, entries in tree.walkdirs():
            dirname, id = dir
            for entry in entries:
                file_path, file_name, file_type = entry[:3]
                if file_type == 'file':
                    stored_file = tree.get_file_by_path(file_path)
                    contents[file_path] = stored_file.read()
    finally:
        tree.unlock()

    return contents


def set_feature_flag(name, value, scope=u'default', priority=1):
    """Set a feature flag to the specified value.

    In order to access the flag, use the feature_flags context manager or
    set the feature controller in some other way.
    :param name: The name of the flag.
    :param value: The value of the flag.
    :param scope: The scope in which the specified value applies.
    """
    assert features.get_relevant_feature_controller() is not None
    flag = FeatureFlag(
        scope=scope, flag=name, value=value, priority=priority)
    store = getFeatureStore()
    store.add(flag)
    # Make sure that the feature is saved into the db right now.
    store.flush()


def validate_mock_class(mock_class):
    """Validate method signatures in mock classes derived from real classes.

    We often use mock classes in tests which are derived from real
    classes.

    This function ensures that methods redefined in the mock
    class have the same signature as the corresponding methods of
    the base class.

    >>> class A:
    ...
    ...     def method_one(self, a):
    ...         pass

    >>>
    >>> class B(A):
    ...     def method_one(self, a):
    ...        pass
    >>> validate_mock_class(B)

    If a class derived from A defines method_one with a different
    signature, we get an AssertionError.

    >>> class C(A):
    ...     def method_one(self, a, b):
    ...        pass
    >>> validate_mock_class(C)
    Traceback (most recent call last):
    ...
    AssertionError: Different method signature for method_one:...

    Even a parameter name must not be modified.

    >>> class D(A):
    ...     def method_one(self, b):
    ...        pass
    >>> validate_mock_class(D)
    Traceback (most recent call last):
    ...
    AssertionError: Different method signature for method_one:...

    If validate_mock_class() for anything but a class, we get an
    AssertionError.

    >>> validate_mock_class('a string')
    Traceback (most recent call last):
    ...
    AssertionError: validate_mock_class() must be called for a class
    """
    assert isclass(mock_class), (
        "validate_mock_class() must be called for a class")
    base_classes = getmro(mock_class)
    # Don't use inspect.getmembers() here because it fails on __provides__, a
    # descriptor added by zope.interface as part of its caching strategy. See
    # http://comments.gmane.org/gmane.comp.python.zope.interface/241.
    for name in dir(mock_class):
        if name == '__provides__':
            continue
        obj = getattr(mock_class, name)
        if ismethod(obj):
            for base_class in base_classes[1:]:
                if name in base_class.__dict__:
                    mock_args = getargspec(obj)
                    real_args = getargspec(base_class.__dict__[name])
                    if mock_args != real_args:
                        raise AssertionError(
                            'Different method signature for %s: %r %r' % (
                            name, mock_args, real_args))
                    else:
                        break


def ws_object(launchpad, obj):
    """Convert an object into its webservice version.

    :param launchpad: The Launchpad instance to convert from.
    :param obj: The object to convert.
    :return: A launchpadlib Entry object.
    """
    api_request = WebServiceTestRequest(SERVER_URL=str(launchpad._root_uri))
    return launchpad.load(canonical_url(obj, request=api_request))


class NestedTempfile(fixtures.Fixture):
    """Nest all temporary files and directories inside a top-level one."""

    def setUp(self):
        super(NestedTempfile, self).setUp()
        tempdir = fixtures.TempDir()
        self.useFixture(tempdir)
        patch = fixtures.MonkeyPatch("tempfile.tempdir", tempdir.path)
        self.useFixture(patch)


@contextmanager
def monkey_patch(context, **kwargs):
    """In the ContextManager scope, monkey-patch values.

    The context may be anything that supports setattr.  Packages,
    modules, objects, etc.  The kwargs are the name/value pairs for the
    values to set.
    """
    old_values = {}
    not_set = object()
    for name, value in kwargs.iteritems():
        old_values[name] = getattr(context, name, not_set)
        setattr(context, name, value)
    try:
        yield
    finally:
        for name, value in old_values.iteritems():
            if value is not_set:
                delattr(context, name)
            else:
                setattr(context, name, value)


def unlink_source_packages(product):
    """Remove all links between the product and source packages.

    A product cannot be deactivated if it is linked to source packages.
    """
    packaging_util = getUtility(IPackagingUtil)
    for source_package in product.sourcepackages:
        packaging_util.deletePackaging(
            source_package.productseries,
            source_package.sourcepackagename,
            source_package.distroseries)


class ExpectedException(TTExpectedException):
    """An ExpectedException that provides access to the caught exception."""

    def __init__(self, exc_type, value_re):
        super(ExpectedException, self).__init__(exc_type, value_re)
        self.caught_exc = None

    def __exit__(self, exc_type, exc_value, traceback):
        self.caught_exc = exc_value
        return super(ExpectedException, self).__exit__(
            exc_type, exc_value, traceback)


def extract_lp_cache(text):
    match = re.search(r'<script[^>]*>LP.cache = (\{.*\});</script>', text)
    if match is None:
        raise ValueError('No JSON cache found.')
    return simplejson.loads(match.group(1))


def nonblocking_readline(instream, timeout):
    """Non-blocking readline.

    Files must provide a valid fileno() method. This is a test helper
    as it is inefficient and unlikely useful for production code.
    """
    result = StringIO()
    start = now = time.time()
    deadline = start + timeout
    while (now < deadline and not result.getvalue().endswith('\n')):
        rlist = select([instream], [], [], deadline - now)
        if rlist:
            # Reading 1 character at a time is inefficient, but means
            # we don't need to implement put-back.
            next_char = os.read(instream.fileno(), 1)
            if next_char == "":
                break  # EOF
            result.write(next_char)
        now = time.time()
    return result.getvalue()


class FakeLaunchpadRequest(FakeRequest):

    @property
    def stepstogo(self):
        """See `IBasicLaunchpadRequest`."""
        return StepsToGo(self)


class FakeAdapterMixin:
    """A testcase mixin that helps register/unregister Zope adapters.

    These helper methods simplify the task to registering Zope adapters
    during the setup of a test and they will be unregistered when the
    test completes.
    """
    def registerAdapter(self, adapter_class, for_interfaces,
                        provided_interface, name=None):
        """Register an adapter from the required interfacs to the provided.

        eg. registerAdapter(
                TestOtherThing, (IThing, ILayer), IOther, name='fnord')
        """
        getSiteManager().registerAdapter(
            adapter_class, for_interfaces, provided_interface, name=name)
        self.addCleanup(
            getSiteManager().unregisterAdapter, adapter_class,
            for_interfaces, provided_interface, name=name)

    def registerAuthorizationAdapter(self, authorization_class,
                                     for_interface, permission_name):
        """Register a security checker to test authorisation.

        eg. registerAuthorizationAdapter(
                TestChecker, IPerson, 'launchpad.View')
        """
        self.registerAdapter(
            authorization_class, (for_interface, ), IAuthorization,
            name=permission_name)

    def registerBrowserViewAdapter(self, view_class, for_interface, name):
        """Register a security checker to test authorization.

        eg registerBrowserViewAdapter(TestView, IPerson, '+test-view')
        """
        self.registerAdapter(
            view_class, (for_interface, IBrowserRequest), Interface,
            name=name)

    def getAdapter(self, for_interfaces, provided_interface, name=None):
        return getMultiAdapter(for_interfaces, provided_interface, name=name)

    def registerUtility(self, component, for_interface, name=''):
        try:
            current_commponent = getUtility(for_interface, name=name)
        except ComponentLookupError:
            current_commponent = None
        site_manager = getSiteManager()
        site_manager.registerUtility(component, for_interface, name)
        self.addCleanup(
            site_manager.unregisterUtility, component, for_interface, name)
        if current_commponent is not None:
            # Restore the default utility.
            self.addCleanup(
                site_manager.registerUtility, current_commponent,
                for_interface, name)


def clean_up_reactor():
    # XXX: JonathanLange 2010-11-22: These tests leave stacks of delayed
    # calls around.  They need to be updated to use Twisted correctly.
    # For the meantime, just blat the reactor.
    from twisted.internet import reactor
    for delayed_call in reactor.getDelayedCalls():
        delayed_call.cancel()


def verifyObject(iface, candidate, tentative=0):
    """A specialized verifyObject which removes the security proxy of the
    object before verifying it.
    """
    naked_candidate = removeSecurityProxy(candidate)
    return zope_verifyObject(iface, naked_candidate, tentative=0)
