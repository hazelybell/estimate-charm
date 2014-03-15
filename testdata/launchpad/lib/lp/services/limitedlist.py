# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'LimitedList',
    ]

class LimitedList(list):
    """A mutable sequence that takes a limited number of elements."""

    def __new__(cls, max_length, value=None):
        return super(LimitedList, cls).__new__(cls)

    def __init__(self, max_length, value=None):
        if value is None:
            value = []
        elif len(value) > max_length:
            value = value[-max_length:]
        super(LimitedList, self).__init__(value)
        self.max_length = max_length

    def __repr__(self):
        return (
            '<LimitedList(%s, %s)>'
            % (self.max_length, super(LimitedList, self).__repr__()))

    def _ensureLength(self):
        """Ensure that the maximum length is not exceeded."""
        elements_to_drop = self.__len__() - self.max_length
        if elements_to_drop > 0:
            self.__delslice__(0, elements_to_drop)

    def __add__(self, other):
        return LimitedList(
            self.max_length, super(LimitedList, self).__add__(other))

    def __radd__(self, other):
        return LimitedList(self.max_length, other.__add__(self))

    def __iadd__(self, other):
        result = super(LimitedList, self).__iadd__(other)
        self._ensureLength()
        return result

    def __mul__(self, other):
        return LimitedList(
            self.max_length, super(LimitedList, self).__mul__(other))

    def __rmul__(self, other):
        return self.__mul__(other)

    def __imul__(self, other):
        result = super(LimitedList, self).__imul__(other)
        self._ensureLength()
        return result

    def __setslice__(self, i, j, sequence):
        result = super(LimitedList, self).__setslice__(i, j, sequence)
        self._ensureLength()
        return result

    def append(self, value):
        result = super(LimitedList, self).append(value)
        self._ensureLength()
        return result

    def extend(self, value):
        result = super(LimitedList, self).extend(value)
        self._ensureLength()
        return result

    def insert(self, position, value):
        result = super(LimitedList, self).insert(position, value)
        self._ensureLength()
        return result
