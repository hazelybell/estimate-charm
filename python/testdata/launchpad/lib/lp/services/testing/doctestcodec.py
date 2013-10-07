# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Codecs to convert Unicode strings to more human readable representations.

Defines the 'doctest' encoding. This is ASCII, with Unicode characters
represented using the standard Python \N{YEN SIGN} syntax.
"""

__metaclass__ = type
__all__ = []

import codecs
import unicodedata


def doctest_unicode_error_handler(error):
    r"""Codec error handler for doctests, registered as 'doctest'.

    >>> unicode_string = u"I \N{BLACK HEART SUIT}\N{YEN SIGN}!"
    >>> print unicode_string.encode('ascii', 'doctest')
    I \N{BLACK HEART SUIT}\N{YEN SIGN}!
    """
    replacement = []
    for char in error.object[error.start:error.end]:
        replacement.append(u"\\N{%s}" % unicodedata.name(char, '<UNNAMED>'))
    return (u''.join(replacement), error.end)


def doctest_unicode_encode(input, errors='strict'):
    r"""Encoder to convert Unicode to 'doctest' format.

    >>> unicode_string = u"I \N{BLACK HEART SUIT}\N{YEN SIGN}!"
    >>> print unicode_string.encode('doctest')
    I \N{BLACK HEART SUIT}\N{YEN SIGN}!
    """
    return (input.encode('ASCII', 'doctest'), len(input))


def doctest_unicode_decode(input, errors='strict'):
    r"""Decoder to convert from 'doctest' encoding to Unicode.

    >>> unicode_string = u"I \N{BLACK HEART SUIT}\N{YEN SIGN}!"
    >>> doctest_string = unicode_string.encode('doctest')
    >>> print doctest_string
    I \N{BLACK HEART SUIT}\N{YEN SIGN}!
    >>> roundtrip_string = doctest_string.decode('doctest')
    >>> roundtrip_string == unicode_string
    True
    """
    return (input.decode('unicode_escape', errors), len(input))


def doctest_unicode_search(encoding_name):
    """Codec search function for the 'doctest' codec."""
    if encoding_name == 'doctest':
        return (doctest_unicode_encode, doctest_unicode_decode, None, None)

codecs.register_error('doctest', doctest_unicode_error_handler)
codecs.register(doctest_unicode_search)

