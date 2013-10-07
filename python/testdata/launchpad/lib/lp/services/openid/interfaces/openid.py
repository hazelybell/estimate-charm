# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Miscelaneous OpenID-related interfaces."""

__metaclass__ = type
__all__ = [
    'IOpenIDPersistentIdentity',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class IOpenIDPersistentIdentity(Interface):
    """An object that represents a persistent user identity URL.

    This interface is generally needed by the UI.
    """
    account = Attribute('The `IAccount` for the user.')
    openid_identity_url = Attribute(
        'The OpenID identity URL for the user.')
    openid_identifier = Attribute(
        'The OpenID identifier used with the request.')


