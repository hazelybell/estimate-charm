# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XMLRPC APIs for person set."""

__metaclass__ = type
__all__ = [
    'SoftwareCenterAgentAPI',
    ]


from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.person import (
    IPersonSet,
    ISoftwareCenterAgentAPI,
    ISoftwareCenterAgentApplication,
    PersonCreationRationale,
    TeamEmailAddressError,
    )
from lp.services.identity.interfaces.account import AccountSuspendedError
from lp.services.webapp import LaunchpadXMLRPCView
from lp.xmlrpc import faults


class SoftwareCenterAgentAPI(LaunchpadXMLRPCView):
    """See `ISoftwareCenterAgentAPI`."""

    implements(ISoftwareCenterAgentAPI)

    def getOrCreateSoftwareCenterCustomer(self, openid_identifier, email,
                                      full_name):
        try:
            person, db_updated = getUtility(
                IPersonSet).getOrCreateByOpenIDIdentifier(
                    openid_identifier.decode('ASCII'), email, full_name,
                    PersonCreationRationale.SOFTWARE_CENTER_PURCHASE,
                    "when purchasing an application via Software Center.")
        except AccountSuspendedError:
            return faults.AccountSuspended(openid_identifier)
        except TeamEmailAddressError:
            return faults.TeamEmailAddress(email, openid_identifier)

        return person.name


class SoftwareCenterAgentApplication:
    """Software center agent end-point."""
    implements(ISoftwareCenterAgentApplication)

    title = "Software Center Agent API"
