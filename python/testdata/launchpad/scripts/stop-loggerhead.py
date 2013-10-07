#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from optparse import OptionParser
import os
import sys


parser = OptionParser(description="Stop loggerhead.")
parser.parse_args()

home = os.path.realpath(os.path.dirname(__file__))
pidfile = os.path.join(home, 'loggerhead.pid')

try:
    f = open(pidfile, 'r')
except IOError as e:
    print 'No pid file found.'
    sys.exit(1)

pid = int(f.readline())

try:
    os.kill(pid, 0)
except OSError as e:
    print 'Stale pid file; server is not running.'
    sys.exit(1)

print
print 'Shutting down previous server @ pid %d.' % (pid,)
print

import signal
os.kill(pid, signal.SIGTERM)
