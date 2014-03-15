#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script to sort SQL dumps.

This script reads a series of SQL statements on standard input, and prints
them out, possibly in a different order, on standard output.

When we dump data from the database, we do it in the form of SQL statements.
Most of these statements are INSERTs. We keep a dump in this form in revision
control for use as sample data.

The problem is that the statements are not dumped in a consistent order. This
means that it is much more likely for conflicts to occur when more than one
person works on the sample data at the same time. It also means the conflicts
are harder to resolve when they happen.

This script fixes the problem by sorting INSERT statements by the numeric
value of the first column. This works because the first column is the numeric
id of the row being inserted. Statements are sorted in blocks; i.e. contiguous
groups of statements separated by empty lines. This works because the dumps
happen by table, with one block of statements for each table.
"""

__metaclass__ = type

import _pythonpath

import sys

from lp.services.database.sort_sql import (
    Parser,
    print_lines_sorted,
    )


def main(argv):
    if len(argv) > 1:
        input = open(argv[1])
    else:
        input = sys.stdin

    parser = Parser()

    for line in input:
        parser.feed(line)

    print_lines_sorted(sys.stdout, parser.lines)

    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))

