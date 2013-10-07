# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Sort SQL dumps.

This library provides functions for the script sort_sql.py, which resides in
database/schema/.
"""

__metaclass__ = type

import re


class Parser:
    r"""Parse an SQL dump into logical lines.

    >>> p = Parser()
    >>> p.feed("UPDATE foo SET bar='baz';\n")
    >>> p.feed("\n")
    >>> p.feed("INSERT INTO foo (id, x) VALUES (1, 23);\n")
    >>> p.feed("INSERT INTO foo (id, x) VALUES (2, 34);\n")
    >>> for line in p.lines:
    ...     print repr(line)
    (None, "UPDATE foo SET bar='baz';")
    (None, '')
    (1, 'INSERT INTO foo (id, x) VALUES (1, 23);')
    (2, 'INSERT INTO foo (id, x) VALUES (2, 34);')
    """

    def __init__(self):
        self.lines = []
        self.buffer = ''
        self.line = ''

    def parse_quoted_string(self, string):
        """Parse strings enclosed in single quote marks.

        This takes a string of the form "'foo' ..." and returns a pair
        containing the first quoted string and the rest of the string. The
        escape sequence "''" is recognised in the middle of a quoted string as
        representing a single quote, but is not unescaped.

        ValueError is raised if there is no quoted string at the beginning of
        the string.

        >>> p = Parser()
        >>> p.parse_quoted_string("'foo'")
        ("'foo'", '')
        >>> p.parse_quoted_string("'foo' bar")
        ("'foo'", ' bar')
        >>> p.parse_quoted_string("'foo '' bar'")
        ("'foo '' bar'", '')
        >>> p.parse_quoted_string("foo 'bar'")
        Traceback (most recent call last):
        ...
        ValueError: Couldn't parse quoted string
        """

        quoted_pattern = re.compile('''
            ' (?: [^'] | '' )* '
            ''', re.X | re.S)

        match = quoted_pattern.match(string)

        if match:
            quoted_length = len(match.group(0))
            return string[:quoted_length], string[quoted_length:]
        else:
            raise ValueError("Couldn't parse quoted string")

    def is_complete_insert_statement(self, statement):
        """Check whether a string looks like a complete SQL INSERT
        statement."""

        while statement:
            if statement == ');\n':
                return True
            elif statement[0] == "'":
                string, statement = self.parse_quoted_string(statement)
            else:
                statement = statement[1:]

        return False

    def parse_line(self, line):
        r"""Parse a single line of SQL.

        >>> p = Parser()

        Something that's not an INSERT.

        >>> p.parse_line('''UPDATE foo SET bar = 42;\n''')
        (None, 'UPDATE foo SET bar = 42;\n')

        A simple INSERT.

        >>> p.parse_line('''INSERT INTO foo (id, x) VALUES (2, 'foo');\n''')
        (2, "INSERT INTO foo (id, x) VALUES (2, 'foo');\n")

        Something trickier: multiple lines, and a ');' in the middle.

        >>> p.parse_line('''INSERT INTO foo (id, x) VALUES (3, 'b',
        ... 'b
        ... b);
        ... b');
        ... ''')
        (3, "INSERT INTO foo (id, x) VALUES (3, 'b',\n'b\nb);\nb');\n")
        """

        if not line.startswith('INSERT '):
            return (None, line)

        if not self.is_complete_insert_statement(line):
            raise ValueError("Incomplete line")

        insert_pattern = re.compile('''
            ^INSERT \s+ INTO \s+ \S+ \s+ \([^)]+\) \s+ VALUES \s+ \((\d+)
            ''', re.X)
        match = insert_pattern.match(line)

        if match:
            return int(match.group(1)), line
        else:
            return line, line

    def feed(self, s):
        """Give the parser some text to parse."""

        self.buffer += s

        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            self.line += line + '\n'

            try:
                value, line = self.parse_line(self.line)
            except ValueError:
                pass
            else:
                self.lines.append((value, self.line[:-1]))
                self.line = ''


def print_lines_sorted(file, lines):
    r"""Print a set of (value, line) pairs in sorted order.

    Sorting only occurs within blocks of statements.

    >>> lines = [
    ...     (10, "INSERT INTO foo (id, x) VALUES (10, 'data');"),
    ...     (4, "INSERT INTO foo (id, x) VALUES (4, 'data\nmore\nmore');"),
    ...     (7, "INSERT INTO foo (id, x) VALUES (7, 'data');"),
    ...     (1, "INSERT INTO foo (id, x) VALUES (1, 'data');"),
    ...     (None, ""),
    ...     (2, "INSERT INTO baz (id, x) VALUES (2, 'data');"),
    ...     (1, "INSERT INTO baz (id, x) VALUES (1, 'data');"),
    ...     ]
    >>> import sys
    >>> print_lines_sorted(sys.stdout, lines)
    INSERT INTO foo (id, x) VALUES (1, 'data');
    INSERT INTO foo (id, x) VALUES (4, 'data
    more
    more');
    INSERT INTO foo (id, x) VALUES (7, 'data');
    INSERT INTO foo (id, x) VALUES (10, 'data');
    <BLANKLINE>
    INSERT INTO baz (id, x) VALUES (1, 'data');
    INSERT INTO baz (id, x) VALUES (2, 'data');

    """

    block = []

    def print_block(block):
        block.sort()

        for line in block:
            sort_value, string = line
            print >>file, string

    for line in lines:
        sort_value, string = line

        if string == '':
            if block:
                print_block(block)
                block = []

            file.write('\n')
        else:
            block.append(line)

    if block:
        print_block(block)

