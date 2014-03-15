#!/usr/bin/python
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This file is mirrored into lp:losa-db-scripts, so please keep that
# version in sync with the master in the Launchpad tree.

"""
dropdb only more so.

Cut off access, slaughter connections and burn the database to the ground
(but do nothing that could put the system into recovery mode).
"""

from optparse import OptionParser
import sys
import time

import psycopg2
import psycopg2.extensions


def connect(dbname='template1'):
    """Connect to the database, returning the DB-API connection."""
    if options.user is not None:
        return psycopg2.connect("dbname=%s user=%s" % (dbname, options.user))
    else:
        return psycopg2.connect("dbname=%s" % dbname)


def rollback_prepared_transactions(database):
    """Rollback any prepared transactions.

    PostgreSQL will refuse to drop a database with outstanding prepared
    transactions.
    """
    con = connect(database)
    con.set_isolation_level(0)  # Autocommit so we can ROLLBACK PREPARED.
    cur = con.cursor()

    # Get a list of outstanding prepared transactions.
    cur.execute(
            "SELECT gid FROM pg_prepared_xacts WHERE database=%(database)s",
            vars())
    xids = [row[0] for row in cur.fetchall()]
    for xid in xids:
        cur.execute("ROLLBACK PREPARED %(xid)s", vars())
    con.close()


def still_open(database, max_wait=120):
    """Return True if there are still open connections, apart from our own.

    Waits a while to ensure that connections shutting down have a chance
    to. This might take a while if there is a big transaction to
    rollback.
    """
    con = connect()
    con.set_isolation_level(0)  # Autocommit.
    cur = con.cursor()
    # Keep checking until the timeout is reached, returning True if all
    # of the backends are gone.
    start = time.time()
    while time.time() < start + max_wait:
        cur.execute("""
            SELECT TRUE FROM pg_stat_activity
            WHERE
                datname=%(database)s
                AND procpid != pg_backend_pid()
            LIMIT 1
            """, vars())
        if cur.fetchone() is None:
            return False
        time.sleep(0.6)  # Stats only updated every 500ms.
    con.close()
    return True


def massacre(database):
    con = connect()
    con.set_isolation_level(0)  # Autocommit
    cur = con.cursor()

    # Allow connections to the doomed database if something turned this off,
    # such as an aborted run of this script.
    cur.execute(
        "UPDATE pg_database SET datallowconn=TRUE WHERE datname=%s",
        [database])

    # Rollback prepared transactions.
    rollback_prepared_transactions(database)

    try:
        # Stop connections to the doomed database.
        cur.execute(
            "UPDATE pg_database SET datallowconn=FALSE WHERE datname=%s",
            [database])

        # New connections are disabled, but pg_stat_activity is only
        # updated every 500ms. Ensure that pg_stat_activity has
        # been refreshed to catch any connections that opened
        # immediately before setting datallowconn.
        time.sleep(1)

        # Terminate open connections.
        cur.execute("""
            SELECT procpid, pg_terminate_backend(procpid)
            FROM pg_stat_activity
            WHERE datname=%s AND procpid <> pg_backend_pid()
            """, [database])
        for procpid, success in cur.fetchall():
            if not success:
                print >> sys.stderr, (
                    "pg_terminate_backend(%s) failed" % procpid)
        con.close()

        if still_open(database):
            print >> sys.stderr, (
                    "Unable to kill all backends! Database not destroyed.")
            return 9

        # Destroy the database.
        con = connect()
        # AUTOCOMMIT required to execute commands like DROP DATABASE.
        con.set_isolation_level(0)
        cur = con.cursor()
        cur.execute("DROP DATABASE %s" % database)  # Not quoted.
        con.close()
        return 0
    finally:
        # In case something messed up, allow connections again so we can
        # inspect the damage.
        con = connect()
        con.set_isolation_level(0)
        cur = con.cursor()
        cur.execute(
                "UPDATE pg_database SET datallowconn=TRUE WHERE datname=%s",
                [database])
        con.close()


def rebuild(database, template):
    if still_open(template, 20):
        print >> sys.stderr, (
            "Giving up waiting for connections to %s to drop." % template)
        report_open_connections(template)
        return 10

    start = time.time()
    now = start
    error_msg = None
    con = connect()
    con.set_isolation_level(0)  # Autocommit required for CREATE DATABASE.
    create_db_cmd = """
        CREATE DATABASE %s WITH ENCODING='UTF8' TEMPLATE=%s
        """ % (database, template)
    # 8.4 allows us to create empty databases with a different locale
    # to template1 by using the template0 database as a template.
    # We make use of this feature so we don't have to care what locale
    # was used to create the database cluster rather than requiring it
    # to be rebuilt in the C locale.
    if template == "template0":
        create_db_cmd += "LC_COLLATE='C' LC_CTYPE='C'"
    while now < start + 20:
        cur = con.cursor()
        try:
            cur.execute(create_db_cmd)
            con.close()
            return 0
        except psycopg2.Error as exception:
            error_msg = str(exception)
        time.sleep(0.6)  # Stats only updated every 500ms.
        now = time.time()
    con.close()

    print >> sys.stderr, "Unable to recreate database: %s" % error_msg
    return 11


def report_open_connections(database):
    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT usename, datname, count(*)
        FROM pg_stat_activity
        WHERE procpid != pg_backend_pid()
        GROUP BY usename, datname
        ORDER BY datname, usename
        """, [database])
    for usename, datname, num_connections in cur.fetchall():
        print >> sys.stderr, "%d connections by %s to %s" % (
            num_connections, usename, datname)
    con.close()


options = None


def main():
    parser = OptionParser("Usage: %prog [options] DBNAME")
    parser.add_option("-U", "--user", dest="user", default=None,
        help="Connect as USER", metavar="USER")
    parser.add_option("-t", "--template", dest="template", default=None,
        help="Recreate database using DBNAME as a template database."
            " If template0, database will be created in the C locale.",
        metavar="DBNAME")
    global options
    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error('Must specify one, and only one, database to destroy')

    database = args[0]

    # Don't be stupid protection.
    if database in ('template1', 'template0'):
        parser.error(
            "Running this script against template1 or template0 is nuts.")

    con = connect()
    cur = con.cursor()

    # Ensure the template database exists.
    if options.template is not None:
        cur.execute(
            "SELECT TRUE FROM pg_database WHERE datname=%s",
            [options.template])
        if cur.fetchone() is None:
            parser.error(
                "Template database %s does not exist." % options.template)
    # If the database doesn't exist, no point attempting to drop it.
    cur.execute("SELECT TRUE FROM pg_database WHERE datname=%s", [database])
    db_exists = cur.fetchone() is not None
    con.close()

    if db_exists:
        rv = massacre(database)
        if rv != 0:
            print >> sys.stderr, "Fail %d" % rv
            return rv

    if options.template is not None:
        return rebuild(database, options.template)
    else:
        return 0


if __name__ == '__main__':
    sys.exit(main())
