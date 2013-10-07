#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
#
# This modules uses relative imports.
"""
Add full text indexes to the launchpad database
"""
__metaclass__ = type

import _pythonpath

from distutils.version import LooseVersion
from optparse import OptionParser
import os.path
import sys
from textwrap import dedent

import psycopg2.extensions

from lp.services.database.sqlbase import (
    connect,
    ISOLATION_LEVEL_AUTOCOMMIT,
    ISOLATION_LEVEL_READ_COMMITTED,
    quote,
    quote_identifier,
    )
from lp.services.scripts import (
    db_options,
    logger,
    logger_options,
    )


PGSQL_BASE = '/usr/share/postgresql'

# tsearch2 ranking constants:
A, B, C, D = 'ABCD'

# This data structure defines all of our full text indexes.  Each tuple in the
# top level list creates a 'fti' column in the specified table.
# The letters letters A-D assign a weight to the corresponding column.
# A is most important, and D is least important. This affects result ordering
# when you are ordering by rank.
ALL_FTI = [
    ('archive', [
            ('description', A),
            ('package_description_cache', B),
            ]),
    ('bug', [
            ('name', A),
            ('title', B),
            ('description', D),
            ]),

    ('binarypackagerelease', [
            ('summary', B),
            ('description', C),
            ]),

    ('cve', [
            ('sequence', A),
            ('description', B),
            ]),

    ('distribution', [
            ('name', A),
            ('displayname', A),
            ('title', B),
            ('summary', C),
            ('description', D),
            ]),

    ('distributionsourcepackagecache', [
            ('name', A),
            ('binpkgnames', B),
            ('binpkgsummaries', C),
            ('binpkgdescriptions', D),
            ('changelog', D),
            ]),

    ('distroseriespackagecache', [
            ('name', A),
            ('summaries', B),
            ('descriptions', C),
            ]),

    ('faq', [
            ('title', A),
            ('tags', B),
            ('content', D),
            ]),

    ('message', [
            ('subject', B),
            ]),

    ('messagechunk', [
            ('content', C),
            ]),

    ('person', [
            ('name', A),
            ('displayname', A),
            ]),

    ('product', [
            ('name', A),
            ('displayname', A),
            ('title', B),
            ('summary', C),
            ('description', D),
            ]),

    ('productreleasefile', [
            ('description', D),
            ]),

    ('project', [
            ('name', A),
            ('displayname', A),
            ('title', B),
            ('summary', C),
            ('description', D),
            ]),

    ('specification', [
            ('name', A),
            ('title', A),
            ('summary', B),
            ('whiteboard', D),
            ]),

    ('question', [
            ('title', A),
            ('description', B),
            ('whiteboard', B),
            ])
    ]


def execute(con, sql, results=False, args=None):
    sql = sql.strip()
    log.debug('* %s' % sql)
    cur = con.cursor()
    if args is None:
        cur.execute(sql)
    else:
        cur.execute(sql, args)
    if results:
        return list(cur.fetchall())
    else:
        return None


def sexecute(con, sql):
    """If we are generating a slonik script, write out the SQL to our
    SQL script. Otherwise execute on the DB.
    """
    if slonik_sql is not None:
        print >> slonik_sql, dedent(sql + ';')
    else:
        execute(con, sql)


def nullify(con):
    """Set all fti index columns to NULL"""
    for table, ignored in ALL_FTI:
        table = quote_identifier(table)
        log.info("Removing full text index data from %s", table)
        sexecute(con, "ALTER TABLE %s DISABLE TRIGGER tsvectorupdate" % table)
        sexecute(con, "UPDATE %s SET fti=NULL" % table)
        sexecute(con, "ALTER TABLE %s ENABLE TRIGGER tsvectorupdate" % table)
    sexecute(con, "DELETE FROM FtiCache")


def liverebuild(con):
    """Rebuild the data in all the fti columns against possibly live database.
    """
    # Update number of rows per transaction.
    batch_size = 50

    cur = con.cursor()
    for table, ignored in ALL_FTI:
        table = quote_identifier(table)
        cur.execute("SELECT max(id) FROM %s" % table)
        max_id = cur.fetchone()[0]
        if max_id is None:
            log.info("No data in %s - skipping", table)
            continue

        log.info("Rebuilding fti column on %s", table)
        for id in range(0, max_id, batch_size):
            try:
                query = """
                    UPDATE %s SET fti=NULL WHERE id BETWEEN %d AND %d
                    """ % (table, id + 1, id + batch_size)
                log.debug(query)
                cur.execute(query)
            except psycopg2.Error:
                # No commit - we are in autocommit mode
                log.exception('psycopg error')
                con = connect()
                con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)


def needs_refresh(con, table, columns):
    '''Return true if the index needs to be rebuilt.

    We know this by looking in our cache to see what the previous
    definitions were, and the --force command line argument
    '''
    current_columns = repr(sorted(columns))

    existing = execute(
        con, "SELECT columns FROM FtiCache WHERE tablename=%(table)s",
        results=True, args=vars()
        )
    if len(existing) == 0:
        log.debug("No fticache for %(table)s" % vars())
        sexecute(con, """
            INSERT INTO FtiCache (tablename, columns) VALUES (%s, %s)
            """ % (quote(table), quote(current_columns)))
        return True

    if not options.force:
        previous_columns = existing[0][0]
        if current_columns == previous_columns:
            log.debug("FtiCache for %(table)s still valid" % vars())
            return False
        log.debug("Cache out of date - %s != %s" % (
            current_columns, previous_columns
            ))
    sexecute(con, """
        UPDATE FtiCache SET columns = %s
        WHERE tablename = %s
        """ % (quote(current_columns), quote(table)))

    return True


def get_pgversion(con):
    rows = execute(con, r"show server_version", results=True)
    return LooseVersion(rows[0][0])


def get_tsearch2_sql_path(con):
    major, minor = get_pgversion(con).version[:2]
    path = os.path.join(
        PGSQL_BASE, '%d.%d' % (major, minor), 'contrib', 'tsearch2.sql')
    assert os.path.exists(path), '%s does not exist' % path
    return path


# Script options and arguments parsed from the command line by main()
options = None
args = None

# Logger, setup by main()
log = None

# Files for output generated for slonik(1). None if not a Slony-I install.
slonik_sql = None


def main():
    parser = OptionParser()
    parser.add_option(
            "-0", "--null", dest="null",
            action="store_true", default=False,
            help="Set all full text index column values to NULL.",
            )
    parser.add_option(
            "-l", "--live-rebuild", dest="liverebuild",
            action="store_true", default=False,
            help="Rebuild all the indexes against a live database.",
            )
    db_options(parser)
    logger_options(parser)

    global options, args
    (options, args) = parser.parse_args()

    if options.null + options.liverebuild > 1:
        parser.error("Incompatible options")

    global log
    log = logger(options)

    con = connect()

    if options.liverebuild:
        con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        liverebuild(con)
    elif options.null:
        con.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
        nullify(con)
    else:
        parser.error("Required argument not specified")

    con.commit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
