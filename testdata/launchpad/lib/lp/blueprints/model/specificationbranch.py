# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes for linking specifications and branches."""

__metaclass__ = type

__all__ = [
    "SpecificationBranch",
    "SpecificationBranchSet",
    ]

from sqlobject import (
    ForeignKey,
    IN,
    )
from zope.interface import implements

from lp.blueprints.interfaces.specificationbranch import (
    ISpecificationBranch,
    ISpecificationBranchSet,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase


class SpecificationBranch(SQLBase):
    """See `ISpecificationBranch`."""
    implements(ISpecificationBranch)

    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    specification = ForeignKey(dbName="specification",
                               foreignKey="Specification", notNull=True)
    branch = ForeignKey(dbName="branch", foreignKey="Branch", notNull=True)

    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)


class SpecificationBranchSet:
    """See `ISpecificationBranchSet`."""
    implements(ISpecificationBranchSet)

    def getSpecificationBranchesForBranches(self, branches, user):
        """See `ISpecificationBranchSet`."""
        branch_ids = [branch.id for branch in branches]
        if not branch_ids:
            return []

        # When specification gain the ability to be private, this
        # method will need to be updated to enforce the privacy checks.
        return SpecificationBranch.select(
            IN(SpecificationBranch.q.branchID, branch_ids))
