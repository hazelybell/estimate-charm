# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

'''
Test harness for tests needing a PostgreSQL backend.
'''

__metaclass__ = type

import atexit
import os
import random
import sys
import time

from bzrlib.errors import LockContention
from bzrlib.lock import WriteLock
import psycopg2

from lp.services.config import config
from lp.services.database.postgresql import (
    generateResetSequencesSQL,
    resetSequences,
    )


class ConnectionWrapper:
    real_connection = None
    committed = False
    last_execute = None
    dirty = False
    auto_close = True

    def __init__(self, real_connection):
        assert not isinstance(real_connection, ConnectionWrapper), \
                "Wrapped the wrapper!"
        self.real_connection = real_connection
        # Set to True to stop test cleanup forcing the connection closed.
        PgTestSetup.connections.append(self)

    def close(self):
        if self in PgTestSetup.connections:
            PgTestSetup.connections.remove(self)
            try:
                self.real_connection.close()
            except psycopg2.InterfaceError:
                # Already closed, killed etc. Ignore.
                pass

    def rollback(self, InterfaceError=psycopg2.InterfaceError):
        # In our test suites, rollback ends up being called twice in some
        # circumstances. Silently ignoring this is probably not correct,
        # but the alternative is wasting further time chasing this
        # and probably refactoring sqlos and/or zope3
        # -- StuartBishop 2005-01-11
        # Need to store InterfaceError cleverly, otherwise it may have been
        # GCed when the world is being destroyed, leading to an odd
        # AttributeError with
        #   except psycopg2.InterfaceError:
        # -- SteveAlexander 2005-03-22
        try:
            self.real_connection.rollback()
        except InterfaceError:
            pass

    def commit(self):
        # flag that a connection has had commit called. This allows
        # optimizations by subclasses, since if no commit has been made,
        # dropping and recreating the database might be unnecessary
        try:
            return self.real_connection.commit()
        finally:
            ConnectionWrapper.committed = True

    def cursor(self):
        return CursorWrapper(self.real_connection.cursor())

    def __getattr__(self, key):
        return getattr(self.real_connection, key)

    def __setattr__(self, key, val):
        if key in ConnectionWrapper.__dict__.keys():
            return object.__setattr__(self, key, val)
        else:
            return setattr(self.real_connection, key, val)


class CursorWrapper:
    """A wrapper around cursor objects.

    Acts like a normal cursor object, except if CursorWrapper.record_sql is
    set, then queries that pass through CursorWrapper.execute will be appended
    to CursorWrapper.last_executed_sql.  This is useful for tests that want to
    ensure that certain SQL is generated.
    """
    real_cursor = None
    last_executed_sql = []
    record_sql = False

    def __init__(self, real_cursor):
        assert not isinstance(real_cursor, CursorWrapper), \
                "Wrapped the wrapper!"
        self.real_cursor = real_cursor

    def execute(self, *args, **kwargs):
        # Detect if DML has been executed. This method isn't perfect,
        # but should be good enough. In particular, it won't notice
        # data modification made by stored procedures.
        mutating_commands = [
                'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'INTO',
                'TRUNCATE', 'REPLACE',
                ]
        for command in mutating_commands:
            if command in args[0].upper():
                ConnectionWrapper.dirty = True
                break

        # Record the last query executed.
        if CursorWrapper.record_sql:
            CursorWrapper.last_executed_sql.append(args[0])
        return self.real_cursor.execute(*args, **kwargs)

    def __getattr__(self, key):
        return getattr(self.real_cursor, key)

    def __setattr__(self, key, val):
        if key in CursorWrapper.__dict__.keys():
            return object.__setattr__(self, key, val)
        else:
            return setattr(self.real_cursor, key, val)


_org_connect = None


def fake_connect(*args, **kw):
    return ConnectionWrapper(_org_connect(*args, **kw))


def installFakeConnect():
    global _org_connect
    assert _org_connect is None
    _org_connect = psycopg2.connect
    psycopg2.connect = fake_connect


def uninstallFakeConnect():
    global _org_connect
    assert _org_connect is not None
    psycopg2.connect = _org_connect
    _org_connect = None


class PgTestSetup:

    # Shared:
    connections = []
    # Use a dynamically generated dbname:
    dynamic = object()

    template = 'template1'
    # Needs to match configs/testrunner*/*:
    dbname = 'launchpad_ftest'
    dbuser = None
    host = None
    port = None

    # Class attributes. With PostgreSQL 8.4, pg_shdepend bloats
    # hugely when we drop and create databases, because this
    # operation cancels any autovacuum process maintaining it.
    # To cope, we need to manually vacuum it ourselves occasionally.
    vacuum_shdepend_every = 10
    _vacuum_shdepend_counter = 0

    # (template, name) of last test. Class attribute.
    _last_db = (None, None)
    # Class attribute. True if we should destroy the DB because changes made.
    _reset_db = True

    def __init__(self, template=None, dbname=dynamic, dbuser=None,
            host=None, port=None, reset_sequences_sql=None):
        '''Construct the PgTestSetup

        Note that dbuser is not used for setting up or tearing down
        the database - it is only used by the connect() method
        '''
        if template is not None:
            self.template = template
        if dbname is PgTestSetup.dynamic:
            from lp.testing.layers import BaseLayer
            if os.environ.get('LP_TEST_INSTANCE'):
                self.dbname = "%s_%s" % (
                    self.__class__.dbname, os.environ.get('LP_TEST_INSTANCE'))
                # Stash the name we use in the config if a writable config is
                # available.
                # Avoid circular imports
                section = """[database]
rw_main_master: dbname=%s host=localhost
rw_main_slave:  dbname=%s host=localhost

""" % (self.dbname, self.dbname)
                if BaseLayer.config_fixture is not None:
                    BaseLayer.config_fixture.add_section(section)
                if BaseLayer.appserver_config_fixture is not None:
                    BaseLayer.appserver_config_fixture.add_section(section)
            if config.instance_name in (
                BaseLayer.config_name, BaseLayer.appserver_config_name):
                config.reloadConfig()
            else:
                # Fallback to the class name.
                self.dbname = self.__class__.dbname
        elif dbname is not None:
            self.dbname = dbname
        else:
            # Fallback to the class name.
            self.dbname = self.__class__.dbname
        if dbuser is not None:
            self.dbuser = dbuser
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port
        self.reset_sequences_sql = reset_sequences_sql

    def _connectionString(self, dbname, dbuser=None):
        connection_parameters = ['dbname=%s' % dbname]
        if dbuser is not None:
            connection_parameters.append('user=%s' % dbuser)
        if self.host is not None:
            connection_parameters.append('host=%s' % self.host)
        if self.port is not None:
            connection_parameters.append('port=%s' % self.host)
        return ' '.join(connection_parameters)

    def superuser_connection(self, dbname=None):
        if dbname is None:
            dbname = self.dbname
        return psycopg2.connect(self._connectionString(dbname))

    def generateResetSequencesSQL(self):
        """Return a SQL statement that resets all sequences."""
        con = self.superuser_connection()
        cur = con.cursor()
        try:
            return generateResetSequencesSQL(cur)
        finally:
            con.close()

    def setUp(self):
        '''Create a fresh database (dropping the old if necessary)

        Skips db creation if reset_db is False
        '''
        # This is now done globally in test.py
        #installFakeConnect()
        if (self.template, self.dbname) != PgTestSetup._last_db:
            PgTestSetup._reset_db = True
        if not PgTestSetup._reset_db:
            # The database doesn't need to be reset. We reset the sequences
            # anyway (because they might have been incremented even if
            # nothing was committed), making sure not to disturb the
            # 'committed' flag, and we're done.
            con = self.superuser_connection()
            cur = con.cursor()
            if self.reset_sequences_sql is None:
                resetSequences(cur)
            else:
                cur.execute(self.reset_sequences_sql)
            con.commit()
            con.close()
            ConnectionWrapper.committed = False
            ConnectionWrapper.dirty = False
            return
        self.dropDb()

        # Take out an external lock on the template to avoid causing
        # contention and impeding other processes (pg performs poorly
        # when performing concurrent create db from a single template).
        pid = os.getpid()
        start = time.time()
        # try for up to 10 seconds:
        debug = False
        if debug:
            sys.stderr.write('%0.2f starting %s\n' % (start, pid,))
        l = None
        lockname = '/tmp/lp.createdb.%s' % (self.template,)
        # Wait for the external lock.  Most LP tests use the
        # DatabaseLayer which does a double-indirect: it clones the
        # launchpad_ftest_template into a per-test runner template, so
        # we don't have much template contention.
        # However there are a few tests in LP which do use template1 and
        # will contend a lot. Cloning template1 takes 0.2s on a modern
        # machine, so even a modest 8-way server will trivially backlog
        # on db cloning.
        # The 30 second time is enough to deal with the backlog on the
        # known template1 using tests.
        while time.time() - start < 30.0:
            try:
                if debug:
                    sys.stderr.write('taking %s\n' % (pid,))
                l = WriteLock(lockname)
                if debug:
                    sys.stderr.write('%0.2f taken %s\n' % (time.time(), pid,))
                break
            except LockContention:
                if debug:
                    sys.stderr.write('blocked %s\n' % (pid,))
            time.sleep(random.random())
        if l is None:
            raise LockContention(lockname)
        try:
            # The clone may be delayed if gc has not disconnected other
            # processes which have done a recent clone. So provide a spin
            # with an exponential backoff.
            attempts = 10
            for counter in range(0, attempts):
                if debug:
                    sys.stderr.write(
                        "%0.2f connecting %s %s\n"
                        % (time.time(), pid, self.template))
                con = self.superuser_connection(self.template)
                try:
                    con.set_isolation_level(0)
                    cur = con.cursor()
                    try:
                        _start = time.time()
                        try:
                            cur.execute(
                                "CREATE DATABASE %s TEMPLATE=%s "
                                "ENCODING='UNICODE'" % (
                                    self.dbname, self.template))
                            # Try to ensure our cleanup gets invoked, even in
                            # the face of adversity such as the test suite
                            # aborting badly.
                            atexit.register(self.dropDb)
                            if debug:
                                sys.stderr.write(
                                    "create db in %0.2fs\n" % (
                                        time.time() - _start))
                            break
                        except psycopg2.DatabaseError as x:
                            if counter == attempts - 1:
                                raise
                            x = str(x)
                            if 'being accessed by other users' not in x:
                                raise
                    finally:
                        cur.close()
                finally:
                    con.close()
                duration = (2 ** counter) * random.random()
                if debug:
                    sys.stderr.write(
                        '%0.2f busy:sleeping (%d retries) %s %s %s\n' % (
                        time.time(), counter, pid, self.template, duration))
                # Let the server wrap up whatever was blocking the copy
                # of the template.
                time.sleep(duration)
            end = time.time()
            if debug:
                sys.stderr.write(
                    '%0.2f (%0.2f) completed (%d retries) %s %s\n'
                    % (end, end - start, counter, pid, self.template))
        finally:
            l.unlock()
            if debug:
                sys.stderr.write('released %s\n' % (pid,))
        ConnectionWrapper.committed = False
        ConnectionWrapper.dirty = False
        PgTestSetup._last_db = (self.template, self.dbname)
        PgTestSetup._reset_db = False

    def tearDown(self):
        '''Close all outstanding connections and drop the database'''
        for con in self.connections[:]:
            if con.auto_close:
                # Removes itself from self.connections:
                con.close()
        if (ConnectionWrapper.committed and ConnectionWrapper.dirty):
            PgTestSetup._reset_db = True
        ConnectionWrapper.committed = False
        ConnectionWrapper.dirty = False
        if PgTestSetup._reset_db:
            self.dropDb()
        #uninstallFakeConnect()

    def connect(self):
        """Get an open DB-API Connection object to a temporary database"""
        con = psycopg2.connect(
            self._connectionString(self.dbname, self.dbuser)
            )
        if isinstance(con, ConnectionWrapper):
            return con
        else:
            return ConnectionWrapper(con)

    def dropDb(self):
        '''Drop the database if it exists.

        Raises an exception if there are open connections
        '''
        attempts = 100
        for i in range(0, attempts):
            try:
                con = self.superuser_connection(self.template)
            except psycopg2.OperationalError as x:
                if 'does not exist' in str(x):
                    return
                raise
            try:
                con.set_isolation_level(0)

                # Kill all backend connections if this helper happens to be
                # available. We could create it if it doesn't exist if not
                # always having this is a problem.
                try:
                    cur = con.cursor()
                    cur.execute("""
                        SELECT pg_terminate_backend(procpid)
                        FROM pg_stat_activity
                        WHERE procpid <> pg_backend_pid() AND datname=%s
                        """, [self.dbname])
                except psycopg2.DatabaseError:
                    pass

                # Drop the database, trying for a number of seconds in case
                # connections are slow in dropping off.
                try:
                    cur = con.cursor()
                    cur.execute('DROP DATABASE %s' % self.dbname)
                except psycopg2.DatabaseError as x:
                    if i == attempts - 1:
                        # Too many failures - raise an exception
                        raise
                    if 'being accessed by other users' in str(x):
                        if i < attempts - 1:
                            time.sleep(0.1)
                            continue
                    if 'does not exist' in str(x):
                        break
                    raise
                PgTestSetup._vacuum_shdepend_counter += 1
                if (PgTestSetup._vacuum_shdepend_counter
                    % PgTestSetup.vacuum_shdepend_every) == 0:
                    cur.execute('VACUUM pg_catalog.pg_shdepend')
            finally:
                con.close()
        # Any further setUp's must make a new DB.
        PgTestSetup._reset_db = True

    def force_dirty_database(self):
        """flag the database as being dirty

        This ensures that the database will be recreated for the next test.
        Tearing down the database is done automatically when we detect
        changes. Currently, however, not all changes are detectable (such
        as database changes made from a subprocess.
        """
        PgTestSetup._reset_db = True
