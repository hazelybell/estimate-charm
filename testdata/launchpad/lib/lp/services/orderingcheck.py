# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'OrderingCheck',
    ]


class OrderingCheck:
    """Helper class: verify that items are in an expected order.

    Use this if to verify that a series of items you are iterating over
    is in some expected order.  Any items that are not ordered the way
    you expect are reported to a customizable failure handler; it raises
    an error by default.
    """
    def __init__(self, **kwargs):
        """Define an ordering.  Parameters are as for sorted()."""
        self.ordering = kwargs
        self.last_item = None
        self.item_count = 0

    def check(self, item):
        """Verify that `item` comes after the previous item, if any.

        Call this with each of the items in the sequence as you process
        them.  If any of the items is not at its right place in the
        sequence, this will call `fail` with that item.
        """
        try:
            if self.item_count > 0:
                local_order = [self.last_item, item]
                if sorted(local_order, **self.ordering) != local_order:
                    self.fail(item)
        finally:
            self.item_count += 1

        self.last_item = item

    def fail(self, item):
        """Report that `item` is not in its proper place.

        Default action is to raise an assertion error.
        """
        raise AssertionError(
            "Unexpected ordering at item %d: %s should come before %s." % (
                self.item_count, repr(item), repr(self.last_item)))
