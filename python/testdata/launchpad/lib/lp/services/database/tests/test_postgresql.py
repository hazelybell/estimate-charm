# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite

from lp.testing.layers import BaseLayer
from lp.testing.pgsql import PgTestSetup


def setUp(test):

    # Build a fresh, empty database and connect
    test._db_fixture = PgTestSetup()
    test._db_fixture.setUp()
    con = test._db_fixture.connect()

    # Create a test schema demonstrating the edge cases
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE A (
            aid     serial PRIMARY KEY,
            selfref integer CONSTRAINT a_selfref_fk REFERENCES A(aid)
            )
        """)
    cur.execute("""
        CREATE TABLE B (
            bid integer PRIMARY KEY,
            aid integer UNIQUE CONSTRAINT b_aid_fk REFERENCES A(aid)
                ON DELETE CASCADE ON UPDATE CASCADE
            )
        """)
    cur.execute("""
        CREATE TABLE C (
            cid integer PRIMARY KEY,
            aid integer CONSTRAINT c_aid_fk REFERENCES B(aid),
            bid integer CONSTRAINT c_bid_fk REFERENCES B(bid),
            CONSTRAINT c_aid_bid_key UNIQUE (aid, bid)
            )
        """)
    cur.execute("""
        CREATE TABLE D (
            did integer PRIMARY KEY,
            aid integer UNIQUE CONSTRAINT d_aid_fk REFERENCES B(aid),
            bid integer CONSTRAINT d_bid_fk REFERENCES B(bid),
            CONSTRAINT d_aid_bid_key UNIQUE (aid, bid)
            )
        """)
    cur.execute("CREATE SEQUENCE standalone")
    con.commit()

    # Store the connection and a cursor for the tests to use
    cur = con.cursor()
    test.globs['con'] = con
    test.globs['cur'] = cur

def tearDown(test):
    test.globs['con'].close()
    test._db_fixture.tearDown()
    del test._db_fixture

def test_suite():
    suite = DocTestSuite(
            "lp.services.database.postgresql",
            setUp=setUp, tearDown=tearDown
            )
    suite.layer = BaseLayer
    return suite

