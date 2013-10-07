# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests that the PillarName materialized view is being maintained correctly.
"""

__metaclass__ = type

import unittest

from lp.services.database.sqlbase import cursor
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class PillarNameTriggersTestCase(unittest.TestCase):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        switch_dbuser('testadmin')

    def testDistributionTable(self):
        cur = cursor()

        # Ensure our sample data is valid and that each Distribution.name
        # has a corresponding entry in PillarName.name
        cur.execute("""
            SELECT COUNT(*)
            FROM Distribution FULL OUTER JOIN PillarName
                ON Distribution.id = PillarName.distribution
            WHERE Distribution.name != PillarName.name
            """)
        self.failUnlessEqual(cur.fetchone()[0], 0)

        def is_in_sync(name):
            cur.execute("""
                SELECT COUNT(*)
                FROM Distribution, PillarName
                WHERE Distribution.id = PillarName.distribution
                    AND Distribution.name = PillarName.name
                    AND PillarName.product IS NULL
                    AND PillarName.project IS NULL
                    AND Distribution.name = %(name)s
                """, dict(name=name))
            return cur.fetchone()[0] == 1

        # Inserting a new Distribution will populate PillarName
        cur.execute("""
            INSERT INTO Distribution (
                name, description, domainname, owner, registrant,
                displayname, summary, title, members, mirror_admin
                )
                VALUES (
                    'whatever', 'whatever', 'whatever', 1, 1,
                    'whatever', 'whatever', 'whatever', 1, 1
                    )
            """)
        self.failUnless(is_in_sync('whatever'))

        # Updating the Distribution.name will propogate changes to PillarName
        cur.execute("""
            UPDATE Distribution SET name='whatever2' where name='whatever'
            """)
        self.failUnless(is_in_sync('whatever2'))

        # Updating other fields won't do any harm.
        cur.execute("""
            UPDATE Distribution SET description='whatever2'
            WHERE name='whatever2'
            """)
        self.failUnless(is_in_sync('whatever2'))

        # Deleting a Distribution removes the corresponding entry in
        # PillarName
        cur.execute("DELETE FROM Distribution WHERE name='whatever2'")
        cur.execute("SELECT COUNT(*) FROM PillarName WHERE name='whatever2'")
        self.failUnlessEqual(cur.fetchone()[0], 0)

    def testProductTable(self):
        cur = cursor()

        # Ensure our sample data is valid and that each Product.name
        # has a corresponding entry in PillarName.name
        cur.execute("""
            SELECT COUNT(*)
            FROM Product FULL OUTER JOIN PillarName
                ON Product.id = PillarName.product
            WHERE Product.name != PillarName.name
            """)
        self.failUnlessEqual(cur.fetchone()[0], 0)

        def is_in_sync(name):
            cur.execute("""
                SELECT COUNT(*)
                FROM Product, PillarName
                WHERE Product.id = PillarName.product
                    AND Product.name = PillarName.name
                    AND PillarName.distribution IS NULL
                    AND PillarName.project IS NULL
                    AND Product.name = %(name)s
                """, dict(name=name))
            return cur.fetchone()[0] == 1

        # Inserting a new Product will populate PillarName
        cur.execute("""
            INSERT INTO Product (
                owner, registrant, name, displayname, title, summary)
            VALUES (
                1, 1, 'whatever', 'whatever', 'whatever', 'whatever'
                )
            """)
        self.failUnless(is_in_sync('whatever'))

        # Updating the Product.name will propogate changes to PillarName
        cur.execute("""
            UPDATE Product SET name='whatever2' where name='whatever'
            """)
        self.failUnless(is_in_sync('whatever2'))

        # Updating other fields won't do any harm.
        cur.execute("""
            UPDATE Product SET summary='whatever2'
            WHERE name='whatever2'
            """)
        self.failUnless(is_in_sync('whatever2'))

        # Deleting a Product removes the corresponding entry in PillarName
        cur.execute("DELETE FROM Product WHERE name='whatever2'")
        cur.execute("SELECT COUNT(*) FROM PillarName WHERE name='whatever2'")
        self.failUnlessEqual(cur.fetchone()[0], 0)

    def testProjectTable(self):
        cur = cursor()

        # Ensure our sample data is valid and that each Project.name
        # has a corresponding entry in PillarName.name
        cur.execute("""
            SELECT COUNT(*)
            FROM Project FULL OUTER JOIN PillarName
                ON Project.id = PillarName.project
            WHERE Project.name != PillarName.name
            """)
        self.failUnlessEqual(cur.fetchone()[0], 0)

        def is_in_sync(name):
            cur.execute("""
                SELECT COUNT(*)
                FROM Project, PillarName
                WHERE Project.id = PillarName.project
                    AND Project.name = PillarName.name
                    AND PillarName.product IS NULL
                    AND PillarName.distribution IS NULL
                    AND Project.name = %(name)s
                """, dict(name=name))
            return cur.fetchone()[0] == 1

        # Inserting a new ProjectGroup will populate PillarName
        cur.execute("""
            INSERT INTO Project (
                name, owner, registrant, displayname, title, summary,
                description
                )
                VALUES (
                    'whatever', 1, 1, 'whatever', 'whatever',
                    'whatever', 'whatever'
                    )
            """)
        self.failUnless(is_in_sync('whatever'))

        # Updating the ProjectGroup.name will propogate changes to PillarName
        cur.execute("""
            UPDATE Project SET name='whatever2' where name='whatever'
            """)
        self.failUnless(is_in_sync('whatever2'))

        # Updating other fields won't do any harm.
        cur.execute("""
            UPDATE Project SET description='whatever2'
            WHERE name='whatever2'
            """)
        self.failUnless(is_in_sync('whatever2'))

        # Deleting a ProjectGroup removes the corresponding entry in
        # PillarName.
        cur.execute("DELETE FROM Project WHERE name='whatever2'")
        cur.execute("SELECT COUNT(*) FROM PillarName WHERE name='whatever2'")
        self.failUnlessEqual(cur.fetchone()[0], 0)
