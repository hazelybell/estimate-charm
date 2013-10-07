#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Create a database

Like createdb, except will retry on failure.
."""

__metaclass__ = type

import sys
import time

import psycopg2


def main():
    if len(sys.argv) != 3:
        print >> sys.stderr, 'Usage: %s [template] [dbname]' % sys.argv[0]
        return 1

    template, dbname = sys.argv[1:]

    for attempt in range(0, 10):
        con = psycopg2.connect('dbname=template1')
        con.set_isolation_level(0)
        try:
            cur = con.cursor()
            cur.execute(
                    "CREATE DATABASE %s TEMPLATE = %s ENCODING = 'UTF8'" % (
                        dbname, template
                        )
                    )
        except psycopg2.Error:
            if attempt == 9:
                raise
            con.close()
            time.sleep(1)
        else:
            return 0
    return 1

if __name__ == '__main__':
    sys.exit(main())
