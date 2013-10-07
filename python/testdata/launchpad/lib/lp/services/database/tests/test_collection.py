# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `Collection`."""

__metaclass__ = type

from storm.locals import (
    Int,
    Storm,
    )

from lp.registry.model.person import Person
from lp.services.database.collection import Collection
from lp.services.database.interfaces import IStore
from lp.testing import TestCaseWithFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessDatabaseLayer


class FakeStore:
    find = FakeMethod(result=[])

    def using(self, *args):
        return self


def make_table(range_start, range_end, table_name=None):
    """Create a temporary table and a storm class for it."""
    assert range_start < range_end, "Invalid range."
    if table_name is None:
        table_name = "TestTable"
    IStore(Person).execute("""
       CREATE TEMP TABLE %s AS
       SELECT generate_series AS id
       FROM generate_series(%d, %d)
       """ % (table_name, range_start, range_end - 1))

    class TestTable(Storm):
        """A test class/table generated on the fly for testing purposes."""
        __storm_table__ = table_name
        id = Int(primary=True)

        def __init__(self, id):
            self.id = id

        def __eq__(self, other):
            return self.id == other.id

    return TestTable


def get_ids(testtable_objects):
    """Helper to unpack ids from a sequence of TestTable objects."""
    return [obj.id for obj in testtable_objects]


class CollectionTest(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_make_table(self):
        TestTable = make_table(1, 5)
        result = IStore(Person).find(TestTable).order_by(TestTable.id)
        self.assertEqual(range(1, 5), get_ids(result))

    def test_select_one(self):
        TestTable = make_table(1, 5)
        collection = Collection(TestTable.id == 1, tables=TestTable)
        result = collection.select(TestTable)
        self.assertEqual([1], get_ids(result))

    def test_select_all(self):
        TestTable = make_table(1, 3)
        collection = Collection(tables=TestTable)
        result = collection.select(TestTable)
        self.assertContentEqual([1, 2], get_ids(result))

    def test_select_condition(self):
        TestTable = make_table(1, 5)
        collection = Collection(TestTable.id > 2, tables=TestTable)
        result = collection.select(TestTable)
        self.assertContentEqual([3, 4], get_ids(result))

    def test_select_conditions(self):
        TestTable = make_table(1, 5)
        collection = Collection(
            TestTable.id > 2, TestTable.id < 4, tables=TestTable)
        result = collection.select(TestTable)
        self.assertContentEqual([3], get_ids(result))

    def test_select_column(self):
        TestTable = make_table(1, 3)
        collection = Collection(tables=TestTable)
        result = collection.select(TestTable.id)
        self.assertContentEqual([1, 2], list(result))

    def test_copy_collection(self):
        TestTable = make_table(1, 3)
        collection = Collection(tables=TestTable)
        copied_collection = Collection(collection)
        result = copied_collection.select(TestTable)
        self.assertContentEqual([1, 2], get_ids(result))

    def test_restrict_collection(self):
        TestTable = make_table(1, 3)
        collection = Collection(tables=TestTable)
        copied_collection = Collection(collection, TestTable.id < 2)
        result = copied_collection.select(TestTable)
        self.assertContentEqual([1], get_ids(result))

    def test_add_tables(self):
        # The list of tables to select from carries across copies.
        TestTable1 = make_table(1, 2, 'TestTable1')
        TestTable2 = make_table(2, 3, 'TestTable2')
        collection = Collection(tables=TestTable1)
        collection = Collection(collection, tables=TestTable2)
        result = collection.select(TestTable1.id, TestTable2.id)
        self.assertEqual([(1, 2)], list(result))

    def test_add_tables_and_conditions(self):
        TestTable1 = make_table(1, 2, 'TestTable1')
        TestTable2 = make_table(2, 3, 'TestTable2')
        collection = Collection(TestTable1.id == 1, tables=TestTable1)
        collection = Collection(
            collection, TestTable2.id == 2, tables=TestTable2)
        result = collection.select(TestTable1.id, TestTable2.id)
        self.assertEqual([(1, 2)], list(result))

    def test_select_join(self):
        TestTable1 = make_table(1, 2, 'TestTable1')
        TestTable2 = make_table(2, 3, 'TestTable2')
        collection = Collection(tables=(TestTable1, TestTable2))
        result = collection.select(TestTable1, TestTable2)
        self.assertEqual(
            [(TestTable1(id=1), TestTable2(id=2))], list(result))

    def test_select_join_column(self):
        TestTable1 = make_table(1, 2, 'TestTable1')
        TestTable2 = make_table(2, 3, 'TestTable2')
        collection = Collection(tables=(TestTable1, TestTable2))
        result = collection.select(TestTable1.id, TestTable2.id)
        self.assertEqual([(1, 2)], list(result))

    def test_select_partial_join(self):
        TestTable1 = make_table(1, 2, 'TestTable1')
        TestTable2 = make_table(2, 3, 'TestTable2')
        collection = Collection(
            TestTable2.id == TestTable1.id + 1,
            tables=(TestTable1, TestTable2))
        result = collection.select(TestTable1.id)
        self.assertEqual([1], list(result))

    def test_joinInner(self):
        TestTable1 = make_table(1, 3, 'TestTable1')
        TestTable2 = make_table(2, 4, 'TestTable2')

        # Add a join table to the collection.
        collection = Collection(tables=TestTable1).joinInner(
            TestTable2, TestTable2.id == TestTable1.id)
        result = collection.select(TestTable1.id, TestTable2.id)
        self.assertContentEqual([(2, 2)], list(result))

    def test_joinOuter(self):
        TestTable1 = make_table(1, 3, 'TestTable1')
        TestTable2 = make_table(2, 4, 'TestTable2')

        # Add an outer-join table to the collection.
        collection = Collection(tables=TestTable1).joinOuter(
            TestTable2, TestTable2.id == TestTable1.id)
        result = collection.select(TestTable1.id, TestTable2.id)
        self.assertContentEqual([(1, None), (2, 2)], list(result))

    def test_select_store(self):
        TestTable = make_table(1, 2)
        collection = Collection(tables=TestTable)

        store = FakeStore()
        self.assertNotEqual(store, collection.store)

        collection_with_store = collection.use(store)
        self.assertEqual(store, collection_with_store.store)

        self.assertEqual([], collection_with_store.select(TestTable))
