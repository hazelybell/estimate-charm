# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Class that implements the IPersonRoles interface."""

__metaclass__ = type
__all__ = ['PersonRoles']

from zope.component import (
    adapts,
    getUtility,
    )
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.role import (
    IHasDrivers,
    IPersonRoles,
    )


class PersonRoles:
    implements(IPersonRoles)
    adapts(IPerson)

    def __init__(self, person):
        self.person = person
        self._celebrities = getUtility(ILaunchpadCelebrities)
        # Use an unproxied inTeam() method for security checks.
        self.inTeam = removeSecurityProxy(self.person).inTeam

    def __getattr__(self, name):
        """Handle all in_* attributes."""
        prefix = 'in_'
        errortext = "'PersonRoles' object has no attribute '%s'" % name
        if not name.startswith(prefix):
            raise AttributeError(errortext)
        attribute = name[len(prefix):]
        try:
            return self.inTeam(getattr(self._celebrities, attribute))
        except AttributeError:
            raise AttributeError(errortext)

    @property
    def id(self):
        return self.person.id

    def isOwner(self, obj):
        """See IPersonRoles."""
        return self.inTeam(obj.owner)

    def isBugSupervisor(self, obj):
        """See IPersonRoles."""
        return (IHasBugSupervisor.providedBy(obj)
                and self.inTeam(obj.bug_supervisor))

    def isDriver(self, obj):
        """See IPersonRoles."""
        return self.inTeam(obj.driver)

    def isOneOfDrivers(self, obj):
        """See IPersonRoles."""
        if not IHasDrivers.providedBy(obj):
            return self.isDriver(obj)
        for driver in obj.drivers:
            if self.inTeam(driver):
                return True
        return False

    def isOneOf(self, obj, attributes):
        """See IPersonRoles."""
        for attr in attributes:
            role = getattr(obj, attr)
            if self.inTeam(role):
                return True
        return False
