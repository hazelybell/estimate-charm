# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for read-only users."""

__metaclass__ = type

import unittest

import psycopg2

from lp.services.database.sqlbase import cursor
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class RoUserTestCase(unittest.TestCase):
    """Test that the read-only PostgreSQL user actually has read access"""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        switch_dbuser('ro')

    def test(self):
        """Test that read-only users cannot make changes to the database."""
        # Only one uncancelled, possibly approved unshipped order
        # per user.
        cur = cursor()

        # SELECTs should pass
        cur.execute("SELECT * FROM Person")

        # Except on sequences
        cur.execute("SAVEPOINT attempt")
        self.failUnlessRaises(
                psycopg2.Error, cur.execute, "SELECT nextval('person_id_seq')"
                )
        cur.execute("ROLLBACK TO SAVEPOINT attempt")

        # UPDATES should fail
        cur.execute("SAVEPOINT attempt")
        self.failUnlessRaises(
                psycopg2.Error, cur.execute, "UPDATE Person SET password=NULL"
                )
        cur.execute("ROLLBACK TO SAVEPOINT attempt")

        # DELETES should fail.
        # We need to use a table with no FK references to it
        cur.execute("SAVEPOINT attempt")
        self.failUnlessRaises(
                psycopg2.Error, cur.execute, "DELETE FROM WikiName"
                )
        cur.execute("ROLLBACK TO SAVEPOINT attempt")
