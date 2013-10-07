#!/usr/bin/python -S
#
# Copyright 2009, 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests that get run automatically on a merge."""
import _pythonpath

import errno
import os
import select
from signal import (
    SIGHUP,
    SIGINT,
    SIGKILL,
    SIGTERM,
    )
from StringIO import StringIO
from subprocess import (
    PIPE,
    Popen,
    STDOUT,
    )
import sys
import tabnanny
import time

import psycopg2

# The TIMEOUT setting (expressed in seconds) affects how long a test will run
# before it is deemed to be hung, and then appropriately terminated.
# It's principal use is preventing a PQM job from hanging indefinitely and
# backing up the queue.
# e.g. Usage: TIMEOUT = 60 * 10
# This will set the timeout to 10 minutes.
TIMEOUT = 60 * 10

HERE = os.path.dirname(os.path.realpath(__file__))


def main():
    """Call bin/test with whatever arguments this script was run with.

    Prior to running the tests this script sets up the test database.

    Returns 1 on error, otherwise it returns the testrunner's exit code.
    """
    if setup_test_database() != 0:
        return 1

    return run_test_process()


def setup_test_database():
    """Set up a test instance of our postgresql database.

    Returns 0 for success, 1 for errors.
    """
    # Sanity check PostgreSQL version. No point in trying to create a test
    # database when PostgreSQL is too old.
    con = psycopg2.connect('dbname=template1')
    cur = con.cursor()
    cur.execute('show server_version')
    server_version = cur.fetchone()[0]
    try:
        numeric_server_version = tuple(map(int, server_version.split('.')))
    except ValueError:
        # Skip this check if the version number is more complicated than
        # we expected.
        pass
    else:
        if numeric_server_version < (8, 0):
            print 'Your PostgreSQL version is too old.  You need 8.x.x'
            print 'You have %s' % server_version
            return 1

    # Drop the template database if it exists - the Makefile does this
    # too, but we can explicity check for errors here
    con = psycopg2.connect('dbname=template1')
    con.set_isolation_level(0)
    cur = con.cursor()
    try:
        cur.execute('drop database launchpad_ftest_template')
    except psycopg2.ProgrammingError as x:
        if 'does not exist' not in str(x):
            raise

    # If there are existing database connections, terminate. We have
    # rogue processes still connected to the database.
    for loop in range(2):
        cur.execute("""
            SELECT usename, current_query
            FROM pg_stat_activity
            WHERE datname IN (
                'launchpad_dev', 'launchpad_ftest_template', 'launchpad_ftest')
            """)
        results = list(cur.fetchall())
        if not results:
            break
        # Rogue processes. Report, sleep for a bit, and try again.
        for usename, current_query in results:
            print '!! Open connection %s - %s' % (usename, current_query)
        print 'Sleeping'
        time.sleep(20)
    else:
        print 'Cannot rebuild database. There are open connections.'
        return 1

    cur.close()
    con.close()

    # Build the template database. Tests duplicate this.
    schema_dir = os.path.join(HERE, 'database', 'schema')
    if os.system('cd %s; make test > /dev/null' % (schema_dir)) != 0:
        print 'Failed to create database or load sampledata.'
        return 1

    # Sanity check the database. No point running tests if the
    # bedrock is crumbling.
    con = psycopg2.connect('dbname=launchpad_ftest_template')
    cur = con.cursor()
    cur.execute('show search_path')
    search_path = cur.fetchone()[0]
    if search_path != '$user,public,ts2':
        print 'Search path incorrect.'
        print 'Add the following line to /etc/postgresql/postgresql.conf:'
        print "    search_path = '$user,public,ts2'"
        print "and tell postgresql to reload its configuration file."
        return 1
    cur.execute("""
        select pg_encoding_to_char(encoding) as encoding from pg_database
        where datname='launchpad_ftest_template'
        """)
    enc = cur.fetchone()[0]
    if enc not in ('UNICODE', 'UTF8'):
        print 'Database encoding incorrectly set'
        return 1
    cur.execute(r"""
        SELECT setting FROM pg_settings
        WHERE context='internal' AND name='lc_ctype'
        """)
    loc = cur.fetchone()[0]
    #if not (loc.startswith('en_') or loc in ('C', 'en')):
    if loc != 'C':
        print 'Database locale incorrectly set. Need to rerun initdb.'
        return 1

    # Explicity close our connections - things will fail if we leave open
    # connections.
    cur.close()
    del cur
    con.close()
    del con

    return 0


def run_test_process():
    """Start the testrunner process and return its exit code."""
    print 'Running tests.'
    os.chdir(HERE)

    # We run the test suite under a virtual frame buffer server so that the
    # JavaScript integration test suite can run.
    cmd = [
        '/usr/bin/xvfb-run',
        "--error-file=/var/tmp/xvfb-errors.log",
        "--server-args='-screen 0 1024x768x24'",
        os.path.join(HERE, 'bin', 'test')] + sys.argv[1:]
    command_line = ' '.join(cmd)
    print "Running command:", command_line

    # Run the test suite.  Make the suite the leader of a new process group
    # so that we can signal the group without signaling ourselves.
    xvfb_proc = Popen(
        command_line,
        stdout=PIPE,
        stderr=STDOUT,
        preexec_fn=os.setpgrp,
        shell=True)

    # This code is very similar to what takes place in Popen._communicate(),
    # but this code times out if there is no activity on STDOUT for too long.
    # This keeps us from blocking when reading from a hung testrunner, allows
    # us to time out if the child process hangs, and avoids issues when using
    # Popen.communicate() with large data sets.
    open_readers = set([xvfb_proc.stdout])
    while open_readers:
        # select() blocks for a long time and can easily fail with EINTR
        # <https://bugs.launchpad.net/launchpad/+bug/615740>.  Really we
        # should have EINTR protection across the whole script (other syscalls
        # might be interrupted) but this is the longest and most likely to
        # hit, and doing it perfectly in python has proved to be quite hard in
        # bzr. -- mbp 20100924
        while True:
            try:
                rlist, wlist, xlist = select.select(open_readers, [], [], TIMEOUT)
                break
            except select.error as e:
                # nb: select.error doesn't expose a named 'errno' attribute,
                # at least in python 2.6.5; see
                # <http://mail.python.org/pipermail/python-dev/2000-October/009671.html>
                if e[0] == errno.EINTR:
                    continue
                else:
                    raise

        if len(rlist) == 0:
            # The select() statement timed out!

            if xvfb_proc.poll() is not None:
                # The process we were watching died.
                break

            cleanup_hung_testrunner(xvfb_proc)
            break

        if xvfb_proc.stdout in rlist:
            # Read a chunk of output from STDOUT.
            chunk = os.read(xvfb_proc.stdout.fileno(), 1024)
            sys.stdout.write(chunk)
            if chunk == "":
                # Gracefully exit the loop if STDOUT is empty.
                open_readers.remove(xvfb_proc.stdout)

    rv = xvfb_proc.wait()

    if rv == 0:
        print
        print 'Successfully ran all tests.'
    else:
        print
        print 'Tests failed (exit code %d)' % rv

    return rv


def cleanup_hung_testrunner(process):
    """Kill and clean up the testrunner process and its children."""
    print
    print
    print ("WARNING: A test appears to be hung. There has been no "
        "output for %d seconds." % TIMEOUT)
    print "Forcibly shutting down the test suite"

    # This guarantees the process will die.  In rare cases
    # a child process may survive this if they are in a different
    # process group and they ignore the signals we send their parent.
    nice_killpg(process.pid)

    # The process should absolutely be dead now.
    assert process.poll() is not None

    # Drain the subprocess's stdout and stderr.
    print "The dying processes left behind the following output:"
    print "--------------- BEGIN OUTPUT ---------------"
    sys.stdout.write(process.stdout.read())
    print
    print "---------------- END OUTPUT ----------------"


def nice_killpg(pgid):
    """Kill a Unix process group using increasingly harmful signals."""
    try:
        print "Process group %d will be killed" % pgid

        # Attempt a series of increasingly brutal methods of killing the
        # process.
        for signum in [SIGTERM, SIGINT, SIGHUP, SIGKILL]:
            print "Sending signal %s to process group %d" % (signum, pgid)
            os.killpg(pgid, signum)

            # Give the processes some time to shut down.
            time.sleep(3)

    except OSError as exc:
        if exc.errno == errno.ESRCH:
            # We tried to call os.killpg() and found the group to be empty.
            pass
        else:
            raise
    print "Process group %d is now empty." % pgid


if __name__ == '__main__':
    sys.exit(main())
