# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Convert the tuples returned by Cursor.fetchall() into namedtuples."""

__metaclass__ = type
__all__ = []

from collections import namedtuple


def named_fetchall(cur):
    row_type = namedtuple(
        'DatabaseRow',
        (description[0] for description in cur.description))
    for row in cur.fetchall():
        yield row_type(*row)
