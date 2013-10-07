# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'builder_url_validator',
    'valid_absolute_url',
    'valid_builder_url',
    'valid_webref',
    'validate_url',
    ]

from textwrap import dedent
import urllib

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.services.webapp.url import urlparse


def valid_absolute_url(name):
    """Validate an absolute URL.

    It looks like this function has been deprecated by
    lp.app.validators.validation.

    We define this as something that can be parsed into a URL that has both
    a protocol and a network address.

      >>> valid_absolute_url('sftp://chinstrap.ubuntu.com/foo/bar')
      True
      >>> valid_absolute_url('http://www.example.com')
      True
      >>> valid_absolute_url('whatever:/uxample.com/blah')
      False
      >>> valid_absolute_url('whatever://example.com/blah')
      True

    Unicode urls are ascii encoded, and a failure here means it isn't valid.

      >>> valid_absolute_url(u'http://www.example.com/test...')
      True
      >>> valid_absolute_url(u'http://www.example.com/test\u2026')
      False

    """
    try:
        (scheme, netloc, path, params, query, fragment) = urlparse(name)
    except UnicodeEncodeError:
        return False
    # note that URL checking is also done inside the database, in
    # trusted.sql, the valid_absolute_url function, and that code uses
    # stdlib urlparse, not our customized version.
    if not (scheme and netloc):
        return False
    return True


def valid_builder_url(url):
    """validate a url for a builder.

    Builder urls must be http://host/ or http://host:port/
    (with or without the trailing slash) only.

    >>> valid_builder_url('http://example.com:54321/')
    True
    >>> valid_builder_url('http://example.com/foo')
    False
    >>> valid_builder_url('ftp://foo.com/')
    False

    """
    try:
        (scheme, netloc, path, params, query, fragment) = urlparse(url)
    except UnicodeEncodeError:
        return False
    if scheme != 'http':
        return False
    if params or query or fragment:
        return False
    if path and path != '/':
        return False
    return True


def builder_url_validator(url):
    """Return True if the url is valid, or raise a LaunchpadValidationError"""
    if not valid_builder_url(url):
        raise LaunchpadValidationError(_(dedent("""
            Invalid builder url '${url}'. Builder urls must be
            http://host/ or http://host:port/ only.
            """), mapping={'url': url}))
    return True


def validate_url(url, valid_schemes):
    """Returns a boolean stating whether 'url' is a valid URL.

    A URL is valid if:
      - its URL scheme is in the provided 'valid_schemes' list, and
      - it has a non-empty host name.

    None and an empty string are not valid URLs::

      >>> validate_url(None, [])
      False
      >>> validate_url('', [])
      False

    The valid_schemes list is checked::

      >>> validate_url('http://example.com', ['http'])
      True
      >>> validate_url('http://example.com', ['https', 'ftp'])
      False

    A URL without a host name is not valid:

      >>> validate_url('http://', ['http'])
      False

    Unicode urls are converted to ascii for checking.  Failure to convert
    results in failure.

      >>> validate_url(u'http://example.com', ['http'])
      True
      >>> validate_url(u'http://example.com/test\u2026', ['http'])
      False

    """
    if not url:
        return False
    scheme, host = urllib.splittype(url)
    if not scheme in valid_schemes:
        return False
    if not valid_absolute_url(url):
        return False
    return True


def valid_webref(web_ref):
    """Returns True if web_ref is a valid download URL, or raises a
    LaunchpadValidationError.

    >>> valid_webref('http://example.com')
    True
    >>> valid_webref('https://example.com/foo/bar')
    True
    >>> valid_webref('ftp://example.com/~ming')
    True
    >>> valid_webref('sftp://example.com//absolute/path/maybe')
    True
    >>> valid_webref('other://example.com/moo')
    Traceback (most recent call last):
    ...
    LaunchpadValidationError: ...
    """
    if validate_url(web_ref, ['http', 'https', 'ftp', 'sftp']):
        # Allow ftp so valid_webref can be used for download_url, and so
        # it doesn't lock out weird projects where the site or
        # screenshots are kept on ftp.
        return True
    else:
        raise LaunchpadValidationError(_(dedent("""
            Not a valid URL. Please enter the full URL, including the
            scheme (for instance, http:// for a web URL), and ensure the
            URL uses either http, https or ftp.""")))
