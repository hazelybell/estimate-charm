# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the LaunchpadStatementTracer."""

__metaclass__ = type

from contextlib import contextmanager
import StringIO
import sys

from lazr.restful.utils import get_current_browser_request

from lp.services.osutils import override_environ
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.services.webapp import adapter as da
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


@contextmanager
def stdout():
    file = StringIO.StringIO()
    original = sys.stdout
    sys.stdout = file
    try:
        yield file
    finally:
        sys.stdout = original


@contextmanager
def stderr():
    file = StringIO.StringIO()
    original = sys.stderr
    sys.stderr = file
    try:
        yield file
    finally:
        sys.stderr = original


class StubTime:

    time = 1000.0

    def __call__(self):
        result = self.time
        self.time += 0.001
        return result


class StubConnection:

    def __init__(self):
        self._database = type('StubDatabase', (), dict(name='stub-database'))

    def to_database(self, params):
        for param in params:
            yield param


class StubCursor:

    def mogrify(self, statement, params):
        # This will behave rather differently than the real thing for
        # most types, but we can't use psycopg2's mogrify without a real
        # connection.
        mangled_params = tuple(
            repr(p) if isinstance(p, basestring) else p for p in params)
        return statement % tuple(mangled_params)


class TestLoggingOutsideOfRequest(TestCase):

    def setUp(self):
        super(TestLoggingOutsideOfRequest, self).setUp()
        self.connection = StubConnection()
        self.cursor = StubCursor()
        original_time = da.time
        self.addCleanup(setattr, da, 'time', original_time)
        da.time = StubTime()

    def execute(self, statement=None, params=None, **environ):
        with override_environ(**environ):
            tracer = da.LaunchpadStatementTracer()
        if statement is None:
            statement = 'SELECT * FROM bar WHERE bing = 42'
        tracer.connection_raw_execute(
            self.connection, self.cursor, statement, params)
        tracer.connection_raw_execute_success(
            self.connection, self.cursor, statement, params)

    def test_no_logging(self):
        with stderr() as file:
            self.execute()
            self.assertEqual('', file.getvalue())

    def test_stderr(self):
        with stderr() as file:
            self.execute(LP_DEBUG_SQL='1')
            self.assertEqual(
                '0-1@SQL-stub-database SELECT * FROM bar WHERE bing = 42\n' +
                "-" * 70 + "\n",
                file.getvalue())

    def test_stderr_with_stacktrace(self):
        with stderr() as file:
            self.execute(LP_DEBUG_SQL_EXTRA='1')
            self.assertStartsWith(
                file.getvalue(),
                '  File "')
            self.assertEndsWith(
                file.getvalue(),
                "." * 70 + "\n" +
                '0-1@SQL-stub-database SELECT * FROM bar WHERE bing = 42\n' +
                "-" * 70 + "\n")

    def test_data_logging(self):
        da.start_sql_logging()
        with stderr() as file:
            self.execute()
            self.assertEqual('', file.getvalue())
        result = da.stop_sql_logging()
        self.assertEqual(1, len(result))
        self.assertIs(None, result[0]['stack'])
        self.assertIs(None, result[0]['exception'])
        self.assertEqual(
            (1, 2, 'SQL-stub-database', 'SELECT * FROM bar WHERE bing = 42',
             None),
            result[0]['sql'])

    def test_data_logging_with_stacktrace(self):
        da.start_sql_logging(tracebacks_if=True)
        with stderr() as file:
            self.execute()
            self.assertEqual('', file.getvalue())
        result = da.stop_sql_logging()
        self.assertEqual(1, len(result))
        self.assertIsNot(None, result[0]['stack'])
        self.assertIs(None, result[0]['exception'])
        self.assertEqual(
            (1, 2, 'SQL-stub-database', 'SELECT * FROM bar WHERE bing = 42',
             None),
            result[0]['sql'])

    def test_data_logging_with_conditional_stacktrace(self):
        # Conditions must be normalized to uppercase.
        da.start_sql_logging(tracebacks_if=lambda sql: 'KUMQUAT' in sql)
        with stderr() as file:
            self.execute()
            self.execute(statement='SELECT * FROM kumquat WHERE bing = 42')
            self.assertEqual('', file.getvalue())
        result = da.stop_sql_logging()
        self.assertEqual(2, len(result))
        self.assertIs(None, result[0]['stack'])
        self.assertIsNot(None, result[1]['stack'])

    def test_data_logging_with_conditional_stacktrace_normalized_whitespace(
        self):
        # The whitespace in the SQL is normalized
        da.start_sql_logging(
            tracebacks_if=lambda sql: 'FROM KUMQUAT WHERE' in sql)
        self.execute(
            statement='SELECT * FROM   kumquat \nWHERE bing = 42')
        result = da.stop_sql_logging()
        self.assertEqual(1, len(result))
        self.assertIsNot(None, result[0]['stack'])

    def test_data_logging_with_broken_conditional_stacktrace(self):
        error = ValueError('rutebega')

        def ow(sql):
            raise error
        da.start_sql_logging(tracebacks_if=ow)
        with stderr() as file:
            self.execute()
            self.assertEqual('', file.getvalue())
        result = da.stop_sql_logging()
        self.assertEqual(1, len(result))
        self.assertIsNot(None, result[0]['stack'])
        self.assertEqual((ValueError, error), result[0]['exception'])
        self.assertEqual(
            (1, 2, 'SQL-stub-database', 'SELECT * FROM bar WHERE bing = 42',
             None),
            result[0]['sql'])

    def test_print_queries_with_tracebacks(self):
        da.start_sql_logging(tracebacks_if=True)
        self.execute()
        result = da.stop_sql_logging()
        with stdout() as file:
            da.print_queries(result)
            self.assertStartsWith(
                file.getvalue(),
                '  File "')
            self.assertEndsWith(
                file.getvalue(),
                "." * 70 + "\n" +
                '1-2@SQL-stub-database SELECT * FROM bar WHERE bing = 42\n' +
                "-" * 70 + "\n")

    def test_print_queries_without_tracebacks(self):
        da.start_sql_logging()
        self.execute()
        result = da.stop_sql_logging()
        with stdout() as file:
            da.print_queries(result)
            self.assertEqual(
                '1-2@SQL-stub-database SELECT * FROM bar WHERE bing = 42\n' +
                "-" * 70 + "\n",
            file.getvalue())

    def test_print_queries_with_exceptions(self):
        def ow(sql):
            raise ValueError('rutebega')
        da.start_sql_logging(tracebacks_if=ow)
        self.execute()
        result = da.stop_sql_logging()
        with stdout() as file:
            da.print_queries(result)
            self.assertStartsWith(
                file.getvalue(),
                'Error when determining whether to generate a stacktrace.\n' +
                'Traceback (most recent call last):\n' +
                '  File "')
            self.assertEndsWith(
                file.getvalue(),
                "ValueError: rutebega\n" +
                "." * 70 + "\n" +
                '1-2@SQL-stub-database SELECT * FROM bar WHERE bing = 42\n' +
                "-" * 70 + "\n")

    def test_context_manager(self):
        with StormStatementRecorder() as logger:
            self.execute()
        self.assertEqual(1, len(logger.query_data))
        self.assertIs(None, logger.query_data[0]['stack'])
        self.assertIs(None, logger.query_data[0]['exception'])
        self.assertEqual(
            (1, 2, 'SQL-stub-database', 'SELECT * FROM bar WHERE bing = 42',
             None),
            logger.query_data[0]['sql'])
        self.assertEqual(
            (1, 2, 'SQL-stub-database', 'SELECT * FROM bar WHERE bing = 42',
             None),
            logger.queries[0])
        self.assertEqual(
            'SELECT * FROM bar WHERE bing = 42',
            logger.statements[0])
        self.assertEqual(1, logger.count)
        with stdout() as file:
            # Show that calling str does not actually print (bugfix).
            result = str(logger)
            self.assertEqual('', file.getvalue())
        self.assertEqual(
            '1-2@SQL-stub-database SELECT * FROM bar WHERE bing = 42\n' +
            "-" * 70 + "\n",
            result)

    def test_context_manager_with_stacktrace(self):
        with StormStatementRecorder(tracebacks_if=True) as logger:
            self.execute()
        self.assertEqual(1, len(logger.query_data))
        self.assertIsNot(None, logger.query_data[0]['stack'])

    def test_sql_parameters(self):
        with StormStatementRecorder() as logger:
            self.execute(statement='SELECT * FROM bar WHERE bing = %s',
                         params=(142,))
        self.assertEqual(
            (1, 2, 'SQL-stub-database', 'SELECT * FROM bar WHERE bing = 142',
             None),
            logger.query_data[0]['sql'])


class TestLoggingWithinRequest(TestCaseWithFactory):
    # When called with a request, the code uses the request timeline and
    # its action objects.

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestLoggingWithinRequest, self).setUp()
        self.connection = StubConnection()
        self.person = self.factory.makePerson()
        da.set_request_started(1000.0)
        self.addCleanup(da.clear_request_started)

    def test_logger(self):
        tracer = da.LaunchpadStatementTracer()
        with person_logged_in(self.person):
            with StormStatementRecorder() as logger:
                tracer.connection_raw_execute(
                    self.connection, None,
                    'SELECT * FROM bar WHERE bing = 42', ())
                timeline = get_request_timeline(get_current_browser_request())
                action = timeline.actions[-1]
                self.assertEqual(
                    'SELECT * FROM bar WHERE bing = 42',
                    action.detail)
                self.assertEqual('SQL-stub-database', action.category)
                self.assertIs(None, action.duration)
                # Now we change the detail to verify that the action is the
                # source of the final log.
                action.detail = 'SELECT * FROM surprise'
                tracer.connection_raw_execute_success(
                    self.connection, None,
                    'SELECT * FROM bar WHERE bing = 42', ())
                self.assertIsNot(None, action.duration)
        self.assertEqual(
            'SELECT * FROM surprise', logger.query_data[0]['sql'][3])

    def test_stderr(self):
        with override_environ(LP_DEBUG_SQL='1'):
            tracer = da.LaunchpadStatementTracer()
        with person_logged_in(self.person):
            with stderr() as file:
                tracer.connection_raw_execute(
                    self.connection, None,
                    'SELECT * FROM bar WHERE bing = 42', ())
                timeline = get_request_timeline(get_current_browser_request())
                action = timeline.actions[-1]
                self.assertEqual(
                    'SELECT * FROM bar WHERE bing = 42',
                    action.detail)
                self.assertEqual('SQL-stub-database', action.category)
                self.assertIs(None, action.duration)
                # Now we change the detail to verify that the action is the
                # source of the final log.
                action.detail = 'SELECT * FROM surprise'
                tracer.connection_raw_execute_success(
                    self.connection, None,
                    'SELECT * FROM bar WHERE bing = 42', ())
                self.assertIsNot(None, action.duration)
                self.assertEndsWith(
                    file.getvalue(),
                    '@SQL-stub-database SELECT * FROM surprise\n' +
                    "-" * 70 + "\n")
