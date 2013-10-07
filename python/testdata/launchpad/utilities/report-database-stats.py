#!/usr/bin/python -S
# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generate the database statistics report."""

__metaclass__ = type

import _pythonpath

from datetime import datetime
from operator import attrgetter
from textwrap import (
    dedent,
    fill,
    )

from lp.scripts.helpers import LPOptionParser
from lp.services.database.namedrow import named_fetchall
from lp.services.database.sqlbase import (
    connect,
    sqlvalues,
    )
from lp.services.scripts import db_options


class Table:
    pass


def get_where_clause(options, fuzz='0 seconds'):
    "Generate a WHERE clause referencing the date_created column."
    # We have two of the from timestamp, the until timestamp and an
    # interval. The interval is in a format unsuitable for processing in
    # Python. If the interval is set, it represents the period before
    # the until timestamp or the period after the from timestamp,
    # depending on which of these is set. From this information,
    # generate the SQL representation of the from timestamp and the
    # until timestamp.
    if options.from_ts:
        from_sql = ("CAST(%s AS timestamp without time zone)"
            % sqlvalues(options.from_ts))
    elif options.interval and options.until_ts:
        from_sql = (
            "CAST(%s AS timestamp without time zone) - CAST(%s AS interval)"
            % sqlvalues(options.until_ts, options.interval))
    elif options.interval:
        from_sql = (
            "(CURRENT_TIMESTAMP AT TIME ZONE 'UTC') - CAST(%s AS interval)"
            % sqlvalues(options.interval))
    else:
        from_sql = "CAST('1970-01-01' AS timestamp without time zone)"

    if options.until_ts:
        until_sql = (
            "CAST(%s AS timestamp without time zone)"
            % sqlvalues(options.until_ts))
    elif options.interval and options.from_ts:
        until_sql = (
            "CAST(%s AS timestamp without time zone) + CAST(%s AS interval)"
            % sqlvalues(options.from_ts, options.interval))
    else:
        until_sql = "CURRENT_TIMESTAMP AT TIME ZONE 'UTC'"

    fuzz_sql = "CAST(%s AS interval)" % sqlvalues(fuzz)
    clause = "date_created BETWEEN (%s - %s) AND (%s + %s)" % (
        from_sql, fuzz_sql, until_sql, fuzz_sql)

    return clause


def get_table_stats(cur, options):
    params = {'where': get_where_clause(options)}
    tablestats_query = dedent("""\
        SELECT
            Earliest.date_created AS date_start,
            Latest.date_created AS date_end,
            Latest.schemaname,
            Latest.relname,
            Latest.seq_scan - Earliest.seq_scan AS seq_scan,
            Latest.seq_tup_read - Earliest.seq_tup_read AS seq_tup_read,
            Latest.idx_scan - Earliest.idx_scan AS idx_scan,
            Latest.idx_tup_fetch - Earliest.idx_tup_fetch AS idx_tup_fetch,
            Latest.n_tup_ins - Earliest.n_tup_ins AS n_tup_ins,
            Latest.n_tup_upd - Earliest.n_tup_upd AS n_tup_upd,
            Latest.n_tup_del - Earliest.n_tup_del AS n_tup_del,
            Latest.n_tup_hot_upd - Earliest.n_tup_hot_upd AS n_tup_hot_upd,
            Latest.n_live_tup,
            Latest.n_dead_tup,
            Latest.last_vacuum,
            Latest.last_autovacuum,
            Latest.last_analyze,
            Latest.last_autoanalyze
        FROM
            DatabaseTableStats AS Earliest,
            DatabaseTableStats AS Latest
        WHERE
            Earliest.date_created = (
                SELECT min(date_created) FROM DatabaseTableStats
                WHERE %(where)s)
            AND Latest.date_created = (
                SELECT max(date_created) FROM DatabaseTableStats
                WHERE %(where)s)
            AND Earliest.schemaname = Latest.schemaname
            AND Earliest.relname = Latest.relname
        """ % params)
    cur.execute(tablestats_query)

    # description[0] is the column name, per PEP-0249
    fields = [description[0] for description in cur.description]
    tables = set()
    for row in cur.fetchall():
        table = Table()
        for index in range(len(fields)):
            setattr(table, fields[index], row[index])
        table.total_tup_read = table.seq_tup_read + table.idx_tup_fetch
        table.total_tup_written = (
            table.n_tup_ins + table.n_tup_upd + table.n_tup_del)
        tables.add(table)

    return tables


def get_cpu_stats(cur, options):
    # This query calculates the averate cpu utilization from the
    # samples. It assumes samples are taken at regular intervals over
    # the period.
    # Note that we have to use SUM()/COUNT() instead of AVG() as
    # database users not connected when the sample was taken are not
    # recorded - we want the average utilization over the time period,
    # not the subset of the time period the user was actually connected.
    params = {'where': get_where_clause(options)}
    query = dedent("""\
        SELECT (
            CAST(SUM(cpu) AS float) / (
                SELECT COUNT(DISTINCT date_created) FROM DatabaseCpuStats
                WHERE %(where)s
            )) AS avg_cpu, username
        FROM DatabaseCpuStats
        WHERE %(where)s
        GROUP BY username
        """ % params)
    cur.execute(query)
    cpu_stats = set(cur.fetchall())

    # Fold edge into lpnet, as they are now running the same code.
    # This is a temporary hack until we drop edge entirely. See
    # Bug #667883 for details.
    lpnet_avg_cpu = 0.0
    edge_avg_cpu = 0.0
    for stats_tuple in list(cpu_stats):
        avg_cpu, username = stats_tuple
        if username == 'lpnet':
            lpnet_avg_cpu = avg_cpu
            cpu_stats.discard(stats_tuple)
        elif username == 'edge':
            edge_avg_cpu = avg_cpu
            cpu_stats.discard(stats_tuple)
    cpu_stats.add((lpnet_avg_cpu + edge_avg_cpu, 'lpnet'))

    return cpu_stats


def get_bloat_stats(cur, options, kind):
    # Return information on bloated tables and indexes, as of the end of
    # the requested time period.
    params = {
        # We only collect these statistics daily, so add some fuzz
        # to ensure bloat information ends up on the daily reports;
        # we cannot guarantee the disk utilization statistics occur
        # exactly 24 hours apart. Our most recent snapshot could be 1
        # day ago, give or take a few hours.
        'where': get_where_clause(options, fuzz='1 day 6 hours'),
        'bloat': options.bloat,
        'min_bloat': options.min_bloat,
        'kind': kind,
        }
    query = dedent("""
        SELECT * FROM (
            SELECT DISTINCT
                namespace,
                name,
                sub_namespace,
                sub_name,
                count(*) OVER t AS num_samples,
                last_value(table_len) OVER t AS table_len,
                pg_size_pretty(last_value(table_len) OVER t) AS table_size,
                last_value(dead_tuple_len + free_space) OVER t AS bloat_len,
                pg_size_pretty(last_value(dead_tuple_len + free_space) OVER t)
                    AS bloat_size,
                first_value(dead_tuple_percent + free_percent) OVER t
                    AS start_bloat_percent,
                last_value(dead_tuple_percent + free_percent) OVER t
                    AS end_bloat_percent,
                (last_value(dead_tuple_percent + free_percent) OVER t
                    - first_value(dead_tuple_percent + free_percent) OVER t
                    ) AS delta_bloat_percent,
                (last_value(table_len) OVER t
                    - first_value(table_len) OVER t) AS delta_bloat_len,
                pg_size_pretty(
                    last_value(table_len) OVER t
                    - first_value(table_len) OVER t) AS delta_bloat_size
            FROM DatabaseDiskUtilization
            WHERE
                %(where)s
                AND kind = %%(kind)s
            WINDOW t AS (
                PARTITION BY sort ORDER BY date_created
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            ) AS whatever
        WHERE
            table_len >= %(min_bloat)s
            AND end_bloat_percent >= %(bloat)s
        ORDER BY bloat_len DESC
        """ % params)
    cur.execute(query, params)
    bloat_stats = named_fetchall(cur)
    return list(bloat_stats)


def main():
    parser = LPOptionParser()
    db_options(parser)
    parser.add_option(
        "-f", "--from", dest="from_ts", type=datetime,
        default=None, metavar="TIMESTAMP",
        help="Use statistics collected since TIMESTAMP.")
    parser.add_option(
        "-u", "--until", dest="until_ts", type=datetime,
        default=None, metavar="TIMESTAMP",
        help="Use statistics collected up until TIMESTAMP.")
    parser.add_option(
        "-i", "--interval", dest="interval", type=str,
        default=None, metavar="INTERVAL",
        help=(
            "Use statistics collected over the last INTERVAL period. "
            "INTERVAL is a string parsable by PostgreSQL "
            "such as '5 minutes'."))
    parser.add_option(
        "-n", "--limit", dest="limit", type=int,
        default=15, metavar="NUM",
        help="Display the top NUM items in each category.")
    parser.add_option(
        "-b", "--bloat", dest="bloat", type=float,
        default=40, metavar="BLOAT",
        help="Display tables and indexes bloated by more than BLOAT%.")
    parser.add_option(
        "--min-bloat", dest="min_bloat", type=int,
        default=10000000, metavar="BLOAT",
        help="Don't report tables bloated less than BLOAT bytes.")
    parser.set_defaults(dbuser="database_stats_report")
    options, args = parser.parse_args()

    if options.from_ts and options.until_ts and options.interval:
        parser.error(
            "Only two of --from, --until and --interval may be specified.")

    con = connect()
    cur = con.cursor()

    tables = list(get_table_stats(cur, options))
    if len(tables) == 0:
        parser.error("No statistics available in that time range.")
    arbitrary_table = tables[0]
    interval = arbitrary_table.date_end - arbitrary_table.date_start
    per_second = float(interval.days * 24 * 60 * 60 + interval.seconds)
    if per_second == 0:
        parser.error("Only one sample in that time range.")

    user_cpu = get_cpu_stats(cur, options)
    print "== Most Active Users =="
    print
    for cpu, username in sorted(user_cpu, reverse=True)[:options.limit]:
        print "%40s || %10.2f%% CPU" % (username, float(cpu) / 10)

    print
    print "== Most Written Tables =="
    print
    tables_sort = [
        'total_tup_written', 'n_tup_upd', 'n_tup_ins', 'n_tup_del', 'relname']
    most_written_tables = sorted(
        tables, key=attrgetter(*tables_sort), reverse=True)
    for table in most_written_tables[:options.limit]:
        print "%40s || %10.2f tuples/sec" % (
            table.relname, table.total_tup_written / per_second)

    print
    print "== Most Read Tables =="
    print
    # These match the pg_user_table_stats view. schemaname is the
    # namespace (normally 'public'), relname is the table (relation)
    # name. total_tup_red is the total number of rows read.
    # idx_tup_fetch is the number of rows looked up using an index.
    tables_sort = ['total_tup_read', 'idx_tup_fetch', 'schemaname', 'relname']
    most_read_tables = sorted(
        tables, key=attrgetter(*tables_sort), reverse=True)
    for table in most_read_tables[:options.limit]:
        print "%40s || %10.2f tuples/sec" % (
            table.relname, table.total_tup_read / per_second)

    table_bloat_stats = get_bloat_stats(cur, options, 'r')

    if not table_bloat_stats:
        print
        print "(There is no bloat information available in this time range.)"

    else:
        print
        print "== Most Bloated Tables =="
        print
        for bloated_table in table_bloat_stats[:options.limit]:
            print "%40s || %2d%% || %s of %s" % (
                bloated_table.name,
                bloated_table.end_bloat_percent,
                bloated_table.bloat_size,
                bloated_table.table_size)

        index_bloat_stats = get_bloat_stats(cur, options, 'i')

        print
        print "== Most Bloated Indexes =="
        print
        for bloated_index in index_bloat_stats[:options.limit]:
            print "%65s || %2d%% || %s of %s" % (
                bloated_index.sub_name,
                bloated_index.end_bloat_percent,
                bloated_index.bloat_size,
                bloated_index.table_size)

        # Order bloat delta report by size of bloat increase.
        # We might want to change this to percentage bloat increase.
        bloating_sort_key = lambda x: x.delta_bloat_len

        table_bloating_stats = sorted(
            table_bloat_stats, key=bloating_sort_key, reverse=True)

        if table_bloating_stats[0].num_samples <= 1:
            print
            print fill(dedent("""\
                (There are not enough samples in this time range to display
                bloat change statistics)
                """))
        else:
            print
            print "== Most Bloating Tables =="
            print

            for bloated_table in table_bloating_stats[:options.limit]:
                # Bloat decreases are uninteresting, and would need to be in
                # a separate table sorted in reverse anyway.
                if bloated_table.delta_bloat_percent > 0:
                    print "%40s || +%4.2f%% || +%s" % (
                        bloated_table.name,
                        bloated_table.delta_bloat_percent,
                        bloated_table.delta_bloat_size)

            index_bloating_stats = sorted(
                index_bloat_stats, key=bloating_sort_key, reverse=True)

            print
            print "== Most Bloating Indexes =="
            print
            for bloated_index in index_bloating_stats[:options.limit]:
                # Bloat decreases are uninteresting, and would need to be in
                # a separate table sorted in reverse anyway.
                if bloated_index.delta_bloat_percent > 0:
                    print "%65s || +%4.2f%% || +%s" % (
                        bloated_index.sub_name,
                        bloated_index.delta_bloat_percent,
                        bloated_index.delta_bloat_size)


if __name__ == '__main__':
    main()
