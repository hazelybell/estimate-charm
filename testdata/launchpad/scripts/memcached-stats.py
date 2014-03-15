#!/usr/bin/python -S
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Output memcached statistics."""

__metaclass__ = type
__all__ = []

import _pythonpath

from optparse import OptionParser
from pprint import pprint
import sys
from textwrap import dedent
import time

from zope.component import getUtility

from lp.services.memcache.interfaces import IMemcacheClient
from lp.services.scripts import execute_zcml_for_scripts

# The interesting bits we pull from the memcached stats.
INTERESTING_KEYS = [
    'cmd_set', # Number of sets.
    'get_hits', # Number of gets that hit.
    'get_misses', # Number of gets that missed.
    'evictions', # Objects evicted from memcached.
    'bytes_read', # Bytes read from memcached.
    'bytes_written', # Bytes written to memcached.
    ]


def get_summary(all_raw_stats):
    """Aggregate individual server statistics into a summary."""
    totals = dict((key, 0) for key in INTERESTING_KEYS)
    for server, raw_stats in all_raw_stats:
        for key in INTERESTING_KEYS:
            totals[key] += int(raw_stats.get(key, 0))
    return totals


def print_stats(stats):
    """Output human readable statistics."""
    print dedent('''\
            Sets:          %(cmd_set)s
            Hits:          %(get_hits)s
            Misses:        %(get_misses)s
            Evictions:     %(evictions)s
            Bytes read:    %(bytes_read)s
            Bytes written: %(bytes_written)s
            ''' % stats)


def print_summary(all_raw_stats):
    """Output the summary in a human readable format."""
    summary = get_summary(all_raw_stats)
    print "Totals\n======\n"
    print_stats(summary)


def print_full(all_raw_stats):
    """Output stats for individual servers in a human readable format."""
    for server, stats in all_raw_stats:
        print server
        print "="*len(server)
        print
        print_stats(stats)


def print_cricket(all_raw_stats):
    """Output stats in cricket format for graphing."""
    summary = get_summary(all_raw_stats)
    now = time.time()
    for key in INTERESTING_KEYS:
        print 'memcached_total_%s:%s@%d' % (
            key, summary[key], now)
    for server, stats in all_raw_stats:
        # Convert the '127.0.0.1:11217 (1)' style server string to a
        # cricket key.
        server = server.split()[0].replace(':','_').replace('.','_')
        for key in INTERESTING_KEYS:
            print 'memcached_%s_%s:%s@%d' % (
                server, key, stats[key], now)


def main():
    parser = OptionParser()
    parser.add_option(
        "-r", "--raw", action="store_true", default=False,
        help="Output full raw data")
    parser.add_option(
        "-f", "--full", action="store_true", default=False,
        help="Output individual memcached server stats.")
    parser.add_option(
        "-c", "--cricket", action="store_true", default=False,
        help="Output stats in cricket compatible format.")
    options, args = parser.parse_args()
    if len(args) > 0:
        parser.error("Too many arguments.")
    execute_zcml_for_scripts()
    all_raw_stats = getUtility(IMemcacheClient).get_stats()
    if options.raw:
        pprint(all_raw_stats)
    elif options.cricket:
        print_cricket(all_raw_stats)
    elif options.full:
        print_summary(all_raw_stats)
        print_full(all_raw_stats)
    else:
        print_summary(all_raw_stats)
    return 0


if __name__ == '__main__':
    sys.exit(main())
