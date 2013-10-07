#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Rebuild the full text indexes in a more friendly fashion, enabling this to
be done without downtime.
"""
__metaclass__ = type

import _pythonpath

import psycopg

from fti import ALL_FTI


def main():
    con = psycopg.connect("dbname=launchpad_prod user=postgres")
    con.set_isolation_level(0) # autocommit
    cur = con.cursor()

    for table, ignored in ALL_FTI:
        print 'Doing %(table)s' % vars(),
        cur.execute("SELECT id FROM %(table)s" % vars())
        ids = [row[0] for row in cur.fetchall()]
        for id in ids:
            cur.execute(
                    "UPDATE %(table)s SET fti=NULL WHERE id=%(id)s" % vars()
                    )
            if id % 100 == 0:
                print '.',
        print

if __name__ == '__main__':
    main()
