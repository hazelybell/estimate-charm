# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Profile requests when enabled."""

__all__ = ['profiling',
           'start',
           'stop',
          ]

__metaclass__ = type

import contextlib
from cProfile import Profile
from datetime import datetime
from functools import partial
import heapq
import os
import pstats
import re
import StringIO
import sys
import threading

from bzrlib import lsprof
import oops_datedir_repo.serializer_rfc822
from z3c.pt.pagetemplate import PageTemplateFile
from zope.component import (
    adapter,
    getUtility,
    )
from zope.contenttype.parse import parse
from zope.error.interfaces import IErrorReportingUtility
from zope.exceptions.exceptionformatter import format_exception
from zope.publisher.interfaces import (
    IEndRequestEvent,
    IStartRequestEvent,
    )
from zope.traversing.namespace import view

from lp.services.config import config
from lp.services.database.interfaces import DisallowedStore
from lp.services.features import getFeatureFlag
from lp.services.profile.mem import (
    memory,
    resident,
    )
import lp.services.webapp.adapter as da


class ProfilingOops(Exception):
    """Fake exception used to log OOPS information when profiling pages."""


class Profiler:

    profiler_lock = threading.Lock()
    """Global lock used to serialise profiles."""

    started = enabled = False

    def disable(self):
        if self.enabled:
            self.p.disable()
            self.enabled = False
            stats = pstats.Stats(self.p)
            if self.pstats is None:
                self.pstats = stats
            else:
                self.pstats.add(stats)
            self.count += 1

    def enable(self):
        if not self.started:
            self.start()
        elif not self.enabled:
            self.p = Profile()
            self.p.enable(subcalls=True)
            self.enabled = True

    def start(self):
        """Start profiling.
        """
        if self.started:
            return
        self.count = 0
        self.pstats = None
        self.started = True
        self.profiler_lock.acquire(True)  # Blocks.
        try:
            self.enable()
        except:
            self.profiler_lock.release()
            self.started = False
            raise

    def stop(self):
        """Stop profiling.

        This unhooks from threading and cleans up the profiler, returning
        the gathered Stats object.

        :return: A bzrlib.lsprof.Stats object.
        """
        try:
            self.disable()
            p = self.p
            del self.p
            return Stats(self.pstats, p.getstats(), self.count)
        finally:
            self.profiler_lock.release()
            self.started = False


class Stats:

    _callgrind_stats = None

    def __init__(self, stats, rawstats, count):
        self.stats = stats
        self.rawstats = rawstats
        self.count = count

    @property
    def callgrind_stats(self):
        if self._callgrind_stats is None:
            self._callgrind_stats = lsprof.Stats(self.rawstats, {})
        return self._callgrind_stats

    def save(self, filename, callgrind=False):
        if callgrind:
            self.callgrind_stats.save(filename, format="callgrind")
        else:
            self.stats.dump_stats(filename)

    def strip_dirs(self):
        self.stats.strip_dirs()

    def sort(self, name):
        self.stats.sort_stats(name)

    def pprint(self, file):
        stats = self.stats
        stream = stats.stream
        stats.stream = file
        try:
            stats.print_stats()
        finally:
            stats.stream = stream


# Profilers may only run one at a time, but block and serialize.


class Profilers(threading.local):
    """A simple subclass to initialize our thread local values."""

    def __init__(self):
        self.profiling = False
        self.actions = None
        self.profiler = None
        self.memory_profile_start = None

_profilers = Profilers()


def before_traverse(event):
    "Handle profiling when enabled via the profiling.enabled feature flag."
    # This event is raised on each step of traversal so needs to be
    # lightweight and not assume that profiling has not started - but this is
    # equally well done in _maybe_profile so that function takes care of it.
    # We have to use this event (or add a new one) because we depend on the
    # feature flags system being configured and usable, and on the principal
    # being known.
    try:
        if getFeatureFlag('profiling.enabled'):
            _maybe_profile(event)
    except DisallowedStore:
        pass


@adapter(IStartRequestEvent)
def start_request(event):
    """Handle profiling when configured as permitted."""
    if not config.profiling.profiling_allowed:
        return
    _maybe_profile(event)


def _maybe_profile(event):
    """Setup profiling as requested.

    If profiling is enabled, start a profiler for this thread. If memory
    profiling is requested, save the VSS and RSS.

    If already profiling, this is a no-op.
    """
    try:
        if _profilers.profiling:
            # Already profiling - e.g. called in from both start_request and
            # before_traverse, or by successive before_traverse on one
            # request.
            return
    except AttributeError:
        # The first call in on a new thread cannot be profiling at the start.
        pass
    # If this assertion has reason to fail, we'll need to add code
    # to try and stop the profiler before we delete it, in case it is
    # still running.
    assert _profilers.profiler is None
    actions = get_desired_profile_actions(event.request)
    if config.profiling.profile_all_requests:
        actions['callgrind'] = ''
    if config.profiling.memory_profile_log:
        actions['memory_profile_start'] = (memory(), resident())
    if actions:
        if 'sql' in actions:
            condition = actions['sql']
            if condition not in (True, False):
                condition = condition['condition']
            da.start_sql_logging(condition)
        if 'show' in actions or available_profilers.intersection(actions):
            _profilers.profiler = Profiler()
            _profilers.profiler.start()
        _profilers.profiling = True
        _profilers.actions = actions

template = PageTemplateFile(
    os.path.join(os.path.dirname(__file__), 'profile.pt'))


available_profilers = frozenset(('pstats', 'callgrind'))


def start():
    """Turn on profiling from code.
    """
    actions = _profilers.actions
    profiler = _profilers.profiler
    if actions is None:
        actions = _profilers.actions = {}
        _profilers.profiling = True
    elif 'inline' not in actions and (
        'show' in actions or available_profilers.intersection(actions)):
        # We have a request-based profile in progress.  That wins.
        actions['inline_ignored'] = ''
        return
    actions.update((k, '') for k in ('pstats', 'show', 'inline'))
    if profiler is None:
        profiler = _profilers.profiler = Profiler()
        profiler.start()
    else:
        # For simplicity, we just silently ignore start requests when we
        # have already started.
        profiler.enable()


def stop():
    """Stop profiling."""
    # For simplicity, we just silently ignore stop requests when we
    # have not started.
    actions = _profilers.actions
    profiler = _profilers.profiler
    if actions is not None and 'inline' in actions and profiler is not None:
        profiler.disable()


@contextlib.contextmanager
def profiling():
    start()
    try:
        yield
    finally:
        stop()


@adapter(IEndRequestEvent)
def end_request(event):
    """If profiling is turned on, save profile data for the request."""
    try:
        if not _profilers.profiling:
            return
        _profilers.profiling = False
    except AttributeError:
        # Some tests don't go through all the proper motions, like firing off
        # a start request event.  Just be quiet about it.
        return
    actions = _profilers.actions
    _profilers.actions = None
    request = event.request
    # Create a timestamp including milliseconds.
    now = datetime.fromtimestamp(da.get_request_start_time())
    timestamp = "%s.%d" % (
        now.strftime('%Y-%m-%d_%H:%M:%S'), int(now.microsecond / 1000.0))
    pageid = request._orig_env.get('launchpad.pageid', 'Unknown')
    oopsid = getattr(request, 'oopsid', None)
    content_type = request.response.getHeader('content-type')
    if content_type is None:
        content_type_params = {}
        is_html = False
    else:
        _major, _minor, content_type_params = parse(content_type)
        is_html = _major == 'text' and _minor == 'html'
    template_context = {
        'actions': dict((key, True) for key in actions),
        'always_log': config.profiling.profile_all_requests}
    dump_path = config.profiling.profile_dir
    if _profilers.profiler is not None:
        prof_stats = _profilers.profiler.stop()
        # Free some memory (at least for the BzrProfiler).
        _profilers.profiler = None
        if oopsid is None:
            # Log an OOPS to get a log of the SQL queries, and other
            # useful information,  together with the profiling
            # information.
            info = (ProfilingOops, None, None)
            error_utility = getUtility(IErrorReportingUtility)
            oops_report = error_utility.raising(info, request)
            oopsid = oops_report['id']
        else:
            oops_report = request.oops
        filename = '%s-%s-%s-%s' % (
            timestamp, pageid, oopsid,
            threading.currentThread().getName())
        if 'callgrind' in actions:
            # The stats class looks at the filename to know to use
            # callgrind syntax.
            callgrind_path = os.path.join(
                dump_path, 'callgrind.out.' + filename)
            prof_stats.save(callgrind_path, callgrind=True)
            template_context['callgrind_path'] = os.path.abspath(
                callgrind_path)
        if 'pstats' in actions:
            pstats_path = os.path.join(
                dump_path, filename + '.prof')
            prof_stats.save(pstats_path)
            template_context['pstats_path'] = os.path.abspath(
                pstats_path)
        if is_html and 'show' in actions:
            # Generate rfc822 OOPS result (might be nice to have an html
            # serializer..).
            template_context['oops'] = ''.join(
                oops_datedir_repo.serializer_rfc822.to_chunks(oops_report))
            # Generate profile summaries.
            prof_stats.strip_dirs()
            for name in ('time', 'cumulative', 'calls'):
                prof_stats.sort(name)
                f = StringIO.StringIO()
                prof_stats.pprint(file=f)
                template_context[name] = f.getvalue()
        template_context['profile_count'] = prof_stats.count
        template_context['multiple_profiles'] = prof_stats.count > 1
        # Try to free some more memory.
        del prof_stats
    # Dump memory profiling info.
    if 'memory_profile_start' in actions:
        log = file(config.profiling.memory_profile_log, 'a')
        vss_start, rss_start = actions.pop('memory_profile_start')
        vss_end, rss_end = memory(), resident()
        if oopsid is None:
            oopsid = '-'
        log.write('%s %s %s %f %d %d %d %d\n' % (
            timestamp, pageid, oopsid, da.get_request_duration(),
            vss_start, rss_start, vss_end, rss_end))
        log.close()
    trace = None
    if 'sql' in actions:
        trace = da.stop_sql_logging() or ()
        # The trace is a list of dicts, each with the keys "sql" and "stack".
        # "sql" is a tuple of start time, stop time, database name (with a
        # "SQL-" prefix), sql statement and possibly a backtrace (backtraces
        # are included when the timeline storm trace is installed).  "stack" is
        # None or a tuple of filename, line number, function name, text, module
        # name, optional supplement dict, and optional info string.  The
        # supplement dict has keys 'source_url', 'line', 'column',
        # 'expression', 'warnings' (an iterable), and 'extra', any of which may
        # be None.
        top_sql = []
        top_python = []
        triggers = {}
        ix = 1  # We display these, so start at 1, not 0.
        last_stop_time = 0
        _heappushpop = heapq.heappushpop  # This is an optimization.
        for step in trace:
            # Set up an identifier for each trace step.
            step['id'] = ix
            step['sql'] = dict(zip(
                ('start', 'stop', 'name', 'statement', 'backtrace'),
                step['sql']))
            # NB: step['sql']['backtrace'] is a string backtrace, not a live
            # stack: less flexible than what the profiler gathers, but cheaper
            # to keep alive as it holds no references. For now, its not usable
            # here.
            if step['stack'] is not None:
                # Divide up the stack into the more unique (app) and less
                # unique (db) bits.
                app_stack = step['app_stack'] = []
                db_stack = step['db_stack'] = []
                storm_found = False
                for f in step['stack']:
                    f_data = dict(zip(
                        ('filename', 'lineno', 'name', 'line', 'module',
                         'supplement', 'info'), f))
                    storm_found = storm_found or (
                        f_data['module'] and
                        f_data['module'].startswith('storm.'))
                    if storm_found:
                        db_stack.append(f_data)
                    else:
                        app_stack.append(f_data)
                # Begin to gather what app code is triggering the most SQL
                # calls.
                trigger_key = tuple(
                    (f['filename'], f['lineno']) for f in app_stack)
                if trigger_key not in triggers:
                    triggers[trigger_key] = []
                triggers[trigger_key].append(ix)
            # Get the nbest (n=10) sql and python times
            step['python_time'] = step['sql']['start'] - last_stop_time
            step['sql_time'] = step['sql']['stop'] - step['sql']['start']
            python_data = (step['python_time'], ix, step)
            sql_data = (step['sql_time'], ix, step)
            if ix < 10:
                top_sql.append(sql_data)
                top_python.append(python_data)
            else:
                if ix == 10:
                    heapq.heapify(top_sql)
                    heapq.heapify(top_python)
                _heappushpop(top_sql, sql_data)
                _heappushpop(top_python, python_data)
            # Reset for next loop.
            last_stop_time = step['sql']['stop']
            ix += 1
        # Finish setting up top sql and python times.
        top_sql.sort(reverse=True)
        top_python.sort(reverse=True)
        top_sql_ids = []
        for rank, (key, ix, step) in enumerate(top_sql):
            step['sql_rank'] = rank + 1
            step['sql_class'] = (
                'sql_danger' if key > 500 else
                'sql_warning' if key > 100 else None)
            top_sql_ids.append(dict(
                value=key,
                ix=ix,
                rank=step['sql_rank'],
                cls=step['sql_class']))
        top_python_ids = []
        for rank, (key, ix, step) in enumerate(top_python):
            step['python_rank'] = rank + 1
            step['python_class'] = (
                'python_danger' if key > 500 else
                'python_warning' if key > 100 else None)
            top_python_ids.append(dict(
                value=key,
                ix=ix,
                rank=step['python_rank'],
                cls=step['python_class']))
        # Identify the repeated Python calls that generated SQL.
        triggers = triggers.items()
        triggers.sort(key=lambda x: len(x[1]))
        triggers.reverse()
        top_triggers = []
        for (key, ixs) in triggers:
            if len(ixs) == 1:
                break
            info = trace[ixs[0] - 1]['app_stack'][-1].copy()
            info['indexes'] = ixs
            info['count'] = len(ixs)
            top_triggers.append(info)
        template_context.update(dict(
            sqltrace=trace,
            top_sql=top_sql_ids,
            top_python=top_python_ids,
            top_triggers=top_triggers,
            sql_count=len(trace)))
        if actions['sql'] is True:
            template_context['sql_traceback_all'] = True
        elif actions['sql'] is False:
            template_context['sql_traceback_none'] = True
        else:
            conditions = actions['sql'].copy()
            del conditions['condition']
            template_context['sql_traceback_conditions'] = conditions
    template_context['dump_path'] = os.path.abspath(dump_path)
    if actions and is_html:
        # Hack the new HTML in at the end of the page.
        encoding = content_type_params.get('charset', 'utf-8')
        try:
            added_html = template(**template_context).encode(encoding)
        except (SystemExit, KeyboardInterrupt):
            raise
        except:
            error = ''.join(format_exception(*sys.exc_info(), as_html=True))
            added_html = (
                '<div class="profiling_info">' + error + '</div>')
        existing_html = request.response.consumeBody()
        e_start, e_close_body, e_end = existing_html.rpartition(
            '</body>')
        new_html = ''.join(
            (e_start, added_html, e_close_body, e_end))
        request.response.setResult(new_html)


def get_desired_profile_actions(request):
    """What does the URL show that the user wants to do about profiling?

    Returns a set of actions (comma-separated) if ++profile++ is in the
    URL.  Note that ++profile++ alone without actions is interpreted as
    the "help" action.
    """
    result = dict()
    path_info = request.get('PATH_INFO')
    if path_info:
        # if not, this is almost certainly a test not bothering to set up
        # certain bits.  We'll handle it silently.
        start, match, end = path_info.partition('/++profile++')
        # We don't need no steenkin' regex.
        if match:
            # Now we figure out what actions are desired.  Normally,
            # parsing the url segment after the namespace ('++profile++'
            # in this case) is done in the traverse method of the
            # namespace view (see ProfileNamespace in this file).  We
            # are doing it separately because we want to know what to do
            # before the traversal machinery gets started, so we can
            # include traversal in the profile.
            actions, slash, tail = end.partition('/')
            result.update(
                (name.strip(), config.strip())
                for name, partition, config in (
                    item.strip().lower().partition(':')
                    for item in actions.split('&'))
                if name.strip())
            # 'log' is backwards compatible for 'callgrind'.
            if 'log' in result:
                result['callgrind'] = result.pop('log')
            if 'sqltrace' in result:
                condition = result['sqltrace']
                if condition:
                    condition = _make_condition_function(condition)
                else:
                    condition = True
                del result['sqltrace']
                result['sql'] = condition
            elif 'sql' in result:
                result['sql'] = False
            # Only honor the available options.
            available_options = set(('show', 'sql', 'help'))
            available_options.update(available_profilers)
            # .keys() gives a list, not mutated during iteration.
            for key in result.keys():
                if key not in available_options:
                    del result[key]
            # If we didn't end up with any known actions, we need to help the
            # user.
            if not result:
                result['help'] = ''
    return result


def _make_startswith(value):
    """Return a function that returns true if its argument startswith value"""
    def startswith(sql):
        return sql.startswith(value)
    return startswith


def _make_endswith(value):
    """Return a function that returns true if its argument endswith value"""
    def endswith(sql):
        return sql.endswith(value)
    return endswith


def _make_includes(value):
    """Return a function that returns true if its argument includes value"""
    def includes(sql):
        return value in sql
    return includes

_condition_functions = {
    'STARTSWITH': _make_startswith,
    'ENDSWITH': _make_endswith,
    'INCLUDES': _make_includes
    }

_normalize_whitespace = partial(re.compile('\s+').sub, ' ')


def _make_condition_function(condition_string):
    """Given DSL string, return dict including function implementing string.

    DSL is very simple. Conditions are separated by semicolons, which
    represent logical or.  Each condition should begin with (case insensitive)
    "startswith ", "endswith ", or "includes ".  The part of the condition
    after this word and before the next semicolon or end-of-string is the
    match string, which is case-insensitive and whitespace-normalized.

    Returned dict has three elements: the function that implements the DSL,
    the list of conditions that were included, and the list of conditions
    that were excluded (because they were not understood).
    """
    conditions = []
    included = []
    ignored = []
    for constraint, partition, value in (
        c.strip().partition(' ') for c
        in condition_string.upper().split('|')):
        # Process each condition.
        constraint = constraint.strip()
        if not constraint:
            # This was something ignorable, like a trailing | or something.
            continue
        value = _normalize_whitespace(value.strip())
        description = dict(constraint=constraint, value=value)
        if constraint in _condition_functions:
            conditions.append(_condition_functions[constraint](value))
            included.append(description)
        else:
            ignored.append(description)

    def condition_aggregate(sql):
        for condition in conditions:
            if condition(sql):
                return True
        return False
    return dict(
        condition=condition_aggregate, included=included, ignored=ignored)


class ProfileNamespace(view):
    """A see-through namespace that handles traversals with ++profile++."""

    def traverse(self, name, remaining):
        """Continue on with traversal.
        """
        # Note that handling the name is done in get_desired_profile_actions,
        # above.  See the comment in that function.
        return self.context
