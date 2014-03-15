# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad Pillars share a namespace.

Pillars are currently Product, ProjectGroup and Distribution.
"""

__metaclass__ = type

import warnings

from sqlobject import (
    BoolCol,
    ForeignKey,
    StringCol,
    )
from storm.expr import LeftJoin
from storm.info import ClassAlias
from storm.locals import SQL
from storm.store import Store
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.app.errors import NotFoundError
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.pillar import (
    IPillarName,
    IPillarNameSet,
    IPillarPerson,
    IPillarPersonFactory,
    )
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    )
from lp.registry.interfaces.projectgroup import IProjectGroupSet
from lp.registry.model.featuredproject import FeaturedProject
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import ensure_unicode


__all__ = [
    'pillar_sort_key',
    'HasAliasMixin',
    'PillarNameSet',
    'PillarName',
    'PillarPerson',
    ]


def pillar_sort_key(pillar):
    """A sort key for a set of pillars. We want:

          - products first, alphabetically
          - distributions, with ubuntu first and the rest alphabetically
    """
    product_name = None
    distribution_name = None
    if IProduct.providedBy(pillar):
        product_name = pillar.name
    elif IDistribution.providedBy(pillar):
        distribution_name = pillar.name
    # Move ubuntu to the top.
    if distribution_name == 'ubuntu':
        distribution_name = '-'

    return (distribution_name, product_name)


class PillarNameSet:
    implements(IPillarNameSet)

    def __contains__(self, name):
        """See `IPillarNameSet`."""
        name = ensure_unicode(name)
        result = IStore(PillarName).execute("""
            SELECT TRUE
            FROM PillarName
            WHERE (id IN (SELECT alias_for FROM PillarName WHERE name=?)
                   OR name=?)
                AND alias_for IS NULL
                AND active IS TRUE
            """, [name, name])
        return result.get_one() is not None

    def __getitem__(self, name):
        """See `IPillarNameSet`."""
        pillar = self.getByName(name, ignore_inactive=True)
        if pillar is None:
            raise NotFoundError(name)
        return pillar

    def getByName(self, name, ignore_inactive=False):
        """Return the pillar with the given name.

        If ignore_inactive is True, then only active pillars are considered.

        If no pillar is found, None is returned.
        """
        # We could attempt to do this in a single database query, but I
        # expect that doing two queries will be faster that OUTER JOINing
        # the Project, Product and Distribution tables (and this approach
        # works better with SQLObject too.

        # Retrieve information out of the PillarName table.
        query = """
            SELECT id, product, project, distribution
            FROM PillarName
            WHERE (id = (SELECT alias_for FROM PillarName WHERE name=?)
                   OR name=?)
                AND alias_for IS NULL%s
            LIMIT 1
            """
        if ignore_inactive:
            query %= " AND active IS TRUE"
        else:
            query %= ""
        name = ensure_unicode(name)
        result = IStore(PillarName).execute(query, [name, name])
        row = result.get_one()
        if row is None:
            return None

        assert len([column for column in row[1:] if column is None]) == 2, (
            "One (and only one) of product, project or distribution may be "
            "NOT NULL: %s" % row[1:])

        id, product, project, distribution = row

        if product is not None:
            return getUtility(IProductSet).get(product)
        elif project is not None:
            return getUtility(IProjectGroupSet).get(project)
        else:
            return getUtility(IDistributionSet).get(distribution)

    def build_search_query(self, text, extra_columns=()):
        """Query parameters shared by search() and count_search_matches().

        :returns: Storm ResultSet object
        """
        # These classes are imported in this method to prevent an import loop.
        from lp.registry.model.product import Product
        from lp.registry.model.projectgroup import ProjectGroup
        from lp.registry.model.distribution import Distribution
        OtherPillarName = ClassAlias(PillarName)
        origin = [
            PillarName,
            LeftJoin(
                OtherPillarName, PillarName.alias_for == OtherPillarName.id),
            LeftJoin(Product, PillarName.product == Product.id),
            LeftJoin(ProjectGroup, PillarName.project == ProjectGroup.id),
            LeftJoin(
                Distribution, PillarName.distribution == Distribution.id),
            ]
        conditions = SQL('''
            PillarName.active = TRUE
            AND (PillarName.name = lower(%(text)s) OR

                 Product.fti @@ ftq(%(text)s) OR
                 lower(Product.title) = lower(%(text)s) OR

                 Project.fti @@ ftq(%(text)s) OR
                 lower(Project.title) = lower(%(text)s) OR

                 Distribution.fti @@ ftq(%(text)s) OR
                 lower(Distribution.title) = lower(%(text)s)
                )
            ''' % sqlvalues(text=ensure_unicode(text)))
        columns = [
            PillarName, OtherPillarName, Product, ProjectGroup, Distribution]
        for column in extra_columns:
            columns.append(column)
        return IStore(PillarName).using(*origin).find(
            tuple(columns), conditions)

    def count_search_matches(self, text):
        result = self.build_search_query(text)
        return result.count()

    def search(self, text, limit):
        """See `IPillarSet`."""
        # Avoid circular import.
        from lp.registry.model.product import ProductWithLicenses
        if limit is None:
            limit = config.launchpad.default_batch_size

        # Pull out the licences as a subselect which is converted
        # into a PostgreSQL array so that multiple licences per product
        # can be retrieved in a single row for each product.
        extra_column = ProductWithLicenses.composeLicensesColumn()
        result = self.build_search_query(text, [extra_column])

        # If the search text matches the name or title of the
        # Product, Project, or Distribution exactly, then this
        # row should get the highest search rank (9999999).
        # Each row in the PillarName table will join with only one
        # of either the Product, Project, or Distribution tables,
        # so the coalesce() is necessary to find the rank() which
        # is not null.
        result.order_by(SQL('''
            (CASE WHEN PillarName.name = lower(%(text)s)
                      OR lower(Product.title) = lower(%(text)s)
                      OR lower(Project.title) = lower(%(text)s)
                      OR lower(Distribution.title) = lower(%(text)s)
                THEN 9999999
                ELSE coalesce(rank(Product.fti, ftq(%(text)s)),
                              rank(Project.fti, ftq(%(text)s)),
                              rank(Distribution.fti, ftq(%(text)s)))
            END) DESC, PillarName.name
            ''' % sqlvalues(text=text)))
        # People shouldn't be calling this method with too big limits
        longest_expected = 2 * config.launchpad.default_batch_size
        if limit > longest_expected:
            warnings.warn(
                "The search limit (%s) was greater "
                "than the longest expected size (%s)"
                % (limit, longest_expected),
                stacklevel=2)
        pillars = []
        # Prefill pillar.product.licenses.
        for pillar_name, other, product, project, distro, licenses in (
            result[:limit]):
            pillar = pillar_name.pillar
            if IProduct.providedBy(pillar):
                pillar = ProductWithLicenses(pillar, licenses)
            pillars.append(pillar)
        return pillars

    def add_featured_project(self, project):
        """See `IPillarSet`."""
        query = """
            PillarName.name = %s
            AND PillarName.id = FeaturedProject.pillar_name
            """ % sqlvalues(project.name)
        existing = FeaturedProject.selectOne(
            query, clauseTables=['PillarName'])
        if existing is None:
            pillar_name = PillarName.selectOneBy(name=project.name)
            return FeaturedProject(pillar_name=pillar_name.id)

    def remove_featured_project(self, project):
        """See `IPillarSet`."""
        query = """
            PillarName.name = %s
            AND PillarName.id = FeaturedProject.pillar_name
            """ % sqlvalues(project.name)
        existing = FeaturedProject.selectOne(
            query, clauseTables=['PillarName'])
        if existing is not None:
            existing.destroySelf()

    @property
    def featured_projects(self):
        """See `IPillarSet`."""

        query = "PillarName.id = FeaturedProject.pillar_name"
        return [pillar_name.pillar for pillar_name in PillarName.select(
                    query, clauseTables=['FeaturedProject'])]


class PillarName(SQLBase):
    implements(IPillarName)

    _table = 'PillarName'
    _defaultOrder = 'name'

    name = StringCol(
        dbName='name', notNull=True, unique=True, alternateID=True)
    product = ForeignKey(
        foreignKey='Product', dbName='product')
    project = ForeignKey(
        foreignKey='ProjectGroup', dbName='project')
    distribution = ForeignKey(
        foreignKey='Distribution', dbName='distribution')
    active = BoolCol(dbName='active', notNull=True, default=True)
    alias_for = ForeignKey(
        foreignKey='PillarName', dbName='alias_for', default=None)

    @property
    def pillar(self):
        pillar_name = self
        if self.alias_for is not None:
            pillar_name = self.alias_for

        if pillar_name.distribution is not None:
            return pillar_name.distribution
        elif pillar_name.project is not None:
            return pillar_name.project
        elif pillar_name.product is not None:
            return pillar_name.product
        else:
            raise AssertionError("Unknown pillar type: %s" % pillar_name.name)


class HasAliasMixin:
    """Mixin for classes that implement IHasAlias."""

    @property
    def aliases(self):
        """See `IHasAlias`."""
        aliases = PillarName.selectBy(alias_for=PillarName.byName(self.name))
        return [alias.name for alias in aliases]

    def setAliases(self, names):
        """See `IHasAlias`."""
        store = Store.of(self)
        existing_aliases = set(self.aliases)
        self_pillar = store.find(PillarName, name=self.name).one()
        to_remove = set(existing_aliases).difference(names)
        to_add = set(names).difference(existing_aliases)
        for name in to_add:
            assert store.find(PillarName, name=name).count() == 0, (
                "This alias is already in use: %s" % name)
            PillarName(name=name, alias_for=self_pillar)
        for name in to_remove:
            pillar_name = store.find(PillarName, name=name).one()
            assert pillar_name.alias_for == self_pillar, (
                "Can't remove an alias of another pillar.")
            store.remove(pillar_name)


class PillarPerson:

    implements(IPillarPerson)

    classProvides(IPillarPersonFactory)

    def __init__(self, pillar, person):
        self.pillar = pillar
        self.person = person

    @staticmethod
    def create(pillar, person):
        return PillarPerson(pillar, person)
