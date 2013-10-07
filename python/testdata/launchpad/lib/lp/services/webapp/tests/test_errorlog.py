# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for error logging & OOPS reporting."""

__metaclass__ = type

import datetime
import httplib
import StringIO
import sys
from textwrap import dedent
import traceback

from fixtures import TempDir
from lazr.batchnavigator.interfaces import InvalidBatchSizeError
from lazr.restful.declarations import error_status
from lp_sitecustomize import customize_get_converter
import oops_amqp
import pytz
import testtools
from timeline.timeline import Timeline
from zope.authentication.interfaces import IUnauthenticatedPrincipal
from zope.interface import (
    directlyProvides,
    implements,
    )
from zope.publisher.browser import TestRequest
from zope.publisher.interfaces import NotFound
from zope.publisher.interfaces.xmlrpc import IXMLRPCRequest
from zope.security.interfaces import Unauthorized

from lp.app import versioninfo
from lp.app.errors import (
    GoneError,
    TranslationUnavailable,
    )
from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.services.webapp.errorlog import (
    _filter_session_statement,
    _is_sensitive,
    attach_http_request,
    ErrorReport,
    ErrorReportingUtility,
    notify_publisher,
    ScriptRequest,
    )
from lp.services.webapp.interfaces import (
    IUnloggedException,
    NoReferrerError,
    )
from lp.testing.layers import LaunchpadLayer


UTC = pytz.utc


class ArbitraryException(Exception):
    """Used to test handling of exceptions in OOPS reports."""


class TestErrorReport(testtools.TestCase):

    def test___init__(self):
        """Test ErrorReport.__init__()"""
        entry = ErrorReport('id', 'exc-type', 'exc-value', 'timestamp',
                            'traceback-text', 'username', 'url', 42,
                            {'name1': 'value1', 'name2': 'value2',
                             'name3': 'value3'},
                            [(1, 5, 'store_a', 'SELECT 1'),
                             (5, 10, 'store_b', 'SELECT 2')],
                            topic='pageid',
                            )
        self.assertEqual(entry.id, 'id')
        self.assertEqual(entry.type, 'exc-type')
        self.assertEqual(entry.value, 'exc-value')
        self.assertEqual(entry.time, 'timestamp')
        self.assertEqual(entry.topic, 'pageid')
        self.assertEqual(entry.branch_nick, versioninfo.branch_nick)
        self.assertEqual(entry.revno, versioninfo.revno)
        self.assertEqual(entry.username, 'username')
        self.assertEqual(entry.url, 'url')
        self.assertEqual(entry.duration, 42)
        self.assertEqual({
            'name1': 'value1',
            'name2': 'value2',
            'name3': 'value3',
            }, entry.req_vars)
        self.assertEqual(len(entry.timeline), 2)
        self.assertEqual(entry.timeline[0], (1, 5, 'store_a', 'SELECT 1'))
        self.assertEqual(entry.timeline[1], (5, 10, 'store_b', 'SELECT 2'))

    def test_read(self):
        """Test ErrorReport.read()."""
        # Note: this exists to test the compatibility thunk only.
        fp = StringIO.StringIO(dedent("""\
            Oops-Id: OOPS-A0001
            Exception-Type: NotFound
            Exception-Value: error message
            Date: 2005-04-01T00:00:00+00:00
            Page-Id: IFoo:+foo-template
            User: Sample User
            URL: http://localhost:9000/foo
            Duration: 42

            HTTP_USER_AGENT=Mozilla/5.0
            HTTP_REFERER=http://localhost:9000/
            name%3Dfoo=hello%0Aworld

            00001-00005@store_a SELECT 1
            00005-00010@store_b SELECT 2

            traceback-text"""))
        entry = ErrorReport.read(fp)
        self.assertEqual(entry.id, 'OOPS-A0001')
        self.assertEqual(entry.type, 'NotFound')
        self.assertEqual(entry.value, 'error message')
        self.assertEqual(
                entry.time, datetime.datetime(2005, 4, 1, tzinfo=UTC))
        self.assertEqual(entry.topic, 'IFoo:+foo-template')
        self.assertEqual(entry.tb_text, 'traceback-text')
        self.assertEqual(entry.username, 'Sample User')
        self.assertEqual(entry.url, 'http://localhost:9000/foo')
        self.assertEqual(entry.duration, 42)
        self.assertEqual({
            'HTTP_USER_AGENT': 'Mozilla/5.0',
            'HTTP_REFERER': 'http://localhost:9000/',
            'name=foo': 'hello\nworld'},
            entry.req_vars)
        self.assertEqual(len(entry.timeline), 2)
        self.assertEqual(entry.timeline[0], [1, 5, 'store_a', 'SELECT 1'])
        self.assertEqual(entry.timeline[1], [5, 10, 'store_b', 'SELECT 2'])


class TestErrorReportingUtility(testtools.TestCase):

    # want rabbit
    layer = LaunchpadLayer

    def setUp(self):
        super(TestErrorReportingUtility, self).setUp()
        # ErrorReportingUtility reads the global config to get the
        # current error directory.
        tempdir = self.useFixture(TempDir()).path
        test_data = dedent("""
            [error_reports]
            error_dir: %s
            """ % tempdir)
        config.push('test_data', test_data)
        self.addCleanup(config.pop, 'test_data')

    def test_configure(self):
        """Test ErrorReportingUtility.setConfigSection()."""
        utility = ErrorReportingUtility()
        # The ErrorReportingUtility uses the config.error_reports section
        # by default.
        self.assertEqual(config.error_reports.oops_prefix,
            utility.oops_prefix)
        self.assertEqual(config.error_reports.error_dir,
            utility._oops_datedir_repo.root)
        # Some external processes may extend the reporter/prefix with
        # extra information.
        utility.configure(section_name='branchscanner')
        self.assertEqual('T-branchscanner', utility.oops_prefix)

        # The default error section can be restored.
        utility.configure()
        self.assertEqual(config.error_reports.oops_prefix,
            utility.oops_prefix)

        # We should have had three publishers setup:
        oops_config = utility._oops_config
        self.assertEqual(3, len(oops_config.publishers))
        # - a rabbit publisher
        self.assertIsInstance(oops_config.publishers[0], oops_amqp.Publisher)
        # - a datedir publisher wrapped in a publish_new_only wrapper
        datedir_repo = utility._oops_datedir_repo
        publisher = oops_config.publishers[1].func_closure[0].cell_contents
        self.assertEqual(publisher, datedir_repo.publish)
        # - a notify publisher
        self.assertEqual(oops_config.publishers[2], notify_publisher)

    def test_multiple_raises_in_request(self):
        """An OOPS links to the previous OOPS in the request, if any."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[0]

        request = TestRequestWithPrincipal()
        try:
            raise ArbitraryException('foo')
        except ArbitraryException:
            report = utility.raising(sys.exc_info(), request)

        self.assertFalse('last_oops' in report)
        last_oopsid = request.oopsid
        try:
            raise ArbitraryException('foo')
        except ArbitraryException:
            report = utility.raising(sys.exc_info(), request)

        self.assertTrue('last_oops' in report)
        self.assertEqual(report['last_oops'], last_oopsid)

    def test_raising_with_request(self):
        """Test ErrorReportingUtility.raising() with a request"""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[0]

        request = TestRequestWithPrincipal(
                environ={
                    'SERVER_URL': 'http://localhost:9000/foo',
                    'HTTP_COOKIE': 'lp=cookies_hidden_for_security_reasons',
                    'name1': 'value1',
                    },
                form={
                    'name1': 'value3 \xa7',
                    'name2': 'value2',
                    u'\N{BLACK SQUARE}': u'value4',
                    })
        request.setInWSGIEnvironment('launchpad.pageid', 'IFoo:+foo-template')

        try:
            raise ArbitraryException('xyz\nabc')
        except ArbitraryException:
            report = utility.raising(sys.exc_info(), request)

        # topic is obtained from the request
        self.assertEqual('IFoo:+foo-template', report['topic'])
        self.assertEqual(u'Login, 42, title, description |\u25a0|',
                report['username'])
        self.assertEqual('http://localhost:9000/foo', report['url'])
        self.assertEqual({
            'CONTENT_LENGTH': '0',
            'GATEWAY_INTERFACE': 'TestFooInterface/1.0',
            'HTTP_COOKIE': '<hidden>',
            'HTTP_HOST': '127.0.0.1',
            'SERVER_URL': 'http://localhost:9000/foo',
            u'\u25a0': 'value4',
            'lp': '<hidden>',
            'name1': 'value3 \xa7',
            'name2': 'value2',
            }, report['req_vars'])
        # verify that the oopsid was set on the request
        self.assertEqual(request.oopsid, report['id'])
        self.assertEqual(request.oops, report)

    def test_raising_with_xmlrpc_request(self):
        # Test ErrorReportingUtility.raising() with an XML-RPC request.
        request = TestRequest()
        directlyProvides(request, IXMLRPCRequest)
        request.getPositionalArguments = lambda: (1, 2)
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        try:
            raise ArbitraryException('xyz\nabc')
        except ArbitraryException:
            report = utility.raising(sys.exc_info(), request)
        self.assertEqual("(1, 2)", report['req_vars']['xmlrpc args'])

    def test_raising_non_utf8_request_param_key_bug_896959(self):
        # When a form has a nonutf8 request param, the key in req_vars must
        # still be unicode (or utf8).
        request = TestRequest(form={'foo\x85': 'bar'})
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        try:
            raise ArbitraryException('foo')
        except ArbitraryException:
            report = utility.raising(sys.exc_info(), request)
        for key in report['req_vars'].keys():
            if isinstance(key, str):
                key.decode('utf8')
            else:
                self.assertIsInstance(key, unicode)

    def test_raising_with_webservice_request(self):
        # Test ErrorReportingUtility.raising() with a WebServiceRequest
        # request. Only some exceptions result in OOPSes.
        request = TestRequest()
        directlyProvides(request, WebServiceLayer)
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]

        # Exceptions that don't use error_status result in OOPSes.
        try:
            raise ArbitraryException('xyz\nabc')
        except ArbitraryException:
            self.assertNotEqual(None,
                    utility.raising(sys.exc_info(), request))

        # Exceptions with a error_status in the 500 range result
        # in OOPSes.
        @error_status(httplib.INTERNAL_SERVER_ERROR)
        class InternalServerError(Exception):
            pass
        try:
            raise InternalServerError("")
        except InternalServerError:
            self.assertNotEqual(None,
                    utility.raising(sys.exc_info(), request))

        # Exceptions with any other error_status do not result
        # in OOPSes.
        @error_status(httplib.BAD_REQUEST)
        class BadDataError(Exception):
            pass
        try:
            raise BadDataError("")
        except BadDataError:
            self.assertEqual(None, utility.raising(sys.exc_info(), request))

    def test_raising_for_script(self):
        """Test ErrorReportingUtility.raising with a ScriptRequest."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]

        # A list because code using ScriptRequest expects that - ScriptRequest
        # translates it to a dict for now.
        req_vars = [
            ('name2', 'value2'),
            ('name1', 'value1'),
            ('name1', 'value3'),
            ]
        url = 'https://launchpad.net/example'
        try:
            raise ArbitraryException('xyz\nabc')
        except ArbitraryException:
            # Do not test escaping of request vars here, it is already tested
            # in test_raising_with_request.
            request = ScriptRequest(req_vars, URL=url)
            report = utility.raising(sys.exc_info(), request)

        self.assertEqual(url, report['url'])
        self.assertEqual(dict(req_vars), report['req_vars'])

    def test_raising_with_unprintable_exception(self):
        class UnprintableException(Exception):
            def __str__(self):
                raise RuntimeError('arrgh')
            __repr__ = __str__

        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        try:
            raise UnprintableException()
        except UnprintableException:
            report = utility.raising(sys.exc_info())

        unprintable = '<unprintable UnprintableException object>'
        self.assertEqual(unprintable, report['value'])
        self.assertIn(
            'UnprintableException: ' + unprintable, report['tb_text'])

    def test_raising_unauthorized_without_request(self):
        """Unauthorized exceptions are logged when there's no request."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        try:
            raise Unauthorized('xyz')
        except Unauthorized:
            oops = utility.raising(sys.exc_info())
        self.assertNotEqual(None, oops)

    def test_raising_unauthorized_without_principal(self):
        """Unauthorized exceptions are logged when the request has no
        principal."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = ScriptRequest([('name2', 'value2')])
        try:
            raise Unauthorized('xyz')
        except Unauthorized:
            self.assertNotEqual(None,
                    utility.raising(sys.exc_info(), request))

    def test_raising_unauthorized_with_unauthenticated_principal(self):
        """Unauthorized exceptions are not logged when the request has an
        unauthenticated principal."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = TestRequestWithUnauthenticatedPrincipal()
        try:
            raise Unauthorized('xyz')
        except Unauthorized:
            self.assertEqual(None, utility.raising(sys.exc_info(), request))

    def test_raising_unauthorized_with_authenticated_principal(self):
        """Unauthorized exceptions are logged when the request has an
        authenticated principal."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = TestRequestWithPrincipal()
        try:
            raise Unauthorized('xyz')
        except Unauthorized:
            self.assertNotEqual(None,
                    utility.raising(sys.exc_info(), request))

    def test_raising_translation_unavailable(self):
        """Test ErrorReportingUtility.raising() with a TranslationUnavailable
        exception.

        An OOPS is not recorded when a TranslationUnavailable exception is
        raised.
        """
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        self.assertTrue(
            TranslationUnavailable.__name__ in utility._ignored_exceptions,
            'TranslationUnavailable is not in _ignored_exceptions.')
        try:
            raise TranslationUnavailable('xyz')
        except TranslationUnavailable:
            self.assertEqual(None, utility.raising(sys.exc_info()))

    def test_ignored_exceptions_for_offsite_referer(self):
        # Exceptions caused by bad URLs that may not be an Lp code issue.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        errors = set([
            GoneError.__name__, InvalidBatchSizeError.__name__,
            NotFound.__name__])
        self.assertEqual(
            errors, utility._ignored_exceptions_for_offsite_referer)

    def test_ignored_exceptions_for_offsite_referer_reported(self):
        # Oopses are reported when Launchpad is the referer for a URL
        # that caused an exception.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = TestRequest(
            environ={
                'SERVER_URL': 'http://launchpad.dev/fnord',
                'HTTP_REFERER': 'http://launchpad.dev/snarf'})
        try:
            raise GoneError('fnord')
        except GoneError:
            self.assertNotEqual(None,
                    utility.raising(sys.exc_info(), request))

    def test_ignored_exceptions_for_cross_vhost_referer_reported(self):
        # Oopses are reported when a Launchpad  vhost is the referer for a URL
        # that caused an exception.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = TestRequest(
            environ={
                'SERVER_URL': 'http://launchpad.dev/fnord',
                'HTTP_REFERER': 'http://bazaar.launchpad.dev/snarf'})
        try:
            raise GoneError('fnord')
        except GoneError:
            self.assertNotEqual(None,
                    utility.raising(sys.exc_info(), request))

    def test_ignored_exceptions_for_criss_cross_vhost_referer_reported(self):
        # Oopses are reported when a Launchpad referer for a bad URL on a
        # vhost that caused an exception.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = TestRequest(
            environ={
                'SERVER_URL': 'http://bazaar.launchpad.dev/fnord',
                'HTTP_REFERER': 'http://launchpad.dev/snarf'})
        try:
            raise GoneError('fnord')
        except GoneError:
            self.assertNotEqual(
                    None, utility.raising(sys.exc_info(), request))

    def test_ignored_exceptions_for_offsite_referer_not_reported(self):
        # Oopses are not reported when Launchpad is not the referer.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        # There is no HTTP_REFERER header in this request
        request = TestRequest(
            environ={'SERVER_URL': 'http://launchpad.dev/fnord'})
        try:
            raise GoneError('fnord')
        except GoneError:
            self.assertEqual(None, utility.raising(sys.exc_info(), request))

    def test_raising_no_referrer_error(self):
        """Test ErrorReportingUtility.raising() with a NoReferrerError
        exception.

        An OOPS is not recorded when a NoReferrerError exception is
        raised.
        """
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        try:
            raise NoReferrerError('xyz')
        except NoReferrerError:
            self.assertEqual(None, utility.raising(sys.exc_info()))

    def test_raising_with_string_as_traceback(self):
        # ErrorReportingUtility.raising() can be called with a string in the
        # place of a traceback. This is useful when the original traceback
        # object is unavailable - e.g. when logging a failure reported by a
        # non-oops-enabled service.

        try:
            raise RuntimeError('hello')
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            # Turn the traceback into a string. When the traceback itself
            # cannot be passed to ErrorReportingUtility.raising, a string like
            # one generated by format_exc is sometimes passed instead.
            exc_tb = traceback.format_exc()

        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        report = utility.raising((exc_type, exc_value, exc_tb))
        # traceback is what we supplied.
        self.assertEqual(exc_tb, report['tb_text'])

    def test_oopsMessage(self):
        """oopsMessage pushes and pops the messages."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        with utility.oopsMessage({'a': 'b', 'c': 'd'}):
            self.assertEqual(
                {0: {'a': 'b', 'c': 'd'}}, utility._oops_messages)
            # An additional message doesn't supplant the original message.
            with utility.oopsMessage(dict(e='f', a='z', c='d')):
                self.assertEqual({
                    0: {'a': 'b', 'c': 'd'},
                    1: {'a': 'z', 'e': 'f', 'c': 'd'},
                    }, utility._oops_messages)
            # Messages are removed when out of context.
            self.assertEqual(
                {0: {'a': 'b', 'c': 'd'}},
                utility._oops_messages)

    def test__makeErrorReport_includes_oops_messages(self):
        """The error report should include the oops messages."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        with utility.oopsMessage(dict(a='b', c='d')):
            try:
                raise ArbitraryException('foo')
            except ArbitraryException:
                info = sys.exc_info()
                oops = utility._oops_config.create(dict(exc_info=info))
                self.assertEqual(
                    {'<oops-message-0>': "{'a': 'b', 'c': 'd'}"},
                    oops['req_vars'])

    def test__makeErrorReport_combines_request_and_error_vars(self):
        """The oops messages should be distinct from real request vars."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        request = ScriptRequest([('c', 'd')])
        with utility.oopsMessage(dict(a='b')):
            try:
                raise ArbitraryException('foo')
            except ArbitraryException:
                info = sys.exc_info()
                oops = utility._oops_config.create(
                        dict(exc_info=info, http_request=request))
                self.assertEqual(
                    {'<oops-message-0>': "{'a': 'b'}", 'c': 'd'},
                    oops['req_vars'])

    def test_filter_session_statement(self):
        """Removes quoted strings if database_id is SQL-session."""
        statement = "SELECT 'gone'"
        self.assertEqual(
            "SELECT '%s'",
            _filter_session_statement('SQL-session', statement))

    def test_filter_session_statement_noop(self):
        """If database_id is not SQL-session, it's a no-op."""
        statement = "SELECT 'gone'"
        self.assertEqual(
            statement,
            _filter_session_statement('SQL-launchpad', statement))

    def test_session_queries_filtered(self):
        """Test that session queries are filtered."""
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        timeline = Timeline()
        timeline.start("SQL-session", "SELECT 'gone'").finish()
        try:
            raise ArbitraryException('foo')
        except ArbitraryException:
            info = sys.exc_info()
            oops = utility._oops_config.create(
                    dict(exc_info=info, timeline=timeline))
        self.assertEqual("SELECT '%s'", oops['timeline'][0][3])


class TestSensitiveRequestVariables(testtools.TestCase):
    """Test request variables that should not end up in the stored OOPS.

    The _is_sensitive() method will return True for any variable name that
    should not be included in the OOPS.
    """

    def test_oauth_signature_is_sensitive(self):
        """The OAuth signature can be in the body of a POST request, but if
        that happens we don't want it to be included in the OOPS, so we need
        to mark it as sensitive.
        """
        request = TestRequest(
            environ={'SERVER_URL': 'http://api.launchpad.dev'},
            form={'oauth_signature': '&BTXPJ6pQTvh49r9p'})
        self.failUnless(_is_sensitive(request, 'oauth_signature'))


class UnauthenticatedPrincipal:
    implements(IUnauthenticatedPrincipal)
    id = 0
    title = ''
    description = ''


class TestRequestWithUnauthenticatedPrincipal(TestRequest):
    principal = UnauthenticatedPrincipal()


class TestRequestWithPrincipal(TestRequest):

    def setInWSGIEnvironment(self, key, value):
        self._orig_env[key] = value

    class principal:
        id = 42
        title = u'title'
        # non ASCII description
        description = u'description |\N{BLACK SQUARE}|'

        @staticmethod
        def getLogin():
            return u'Login'


class TestOopsIgnoring(testtools.TestCase):

    def test_offsite_404_ignored(self):
        # A request originating from another site that generates a NotFound
        # (404) is ignored (i.e., no OOPS is logged).
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        report = {'type': 'NotFound',
                'url': 'http://example.com',
                'req_vars': {'HTTP_REFERER': 'example.com'}}
        self.assertEqual(None, utility._oops_config.publish(report))

    def test_onsite_404_not_ignored(self):
        # A request originating from a local site that generates a NotFound
        # (404) produces an OOPS.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        report = {'type': 'NotFound',
                'url': 'http://example.com',
                'req_vars': {'HTTP_REFERER': 'http://launchpad.dev/'}}
        self.assertNotEqual(None, utility._oops_config.publish(report))

    def test_404_without_referer_is_ignored(self):
        # If a 404 is generated and there is no HTTP referer, we don't produce
        # an OOPS.
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        report = {'type': 'NotFound',
                'url': 'http://example.com',
                'req_vars': {}}
        self.assertEqual(None, utility._oops_config.publish(report))

    def test_ignored_report_filtered(self):
        utility = ErrorReportingUtility()
        del utility._oops_config.publishers[:]
        report = {'ignore': True}
        self.assertEqual(None, utility._oops_config.publish(report))

    def test_marked_exception_is_ignored(self):
        # If an exception has been marked as ignorable, then it is ignored in
        # the report.
        utility = ErrorReportingUtility()
        try:
            raise ArbitraryException('xyz\nabc')
        except ArbitraryException:
            exc_info = sys.exc_info()
            directlyProvides(exc_info[1], IUnloggedException)
        report = utility._oops_config.create(dict(exc_info=exc_info))
        self.assertTrue(report['ignore'])


class TestWrappedParameterConverter(testtools.TestCase):
    """Make sure URL parameter type conversions don't generate OOPS reports"""

    def test_return_value_untouched(self):
        # When a converter succeeds, its return value is passed through the
        # wrapper untouched.

        class FauxZopePublisherBrowserModule:
            def get_converter(self, type_):
                def the_converter(value):
                    return 'converted %r to %s' % (value, type_)
                return the_converter

        module = FauxZopePublisherBrowserModule()
        customize_get_converter(module)
        converter = module.get_converter('int')
        self.assertEqual("converted '42' to int", converter('42'))

    def test_value_errors_marked(self):
        # When a ValueError is raised by the wrapped converter, the exception
        # is marked with IUnloggedException so the OOPS machinery knows that a
        # report should not be logged.

        class FauxZopePublisherBrowserModule:
            def get_converter(self, type_):
                def the_converter(value):
                    raise ValueError
                return the_converter

        module = FauxZopePublisherBrowserModule()
        customize_get_converter(module)
        converter = module.get_converter('int')
        try:
            converter(42)
        except ValueError as e:
            self.assertTrue(IUnloggedException.providedBy(e))

    def test_other_errors_not_marked(self):
        # When an exception other than ValueError is raised by the wrapped
        # converter, the exception is not marked with IUnloggedException an
        # OOPS report will be created.

        class FauxZopePublisherBrowserModule:
            def get_converter(self, type_):
                def the_converter(value):
                    raise RuntimeError
                return the_converter

        module = FauxZopePublisherBrowserModule()
        customize_get_converter(module)
        converter = module.get_converter('int')
        try:
            converter(42)
        except RuntimeError as e:
            self.assertFalse(IUnloggedException.providedBy(e))

    def test_none_is_not_wrapped(self):
        # The get_converter function that we're wrapping can return None, in
        # that case there's no function for us to wrap and we just return None
        # as well.

        class FauxZopePublisherBrowserModule:
            def get_converter(self, type_):
                return None

        module = FauxZopePublisherBrowserModule()
        customize_get_converter(module)
        converter = module.get_converter('int')
        self.assertTrue(converter is None)


class TestHooks(testtools.TestCase):

    def test_attach_http_nonbasicvalue(self):
        report = {'req_vars': {}}
        complexthing = object()
        context = {
            'http_request': {'SIMPLE': 'string', 'COMPLEX': complexthing}}
        attach_http_request(report, context)
        self.assertEqual(
            {'SIMPLE': 'string', 'COMPLEX': unicode(complexthing)},
            report['req_vars'])
