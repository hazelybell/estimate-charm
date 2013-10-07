# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'Karma',
    'KarmaAction',
    'KarmaActionSet',
    'KarmaAssignedEvent',
    'KarmaCache',
    'KarmaCacheManager',
    'KarmaTotalCache',
    'KarmaCategory',
    'KarmaContextMixin',
    ]

from sqlobject import (
    ForeignKey,
    IntCol,
    SQLMultipleJoin,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import Desc
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.karma import (
    IKarma,
    IKarmaAction,
    IKarmaActionSet,
    IKarmaAssignedEvent,
    IKarmaCache,
    IKarmaCacheManager,
    IKarmaCategory,
    IKarmaContext,
    IKarmaTotalCache,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )


class KarmaAssignedEvent:
    """See `IKarmaAssignedEvent`."""

    implements(IKarmaAssignedEvent)

    def __init__(self, object, karma):
        self.object = object
        self.karma = karma


class Karma(SQLBase):
    """See IKarma."""
    implements(IKarma)

    _table = 'Karma'
    _defaultOrder = ['action', 'id']

    person = ForeignKey(
        dbName='person', foreignKey='Person', notNull=True)
    action = ForeignKey(
        dbName='action', foreignKey='KarmaAction', notNull=True)
    product = ForeignKey(
        dbName='product', foreignKey='Product', notNull=False)
    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution', notNull=False)
    sourcepackagename = ForeignKey(
        dbName='sourcepackagename', foreignKey='SourcePackageName',
        notNull=False)
    datecreated = UtcDateTimeCol(
        dbName='datecreated', notNull=True, default=UTC_NOW)


class KarmaAction(SQLBase):
    """See IKarmaAction."""
    implements(IKarmaAction)

    _table = 'KarmaAction'
    sortingColumns = ['category', 'name']
    _defaultOrder = sortingColumns

    name = StringCol(notNull=True, alternateID=True)
    title = StringCol(notNull=True)
    summary = StringCol(notNull=True)
    category = ForeignKey(dbName='category', foreignKey='KarmaCategory',
        notNull=True)
    points = IntCol(dbName='points', notNull=True)


class KarmaActionSet:
    """See IKarmaActionSet."""
    implements(IKarmaActionSet)

    def __iter__(self):
        return iter(KarmaAction.select())

    def getByName(self, name, default=None):
        """See IKarmaActionSet."""
        try:
            return KarmaAction.byName(name)
        except SQLObjectNotFound:
            return default

    def selectByCategory(self, category):
        """See IKarmaActionSet."""
        return KarmaAction.selectBy(category=category)

    def selectByCategoryAndPerson(self, category, person, orderBy=None):
        """See IKarmaActionSet."""
        if orderBy is None:
            orderBy = KarmaAction.sortingColumns
        query = ('KarmaAction.category = %s '
                 'AND Karma.action = KarmaAction.id '
                 'AND Karma.person = %s' % sqlvalues(category.id, person.id))
        return KarmaAction.select(
                query, clauseTables=['Karma'], distinct=True, orderBy=orderBy)


class KarmaCache(SQLBase):
    """See IKarmaCache."""
    implements(IKarmaCache)

    _table = 'KarmaCache'
    _defaultOrder = ['category', 'id']

    person = ForeignKey(
        dbName='person', foreignKey='Person', notNull=True)
    category = ForeignKey(
        dbName='category', foreignKey='KarmaCategory', notNull=False)
    karmavalue = IntCol(
        dbName='karmavalue', notNull=True)
    product = ForeignKey(
        dbName='product', foreignKey='Product', notNull=False)
    project = ForeignKey(
        dbName='project', foreignKey='ProjectGroup', notNull=False)
    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution', notNull=False)
    sourcepackagename = ForeignKey(
        dbName='sourcepackagename', foreignKey='SourcePackageName',
        notNull=False)


class KarmaCacheManager:
    """See IKarmaCacheManager."""
    implements(IKarmaCacheManager)

    def new(self, value, person_id, category_id, product_id=None,
            distribution_id=None, sourcepackagename_id=None, project_id=None):
        """See IKarmaCacheManager."""
        return KarmaCache(
            karmavalue=value, person=person_id, category=category_id,
            product=product_id, distribution=distribution_id,
            sourcepackagename=sourcepackagename_id, project=project_id)

    def updateKarmaValue(self, value, person_id, category_id, product_id=None,
                         distribution_id=None, sourcepackagename_id=None,
                         project_id=None):
        """See IKarmaCacheManager."""
        entry = self._getEntry(
            person_id=person_id, category_id=category_id,
            product_id=product_id, distribution_id=distribution_id,
            project_id=project_id, sourcepackagename_id=sourcepackagename_id)
        if entry is None:
            raise NotFoundError("KarmaCache not found: %s" % vars())
        else:
            entry.karmavalue = value
            entry.syncUpdate()

    def _getEntry(self, person_id, category_id, product_id=None,
                  distribution_id=None, sourcepackagename_id=None,
                  project_id=None):
        """Return the KarmaCache entry with the given arguments.

        Return None if it's not found.
        """
        return IStore(KarmaCache).find(
            KarmaCache,
            KarmaCache.personID == person_id,
            KarmaCache.categoryID == category_id,
            KarmaCache.productID == product_id,
            KarmaCache.projectID == project_id,
            KarmaCache.distributionID == distribution_id,
            KarmaCache.sourcepackagenameID == sourcepackagename_id).one()


class KarmaTotalCache(SQLBase):
    """A cached value of the total of a person's karma (all categories)."""
    implements(IKarmaTotalCache)

    _table = 'KarmaTotalCache'
    _defaultOrder = ['id']

    person = ForeignKey(dbName='person', foreignKey='Person', notNull=True)
    karma_total = IntCol(dbName='karma_total', notNull=True)


class KarmaCategory(SQLBase):
    """See IKarmaCategory."""
    implements(IKarmaCategory)

    _defaultOrder = ['title', 'id']

    name = StringCol(notNull=True, alternateID=True)
    title = StringCol(notNull=True)
    summary = StringCol(notNull=True)

    karmaactions = SQLMultipleJoin(
        'KarmaAction', joinColumn='category', orderBy='name')


class KarmaContextMixin:
    """A mixin to be used by classes implementing IKarmaContext.

    This would be better as an adapter for Product and Distribution, but a
    mixin should be okay for now.
    """

    implements(IKarmaContext)

    def getTopContributorsGroupedByCategory(self, limit=None):
        """See IKarmaContext."""
        contributors_by_category = {}
        for category in KarmaCategory.select():
            results = self.getTopContributors(category=category, limit=limit)
            if results:
                contributors_by_category[category] = results
        return contributors_by_category

    def getTopContributors(self, category=None, limit=None):
        """See IKarmaContext."""
        from lp.registry.model.person import Person
        store = IStore(Person)
        if IProduct.providedBy(self):
            condition = KarmaCache.productID == self.id
        elif IDistribution.providedBy(self):
            condition = KarmaCache.distributionID == self.id
        elif IProjectGroup.providedBy(self):
            condition = KarmaCache.projectID == self.id
        else:
            raise AssertionError(
                "Not a product, project or distribution: %r" % self)

        if category is not None:
            category = category.id
        contributors = store.find(
            (Person, KarmaCache.karmavalue),
            KarmaCache.personID == Person.id,
            KarmaCache.categoryID == category, condition).order_by(
                Desc(KarmaCache.karmavalue)).config(limit=limit)
        return list(contributors)
