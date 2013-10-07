# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A collection of branche merge queues.

See `IBranchMergeQueueCollection` for more details.
"""

__metaclass__ = type
__all__ = [
    'IAllBranchMergeQueues',
    'IBranchMergeQueueCollection',
    'InvalidFilter',
    ]

from zope.interface import Interface


class InvalidFilter(Exception):
    """Raised when an `IBranchMergeQueueCollection` can't apply the filter."""


class IBranchMergeQueueCollection(Interface):
    """A collection of branch merge queues.

    An `IBranchMergeQueueCollection` is an immutable collection of branch
    merge queues. It has two kinds of methods:
    filter methods and query methods.

    Query methods get information about the contents of collection. See
    `IBranchMergeQueueCollection.count` and
    `IBranchMergeQueueCollection.getMergeQueues`.

    Implementations of this interface are not 'content classes'. That is, they
    do not correspond to a particular row in the database.

    This interface is intended for use within Launchpad, not to be exported as
    a public API.
    """

    def count():
        """The number of merge queues in this collection."""

    def getMergeQueues():
        """Return a result set of all merge queues in this collection.

        The returned result set will also join across the specified tables as
        defined by the arguments to this function.  These extra tables are
        joined specificly to allow the caller to sort on values not in the
        Branch table itself.
        """

    def ownedBy(person):
        """Restrict the collection to queues owned by 'person'."""

    def visibleByUser(person):
        """Restrict the collection to queues that 'person' is allowed to see.
        """


class IAllBranchMergeQueues(IBranchMergeQueueCollection):
    """An `IBranchMergeQueueCollection` of all branch merge queues."""
