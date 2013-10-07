# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ZConfig datatypes for <mailman> and <mailman-build> configuration keys."""


import os
import random
from string import (
    ascii_letters,
    digits,
    )


__all__ = [
    'configure_prefix',
    'configure_siteowner',
    ]


EMPTY_STRING = ''


def configure_prefix(value):
    """Specify Mailman's configure's --prefix argument.

    If a value is given we assume it's a path and make it absolute.  If it's
    already absolute, it doesn't change.

    >>> configure_prefix('/tmp/var/mailman')
    '/tmp/var/mailman'

    If it's relative, then it's relative to the current working directory.

    >>> import os
    >>> here = os.getcwd()
    >>> configure_prefix('some/lib/mailman') == os.path.join(
    ...     here, 'some/lib/mailman')
    True

    If the empty string is given (the default), then this returns lib/mailman
    relative to the current working directory.

    >>> configure_prefix('') == os.path.join(here, 'lib/mailman')
    True
    """
    if value:
        return os.path.abspath(value)
    return os.path.abspath(os.path.join('lib', 'mailman'))


def random_characters(length=10):
    """Return a random string of characters."""
    chars = digits + ascii_letters
    return EMPTY_STRING.join(random.choice(chars) for c in range(length))


def configure_siteowner(value):
    """Accept a string of the form email:password.

    Given a value, it must be an address and password separated by a colon.

    >>> configure_siteowner('foo')
    Traceback (most recent call last):
    ...
    ValueError: need more than 1 value to unpack
    >>> configure_siteowner('me@example.com:password')
    ('me@example.com', 'password')

    However, the format (or validity) of the email address is not checked.

    >>> configure_siteowner('email:password')
    ('email', 'password')

    If an empty string is given (the default), we use a random password and a
    random local part, with the domain forced to example.com.

    >>> address, password = configure_siteowner('')
    >>> len(password) == 10
    True
    >>> localpart, domain = address.split('@', 1)
    >>> len(localpart) == 10
    True
    >>> domain
    'example.com'
    """
    if value:
        addr, password = value.split(':', 1)
    else:
        localpart = random_characters()
        password  = random_characters()
        addr = localpart + '@example.com'
    return addr, password
