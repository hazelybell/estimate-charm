# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the GNU
# Affero General Public License version 3 (see the file LICENSE).

"""Soyuz vocabularies."""

__metaclass__ = type

__all__ = [
    'ComponentVocabulary',
    'FilteredDistroArchSeriesVocabulary',
    'PackageReleaseVocabulary',
    'PPAVocabulary',
    'ProcessorVocabulary',
    ]

from storm.locals import (
    And,
    Or,
    )
from zope.component import getUtility
from zope.interface import implements
from zope.schema.vocabulary import SimpleTerm

from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.person import Person
from lp.services.database.interfaces import IStore
from lp.services.database.stormexpr import fti_search
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.vocabulary import (
    IHugeVocabulary,
    NamedSQLObjectVocabulary,
    SQLObjectVocabularyBase,
    )
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.model.archive import Archive
from lp.soyuz.model.component import Component
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.processor import Processor
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease


class ComponentVocabulary(SQLObjectVocabularyBase):

    _table = Component
    _orderBy = 'name'

    def toTerm(self, obj):
        return SimpleTerm(obj, obj.id, obj.name)


class FilteredDistroArchSeriesVocabulary(SQLObjectVocabularyBase):
    """All arch series of a particular distribution."""

    _table = DistroArchSeries
    _orderBy = ['DistroSeries.version', 'architecturetag', 'id']

    def toTerm(self, obj):
        name = "%s %s (%s)" % (obj.distroseries.distribution.name,
                               obj.distroseries.name, obj.architecturetag)
        return SimpleTerm(obj, obj.id, name)

    def __iter__(self):
        distribution = getUtility(ILaunchBag).distribution
        if distribution:
            results = IStore(DistroSeries).find(
                self._table,
                DistroSeries.id == DistroArchSeries.distroseriesID,
                DistroSeries.distributionID == distribution.id).order_by(
                    *self._orderBy)
            for distroarchseries in results:
                yield self.toTerm(distroarchseries)


class PackageReleaseVocabulary(SQLObjectVocabularyBase):
    _table = SourcePackageRelease
    _orderBy = 'id'

    def toTerm(self, obj):
        return SimpleTerm(
            obj, obj.id, obj.name + " " + obj.version)


class PPAVocabulary(SQLObjectVocabularyBase):

    implements(IHugeVocabulary)

    _table = Archive
    _orderBy = ['Person.name, Archive.name']
    _clauseTables = ['Person']
    _filter = And(
        Person.q.id == Archive.q.ownerID,
        Archive.q.purpose == ArchivePurpose.PPA)
    displayname = 'Select a PPA'
    step_title = 'Search'

    def toTerm(self, archive):
        """See `IVocabulary`."""
        description = archive.description
        if description:
            summary = description.splitlines()[0]
        else:
            summary = "No description available"

        token = '%s/%s' % (archive.owner.name, archive.name)

        return SimpleTerm(archive, token, summary)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        try:
            owner_name, archive_name = token.split('/')
        except ValueError:
            raise LookupError(token)

        clause = And(
            self._filter,
            Person.name == owner_name,
            Archive.name == archive_name)

        obj = self._table.selectOne(
            clause, clauseTables=self._clauseTables)

        if obj is None:
            raise LookupError(token)
        else:
            return self.toTerm(obj)

    def search(self, query, vocab_filter=None):
        """Return a resultset of archives.

        This is a helper required by `SQLObjectVocabularyBase.searchForTerms`.
        """
        if not query:
            return self.emptySelectResults()

        query = query.lower()

        try:
            owner_name, archive_name = query.split('/')
        except ValueError:
            clause = And(
                self._filter,
                Or(fti_search(Archive, query), fti_search(Person, query)))
        else:
            clause = And(
                self._filter, Person.name == owner_name,
                Archive.name == archive_name)

        return self._table.select(
            clause, orderBy=self._orderBy, clauseTables=self._clauseTables)


class ProcessorVocabulary(NamedSQLObjectVocabulary):

    displayname = 'Select a processor'
    _table = Processor
    _orderBy = 'name'
