# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = ['SpecificationSubscription']

from sqlobject import (
    BoolCol,
    ForeignKey,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.blueprints.interfaces.specificationsubscription import (
    ISpecificationSubscription,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    )
from lp.registry.interfaces.person import validate_person
from lp.registry.interfaces.role import IPersonRoles
from lp.services.database.sqlbase import SQLBase


class SpecificationSubscription(SQLBase):
    """A subscription for person to a spec."""

    implements(ISpecificationSubscription)

    _table = 'SpecificationSubscription'
    specification = ForeignKey(dbName='specification',
        foreignKey='Specification', notNull=True)
    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_person, notNull=True)
    essential = BoolCol(notNull=True, default=False)

    def canBeUnsubscribedByUser(self, user):
        """See `ISpecificationSubscription`."""
        if user is None:
            return False
        if not IPersonRoles.providedBy(user):
            user = IPersonRoles(user)
        if (
            user.inTeam(self.specification.owner) or
            user.inTeam(self.person) or
            user.in_admin):
            return True
        # XXX Abel Deuring 2012-11-21, bug=1081677
        # People who subscribed users should be able to unsubscribe
        # them again, similar to branch subscriptions. This is
        # essential if somebody was erroneuosly subscribed to a
        # proprietary or embargoed specification. Unfortunately,
        # SpecificationSubscription does not record who subscribed
        # somebody else, but if the specification is private, we can
        # check who issued the artifact grant.
        artifacts = getUtility(IAccessArtifactSource).find(
            [self.specification])
        wanted = [(artifact, self.person) for artifact in artifacts]
        if len(wanted) == 0:
            return False
        for grant in getUtility(IAccessArtifactGrantSource).find(wanted):
            if user.inTeam(grant.grantor):
                return True
        return False
