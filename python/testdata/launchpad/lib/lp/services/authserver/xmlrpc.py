# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Auth-Server XML-RPC API ."""

__metaclass__ = type

__all__ = [
    'AuthServerApplication',
    'AuthServerAPIView',
    ]

from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.person import IPersonSet
from lp.services.authserver.interfaces import (
    IAuthServer,
    IAuthServerApplication,
    )
from lp.services.webapp import LaunchpadXMLRPCView
from lp.xmlrpc import faults


class AuthServerAPIView(LaunchpadXMLRPCView):
    """See `IAuthServer`."""

    implements(IAuthServer)

    def getUserAndSSHKeys(self, name):
        """See `IAuthServer.getUserAndSSHKeys`."""
        person = getUtility(IPersonSet).getByName(name)
        if person is None:
            return faults.NoSuchPersonWithName(name)
        return {
            'id': person.id,
            'name': person.name,
            'keys': [(key.keytype.title, key.keytext)
                     for key in person.sshkeys],
            }


class AuthServerApplication:
    """AuthServer End-Point."""
    implements(IAuthServerApplication)

    title = "Auth Server"


