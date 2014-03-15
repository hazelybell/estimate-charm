# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XMLRPC APIs for Canonical SSO to retrieve person details."""

__metaclass__ = type
__all__ = [
    'CanonicalSSOAPI',
    'CanonicalSSOApplication',
    ]


from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.person import (
    ICanonicalSSOAPI,
    ICanonicalSSOApplication,
    IPerson,
    )
from lp.services.identity.interfaces.account import IAccountSet
from lp.services.webapp import LaunchpadXMLRPCView


class CanonicalSSOAPI(LaunchpadXMLRPCView):
    """See `ICanonicalSSOAPI`."""

    implements(ICanonicalSSOAPI)

    def getPersonDetailsByOpenIDIdentifier(self, openid_identifier):
        try:
            account = getUtility(IAccountSet).getByOpenIDIdentifier(
                openid_identifier.decode('ascii'))
        except LookupError:
            return None
        person = IPerson(account, None)
        if person is None:
            return

        time_zone = person.time_zone
        team_names = dict(
            (removeSecurityProxy(t).name, t.private)
            for t in person.teams_participated_in)
        return {
            'name': person.name,
            'time_zone': time_zone,
            'teams': team_names,
            }


class CanonicalSSOApplication:
    """Canonical SSO end-point."""
    implements(ICanonicalSSOApplication)

    title = "Canonical SSO API"
