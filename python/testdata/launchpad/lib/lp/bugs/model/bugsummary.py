# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BugSummary Storm database classes."""

__metaclass__ = type
__all__ = [
    'BugSummary',
    'CombineBugSummaryConstraint',
    'get_bugsummary_filter_for_user',
    ]

from storm.base import Storm
from storm.expr import (
    And,
    Or,
    Select,
    SQL,
    With,
    )
from storm.properties import (
    Bool,
    Int,
    Unicode,
    )
from storm.references import Reference
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.bugs.interfaces.bugsummary import (
    IBugSummary,
    IBugSummaryDimension,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    BugTaskStatusSearch,
    )
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.model.accesspolicy import (
    AccessPolicy,
    AccessPolicyGrant,
    )
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.milestone import Milestone
from lp.registry.model.person import Person
from lp.registry.model.product import Product
from lp.registry.model.productseries import ProductSeries
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.enumcol import EnumCol


class BugSummary(Storm):
    """BugSummary Storm database class."""

    implements(IBugSummary)

    __storm_table__ = 'combinedbugsummary'

    id = Int(primary=True)
    count = Int()

    product_id = Int(name='product')
    product = Reference(product_id, Product.id)

    productseries_id = Int(name='productseries')
    productseries = Reference(productseries_id, ProductSeries.id)

    distribution_id = Int(name='distribution')
    distribution = Reference(distribution_id, Distribution.id)

    distroseries_id = Int(name='distroseries')
    distroseries = Reference(distroseries_id, DistroSeries.id)

    sourcepackagename_id = Int(name='sourcepackagename')
    sourcepackagename = Reference(sourcepackagename_id, SourcePackageName.id)

    milestone_id = Int(name='milestone')
    milestone = Reference(milestone_id, Milestone.id)

    status = EnumCol(
        dbName='status', schema=(BugTaskStatus, BugTaskStatusSearch))

    importance = EnumCol(dbName='importance', schema=BugTaskImportance)

    tag = Unicode()

    viewed_by_id = Int(name='viewed_by')
    viewed_by = Reference(viewed_by_id, Person.id)
    access_policy_id = Int(name='access_policy')
    access_policy = Reference(access_policy_id, AccessPolicy.id)

    has_patch = Bool()


class CombineBugSummaryConstraint:
    """A class to combine two separate bug summary constraints.

    This is useful for querying on multiple related dimensions (e.g. milestone
    + sourcepackage) - and essential when a dimension is not unique to a
    context.
    """

    implements(IBugSummaryDimension)

    def __init__(self, *dimensions):
        self.dimensions = map(
            lambda x:
            removeSecurityProxy(x.getBugSummaryContextWhereClause()),
            dimensions)

    def getBugSummaryContextWhereClause(self):
        """See `IBugSummaryDimension`."""
        return And(*self.dimensions)


def get_bugsummary_filter_for_user(user):
    """Build a Storm expression to filter BugSummary by visibility.

    :param user: The user for which visible rows should be calculated.
    :return: (with_clauses, where_clauses)
    """
    # Admins get to see every bug, everyone else only sees bugs
    # viewable by them-or-their-teams.
    # Note that because admins can see every bug regardless of
    # subscription they will see rather inflated counts. Admins get to
    # deal.
    public_filter = And(
        BugSummary.viewed_by_id == None,
        BugSummary.access_policy_id == None)
    if user is None:
        return [], [public_filter]
    elif IPersonRoles(user).in_admin:
        return [], []
    else:
        with_clauses = [
            With(
                'teams',
                Select(
                    TeamParticipation.teamID, tables=[TeamParticipation],
                    where=(TeamParticipation.personID == user.id))),
            With(
                'policies',
                Select(
                    AccessPolicyGrant.policy_id,
                    tables=[AccessPolicyGrant],
                    where=(
                        AccessPolicyGrant.grantee_id.is_in(
                            SQL("SELECT team FROM teams"))))),
            ]
        where_clauses = [Or(
            public_filter,
            BugSummary.viewed_by_id.is_in(
                SQL("SELECT team FROM teams")),
            BugSummary.access_policy_id.is_in(
                SQL("SELECT policy FROM policies")))]
        return with_clauses, where_clauses
