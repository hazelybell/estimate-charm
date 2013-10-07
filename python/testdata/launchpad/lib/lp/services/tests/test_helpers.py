# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from doctest import DocTestSuite
from textwrap import dedent
import unittest

from lp.services import helpers
from lp.services.tarfile_helpers import LaunchpadWriteTarFile


def make_test_tarball_1():
    '''
    Generate a test tarball that looks something like a source tarball which
    has exactly one directory called 'po' which is interesting (i.e. contains
    some files which look like POT/PO files).

    >>> tarball = make_test_tarball_1()

    Check it looks vaguely sensible.

    >>> names = tarball.getnames()
    >>> 'uberfrob-0.1/po/cy.po' in names
    True
    '''

    return LaunchpadWriteTarFile.files_to_tarfile({
        'uberfrob-0.1/README':
            'Uberfrob is an advanced frobnicator.',
        'uberfrob-0.1/po/cy.po':
            '# Blah.',
        'uberfrob-0.1/po/es.po':
            '# Blah blah.',
        'uberfrob-0.1/po/uberfrob.pot':
            '# Yowza!',
        'uberfrob-0.1/blah/po/la':
            'la la',
        'uberfrob-0.1/uberfrob.py':
            'import sys\n'
            'print "Frob!"\n',
        })


def make_test_tarball_2():
    r'''
    Generate a test tarball string that has some interesting files in a common
    prefix.

    >>> tarball = make_test_tarball_2()

    Check the expected files are in the archive.

    # XXX: 2010-04-26, Salgado, bug=570244: This rstrip('/') is to make the
    # test pass on python2.5 and 2.6.
    >>> [name.rstrip('/') for name in tarball.getnames()]
    ['test', 'test/cy.po', 'test/es.po', 'test/test.pot']

    Check the contents.

    >>> f = tarball.extractfile('test/cy.po')
    >>> f.readline()
    '# Test PO file.\n'
    '''

    pot = dedent("""
        # Test POT file.
        msgid "foo"
        msgstr ""
        """).strip()

    po = dedent("""
        # Test PO file.
        msgid "foo"
        msgstr "bar"
        """).strip()

    return LaunchpadWriteTarFile.files_to_tarfile({
        'test/test.pot': pot,
        'test/cy.po': po,
        'test/es.po': po,
    })


def test_shortlist_returns_all_elements():
    """
    Override the warning function since by default all warnings raises an
    exception and we can't test the return value of the function.

    >>> import warnings

    >>> def warn(message, category=None, stacklevel=2):
    ...     if category is None:
    ...         category = 'UserWarning'
    ...     else:
    ...         category = category.__class__.__name__
    ...     print "%s: %s" % (category, message)

    >>> old_warn = warnings.warn
    >>> warnings.warn = warn

    Show that shortlist doesn't crop the results when a warning is
    printed.

    >>> from lp.services.helpers import shortlist
    >>> shortlist(list(range(10)), longest_expected=5) #doctest: +ELLIPSIS
    UserWarning: shortlist() should not...
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    >>> shortlist(xrange(10), longest_expected=5) #doctest: +ELLIPSIS
    UserWarning: shortlist() should not...
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    Reset our monkey patch.

    >>> warnings.warn = old_warn

    """


def test_english_list():
    """
    The english_list function takes a list of strings and concatenates them
    in a form suitable for inclusion in an English sentence. For lists of 3
    or more elements it follows the advice given in The Elements of Style,
    chapter I, section 2.

        >>> from lp.services.helpers import english_list

    By default, it joins the last two elements in the list with 'and', and
    joins the rest of the list with ','. It also adds whitespace around
    these delimiters as appropriate.

        >>> english_list([])
        ''

        >>> english_list(['Fred'])
        'Fred'

        >>> english_list(['Fred', 'Bob'])
        'Fred and Bob'

        >>> english_list(['Fred', 'Bob', 'Harold'])
        'Fred, Bob, and Harold'

    It accepts any iterable that yields strings:

        >>> english_list('12345')
        '1, 2, 3, 4, and 5'

        >>> english_list(str(i) for i in xrange(5))
        '0, 1, 2, 3, and 4'

    It does not convert non-string elements:

        >>> english_list(range(3))
        Traceback (most recent call last):
        ...
        TypeError: sequence item 0: expected string, int found

    The conjunction can be changed:

        >>> english_list('123', 'or')
        '1, 2, or 3'
    """


class TruncateTextTest(unittest.TestCase):

    def test_leaves_shorter_text_unchanged(self):
        """When the text is shorter than the length, nothing is truncated."""
        self.assertEqual('foo', helpers.truncate_text('foo', 10))

    def test_single_very_long_word(self):
        """When the first word is longer than the truncation then that word is
        included.
        """
        self.assertEqual('foo', helpers.truncate_text('foooo', 3))

    def test_words_arent_split(self):
        """When the truncation would leave only half of the last word, then
        the whole word is removed.
        """
        self.assertEqual('foo', helpers.truncate_text('foo bar', 5))

    def test_whitespace_is_preserved(self):
        """The whitespace between words is preserved in the truncated text."""
        text = 'foo  bar\nbaz'
        self.assertEqual(text, helpers.truncate_text(text, len(text)))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(DocTestSuite())
    suite.addTest(DocTestSuite(helpers))
    suite.addTest(
        unittest.TestLoader().loadTestsFromTestCase(TruncateTextTest))
    return suite
