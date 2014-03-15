# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""TestOpenID adapters and helpers."""

__metaclass__ = type

__all__ = [
    'TestOpenIDPersistentIdentity',
    ]

from zope.component import adapts
from zope.interface import implements

from lp.services.identity.interfaces.account import IAccount
from lp.services.openid.adapters.openid import OpenIDPersistentIdentity
from lp.services.webapp.vhosts import allvhosts
from lp.testopenid.interfaces.server import ITestOpenIDPersistentIdentity


class TestOpenIDPersistentIdentity(OpenIDPersistentIdentity):
    """See `IOpenIDPersistentIdentity`."""

    adapts(IAccount)
    implements(ITestOpenIDPersistentIdentity)

    @property
    def openid_identity_url(self):
        """See `IOpenIDPersistentIdentity`."""
        identity_root_url = allvhosts.configs['testopenid'].rooturl
        return identity_root_url + self.openid_identifier.encode('ascii')
