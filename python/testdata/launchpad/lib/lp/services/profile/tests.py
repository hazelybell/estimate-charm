# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.profile.

See doc.txt for an end-user description of the functionality.
"""

__metaclass__ = type

import glob
import logging
import os
import random
import unittest

from zope.component import (
    getSiteManager,
    queryUtility,
    )
from zope.error.interfaces import IErrorReportingUtility
from zope.publisher.interfaces import (
    EndRequestEvent,
    StartRequestEvent,
    )
from zope.traversing.interfaces import BeforeTraverseEvent

from lp.services.features.testing import FeatureFixture
from lp.services.profile import profile
import lp.services.webapp.adapter as da
from lp.services.webapp.errorlog import ErrorReportingUtility
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    layers,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


EXAMPLE_HTML_START = '''\
<html><head><title>Random!</title></head>
<body>
<h1>Random!</h1>
<p>Whatever!</p>
'''
EXAMPLE_HTML_END = '''\
</body>
</html>
'''
EXAMPLE_HTML = EXAMPLE_HTML_START + EXAMPLE_HTML_END


class SQLDSLTest(TestCase):

    def assertCondition(self,
                        condition_string, succeeds, fails, included, ignored):
        results = profile._make_condition_function(condition_string)
        self.assertEqual(included, results['included'])
        self.assertEqual(ignored, results['ignored'])
        for example in succeeds:
            self.assertTrue(results['condition'](example))
        for example in fails:
            self.assertFalse(results['condition'](example))

    def test_startswith(self):
        self.assertCondition(
            'startswith foo bar',
            succeeds=['FOO BARBAZ'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='STARTSWITH', value='FOO BAR')],
            ignored=[])

    def test_endswith(self):
        self.assertCondition(
            'endswith foo bar',
            succeeds=['BAZ FOO BAR'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='ENDSWITH', value='FOO BAR')],
            ignored=[])

    def test_includes(self):
        self.assertCondition(
            'includes foo bar',
            succeeds=['BAZ FOO BAR BING'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='INCLUDES', value='FOO BAR')],
            ignored=[])

    def test_whitespace_normalized(self):
        self.assertCondition(
            '  startswith        foo     bar  ',
            succeeds=['FOO BARBAZ'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='STARTSWITH', value='FOO BAR')],
            ignored=[])

    def test_many_conditions(self):
        self.assertCondition(
            'startswith foo bar | endswith shazam|includes balooba',
            succeeds=['FOO BARBAZ', 'SALAMI SHAZAM', 'FORTUNA BALOOBA CAT'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='STARTSWITH', value='FOO BAR'),
                      dict(constraint='ENDSWITH', value='SHAZAM'),
                      dict(constraint='INCLUDES', value='BALOOBA')],
            ignored=[])

    def test_trailing_or(self):
        self.assertCondition(
            'startswith foo bar|',
            succeeds=['FOO BARBAZ'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='STARTSWITH', value='FOO BAR')],
            ignored=[])

    def test_one_ignored(self):
        self.assertCondition(
            'matches foo bar',
            succeeds=[],
            fails=['BARBAZ FOO'],
            included=[],
            ignored=[dict(constraint='MATCHES', value='FOO BAR')])

    def test_one_included_one_ignored(self):
        self.assertCondition(
            'matches kumquat | startswith foo bar',
            succeeds=['FOO BAR HAMSTER'],
            fails=['BARBAZ FOO'],
            included=[dict(constraint='STARTSWITH', value='FOO BAR')],
            ignored=[dict(constraint='MATCHES', value='KUMQUAT')])


class BaseTest(TestCase):

    def _get_request(self, path='/'):
        """Return a test request for the given path."""
        return LaunchpadTestRequest(PATH_INFO=path)

    def _get_start_event(self, path='/'):
        """Return a start event for the given path."""
        return StartRequestEvent(self._get_request(path))

    def assertCleanProfilerState(self, message='something did not clean up'):
        """Check whether profiler thread local is clean."""
        for name in ('profiler', 'actions'):
            self.assertIs(
                getattr(profile._profilers, name, None), None,
                'Profiler state (%s) is dirty; %s.' % (name, message))

    def pushProfilingConfig(
        self, profiling_allowed='False', profile_all_requests='False',
        memory_profile_log=''):
        """This is a convenience for setting profile configs."""
        self.pushConfig(
            'profiling',
            profiling_allowed=profiling_allowed,
            profile_all_requests=profile_all_requests,
            memory_profile_log=memory_profile_log)


class TestCleanupProfiler(BaseTest):
    """Add a tearDown that will cleanup the profiler if it is running."""

    def tearDown(self):
        "Do the usual tearDown, plus clean up the profiler object."
        if profile._profilers.profiler is not None:
            profile._profilers.profiler.stop()
            profile._profilers.profiler = None
        profile._profilers.actions = None
        profile._profilers.profiling = False
        super(TestCleanupProfiler, self).tearDown()


class TestRequestStartHandler(TestCleanupProfiler):
    """Tests for the start handler of the profiler integration.

    See lib/canonical/doc/profiling.txt for an end-user description of
    the functionality.
    """

    def test_config_stops_profiling(self):
        """The ``profiling_allowed`` configuration should disable all
        profiling, even if it is requested"""
        self.pushProfilingConfig(
            profiling_allowed='False', profile_all_requests='True',
            memory_profile_log='.')
        profile.start_request(self._get_start_event(
            '/++profile++show&callgrind'))
        self.assertCleanProfilerState('config was ignored')

    def test_optional_profiling_without_marked_request_has_no_profile(self):
        # Even if profiling is allowed, it does not happen with a normal
        # request.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/'))
        self.assertFalse(profile._profilers.profiling)
        self.assertIs(getattr(profile._profilers, 'profiler', None), None)
        self.assertIs(
            getattr(profile._profilers, 'actions', None), None)

    def test_optional_profiling_with_show_request_starts_profiling(self):
        # If profiling is allowed and a request with the "show" marker
        # URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/++profile++show/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(set(profile._profilers.actions), set(('show', )))

    def test_optional_profiling_with_callgrind_request_starts_profiling(self):
        # If profiling is allowed and a request with the "callgrind" marker
        # URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/++profile++callgrind/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('callgrind', )))

    def test_optional_profiling_with_log_request_starts_profiling(self):
        # If profiling is allowed and a request with the "log" marker URL
        # segment is made, profiling starts as a callgrind profile request.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/++profile++log/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('callgrind', )))

    def test_optional_profiling_with_combined_request_starts_profiling(self):
        # If profiling is allowed and a request with the "callgrind" and
        # "show" marker URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(
            self._get_start_event('/++profile++callgrind&show/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('callgrind', 'show')))

    def test_optional_profiling_with_reversed_request_starts_profiling(self):
        # If profiling is allowed and a request with the "show" and the
        # "callgrind" marker URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        # The fact that this is reversed from the previous request is the only
        # difference from the previous test.  Also, it doesn't have a
        # trailing slash. :-P
        profile.start_request(
            self._get_start_event('/++profile++show&callgrind'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('callgrind', 'show')))

    def test_optional_profiling_with_pstats_request_starts_profiling(self):
        # If profiling is allowed and a request with the "pstats" marker,
        # profiling starts with the pstats profiler.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(
            self._get_start_event('/++profile++pstats/'))
        self.assertIsInstance(profile._profilers.profiler,
                              profile.Profiler)
        self.assertEquals(set(profile._profilers.actions), set(('pstats',)))

    def test_optional_profiling_with_log_pstats(self):
        # If profiling is allowed and a request with the "log" and "pstats"
        # marker URL segments is made, profiling starts as a callgrind profile
        # and pstats request.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(
            self._get_start_event('/++profile++log&pstats/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('callgrind', 'pstats',)))

    def test_optional_profiling_with_callgrind_pstats(self):
        # If profiling is allowed and a request with both the "pstats" and
        # "callgrind" markers, profiling starts with the bzr/callgrind
        # profiler.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(
            self._get_start_event('/++profile++pstats&callgrind/'))
        self.assertIsInstance(profile._profilers.profiler,
                              profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('pstats', 'callgrind')))

    def test_forced_profiling_registers_action(self):
        # profile_all_requests should register as a callgrind action.
        self.pushProfilingConfig(
            profiling_allowed='True', profile_all_requests='True')
        profile.start_request(self._get_start_event('/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('callgrind', )))

    def test_optional_profiling_with_wrong_request_helps(self):
        # If profiling is allowed and a request with the marker URL segment
        # is made incorrectly, profiling does not start and help is an action.
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/++profile++/'))
        self.assertIs(getattr(profile._profilers, 'profiler', None), None)
        self.assertEquals(set(profile._profilers.actions), set(('help', )))

    def test_forced_profiling_with_wrong_request_helps(self):
        # If profiling is forced and a request with the marker URL segment
        # is made incorrectly, profiling starts and help is an action.
        self.pushProfilingConfig(
            profiling_allowed='True', profile_all_requests='True')
        profile.start_request(self._get_start_event('/++profile++/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        self.assertEquals(
            set(profile._profilers.actions), set(('help', 'callgrind')))

    def test_memory_profile_start(self):
        self.pushProfilingConfig(
            profiling_allowed='True', memory_profile_log='.')
        profile.start_request(self._get_start_event('/'))
        self.assertIs(getattr(profile._profilers, 'profiler', None), None)
        actions = profile._profilers.actions
        self.assertEqual(set(actions), set(['memory_profile_start']))
        self.assertIsInstance(actions['memory_profile_start'], tuple)
        self.assertEqual(len(actions['memory_profile_start']), 2)

    def test_combo_memory_and_profile_start(self):
        self.pushProfilingConfig(
            profiling_allowed='True', memory_profile_log='.')
        profile.start_request(self._get_start_event('/++profile++show/'))
        self.assertIsInstance(profile._profilers.profiler, profile.Profiler)
        actions = profile._profilers.actions
        self.assertEqual(set(actions), set(['memory_profile_start', 'show']))
        self.assertIsInstance(actions['memory_profile_start'], tuple)
        self.assertEqual(len(actions['memory_profile_start']), 2)

    def test_sqltrace_start(self):
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/++profile++sqltrace/'))
        self.assertIs(getattr(profile._profilers, 'profiler', None), None)
        self.assertEquals(profile._profilers.actions, dict(sql=True))
        self.assertEqual([], da.stop_sql_logging())

    def test_sql_start(self):
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event('/++profile++sql/'))
        self.assertIs(getattr(profile._profilers, 'profiler', None), None)
        self.assertEquals(profile._profilers.actions, dict(sql=False))
        self.assertEqual([], da.stop_sql_logging())

    def test_sqltrace_filtered_start(self):
        self.pushProfilingConfig(profiling_allowed='True')
        profile.start_request(self._get_start_event(
            '/++profile++sqltrace:includes bugsubscription/'))
        self.assertIs(getattr(profile._profilers, 'profiler', None), None)
        self.assertEquals(set(profile._profilers.actions), set(('sql', )))
        data = profile._profilers.actions['sql']
        self.assertTrue(data['condition']('SELECT BUGSUBSCRIPTION FROM FOO'))
        self.assertEqual([], da.stop_sql_logging())


class BaseRequestEndHandlerTest(BaseTest):

    def setUp(self):
        super(BaseRequestEndHandlerTest, self).setUp()
        self.profile_dir = self.makeTemporaryDirectory()
        self.memory_profile_log = os.path.join(self.profile_dir, 'memory_log')
        self.pushConfig('profiling', profile_dir=self.profile_dir)
        eru = queryUtility(IErrorReportingUtility)
        if eru is None:
            # Register an Error reporting utility for this layer.
            # This will break tests when run with an ERU already registered.
            self.eru = ErrorReportingUtility()
            sm = getSiteManager()
            sm.registerUtility(self.eru)
            self.addCleanup(sm.unregisterUtility, self.eru)

    def endRequest(self, path='/', exception=None, pageid=None, work=None):
        start_event = self._get_start_event(path)
        da.set_request_started()
        profile.start_request(start_event)
        request = start_event.request
        if pageid is not None:
            request.setInWSGIEnvironment('launchpad.pageid', pageid)
        if work is not None:
            work()
        request.response.setResult(EXAMPLE_HTML)
        context = object()
        event = EndRequestEvent(context, request)
        if exception is not None:
            self.eru.raising(
                (type(exception), exception, None), event.request)
        profile.end_request(event)
        da.clear_request_started()
        return event.request

    def getAddedResponse(self, request,
                         start=EXAMPLE_HTML_START, end=EXAMPLE_HTML_END):
        output = request.response.consumeBody()
        return output[len(start):-len(end)]

    def getMemoryLog(self):
        if not os.path.exists(self.memory_profile_log):
            return []
        f = open(self.memory_profile_log)
        result = f.readlines()
        f.close()
        return result

    def getPStatsProfilePaths(self):
        return glob.glob(os.path.join(self.profile_dir, '*.prof'))

    def getCallgrindProfilePaths(self):
        return glob.glob(os.path.join(self.profile_dir, 'callgrind.out.*'))

    def getAllProfilePaths(self):
        return self.getPStatsProfilePaths() + self.getCallgrindProfilePaths()

    def assertBasicProfileExists(self, request, show=False):
        self.assertNotEqual(None, request.oops)
        response = self.getAddedResponse(request)
        self.assertIn('Profile was logged to', response)
        if show:
            self.assertIn('Top Inline Time', response)
        else:
            self.assertNotIn('Top Inline Time', response)
        self.assertEqual(self.getMemoryLog(), [])
        self.assertCleanProfilerState()
        return response

    def assertPStatsProfile(self, response):
        paths = self.getPStatsProfilePaths()
        self.assertEqual(len(paths), 1)
        self.assertIn(paths[0], response)
        self.assertEqual(0, len(self.getCallgrindProfilePaths()))

    def assertCallgrindProfile(self, response):
        paths = self.getCallgrindProfilePaths()
        self.assertEqual(len(paths), 1)
        self.assertIn(paths[0], response)
        self.assertEqual(0, len(self.getPStatsProfilePaths()))

    def assertBothProfiles(self, response):
        paths = self.getAllProfilePaths()
        self.assertEqual(2, len(paths))
        for path in paths:
            self.assertIn(path, response)

    def assertNoProfiles(self):
        self.assertEqual([], self.getAllProfilePaths())


class TestBasicRequestEndHandler(BaseRequestEndHandlerTest):
    """Tests for the end-request handler.

    If the start-request handler is broken, these tests will fail too, so fix
    the tests in the above test case first.

    See lib/canonical/doc/profiling.txt for an end-user description
    of the functionality.
    """

    def test_config_stops_profiling(self):
        # The ``profiling_allowed`` configuration should disable all
        # profiling, even if it is requested.
        self.pushProfilingConfig(
            profiling_allowed='False', profile_all_requests='True',
            memory_profile_log=self.memory_profile_log)
        request = self.endRequest('/++profile++show&callgrind')
        self.assertIs(getattr(request, 'oops', None), None)
        self.assertEqual(self.getAddedResponse(request), '')
        self.assertEqual(self.getMemoryLog(), [])
        self.assertNoProfiles()
        self.assertCleanProfilerState()

    def test_optional_profiling_without_marked_request_has_no_profile(self):
        # Even if profiling is allowed, it does not happen with a normal
        # request.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/')
        self.assertIs(getattr(request, 'oops', None), None)
        self.assertEqual(self.getAddedResponse(request), '')
        self.assertEqual(self.getMemoryLog(), [])
        self.assertNoProfiles()
        self.assertCleanProfilerState()

    def test_forced_profiling_logs(self):
        # profile_all_requests should register as a callgrind action.
        self.pushProfilingConfig(
            profiling_allowed='True', profile_all_requests='True')
        request = self.endRequest('/')
        response = self.assertBasicProfileExists(request)
        self.assertCallgrindProfile(response)
        self.assertIn('profile_all_requests: True', response)

    def test_optional_profiling_with_wrong_request_helps(self):
        # If profiling is allowed and a request with the marker URL segment
        # is made incorrectly, profiling does not start and help is an action.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++')
        self.assertIs(getattr(request, 'oops', None), None)
        response = self.getAddedResponse(request)
        self.assertIn('<h2>Help</h2>', response)
        self.assertNotIn('Top Inline Time', response)
        self.assertEqual(self.getMemoryLog(), [])
        self.assertNoProfiles()
        self.assertCleanProfilerState()

    def test_forced_profiling_with_wrong_request_helps(self):
        # If profiling is forced and a request with the marker URL segment
        # is made incorrectly, profiling starts and help is an action.
        self.pushProfilingConfig(
            profiling_allowed='True', profile_all_requests='True')
        request = self.endRequest('/++profile++')
        response = self.assertBasicProfileExists(request)
        self.assertCallgrindProfile(response)
        self.assertIn('<h2>Help</h2>', response)
        self.assertIn('profile_all_requests: True', response)

    def test_optional_profiling_with_show_request_profiles(self):
        # If profiling is allowed and a request with the "show" marker
        # URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++show/')
        self.assertNotEqual(None, request.oops)
        self.assertIn('Top Inline Time', self.getAddedResponse(request))
        self.assertEqual(self.getMemoryLog(), [])
        self.assertEqual(self.getCallgrindProfilePaths(), [])
        self.assertCleanProfilerState()


class TestCallgrindProfilerRequestEndHandler(BaseRequestEndHandlerTest):
    """Tests for the callgrind results.

    If the start-request handler is broken, these tests will fail too, so fix
    the tests in the above test case first.

    See lib/canonical/doc/profiling.txt for an end-user description
    of the functionality.
    """

    assertProfilePaths = BaseRequestEndHandlerTest.assertCallgrindProfile

    # Note that these tests are re-used by TestStdLibProfilerRequestEndHandler
    # below.

    def test_optional_profiling_with_callgrind_request_profiles(self):
        # If profiling is allowed and a request with the "callgrind" marker
        # URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++callgrind/')
        self.assertProfilePaths(self.assertBasicProfileExists(request))

    def test_optional_profiling_with_combined_request_profiles(self):
        # If profiling is allowed and a request with the "callgrind" and
        # "show" marker URL segment is made, profiling starts.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++callgrind&show')
        self.assertProfilePaths(
            self.assertBasicProfileExists(request, show=True))


class TestPStatsProfilerRequestEndHandler(
    TestCallgrindProfilerRequestEndHandler):
    """Tests for the pstats results.

    If the start-request handler is broken, these tests will fail too, so fix
    the tests in the above test case first.

    See lib/canonical/doc/profiling.txt for an end-user description
    of the functionality.
    """

    def endRequest(self, path):
        return TestCallgrindProfilerRequestEndHandler.endRequest(self,
            path.replace('callgrind', 'pstats'))

    assertProfilePaths = BaseRequestEndHandlerTest.assertPStatsProfile


class TestBothProfilersRequestEndHandler(BaseRequestEndHandlerTest):

    def test_optional_profiling_with_both_request_profiles(self):
        # If profiling is allowed and a request with the "callgrind" and
        # "pstats" markers is made, profiling starts with the callgrind
        # approach only.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++callgrind&pstats/')
        self.assertBothProfiles(self.assertBasicProfileExists(request))
        # We had a bug in which the callgrind file was actually a pstats
        # file.  What we can do minimally to prevent this in the future is
        # to verify that these two files are different.
        data = []
        for filename in self.getAllProfilePaths():
            with open(filename) as f:
                data.append(f.read())
        self.assertEqual(2, len(data))
        self.assertNotEqual(data[0], data[1])


class TestMemoryProfilerRequestEndHandler(BaseRequestEndHandlerTest):
    """Tests for the end-request handler of the memory profile.

    If the start-request handler is broken, these tests will fail too, so fix
    the tests in the above test case first.

    See lib/canonical/doc/profiling.txt for an end-user description
    of the functionality.
    """

    def test_memory_profile(self):
        # Does the memory profile work?
        self.patch(da, 'get_request_duration', lambda: 0.5)
        self.pushProfilingConfig(
            profiling_allowed='True',
            memory_profile_log=self.memory_profile_log)
        request = self.endRequest('/')
        self.assertIs(getattr(request, 'oops', None), None)
        self.assertEqual(self.getAddedResponse(request), '')
        log = self.getMemoryLog()
        self.assertEqual(len(log), 1)
        (timestamp, page_id, oops_id, duration, start_vss, start_rss,
         end_vss, end_rss) = log[0].split()
        self.assertEqual(page_id, 'Unknown')
        self.assertEqual(oops_id, '-')
        self.assertEqual(float(duration), 0.5)
        self.assertNoProfiles()
        self.assertCleanProfilerState()

    def test_memory_profile_with_non_defaults(self):
        # Does the memory profile work with an oops and pageid?
        self.pushProfilingConfig(
            profiling_allowed='True',
            memory_profile_log=self.memory_profile_log)
        request = self.endRequest('/++profile++show/no-such-file',
                                  KeyError(), pageid='Foo')
        log = self.getMemoryLog()
        (timestamp, page_id, oops_id, duration, start_vss, start_rss,
         end_vss, end_rss) = log[0].split()
        self.assertEqual(page_id, 'Foo')
        self.assertEqual(oops_id, request.oopsid)
        self.assertCleanProfilerState()

    def test_combo_memory_and_profile(self):
        self.pushProfilingConfig(
            profiling_allowed='True',
            memory_profile_log=self.memory_profile_log)
        request = self.endRequest('/++profile++show/')
        self.assertNotEqual(None, request.oops)
        self.assertIn('Top Inline Time', self.getAddedResponse(request))
        self.assertEqual(len(self.getMemoryLog()), 1)
        self.assertNoProfiles()
        self.assertCleanProfilerState()


class TestOOPSRequestEndHandler(BaseRequestEndHandlerTest):
    """Tests for the end-request handler of the OOPS output.

    If the start-request handler is broken, these tests will fail too, so fix
    the tests in the above test case first.

    See lib/canonical/doc/profiling.txt for an end-user description
    of the functionality.
    """

    def test_real_oops_trumps_profiling_oops(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++show/no-such-file',
                                  KeyError('foo'))
        self.assertEquals(request.oops['type'], 'KeyError')
        response = self.getAddedResponse(request)
        self.assertIn('Exception-Type: KeyError', response)
        self.assertCleanProfilerState()

    def test_oopsid_is_in_profile_filename(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/++profile++callgrind/')
        self.assertIn(
            "-" + request.oopsid + "-", self.getAllProfilePaths()[0])
        self.assertCleanProfilerState()


class TestBeforeTraverseHandler(TestCleanupProfiler):

    layer = layers.DatabaseFunctionalLayer

    def test_can_enable_profiling_over_config(self):
        # The flag profiling.enabled wins over a config that has
        # disabled profiling. This permits the use of profiling on qastaging
        # and similar systems.
        self.pushProfilingConfig(
            profiling_allowed='False', profile_all_requests='True',
            memory_profile_log='.')
        event = BeforeTraverseEvent(None,
            self._get_request('/++profile++show&callgrind'))
        with FeatureFixture({'profiling.enabled': 'on'}):
            profile.before_traverse(event)
            self.assertTrue(profile._profilers.profiling)
            self.assertIsInstance(
                profile._profilers.profiler, profile.Profiler)
            self.assertEquals(
                set(('show', 'callgrind', 'memory_profile_start')),
                set(profile._profilers.actions))


class TestInlineProfiling(BaseRequestEndHandlerTest):

    def make_work(self, count=1):
        def work():
            for i in range(count):
                profile.start()
                random.random()
                profile.stop()
        return work

    def test_basic_inline_profiling(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/', work=self.make_work())
        self.assertPStatsProfile(
            self.assertBasicProfileExists(request, show=True))

    def test_multiple_inline_profiling(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/', work=self.make_work(count=2))
        response = self.assertBasicProfileExists(request, show=True)
        self.assertPStatsProfile(response)
        self.assertIn('2 individual profiles', response)

    def test_mixed_profiling(self):
        # ++profile++ wins over inline.
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest(
            '/++profile++show&callgrind', work=self.make_work())
        response = self.assertBasicProfileExists(request, show=True)
        self.assertCallgrindProfile(response)
        self.assertIn('Inline request ignored', response)

    def test_context_manager(self):
        def work():
            with profile.profiling():
                random.random()
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest('/', work=work)
        self.assertPStatsProfile(
            self.assertBasicProfileExists(request, show=True))


class TestSqlLogging(TestCaseWithFactory, BaseRequestEndHandlerTest):

    layer = layers.DatabaseFunctionalLayer

    def testLogging(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest(
            '/++profile++sql/', work=self.factory.makeBug)
        response = self.getAddedResponse(request)
        self.assertIn('Top 10 SQL times', response)
        self.assertIn('Query number', response)
        self.assertIn('Top 10 Python times', response)
        self.assertIn('Before query', response)
        self.assertTrue('Repeated Python SQL Triggers' not in response)
        self.assertTrue('Show all tracebacks' not in response)

    def testTraceLogging(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest(
            '/++profile++sqltrace/', work=self.factory.makeBug)
        response = self.getAddedResponse(request)
        self.assertIn('Top 10 SQL times', response)
        self.assertIn('Query number', response)
        self.assertIn('Top 10 Python times', response)
        self.assertIn('Before query', response)
        self.assertIn('Repeated Python SQL Triggers', response)
        self.assertIn('Show all tracebacks', response)
        # This file should be part of several of the tracebacks.
        self.assertIn(__file__.replace('.pyc', '.py'), response)

    def testTraceLoggingConditionally(self):
        self.pushProfilingConfig(profiling_allowed='True')
        request = self.endRequest(
            '/++profile++sqltrace:includes SELECT/',
            work=self.factory.makeBug)
        response = self.getAddedResponse(request)
        self.assertIn('Top 10 SQL times', response)
        self.assertIn('Query number', response)
        self.assertIn('Top 10 Python times', response)
        self.assertIn('Before query', response)
        self.assertIn('Repeated Python SQL Triggers', response)
        self.assertIn('Show all tracebacks', response)
        self.assertIn(
            'You have requested tracebacks for statements that match only',
            response)
        # This file should be part of several of the tracebacks.
        self.assertIn(__file__.replace('.pyc', '.py'), response)


def test_suite():
    """Return the `IBugTarget` TestSuite."""
    suite = unittest.TestSuite()

    doctest = LayeredDocFileSuite(
        './profiling.txt', setUp=setUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer, stdout_logging_level=logging.WARNING)
    suite.addTest(doctest)
    suite.addTest(unittest.TestLoader().loadTestsFromName(__name__))
    return suite
