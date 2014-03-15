# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OpenID adapters and helpers."""

__metaclass__ = type

__all__ = [
    'CurrentOpenIDEndPoint',
    'OpenIDPersistentIdentity',
    ]

from zope.component import (
    adapter,
    adapts,
    )
from zope.interface import (
    implementer,
    implements,
    )

from lp.registry.interfaces.person import IPerson
from lp.services.database.interfaces import IStore
from lp.services.identity.interfaces.account import IAccount
from lp.services.openid.interfaces.openid import IOpenIDPersistentIdentity
from lp.services.openid.model.openididentifier import OpenIdIdentifier
from lp.services.webapp.vhosts import allvhosts


class CurrentOpenIDEndPoint:
    """A utility for working with multiple OpenID End Points."""

    @classmethod
    def getServiceURL(cls):
        """The OpenID server URL (/+openid) for the current request."""
        return allvhosts.configs['openid'].rooturl + '+openid'

    @classmethod
    def supportsURL(cls, identity_url):
        """Does the OpenID current vhost support the identity_url?"""
        root_url = allvhosts.configs['openid'].rooturl
        return identity_url.startswith(root_url + '+id')


class OpenIDPersistentIdentity:
    """A persistent OpenID identifier for a user."""

    adapts(IAccount)
    implements(IOpenIDPersistentIdentity)

    def __init__(self, account):
        self.account = account

    @property
    def openid_identity_url(self):
        """See `IOpenIDPersistentIdentity`."""
        openid_identifier = self.openid_identifier
        if openid_identifier is None:
            return None
        identity_root_url = allvhosts.configs['openid'].rooturl
        return identity_root_url + openid_identifier.encode('ascii')

    @property
    def openid_identifier(self):
        """See `IOpenIDPersistentIdentity`."""
        # We might have multiple OpenID identifiers linked to an
        # account. We just use the first one which is good enough
        # for our purposes.
        identifier = IStore(OpenIdIdentifier).find(
            OpenIdIdentifier, account=self.account).order_by(
                OpenIdIdentifier.date_created).first()
        if identifier is None:
            return None
        else:
            return '+id/' + identifier.identifier


@adapter(IPerson)
@implementer(IOpenIDPersistentIdentity)
def person_to_openidpersistentidentity(person):
    """Adapts an `IPerson` into an `IOpenIDPersistentIdentity`."""
    return OpenIDPersistentIdentity(person.account)
