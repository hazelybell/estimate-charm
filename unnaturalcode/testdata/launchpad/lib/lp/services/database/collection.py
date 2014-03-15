# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A generic collection of database objects."""

__metaclass__ = type
__all__ = [
    'Collection',
    ]

from storm.expr import (
    Join,
    LeftJoin,
    )

from lp.services.database.interfaces import IStore


class Collection(object):
    """An arbitrary collection of database objects.

    Works as a Storm wrapper: create a collection based on another
    collection, adding joins and select conditions to taste.

    As in any Storm query, you can select any mix of classes and
    individual columns or other Storm expressions.
    """

    # Default table for this collection that will always be included.
    # Derived collection classes can use this to say what type they are
    # a collection of.
    starting_table = None

    def __init__(self, *args, **kwargs):
        """Construct a collection, possibly based on another one.

        :param base: Optional collection that this collection is based
            on.  The new collection will inherit its configuration.
        :param conditions: Optional Storm select conditions, e.g.
            `MyClass.attribute > 2`.
        :param classes: A class, or tuple or list of classes, that
            should go into the "FROM" clause of the new collection.
            This need not include classes that are already in the
            base collection, or that are included as outer joins.
        :param store: Optional: Storm `Store` to use.
        """
        starting_tables = []

        if len(args) >= 1 and isinstance(args[0], Collection):
            # There's a base collection.
            base = args[0]
            conditions = args[1:]
        else:
            # We're starting a fresh collection.
            base = None
            conditions = args
            if self.starting_table is not None:
                starting_tables = [self.starting_table]

        self.base = base

        if base is None:
            base_conditions = (True, )
            base_tables = []
        else:
            self.store = base.store
            base_conditions = base.conditions
            base_tables = list(base.tables)

        self.store = kwargs.get('store')
        if self.store is None:
            from lp.services.librarian.model import LibraryFileAlias
            self.store = IStore(LibraryFileAlias)

        self.tables = (
            starting_tables + base_tables +
            self._parseTablesArg(kwargs.get('tables', [])))

        self.conditions = base_conditions + conditions

    def refine(self, *args, **kwargs):
        """Return a copy of self with further restrictions, tables etc."""
        cls = self.__class__
        return cls(self, *args, **kwargs)

    def _parseTablesArg(self, tables):
        """Turn tables argument into a list.

        :param tables: A class, or tuple of classes, or list of classes.
        :param return: All classes that were passed in, as a list.
        """
        if isinstance(tables, tuple):
            return list(tables)
        elif isinstance(tables, list):
            return tables
        else:
            return [tables]

    def use(self, store):
        """Return a copy of this collection that uses the given store."""
        return self.refine(store=store)

    def joinInner(self, cls, *conditions):
        """Convenience method: inner-join `cls` into the query.

        This is equivalent to creating a `Collection` based on this one
        but with `cls` and `conditions` added.
        """
        return self.refine(tables=[Join(cls, *conditions)])

    def joinOuter(self, cls, *conditions):
        """Outer-join `cls` into the query."""
        return self.refine(tables=[LeftJoin(cls, *conditions)])

    def select(self, *values):
        """Return a result set containing the requested `values`.

        If no values are requested, this selects the type of object that
        the Collection is a collection of.
        """
        if len(self.tables) == 0:
            source = self.store
        else:
            source = self.store.using(*self.tables)

        if len(values) > 1:
            # Selecting a tuple of values.  Pass it to Storm unchanged.
            pass
        elif len(values) == 1:
            # One value requested.  Unpack for convenience.
            values = values[0]
        else:
            # Select the starting table by default.
            assert self.starting_table is not None, (
                "Collection %s does not define a starting table." %
                    self.__class__.__name__)
            values = self.starting_table

        return source.find(values, *self.conditions)
