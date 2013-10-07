# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Various functions and classes that are useful across different parts of
launchpad.

Do not simply dump stuff in here.  Think carefully as to whether it would
be better as a method on an existing content object or IFooSet object.
"""

__metaclass__ = type

from difflib import unified_diff
import re
from StringIO import StringIO
import subprocess
import tarfile
import warnings

from zope.security.interfaces import ForbiddenAttribute


def text_replaced(text, replacements, _cache={}):
    """Return a new string with text replaced according to the dict provided.

    The keys of the dict are substrings to find, the values are what to
    replace found substrings with.

    :arg text: An unicode or str to do the replacement.
    :arg replacements: A dictionary with the replacements that should be done

    >>> text_replaced('', {'a':'b'})
    ''
    >>> text_replaced('a', {'a':'c'})
    'c'
    >>> text_replaced('faa bar baz', {'a': 'A', 'aa': 'X'})
    'fX bAr bAz'
    >>> text_replaced('1 2 3 4', {'1': '2', '2': '1'})
    '2 1 3 4'

    Unicode strings work too.

    >>> text_replaced(u'1 2 3 4', {u'1': u'2', u'2': u'1'})
    u'2 1 3 4'

    The argument _cache is used as a cache of replacements that were requested
    before, so we only compute regular expressions once.

    """
    assert replacements, "The replacements dict must not be empty."
    # The ordering of keys and values in the tuple will be consistent within a
    # single Python process.
    cachekey = tuple(replacements.items())
    if cachekey not in _cache:
        L = []
        if isinstance(text, unicode):
            list_item = u'(%s)'
            join_char = u'|'
        else:
            list_item = '(%s)'
            join_char = '|'
        for find, replace in sorted(replacements.items(),
                                    key=lambda (key, value): len(key),
                                    reverse=True):
            L.append(list_item % re.escape(find))
        # Make a copy of the replacements dict, as it is mutable, but we're
        # keeping a cached reference to it.
        replacements_copy = dict(replacements)

        def matchobj_replacer(matchobj):
            return replacements_copy[matchobj.group()]

        regexsub = re.compile(join_char.join(L)).sub

        def replacer(s):
            return regexsub(matchobj_replacer, s)

        _cache[cachekey] = replacer
    return _cache[cachekey](text)


def backslashreplace(str):
    """Return a copy of the string, with non-ASCII characters rendered as
    xNN or uNNNN. Used to test data containing typographical quotes etc.
    """
    return str.decode('UTF-8').encode('ASCII', 'backslashreplace')


def string_to_tarfile(s):
    """Convert a binary string containing a tar file into a tar file obj."""

    return tarfile.open('', 'r', StringIO(s))


def simple_popen2(command, input, env=None, in_bufsize=1024, out_bufsize=128):
    """Run a command, give it input on its standard input, and capture its
    standard output.

    Returns the data from standard output.

    This function is needed to avoid certain deadlock situations. For example,
    if you popen2() a command, write its standard input, then read its
    standard output, this can deadlock due to the parent process blocking on
    writing to the child, while the child process is simultaneously blocking
    on writing to its parent. This function avoids that problem by using
    subprocess.Popen.communicate().
    """

    p = subprocess.Popen(
            command, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output, nothing) = p.communicate(input)
    return output


class ShortListTooBigError(Exception):
    """This error is raised when the shortlist hardlimit is reached"""


def shortlist(sequence, longest_expected=15, hardlimit=None):
    """Return a listified version of sequence.

    If <sequence> has more than <longest_expected> items, a warning is issued.

    >>> shortlist([1, 2])
    [1, 2]

    >>> shortlist([1, 2, 3], 2) #doctest: +NORMALIZE_WHITESPACE
    Traceback (most recent call last):
    ...
    UserWarning: shortlist() should not be used here. It's meant to listify
    sequences with no more than 2 items.  There were 3 items.

    >>> shortlist([1, 2, 3, 4], hardlimit=2)
    Traceback (most recent call last):
    ...
    ShortListTooBigError: Hard limit of 2 exceeded.

    >>> shortlist(
    ...     [1, 2, 3, 4], 2, hardlimit=4) #doctest: +NORMALIZE_WHITESPACE
    Traceback (most recent call last):
    ...
    UserWarning: shortlist() should not be used here. It's meant to listify
    sequences with no more than 2 items.  There were 4 items.

    It works on iterable also which don't support the extended slice protocol.

    >>> xrange(5)[:1] #doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    TypeError: ...

    >>> shortlist(xrange(10), 5, hardlimit=8) #doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    ShortListTooBigError: ...

    """
    if hardlimit is not None:
        last = hardlimit + 1
    else:
        last = None
    try:
        results = list(sequence[:last])
    except (TypeError, ForbiddenAttribute):
        results = []
        for idx, item in enumerate(sequence):
            if hardlimit and idx > hardlimit:
                break
            results.append(item)

    size = len(results)
    if hardlimit and size > hardlimit:
        raise ShortListTooBigError(
           'Hard limit of %d exceeded.' % hardlimit)
    elif size > longest_expected:
        warnings.warn(
            "shortlist() should not be used here. It's meant to listify"
            " sequences with no more than %d items.  There were %s items."
            % (longest_expected, size), stacklevel=2)
    return results


def is_tar_filename(filename):
    '''
    Check whether a filename looks like a filename that belongs to a tar file,
    possibly one compressed somehow.
    '''

    return (filename.endswith('.tar') or
            filename.endswith('.tar.gz') or
            filename.endswith('.tgz') or
            filename.endswith('.tar.bz2'))


def test_diff(lines_a, lines_b):
    """Generate a string indicating the difference between expected and actual
    values in a test.
    """

    return '\n'.join(list(unified_diff(
        a=lines_a,
        b=lines_b,
        fromfile='expected',
        tofile='actual',
        lineterm='',
        )))


def filenameToContentType(fname):
    """ Return the a ContentType-like entry for arbitrary filenames

    deb files

    >>> filenameToContentType('test.deb')
    'application/x-debian-package'

    text files

    >>> filenameToContentType('test.txt')
    'text/plain'

    Not recognized format

    >>> filenameToContentType('test.tgz')
    'application/octet-stream'
    """
    ftmap = {".dsc": "text/plain",
             ".changes": "text/plain",
             ".deb": "application/x-debian-package",
             ".udeb": "application/x-debian-package",
             ".txt": "text/plain",
             # For the build master logs
             ".txt.gz": "text/plain",
             }
    for ending in ftmap:
        if fname.endswith(ending):
            return ftmap[ending]
    return "application/octet-stream"


def intOrZero(value):
    """Return int(value) or 0 if the conversion fails.

    >>> intOrZero('1.23')
    0
    >>> intOrZero('1.ab')
    0
    >>> intOrZero('2')
    2
    >>> intOrZero(None)
    0
    >>> intOrZero(1)
    1
    >>> intOrZero(-9)
    -9
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def truncate_text(text, max_length):
    """Return a version of string no longer than max_length characters.

    Tries not to cut off the text mid-word.
    """
    words = re.compile(r'\s*\S+').findall(text, 0, max_length + 1)
    truncated = words[0]
    for word in words[1:]:
        if len(truncated) + len(word) > max_length:
            break
        truncated += word
    return truncated[:max_length]


def english_list(items, conjunction='and'):
    """Return all the items concatenated into a English-style string.

    Follows the advice given in The Elements of Style, chapter I,
    section 2:

    "In a series of three or more terms with a single conjunction, use
     a comma after each term except the last."

    Beware that this is US English and is wrong for non-US.
    """
    items = list(items)
    if len(items) <= 2:
        return (' %s ' % conjunction).join(items)
    else:
        items[-1] = '%s %s' % (conjunction, items[-1])
        return ', '.join(items)


def ensure_unicode(string):
    r"""Return input as unicode. None is passed through unharmed.

    Do not use this method. This method exists only to help migration
    of legacy code where str objects were being passed into contexts
    where unicode objects are required. All invokations of
    ensure_unicode() should eventually be removed.

    This differs from the builtin unicode() function, as a TypeError
    exception will be raised if the parameter is not a basestring or if
    a raw string is not ASCII.

    >>> ensure_unicode(u'hello')
    u'hello'

    >>> ensure_unicode('hello')
    u'hello'

    >>> ensure_unicode(u'A'.encode('utf-16')) # Not ASCII
    Traceback (most recent call last):
    ...
    TypeError: '\xff\xfeA\x00' is not US-ASCII

    >>> ensure_unicode(42)
    Traceback (most recent call last):
    ...
    TypeError: 42 is not a basestring (<type 'int'>)

    >>> ensure_unicode(None) is None
    True
    """
    if string is None:
        return None
    elif isinstance(string, unicode):
        return string
    elif isinstance(string, basestring):
        try:
            return string.decode('US-ASCII')
        except UnicodeDecodeError:
            raise TypeError("%s is not US-ASCII" % repr(string))
    else:
        raise TypeError(
            "%r is not a basestring (%r)" % (string, type(string)))
