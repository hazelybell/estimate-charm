# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""This module contains sorting utility functions."""

__metaclass__ = type
__all__ = ['expand_numbers',
           'sorted_version_numbers',
           'sorted_dotted_numbers']

import re


def expand_numbers(unicode_text, fill_digits=4):
    """Return a copy of the string with numbers zero filled.

    >>> expand_numbers(u'hello world')
    u'hello world'
    >>> expand_numbers(u'0.12.1')
    u'0000.0012.0001'
    >>> expand_numbers(u'0.12.1', 2)
    u'00.12.01'
    >>> expand_numbers(u'branch-2-3.12')
    u'branch-0002-0003.0012'

    """
    assert(isinstance(unicode_text, unicode))

    def substitute_filled_numbers(match):
        return match.group(0).zfill(fill_digits)
    return re.sub(u'\d+', substitute_filled_numbers, unicode_text)


# Create translation table for numeric ordinals to their
# strings in reversed order.  So ord(u'0') -> u'9' and
# so on.
reversed_numbers_table = dict(
  zip(map(ord, u'0123456789'), reversed(u'0123456789')))


def _reversed_number_comparator(lhs_text, rhs_text):
    """Return comparison value reversed for numbers only.

    >>> _reversed_number_comparator(u'9.3', u'2.4')
    -1
    >>> _reversed_number_comparator(u'world', u'hello')
    1
    >>> _reversed_number_comparator(u'hello world', u'hello world')
    0
    >>> _reversed_number_comparator(u'dev', u'development')
    -1
    >>> _reversed_number_comparator(u'bzr-0.13', u'bzr-0.08')
    -1

    """
    assert isinstance(lhs_text, unicode)
    assert isinstance(rhs_text, unicode)
    translated_lhs_text = lhs_text.translate(reversed_numbers_table)
    translated_rhs_text = rhs_text.translate(reversed_numbers_table)
    return cmp(translated_lhs_text, translated_rhs_text)


def _identity(x):
    return x


def sorted_version_numbers(sequence, key=_identity):
    """Return a new sequence where 'newer' versions appear before 'older' ones.

    >>> bzr_versions = [u'0.9', u'0.10', u'0.11']
    >>> for version in sorted_version_numbers(bzr_versions):
    ...   print version
    0.11
    0.10
    0.9
    >>> bzr_versions = [u'bzr-0.9', u'bzr-0.10', u'bzr-0.11']
    >>> for version in sorted_version_numbers(bzr_versions):
    ...   print version
    bzr-0.11
    bzr-0.10
    bzr-0.9

    >>> class series:
    ...   def __init__(self, name):
    ...     self.name = unicode(name)
    >>> bzr_versions = [series('0.9'), series('0.10'), series('0.11'),
    ...                 series('bzr-0.9'), series('bzr-0.10'),
    ...                 series('bzr-0.11'), series('foo')]
    >>> from operator import attrgetter
    >>> for version in sorted_version_numbers(bzr_versions,
    ...                                       key=attrgetter('name')):
    ...   print version.name
    0.11
    0.10
    0.9
    bzr-0.11
    bzr-0.10
    bzr-0.9
    foo

    """
    expanded_key = lambda x: expand_numbers(key(x))
    return sorted(sequence, key=expanded_key,
                  cmp=_reversed_number_comparator)


def sorted_dotted_numbers(sequence, key=_identity):
    """Sorts numbers inside strings numerically.

    There are times where numbers are used as part of a string
    normally separated with a delimiter, frequently '.' or '-'.
    The intent of this is to sort '0.10' after '0.9'.

    The function returns a new sorted sequence.

    >>> bzr_versions = [u'0.9', u'0.10', u'0.11']
    >>> for version in sorted_dotted_numbers(bzr_versions):
    ...   print version
    0.9
    0.10
    0.11
    >>> bzr_versions = [u'bzr-0.9', u'bzr-0.10', u'bzr-0.11']
    >>> for version in sorted_dotted_numbers(bzr_versions):
    ...   print version
    bzr-0.9
    bzr-0.10
    bzr-0.11

    >>> class series:
    ...   def __init__(self, name):
    ...     self.name = unicode(name)
    >>> bzr_versions = [series('0.9'), series('0.10'), series('0.11'),
    ...                 series('bzr-0.9'), series('bzr-0.10'),
    ...                 series('bzr-0.11'), series('foo')]
    >>> from operator import attrgetter
    >>> for version in sorted_dotted_numbers(bzr_versions,
    ...                                      key=attrgetter('name')):
    ...   print version.name
    0.9
    0.10
    0.11
    bzr-0.9
    bzr-0.10
    bzr-0.11
    foo

    """
    expanded_key = lambda x: expand_numbers(key(x))
    return sorted(sequence, key=expanded_key)
