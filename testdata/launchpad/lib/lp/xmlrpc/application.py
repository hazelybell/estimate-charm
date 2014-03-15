# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XML-RPC API to the application roots."""

__metaclass__ = type

__all__ = [
    'ISelfTest',
    'PrivateApplication',
    'SelfTest',
    ]

import xmlrpclib

from zope.component import getUtility
from zope.interface import (
    implements,
    Interface,
    )

from lp.bugs.interfaces.malone import IPrivateMaloneApplication
from lp.code.interfaces.codehosting import ICodehostingApplication
from lp.code.interfaces.codeimportscheduler import (
    ICodeImportSchedulerApplication,
    )
from lp.registry.interfaces.mailinglist import IMailingListApplication
from lp.registry.interfaces.person import (
    ICanonicalSSOApplication,
    ISoftwareCenterAgentApplication,
    )
from lp.services.authserver.interfaces import IAuthServerApplication
from lp.services.features.xmlrpc import IFeatureFlagApplication
from lp.services.webapp import LaunchpadXMLRPCView
from lp.services.webapp.interfaces import ILaunchBag
from lp.xmlrpc.interfaces import IPrivateApplication

# NOTE: If you add a traversal here, you should update
# the regular expression in utilities/page-performance-report.ini
class PrivateApplication:
    implements(IPrivateApplication)

    @property
    def mailinglists(self):
        """See `IPrivateApplication`."""
        return getUtility(IMailingListApplication)

    @property
    def authserver(self):
        """See `IPrivateApplication`."""
        return getUtility(IAuthServerApplication)

    @property
    def codehosting(self):
        """See `IPrivateApplication`."""
        return getUtility(ICodehostingApplication)

    @property
    def codeimportscheduler(self):
        """See `IPrivateApplication`."""
        return getUtility(ICodeImportSchedulerApplication)

    @property
    def bugs(self):
        """See `IPrivateApplication`."""
        return getUtility(IPrivateMaloneApplication)

    @property
    def softwarecenteragent(self):
        """See `IPrivateApplication`."""
        return getUtility(ISoftwareCenterAgentApplication)

    @property
    def canonicalsso(self):
        """See `IPrivateApplication`."""
        return getUtility(ICanonicalSSOApplication)

    @property
    def featureflags(self):
        """See `IPrivateApplication`."""
        return getUtility(IFeatureFlagApplication)


class ISelfTest(Interface):
    """XMLRPC external interface for testing the XMLRPC external interface."""

    def make_fault():
        """Returns an xmlrpc fault."""

    def concatenate(string1, string2):
        """Return the concatenation of the two given strings."""

    def hello():
        """Return a greeting to the one calling the method."""

    def raise_exception():
        """Raise an exception."""


class SelfTest(LaunchpadXMLRPCView):

    implements(ISelfTest)

    def make_fault(self):
        """Returns an xmlrpc fault."""
        return xmlrpclib.Fault(666, "Yoghurt and spanners.")

    def concatenate(self, string1, string2):
        """Return the concatenation of the two given strings."""
        return u'%s %s' % (string1, string2)

    def hello(self):
        """Return a greeting to the logged in user."""
        caller = getUtility(ILaunchBag).user
        if caller is not None:
            caller_name = caller.displayname
        else:
            caller_name = "Anonymous"
        return "Hello %s." % caller_name

    def raise_exception(self):
        raise RuntimeError("selftest exception")
