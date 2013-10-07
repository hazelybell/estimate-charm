# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions to help with translation templates."""

__all__ = [
    'make_domain',
    'make_name',
    'make_name_from_path',
    ]


import os

from lp.app.validators.name import sanitize_name


GENERIC_TEMPLATE_NAMES = [
    'en-US.xpi',
    'messages.pot',
    'untitled.pot',
    'template.pot',
    ]
GENERIC_TEMPLATE_DIRS = [
    'po',
    ]


def make_domain(path, default=''):
    """Generate the translation domain name from the path of the template
    file.

    :returns: The translation domain name or an empty string if it could
        not be determined.
    """
    dname, fname = os.path.split(path)
    # Handle generic names and xpi cases
    if fname not in GENERIC_TEMPLATE_NAMES:
        domain, ext = os.path.splitext(fname)
        return domain
    dname1, dname2 = os.path.split(dname)
    if dname2 not in GENERIC_TEMPLATE_DIRS:
        return dname2 or default
    rest, domain = os.path.split(dname1)
    return domain or default


def make_name(domain):
    """Make a template name from a translation domain."""
    return sanitize_name(domain.replace('_', '-').lower())


def make_name_from_path(path, default=''):
    """Make a template name from a file path."""
    return make_name(make_domain(path, default=default))
