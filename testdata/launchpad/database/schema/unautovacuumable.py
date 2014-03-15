#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Disable autovacuum on all tables in the database and kill off
any autovacuum processes.

We run this script on databases we require to be totally inactive with
no open connections, such as the template databases we clone. If not
disabled, autovacuum processes sometimes run and break our scripts.

Don't run this on any production systems.
"""

__metaclass__ = type
__all__ = []

import _pythonpath

from distutils.version import LooseVersion
from optparse import OptionParser
import sys
import time

from lp.services.database.sqlbase import (
    connect,
    ISOLATION_LEVEL_AUTOCOMMIT,
    )
from lp.services.scripts import (
    db_options,
    logger,
    logger_options,
    )


def main():
    parser = OptionParser()
    logger_options(parser)
    db_options(parser)

    options, args = parser.parse_args()

    if len(args) > 0:
        parser.error("Too many arguments.")

    log = logger(options)

    log.debug("Connecting")
    con = connect()
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()

    cur.execute('show server_version')
    pg_version = LooseVersion(cur.fetchone()[0])

    log.debug("Disabling autovacuum on all tables in the database.")
    if pg_version < LooseVersion('8.4.0'):
        cur.execute("""
            INSERT INTO pg_autovacuum
            SELECT pg_class.oid, FALSE, -1,-1,-1,-1,-1,-1,-1,-1
            FROM pg_class
            WHERE relkind in ('r','t')
                AND pg_class.oid NOT IN (SELECT vacrelid FROM pg_autovacuum)
            """)
    else:
        cur.execute("""
            SELECT nspname,relname
            FROM pg_namespace, pg_class
            WHERE relnamespace = pg_namespace.oid
                AND relkind = 'r' AND nspname <> 'pg_catalog'
            """)
        for namespace, table in list(cur.fetchall()):
            cur.execute("""
                ALTER TABLE ONLY "%s"."%s" SET (
                    autovacuum_enabled=false,
                    toast.autovacuum_enabled=false)
                """ % (namespace, table))

    log.debug("Killing existing autovacuum processes")
    num_autovacuums = -1
    while num_autovacuums != 0:
        # Sleep long enough for pg_stat_activity to be updated.
        time.sleep(0.6)
        cur.execute("""
            SELECT procpid FROM pg_stat_activity
            WHERE
                datname=current_database()
                AND current_query LIKE 'autovacuum: %'
            """)
        autovacuums = [row[0] for row in cur.fetchall()]
        num_autovacuums = len(autovacuums)
        for procpid in autovacuums:
            log.debug("Cancelling %d" % procpid)
            cur.execute("SELECT pg_cancel_backend(%d)" % procpid)


if __name__ == '__main__':
    sys.exit(main())
