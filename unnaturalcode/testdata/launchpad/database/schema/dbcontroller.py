# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Connect to and control our pgbouncer instance."""

__metaclass__ = type
__all__ = ['DBController', 'streaming_sync']

import time

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import NamedTupleConnection

from lp.services.database.postgresql import ConnectionString

# Increase this timeout once we are confident in the
# implementation. We don't want to block rollouts
# unnecessarily with slow timeouts and a flaky sync
# detection implementation.
STREAMING_SYNC_TIMEOUT = 60


def pg_connect(conn_str):
    con = psycopg2.connect(
        str(conn_str), connection_factory=NamedTupleConnection)
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return con


def streaming_sync(con, timeout=None):
    """Wait for streaming replicas to synchronize with master as of now.

    :param timeout: seconds to wait, None for no timeout.

    :returns: True if sync happened or no streaming replicas
              False if the timeout was passed.
    """
    cur = con.cursor()

    # Force a WAL switch, returning the current position.
    cur.execute('SELECT pg_switch_xlog()')
    wal_point = cur.fetchone()[0]
    start_time = time.time()
    while timeout is None or time.time() < start_time + timeout:
        cur.execute("""
            SELECT FALSE FROM pg_stat_replication
            WHERE replay_location < %s LIMIT 1
            """, (wal_point,))
        if cur.fetchone() is None:
            # All slaves, possibly 0, are in sync.
            return True
        time.sleep(0.2)
    return False


class DBController:
    def __init__(self, log, pgbouncer_conn_str, dbname, dbuser):
        self.log = log

        pgbouncer_conn_str = ConnectionString(pgbouncer_conn_str)
        if not pgbouncer_conn_str.dbname:
            pgbouncer_conn_str.dbname = 'pgbouncer'
        if pgbouncer_conn_str.dbname != 'pgbouncer':
            log.warn("pgbouncer administrative database not named 'pgbouncer'")
        self.pgbouncer_con = pg_connect(pgbouncer_conn_str)

        self.master_name = None
        self.master = None
        self.slaves = {}

        for db in self.pgbouncer_cmd('show databases', results=True):
            if db.database != dbname:
                continue

            conn_str = ConnectionString(
                'dbname=%s port=%s user=%s' % (dbname, db.port, dbuser))
            if db.host:
                conn_str.host = db.host
            con = pg_connect(conn_str)
            cur = con.cursor()
            cur.execute('select pg_is_in_recovery()')
            if cur.fetchone()[0] is True:
                self.slaves[db.name] = conn_str
            else:
                self.master_name = db.name
                self.master = conn_str

        if self.master_name is None:
            log.fatal('No master detected.')
            raise SystemExit(98)

    def pgbouncer_cmd(self, cmd, results):
        cur = self.pgbouncer_con.cursor()
        cur.execute(cmd)
        if results:
            return cur.fetchall()

    def pause_replication(self):
        names = self.slaves.keys()
        self.log.info("Pausing replication to %s.", ', '.join(names))
        for name, conn_str in self.slaves.items():
            try:
                con = pg_connect(conn_str)
                cur = con.cursor()
                cur.execute('select pg_xlog_replay_pause()')
            except psycopg2.Error, x:
                self.log.error(
                    'Unable to pause replication to %s (%s).'
                    % (name, str(x)))
                return False
        return True

    def resume_replication(self):
        names = self.slaves.keys()
        self.log.info("Resuming replication to %s.", ', '.join(names))
        success = True
        for name, conn_str in self.slaves.items():
            try:
                con = pg_connect(conn_str)
                cur = con.cursor()
                cur.execute('select pg_xlog_replay_resume()')
            except psycopg2.Error, x:
                success = False
                self.log.error(
                    'Failed to resume replication to %s (%s).'
                    % (name, str(x)))
        return success

    def ensure_replication_enabled(self):
        """Force replication back on.

        It may have been disabled if a previous run failed horribly,
        or just admin error. Either way, we are trying to make the
        scheduled downtime window so automate this.
        """
        success = True
        wait_for_sync = False
        for name, conn_str in self.slaves.items():
            try:
                con = pg_connect(conn_str)
                cur = con.cursor()
                cur.execute("SELECT pg_is_xlog_replay_paused()")
                replication_paused = cur.fetchone()[0]
                if replication_paused:
                    self.log.warn("Replication paused on %s. Resuming.", name)
                    cur.execute("SELECT pg_xlog_replay_resume()")
                    wait_for_sync = True
            except psycopg2.Error, x:
                success = False
                self.log.error(
                    "Failed to resume replication on %s (%s)", name, str(x))
        if success and wait_for_sync:
            self.sync()
        return success

    def disable(self, name):
        try:
            self.pgbouncer_cmd("DISABLE %s" % name, results=False)
            self.pgbouncer_cmd("KILL %s" % name, results=False)
            return True
        except psycopg2.Error, x:
            self.log.error("Unable to disable %s (%s)", name, str(x))
            return False

    def enable(self, name):
        try:
            self.pgbouncer_cmd("RESUME %s" % name, results=False)
            self.pgbouncer_cmd("ENABLE %s" % name, results=False)
            return True
        except psycopg2.Error, x:
            self.log.error("Unable to enable %s (%s)", name, str(x))
            return False

    def disable_master(self):
        self.log.info("Disabling access to %s.", self.master_name)
        return self.disable(self.master_name)

    def enable_master(self):
        self.log.info("Enabling access to %s.", self.master_name)
        return self.enable(self.master_name)

    def disable_slaves(self):
        names = self.slaves.keys()
        self.log.info(
            "Disabling access to %s.", ', '.join(names))
        for name in self.slaves.keys():
            if not self.disable(name):
                return False  # Don't do further damage if we failed.
        return True

    def enable_slaves(self):
        names = self.slaves.keys()
        self.log.info(
            "Enabling access to %s.", ', '.join(names))
        success = True
        for name in self.slaves.keys():
            if not self.enable(name):
                success = False
        return success

    def sync(self):
        sync = streaming_sync(pg_connect(self.master), STREAMING_SYNC_TIMEOUT)
        if sync:
            self.log.debug('Slaves in sync.')
        else:
            self.log.error(
                'Slaves failed to sync after %d seconds.',
                STREAMING_SYNC_TIMEOUT)
        return sync
