#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Report a breakdown of Librarian disk space usage."""

__metaclass__ = type
__all__ = []

import _pythonpath

from optparse import OptionParser
import sys

from lp.services.database.postgresql import listReferences
from lp.services.database.sqlbase import (
    connect,
    quoteIdentifier,
    sqlvalues,
    )
from lp.services.scripts import db_options


def main():
    parser = OptionParser()

    db_options(parser)
    parser.add_option(
        "-f", "--from", dest="from_date", default=None,
        metavar="DATE", help="Only count new files since DATE (yyyy/mm/dd)")
    parser.add_option(
        "-u", "--until", dest="until_date", default=None,
        metavar="DATE", help="Only count new files until DATE (yyyy/mm/dd)")

    options, args = parser.parse_args()
    if len(args) > 0:
        parser.error("Too many command line arguments.")

    # Handle date filters. We use LibraryFileContent.datecreated rather
    # than LibraryFileAlias.datecreated as this report is about actual
    # disk space usage. A new row in the database linking to a
    # previously existing file in the Librarian takes up no new space.
    if options.from_date is not None:
        from_date = 'AND LFC.datecreated >= %s' % sqlvalues(
            options.from_date)
    else:
        from_date = ''
    if options.until_date is not None:
        until_date = 'AND LFC.datecreated <= %s' % sqlvalues(
            options.until_date)
    else:
        until_date = ''

    con = connect()
    cur = con.cursor()

    # Collect direct references to the LibraryFileAlias table.
    references = set(
        (from_table, from_column)
        # Note that listReferences is recursive, which we don't
        # care about in this simple report. We also ignore the
        # irrelevant constraint type update and delete flags.
        for from_table, from_column, to_table, to_column, update, delete
            in listReferences(cur, 'libraryfilealias', 'id')
        if to_table == 'libraryfilealias'
        )

    totals = set()
    for referring_table, referring_column in sorted(references):
        if referring_table == 'libraryfiledownloadcount':
            continue
        quoted_referring_table = quoteIdentifier(referring_table)
        quoted_referring_column = quoteIdentifier(referring_column)
        cur.execute("""
            SELECT
                COALESCE(SUM(filesize), 0),
                pg_size_pretty(CAST(COALESCE(SUM(filesize), 0) AS bigint)),
                COUNT(*)
            FROM (
                SELECT DISTINCT ON (LFC.id) LFC.id, LFC.filesize
                FROM LibraryFileContent AS LFC, LibraryFileAlias AS LFA, %s
                WHERE LFC.id = LFA.content
                    AND LFA.id = %s.%s
                    AND (
                        LFA.expires IS NULL
                        OR LFA.expires > CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
                    %s %s
                ORDER BY LFC.id
                ) AS Whatever
            """ % (
                quoted_referring_table, quoted_referring_table,
                quoted_referring_column, from_date, until_date))
        total_bytes, formatted_size, num_files = cur.fetchone()
        totals.add((total_bytes, referring_table, formatted_size, num_files))

    for total_bytes, tab_name, formatted_size, num_files in sorted(
        totals, reverse=True):
        print '%-10s %s in %d files' % (formatted_size, tab_name, num_files)

    return 0


if __name__ == '__main__':
    sys.exit(main())
