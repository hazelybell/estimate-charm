#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Generate some statistics about a PostgreSQL database suitable for
emailing via cron
"""

__metaclass__ = type

import sys

import psycopg2


def percentage(num, total):
    """Return a percentage string of num/total"""
    if total == 0:
        return 'Unknown'
    else:
        return '%3.2f%%' % ( (num * 100.0) / total, )


def print_row(key, value):
    print '%(key)-20s: %(value)s' % vars()


def pgstattuple(cur, table):
    """Return the result of PostgreSQL contribs's pgstattuple function
    """
    cur.execute("""
        SELECT
            table_len, tuple_count, tuple_len, tuple_percent,
            dead_tuple_count, dead_tuple_len, dead_tuple_percent,
            free_space, free_percent
        FROM pgstattuple(%(table)s)
        """, vars())
    pgstattuple = cur.fetchone()
    return {
        'name': table,
        'table_len': pgstattuple[0],
        'tuple_count': pgstattuple[1],
        'tuple_len': pgstattuple[2],
        'tuple_percent': pgstattuple[3],
        'dead_tuple_count': pgstattuple[4],
        'dead_tuple_len': pgstattuple[5],
        'dead_tuple_percent': pgstattuple[6],
        'free_space': pgstattuple[7],
        'free_percent': pgstattuple[8],
        }


def main(dbname):
    con = psycopg2.connect("dbname=%s" % dbname)
    cur = con.cursor()

    print 'Statistics for %s' % dbname
    print '===============' + '=' * (len(dbname))

    # Database level statistics
    cur.execute("""
        SELECT blks_hit, blks_read, numbackends,xact_commit, xact_rollback
            FROM pg_stat_database
            WHERE datname=%(dbname)s
        """, vars())
    hit, read, backends, commits, rollbacks = cur.fetchone()

    hit_rate = percentage(hit, hit + read)

    print_row("Cache hit rate", hit_rate)
    print_row("Number of backends", backends)

    commit_rate = percentage(commits, commits + rollbacks)

    print_row("Commit rate", commit_rate)

    # Determine dead tuple bloat, if we have pgstattuple installed
    cur.execute("""
        SELECT COUNT(*) FROM pg_proc, pg_namespace
        WHERE pg_proc.pronamespace = pg_namespace.oid
            AND pg_namespace.nspname = 'public'
            AND proname = 'pgstattuple'
        """)
    pgstattuple_installed = (cur.fetchone()[0] > 0)
    if pgstattuple_installed:
        cur.execute("""
            SELECT nspname || '.' || relname
            FROM pg_class, pg_namespace
            WHERE pg_class.relnamespace = pg_namespace.oid
                AND pg_class.relkind = 'r'
                ORDER BY nspname, relname
            """)
        all_tables = [r[0] for r in cur.fetchall()]
        total_live_bytes = 0
        total_dead_bytes = 0
        stats = []
        for table in all_tables:
            stat = pgstattuple(cur, table)
            total_live_bytes += stat['tuple_len']
            total_dead_bytes += stat['dead_tuple_len']
            stats.append(stat)
        # Just report the worst offenders
        stats.sort(key=lambda x: x['dead_tuple_percent'], reverse=True)
        stats = [
            s for s in stats if s['dead_tuple_percent'] >= 10
                and s['dead_tuple_len'] >= 25 * 1024 * 1024
            ]
        def statstr(stat):
            name = stat['name']
            dead_tuple_percent = stat['dead_tuple_percent']
            dead_len = stat['dead_tuple_len'] / (1024*1024)
            return (
                    '%(name)s (%(dead_len)0.2fMB, '
                    '%(dead_tuple_percent)0.2f%%)' % vars()
                    )
        if len(stats) > 0:
            print_row('Needing vacuum', statstr(stats[0]))
            for stat in stats[1:]:
                print_row('', statstr(stat))

    # Unused indexes, ignoring primary keys.
    # XXX Stuart Bishop 2005-06-28:
    # We should identify constraints used to enforce uniqueness too
    cur.execute("""
        SELECT relname, indexrelname
            FROM pg_stat_user_indexes AS u JOIN pg_indexes AS i
                ON u.schemaname = i.schemaname
                    AND u.relname = i.tablename
                    AND u.indexrelname = i.indexname
            WHERE
                idx_scan = 0
                AND indexrelname NOT LIKE '%_pkey'
                AND indexdef NOT LIKE 'CREATE UNIQUE %'
            ORDER BY relname, indexrelname
        """)

    rows = cur.fetchall()
    if len(rows) == 0:
        print_row('Unused indexes', 'N/A')
    else:
        print_row('Unused indexes', rows[0][1])
        for table, index in rows[1:]:
            print_row('', index)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print >> sys.stderr, "Usage: %s [DBNAME]" % sys.argv[0]
        sys.exit(1)
    dbname = sys.argv[1]
    main(dbname)
