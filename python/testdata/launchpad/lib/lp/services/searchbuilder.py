# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for creating searches with *Set.search methods.

See lib/canonical/launchpad/doc/bugtask.txt for example usages of
searchbuilder helpers.
"""

__metaclass__ = type

# constants for use in search criteria
NULL = "NULL"

class all:
    def __init__(self, *query_values):
        self.query_values = query_values

class any:
    def __init__(self, *query_values):
        self.query_values = query_values

class not_equals:
    def __init__(self, value):
        self.value = value

class greater_than:
    """Greater than value."""

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return "greater_than(%r)" % (self.value,)
