#!/usr/bin/env python

# Copyright (C) 2014  Eddie Antonio Santos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.



"""
Parse token formats.
"""

import more_itertools


# This is pretty gross.
def generate_parsed_tokens(token_str):
    """
    Generate parsed tokens.
    """
    char_stream = more_itertools.peekable(token_str)

    token_text = ''
    token_category = ''
    bucket = 'text'

    while char_stream:
        char = next(char_stream)
        next_char = char_stream.peek(None)
        if char == '\\' and next_char:
            # It's an escaped char; add it to the set.
            token_text += next_char
            next(char_stream)
        elif char == ':' and next_char:
            bucket = 'category'
        elif char == '/' and next_char:
            # We have completed a token!
            yield (token_category, token_text, [], [], token_text)
            # Reset everything.
            bucket = 'text'
            token_text = ''
            token_category = ''
        else:
            # We can simply add the character to the string.
            if bucket == 'text':
                token_text += char
            else:
                token_category += char

    if token_text or token_category:
        yield (token_category, token_text, [], [], token_text)


def parse_tokens(token_str):
    r"""
    Parses a token string.

    >>> ex1 = "for/(/int/i/;"
    >>> ans1 = parse_tokens(ex1)
    >>> ans1[0]
    ('', 'for', [], [], 'for')
    >>> ans1[-1]
    ('', ';', [], [], ';')

    >>> ex2 = r'for:NAME/i:NAME/in:NAME/range:NAME/(:OP/10:NUMBER/):OP/\::OP'
    >>> ans2 = parse_tokens(ex2)
    >>> len(ans2)
    8
    >>> ans2[0]
    ('NAME', 'for', [], [], 'for')
    >>> ans2[-1]
    ('OP', ':', [], [], ':')

    >>> parse_tokens(r'1/\//2')
    [('', '1', [], [], '1'), ('', '/', [], [], '/'), ('', '2', [], [], '2')]

    Edge cases:

    >>> parse_tokens('/')
    [('', '/', [], [], '/')]
    >>> parse_tokens(r'\::OP')
    [('OP', ':', [], [], ':')]
    >>> parse_tokens(':')
    [('', ':', [], [], ':')]
    >>> parse_tokens('\\')
    [('', '\\', [], [], '\\')]

    """

    return list(generate_parsed_tokens(token_str))
