# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Validators for the .name attribute (defined in various schemas.)"""

__metaclass__ = type

import re
from textwrap import dedent

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )


valid_name_pattern = re.compile(r"^[a-z0-9][a-z0-9\+\.\-]+$")
valid_bug_name_pattern = re.compile(r"^[a-z][a-z0-9\+\.\-]+$")
invalid_name_pattern = re.compile(r"^[^a-z0-9]+|[^a-z0-9\\+\\.\\-]+")


def sanitize_name(name):
    """Remove from the given name all characters that are not allowed
    on names.

    The characters not allowed in Launchpad names are described by
    invalid_name_pattern.

    >>> sanitize_name('foo_bar')
    'foobar'
    >>> sanitize_name('baz bar $fd')
    'bazbarfd'
    """
    return invalid_name_pattern.sub('', name)


def valid_name(name):
    """Return True if the name is valid, otherwise False.

    Lauchpad `name` attributes are designed for use as url components
    and short unique identifiers to things.

    The default name constraints may be too strict for some objects,
    such as binary packages or arch branches where naming conventions already
    exists, so they may use their own specialized name validators

    >>> valid_name('hello')
    True
    >>> valid_name('helLo')
    False
    >>> valid_name('he')
    True
    >>> valid_name('h')
    False
    """
    if valid_name_pattern.match(name):
        return True
    return False


def valid_bug_name(name):
    """Return True if the bug name is valid, otherwise False."""
    if valid_bug_name_pattern.match(name):
        return True
    return False


def name_validator(name):
    """Return True if the name is valid, or raise a
    LaunchpadValidationError.
    """
    if not valid_name(name):
        message = _(dedent("""
            Invalid name '${name}'. Names must be at least two characters long
            and start with a letter or number. All letters must be lower-case.
            The characters <samp>+</samp>, <samp>-</samp> and <samp>.</samp>
            are also allowed after the first character."""),
            mapping={'name': html_escape(name)})

        raise LaunchpadValidationError(structured(message))
    return True


def bug_name_validator(name):
    """Return True if the name is valid, or raise a
    LaunchpadValidationError.
    """
    if not valid_bug_name(name):
        message = _(dedent("""
            Invalid name '${name}'. Names must be at least two characters long
            and start with a letter. All letters must be lower-case.
            The characters <samp>+</samp>, <samp>-</samp> and <samp>.</samp>
            are also allowed after the first character."""),
            mapping={'name': html_escape(name)})

        raise LaunchpadValidationError(structured(message))
    return True
