# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BinaryPackageName',
    'BinaryPackageNameSet',
    'BinaryPackageNameVocabulary',
    'getBinaryPackageDescriptions',
]

from sqlobject import (
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import Join
from storm.store import EmptyResultSet
from zope.interface import implements
from zope.schema.vocabulary import SimpleTerm

from lp.app.errors import NotFoundError
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import ensure_unicode
from lp.services.webapp.vocabulary import (
    BatchedCountableIterator,
    NamedSQLObjectHugeVocabulary,
    )
from lp.soyuz.interfaces.binarypackagename import (
    IBinaryPackageName,
    IBinaryPackageNameSet,
    )
from lp.soyuz.interfaces.publishing import active_publishing_status
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease


class BinaryPackageName(SQLBase):

    implements(IBinaryPackageName)
    _table = 'BinaryPackageName'
    name = StringCol(dbName='name', notNull=True, unique=True,
                     alternateID=True)

    def __unicode__(self):
        return self.name

    def __repr__(self):
        return "<BinaryPackageName at %X name=%r>" % (id(self), self.name)


class BinaryPackageNameSet:
    implements(IBinaryPackageNameSet)

    def __getitem__(self, name):
        """See `IBinaryPackageNameSet`."""
        try:
            return BinaryPackageName.byName(name)
        except SQLObjectNotFound:
            raise NotFoundError(name)

    def getAll(self):
        """See `IBinaryPackageNameSet`."""
        return BinaryPackageName.select()

    def queryByName(self, name):
        return IStore(BinaryPackageName).find(
            BinaryPackageName, name=ensure_unicode(name)).one()

    def new(self, name):
        return BinaryPackageName(name=ensure_unicode(name))

    def ensure(self, name):
        """Ensure that the given BinaryPackageName exists, creating it
        if necessary.

        Returns the BinaryPackageName
        """
        name = ensure_unicode(name)
        try:
            return self[name]
        except NotFoundError:
            return self.new(name)

    getOrCreateByName = ensure

    def getNotNewByNames(self, name_ids, distroseries, archive_ids):
        """See `IBinaryPackageNameSet`."""
        # Circular imports.
        from lp.soyuz.model.distroarchseries import DistroArchSeries
        from lp.soyuz.model.publishing import BinaryPackagePublishingHistory

        if len(name_ids) == 0:
            return EmptyResultSet()

        return IStore(BinaryPackagePublishingHistory).using(
            BinaryPackagePublishingHistory,
            Join(BinaryPackageName,
                BinaryPackagePublishingHistory.binarypackagenameID ==
                BinaryPackageName.id),
            Join(DistroArchSeries,
                BinaryPackagePublishingHistory.distroarchseriesID ==
                DistroArchSeries.id)
            ).find(
                BinaryPackageName,
                DistroArchSeries.distroseries == distroseries,
                BinaryPackagePublishingHistory.status.is_in(
                    active_publishing_status),
                BinaryPackagePublishingHistory.archiveID.is_in(archive_ids),
                BinaryPackagePublishingHistory.binarypackagenameID.is_in(
                    name_ids)).config(distinct=True)


class BinaryPackageNameIterator(BatchedCountableIterator):
    """An iterator for BinaryPackageNameVocabulary.

    Builds descriptions based on releases of that binary package name.
    """

    def getTermsWithDescriptions(self, results):
        # Prefill the descriptions dictionary with the latest
        # description uploaded for that package name.
        descriptions = getBinaryPackageDescriptions(results)
        return [SimpleTerm(obj, obj.name,
                    descriptions.get(obj.name, "Not uploaded"))
                for obj in results]


class BinaryPackageNameVocabulary(NamedSQLObjectHugeVocabulary):
    """A vocabulary for searching for binary package names."""
    _table = BinaryPackageName
    _orderBy = 'name'
    displayname = 'Select a Binary Package'
    iterator = BinaryPackageNameIterator


def getBinaryPackageDescriptions(results, use_names=False,
                                 max_title_length=50):
    """Return a dict of descriptions keyed by package name.

    See sourcepackage.py:getSourcePackageDescriptions, which is analogous.
    """
    if len(list(results)) < 1:
        return {}
    if use_names:
        clause = ("BinaryPackageName.name in %s" %
                 sqlvalues([pn.name for pn in results]))
    else:
        clause = ("BinaryPackageName.id in %s" %
                 sqlvalues([bpn.id for bpn in results]))

    descriptions = {}
    releases = BinaryPackageRelease.select(
        """BinaryPackageRelease.binarypackagename =
            BinaryPackageName.id AND
           %s""" % clause,
        clauseTables=["BinaryPackageRelease", "BinaryPackageName"],
        orderBy=["-BinaryPackageRelease.datecreated"])

    for release in releases:
        binarypackagename = release.binarypackagename.name
        if binarypackagename not in descriptions:
            description = release.description.strip().replace("\n", " ")
            if len(description) > max_title_length:
                description = (release.description[:max_title_length]
                              + "...")
            descriptions[binarypackagename] = description
    return descriptions
