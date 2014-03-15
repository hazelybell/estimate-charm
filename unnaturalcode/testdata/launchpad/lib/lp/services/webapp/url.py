# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions for working with URLs."""

__metaclass__ = type
__all__ = ['urlappend', 'urlparse', 'urlsplit']

from urlparse import (
    urljoin,
    urlparse as original_urlparse,
    urlsplit as original_urlsplit,
    )
import urlparse as urlparse_module


def _enable_sftp_in_urlparse():
    """Teach the urlparse module about the sftp scheme.

    That allows the helpers in this module to operate usefully on sftp URLs.
    This fix was suggested by Jamesh Henstridge and is said to be used by bzr
    and other unrelated projects.

    Without that, some operations on sftp URLs give obviously wrong results.
    For example: urlappend('sftp://foo/bar', 'gam') => 'gam'

    >>> urlappend('sftp://foo/bar', 'gam')
    'sftp://foo/bar/gam'
    """
    if 'sftp' not in urlparse_module.uses_netloc:
        urlparse_module.uses_netloc.append('sftp')
    if 'sftp' not in urlparse_module.uses_relative:
        urlparse_module.uses_relative.append('sftp')


# Extend urlparse to support sftp at module load time.
_enable_sftp_in_urlparse()

def _enable_bzr_ssh_in_urlparse():
    """Teach the urlparse module about the bzr+ssh scheme.

    That allows the helpers in this module to operate usefully on bzr+ssh URLs

    >>> tuple(urlparse('bzr+ssh://example.com/code/branch'))
    ('bzr+ssh', 'example.com', '/code/branch', '', '', '')
    """
    if 'bzr+ssh' not in urlparse_module.uses_netloc:
        urlparse_module.uses_netloc.append('bzr+ssh')
    if 'bzr+ssh' not in urlparse_module.uses_relative:
        urlparse_module.uses_relative.append('bzr+ssh')


# Extend this version of urlparse (used by the launchpad validators)
# to support bzr+ssh at module load time
# note that additional URL checking is done inside the database
# (database/schema/trusted.sql, the valid_absolute_url function)
# the database code uses plain stdlib urlparse, not this customized
# version, so be sure to teach trusted.sql about any new URL
# schemes which are added here.
_enable_bzr_ssh_in_urlparse()

def urlappend(baseurl, path):
    """Append the given path to baseurl.

    The path must not start with a slash, but a slash is added to baseurl
    (before appending the path), in case it doesn't end with a slash.

    >>> urlappend('http://foo.bar', 'spam/eggs')
    'http://foo.bar/spam/eggs'
    >>> urlappend('http://localhost:11375/foo', 'bar/baz')
    'http://localhost:11375/foo/bar/baz'
    """
    assert not path.startswith('/')
    if not baseurl.endswith('/'):
        baseurl += '/'
    return urljoin(baseurl, path)


def urlparse(url, scheme='', allow_fragments=True):
    """Convert url to a str object and call the original urlparse function.

    The url parameter should contain ASCII characters only. This
    function ensures that the original urlparse is called always with a
    str object, and never unicode.

        >>> tuple(urlparse(u'http://foo.com/bar'))
        ('http', 'foo.com', '/bar', '', '', '')

        >>> tuple(urlparse('http://foo.com/bar'))
        ('http', 'foo.com', '/bar', '', '', '')

        >>> tuple(original_urlparse('http://foo.com/bar'))
        ('http', 'foo.com', '/bar', '', '', '')

    This is needed since external libraries might expect that the original
    urlparse returns a str object if it is given a str object. However,
    that might not be the case, since urlparse has a cache, and treats
    unicode and str as equal. (http://sourceforge.net/tracker/index.php?
    func=detail&aid=1313119&group_id=5470&atid=105470)
    """
    return original_urlparse(
        url.encode('ascii'), scheme=scheme, allow_fragments=allow_fragments)


def urlsplit(url, scheme='', allow_fragments=True):
    """Convert url to a str object and call the original urlsplit function.

    The url parameter should contain ASCII characters only. This
    function ensures that the original urlsplit is called always with a
    str object, and never unicode.

        >>> tuple(urlsplit(u'http://foo.com/baz'))
        ('http', 'foo.com', '/baz', '', '')

        >>> tuple(urlsplit('http://foo.com/baz'))
        ('http', 'foo.com', '/baz', '', '')

        >>> tuple(original_urlsplit('http://foo.com/baz'))
        ('http', 'foo.com', '/baz', '', '')

    """
    return original_urlsplit(
        url.encode('ascii'), scheme=scheme, allow_fragments=allow_fragments)
