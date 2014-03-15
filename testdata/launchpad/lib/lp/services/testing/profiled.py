# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Profile the test layers."""

__metaclass__ = type
__all__ = ['profiled', 'setup_profiling']

import atexit
import cPickle as pickle
import os
import tempfile
import time


_profile_stats_filename = os.environ.get('lp_layer_profile_filename', None)
_profiling_setup_time = None

def profiled(func):
    """Decorator that automatically profiles invocations of the method."""
    def profiled_func(cls, *args, **kw):
        global _profile_stats_filename
        if _profile_stats_filename is not None:
            start_time = time.time()
            try:
                return func(cls, *args, **kw)
            finally:
                _update_profile_stats(cls, func, time.time() - start_time)
        else:
            return func(cls, *args, **kw)
    return profiled_func


def setup_profiling():
    """Initialize our profiling information.

    This cannot be done on module load as this information should only
    be initialized in the top testrunner process.
    """
    global _profile_stats_filename
    global _profiling_setup_time

    _profiling_setup_time = time.time()

    outf, _profile_stats_filename = tempfile.mkstemp(
            '.pickle', 'lp_layer_prof')
    os.close(outf)

    outf = open(_profile_stats_filename, 'wb')
    pickle.dump({}, outf, pickle.HIGHEST_PROTOCOL)
    outf.close()

    atexit.register(os.remove, _profile_stats_filename)

    # Store filename in the environment so subprocesses can find it.
    os.environ['lp_layer_profile_filename'] = _profile_stats_filename


def _update_profile_stats(cls, func, duration):
    """Update the profile statistics with new information about a method call.
    """
    global _profile_stats_filename

    key = '%s.%s' % (cls.__name__, func.__name__)

    # Load stats from disk. We can't store in RAM as it needs to persist
    # across processes.
    stats = pickle.load(open(_profile_stats_filename, 'rb'))
    hits, total_duration = stats.setdefault(key, (0, 0))

    # Update stats
    stats[key] = (hits + 1, total_duration + duration)

    # Dump stats back to disk, making sure we flush
    outf = open(_profile_stats_filename, 'wb')
    pickle.dump(stats, outf, pickle.HIGHEST_PROTOCOL)
    outf.close() # and flush


def report_profile_stats():
    """Print a report about our collected statistics to stdout."""
    stats = pickle.load(open(_profile_stats_filename, 'rb'))

    print
    print 'Test suite profiling information'
    print '================================'

    total_profiled_duration = 0.0
    for key, value in sorted(stats.items()):
        hits, duration = value
        total_profiled_duration += duration
        if duration < 0.1:
            duration = 'negligible time'
        else:
            duration = '%0.1fs' % duration
        print '%-45s %4d calls taking %s.' % (
                key[:45], hits, duration)

    print
    print "Total duration of profiled methods %0.1f seconds." % (
            total_profiled_duration)

    global _profiling_setup_time
    print
    print "Total duration of test run %0.1f seconds." % (
            time.time() - _profiling_setup_time)

