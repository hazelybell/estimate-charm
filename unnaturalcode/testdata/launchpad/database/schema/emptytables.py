#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""List empty database tables."""

__metaclass__ = type

import _pythonpath

from optparse import OptionParser

from fti import quote_identifier
from lp.services.database.sqlbase import connect
from lp.services.scripts import db_options


def main(options):
    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT relname FROM pg_class,pg_namespace
        WHERE pg_class.relnamespace = pg_namespace.oid
            AND pg_namespace.nspname='public'
            AND pg_class.relkind = 'r'
        ORDER BY relname
        """)
    for table in (row[0] for row in cur.fetchall()):
        cur.execute(
                "SELECT TRUE FROM public.%s LIMIT 1" % quote_identifier(table)
                )
        if cur.fetchone() is None:
            print table


if __name__ == '__main__':
    parser = OptionParser()
    db_options(parser)
    (options, args) = parser.parse_args()

    main(options)
