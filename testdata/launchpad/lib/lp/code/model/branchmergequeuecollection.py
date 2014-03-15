# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementations of `IBranchMergeQueueCollection`."""

__metaclass__ = type
__all__ = [
    'GenericBranchMergeQueueCollection',
    ]

from zope.interface import implements

from lp.code.interfaces.branchmergequeue import (
    user_has_special_merge_queue_access,
    )
from lp.code.interfaces.branchmergequeuecollection import (
    IBranchMergeQueueCollection,
    InvalidFilter,
    )
from lp.code.interfaces.codehosting import LAUNCHPAD_SERVICES
from lp.code.model.branchmergequeue import BranchMergeQueue
from lp.services.database.interfaces import IMasterStore


class GenericBranchMergeQueueCollection:
    """See `IBranchMergeQueueCollection`."""

    implements(IBranchMergeQueueCollection)

    def __init__(self, store=None, merge_queue_filter_expressions=None,
                 tables=None, exclude_from_search=None):
        """Construct a `GenericBranchMergeQueueCollection`.

        :param store: The store to look in for merge queues. If not specified,
            use the default store.
        :param merge_queue_filter_expressions: A list of Storm expressions to
            restrict the queues in the collection. If unspecified, then
            there will be no restrictions on the result set. That is, all
            queues in the store will be in the collection.
        :param tables: A dict of Storm tables to the Join expression.  If an
            expression in merge_queue_filter_expressions refers to a table,
            then that table *must* be in this list.
        """
        self._store = store
        if merge_queue_filter_expressions is None:
            merge_queue_filter_expressions = []
        self._merge_queue_filter_expressions = merge_queue_filter_expressions
        if tables is None:
            tables = {}
        self._tables = tables
        if exclude_from_search is None:
            exclude_from_search = []
        self._exclude_from_search = exclude_from_search

    def count(self):
        return self._getCount()

    def _getCount(self):
        """See `IBranchMergeQueueCollection`."""
        return self._getMergeQueues().count()

    @property
    def store(self):
        if self._store is None:
            return IMasterStore(BranchMergeQueue)
        else:
            return self._store

    def _filterBy(self, expressions, table=None, join=None,
                  exclude_from_search=None):
        """Return a subset of this collection, filtered by 'expressions'."""
        tables = self._tables.copy()
        if table is not None:
            if join is None:
                raise InvalidFilter("Cannot specify a table without a join.")
            tables[table] = join
        if exclude_from_search is None:
            exclude_from_search = []
        if expressions is None:
            expressions = []
        return self.__class__(
            self.store,
            self._merge_queue_filter_expressions + expressions,
            tables,
            self._exclude_from_search + exclude_from_search)

    def _getMergeQueueExpressions(self):
        """Return the where expressions for this collection."""
        return self._merge_queue_filter_expressions

    def getMergeQueues(self):
        return list(self._getMergeQueues())

    def _getMergeQueues(self):
        """See `IBranchMergeQueueCollection`."""
        tables = [BranchMergeQueue] + self._tables.values()
        expressions = self._getMergeQueueExpressions()
        return self.store.using(*tables).find(BranchMergeQueue, *expressions)

    def ownedBy(self, person):
        """See `IBranchMergeQueueCollection`."""
        return self._filterBy([BranchMergeQueue.owner == person])

    def visibleByUser(self, person):
        """See `IBranchMergeQueueCollection`."""
        if (person == LAUNCHPAD_SERVICES or
            user_has_special_merge_queue_access(person)):
            return self
        return VisibleBranchMergeQueueCollection(
            person,
            self._store, None,
            self._tables, self._exclude_from_search)


class VisibleBranchMergeQueueCollection(GenericBranchMergeQueueCollection):
    """A mergequeue collection which provides queues visible by a user."""

    def __init__(self, person, store=None,
                 merge_queue_filter_expressions=None, tables=None,
                 exclude_from_search=None):
        super(VisibleBranchMergeQueueCollection, self).__init__(
            store=store,
            merge_queue_filter_expressions=merge_queue_filter_expressions,
            tables=tables,
            exclude_from_search=exclude_from_search,
        )
        self._user = person

    def _filterBy(self, expressions, table=None, join=None,
                  exclude_from_search=None):
        """Return a subset of this collection, filtered by 'expressions'."""
        tables = self._tables.copy()
        if table is not None:
            if join is None:
                raise InvalidFilter("Cannot specify a table without a join.")
            tables[table] = join
        if exclude_from_search is None:
            exclude_from_search = []
        if expressions is None:
            expressions = []
        return self.__class__(
            self._user,
            self.store,
            self._merge_queue_filter_expressions + expressions,
            tables,
            self._exclude_from_search + exclude_from_search)

    def visibleByUser(self, person):
        """See `IBranchMergeQueueCollection`."""
        if person == self._user:
            return self
        raise InvalidFilter(
            "Cannot filter for merge queues visible by user %r, already "
            "filtering for %r" % (person, self._user))

    def _getCount(self):
        """See `IBranchMergeQueueCollection`."""
        return len(self._getMergeQueues())

    def _getMergeQueues(self):
        """Return the queues visible by self._user.

        A queue is visible to a user if that user can see all the branches
        associated with the queue.
        """

        def allBranchesVisible(user, branches):
            return len([branch for branch in branches
                        if branch.visibleByUser(user)]) == branches.count()

        queues = super(
            VisibleBranchMergeQueueCollection, self)._getMergeQueues()
        return [queue for queue in queues
                if allBranchesVisible(self._user, queue.branches)]
