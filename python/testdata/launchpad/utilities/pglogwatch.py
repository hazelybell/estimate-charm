#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Watch live PostgreSQL logs for interesting stuff
"""

from optparse import OptionParser
import re
import subprocess
import sys


def get_options(args=None):
    parser = OptionParser()
    parser.add_option("-l", "--logfile", dest="logfile",
            default="/var/log/postgresql/postgres.log",
            metavar="LOG", help="Monitor LOG instead of the default"
            )
    parser.add_option("--slow", dest="slow",
            type="float", default=100.0, metavar="TIME",
            help="Report slow queries taking over TIME seconds",
            )
    (options, args) = parser.parse_args(args)
    return options

def generate_loglines(logfile):
    """Generator returning the next line in the logfile (blocking)"""
    cmd = subprocess.Popen(
            ['tail', '-f', logfile],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while cmd.poll() is None:
        yield cmd.stdout.readline()
    if cmd.returncode != 0:
        print >> sys.stderr, cmd.stderr.read()
        raise RuntimeError("tail returned %d" % cmd.returncode)


class Process(object):
    statement = None
    duration = None
    connection = None
    auth = None

    def __init__(self, pid):
        self.pid = pid


class Watcher(object):
    _line_re = re.compile("""
        ^\d{4}-\d\d-\d\d \s \d\d:\d\d:\d\d \s 
        \[(?P<pid>\d+)\] \s (?P<type>LOG|ERROR|DETAIL): \s+ (?P<rest>.*)$
        """, re.X)

    _statement_re = re.compile("""
        ^statement: \s (?P<statement>.*)$
        """, re.X)

    _duration_re = re.compile("""
        ^duration: \s (?P<duration>\d+\.\d+) \s ms$
        """, re.X)

    _connection_received_re = re.compile("""
        ^connection \s received: \s+ (?P<connection>.*)$
        """, re.X)

    _connection_authorized_re = re.compile("""
        ^connection \s authorized: \s+ (?P<auth>.*)$
        """, re.X)

    _ignored_rest_re = re.compile("""
        ^(received \s | ERROR: \s | unexpected \s EOF \s) .*$
        """, re.X)

    _ignored_statements_re = re.compile("""
        ^(BEGIN.*|END)$
        """, re.X)

    def __init__(self, options):
        self.processes = {}
        self.options = options
        self.previous_process = None

    def run(self):
        lines = generate_loglines(options.logfile)
        for line in lines:
            self.feed(line)

    def feed(self, line):

        # Handle continuations of previous statement
        if line.startswith('\t'):
            if self.previous_process is not None:
                self.previous_process.statement += '\n%s' % line[1:-1]
            return

        match = self._line_re.search(line)
        if match is None:
            raise ValueError('Badly formatted line %r' % (line,))

        t = match.group('type')
        if t in ['ERROR', 'DETAIL']:
            return
        if t != 'LOG':
            raise ValueError('Unknown line type %s (%r)' % (t, line))

        pid = int(match.group('pid'))
        rest = match.group('rest')
        
        process = self.processes.get(pid, None)
        if process is None:
            process = Process(pid)
            self.processes[pid] = process
        self.previous_process = process
        
        match = self._statement_re.search(rest)
        if match is not None:
            statement = match.group('statement')
            if process.statement:
                process.statement += '\n%s' % statement
            else:
                process.statement = statement
            return

        match = self._duration_re.search(rest)
        if match is not None:
            process.duration = float(match.group('duration'))
            self.reportDuration(process)
            self.previous_process = None
            del self.processes[process.pid]
            return

        match = self._connection_received_re.search(rest)
        if match is not None:
            process.connection = match.group('connection')
            return

        match = self._connection_authorized_re.search(rest)
        if match is not None:
            process.auth = match.group('auth')
            return

        match = self._ignored_rest_re.search(rest)
        if match is not None:
            return

        raise ValueError('Unknown entry: %r' % (rest,))

    def reportDuration(self, process):
        """Report a slow statement if it is above a threshold"""
        if self.options.slow is None or process.statement is None:
            return

        match = self._ignored_statements_re.search(process.statement)
        if match is not None:
            return

        if process.duration > options.slow:
            print '[%5d] %s' % (process.pid, process.statement)
            print '        Duration: %0.3f' % (process.duration,)

if __name__ == '__main__':
    options = get_options()

    watcher = Watcher(options)
    try:
        watcher.run()
    except KeyboardInterrupt:
        pass

