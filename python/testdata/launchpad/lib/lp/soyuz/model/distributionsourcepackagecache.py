# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['DistributionSourcePackageCache', ]

from operator import itemgetter

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.soyuz.interfaces.distributionsourcepackagecache import (
    IDistributionSourcePackageCache,
    )
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease


class DistributionSourcePackageCache(SQLBase):
    implements(IDistributionSourcePackageCache)
    _table = 'DistributionSourcePackageCache'

    archive = ForeignKey(dbName='archive',
        foreignKey='Archive', notNull=True)
    distribution = ForeignKey(dbName='distribution',
        foreignKey='Distribution', notNull=True)
    sourcepackagename = ForeignKey(dbName='sourcepackagename',
        foreignKey='SourcePackageName', notNull=True)

    name = StringCol(notNull=False, default=None)
    binpkgnames = StringCol(notNull=False, default=None)
    binpkgsummaries = StringCol(notNull=False, default=None)
    binpkgdescriptions = StringCol(notNull=False, default=None)
    changelog = StringCol(notNull=False, default=None)

    @property
    def distributionsourcepackage(self):
        """See IDistributionSourcePackageCache."""

        # import here to avoid circular imports
        from lp.registry.model.distributionsourcepackage import (
            DistributionSourcePackage)

        return DistributionSourcePackage(self.distribution,
            self.sourcepackagename)

    @classmethod
    def _find(cls, distro, archive=None):
        """The set of all source package info caches for this distribution.

        If 'archive' is not given it will return all caches stored for the
        distribution main archives (PRIMARY and PARTNER).
        """
        if archive is not None:
            archives = [archive.id]
        else:
            archives = distro.all_distro_archive_ids

        result = IStore(DistributionSourcePackageCache).find(
            (DistributionSourcePackageCache, SourcePackageName),
            DistributionSourcePackageCache.distribution == distro,
            DistributionSourcePackageCache.archiveID.is_in(archives),
            SourcePackageName.id ==
                DistributionSourcePackageCache.sourcepackagenameID,
            ).order_by(DistributionSourcePackageCache.name)
        return DecoratedResultSet(result, itemgetter(0))

    @classmethod
    def removeOld(cls, distro, archive, log):
        """Delete any cache records for removed packages.

        Also purges all existing cache records for disabled archives.

        :param archive: target `IArchive`.
        :param log: the context logger object able to print DEBUG level
            messages.
        """

        # Get the set of source package names to deal with.
        spns = set(SourcePackageName.select("""
            SourcePackagePublishingHistory.distroseries =
                DistroSeries.id AND
            DistroSeries.distribution = %s AND
            Archive.id = %s AND
            SourcePackagePublishingHistory.archive = Archive.id AND
            SourcePackagePublishingHistory.sourcepackagename =
                SourcePackageName.id AND
            SourcePackagePublishingHistory.dateremoved is NULL AND
            Archive.enabled = TRUE
            """ % sqlvalues(distro, archive),
            distinct=True,
            clauseTables=[
                'Archive',
                'DistroSeries',
                'SourcePackagePublishingHistory']))

        # Remove the cache entries for packages we no longer publish.
        for cache in cls._find(distro, archive):
            if cache.sourcepackagename not in spns:
                log.debug(
                    "Removing source cache for '%s' (%s)"
                    % (cache.name, cache.id))
                cache.destroySelf()

    @classmethod
    def _update(cls, distro, sourcepackagename, archive, log):
        """Update cached source package details.

        Update cache details for a given ISourcePackageName, including
        generated binarypackage names, summary and description fti.
        'log' is required and only prints debug level information.
        """

        # Get the set of published sourcepackage releases.
        sprs = list(SourcePackageRelease.select("""
            SourcePackageRelease.id =
                SourcePackagePublishingHistory.sourcepackagerelease AND
            SourcePackagePublishingHistory.sourcepackagename = %s AND
            SourcePackagePublishingHistory.distroseries =
                DistroSeries.id AND
            DistroSeries.distribution = %s AND
            SourcePackagePublishingHistory.archive = %s AND
            SourcePackagePublishingHistory.dateremoved is NULL
            """ % sqlvalues(sourcepackagename, distro, archive),
            orderBy='id',
            clauseTables=['SourcePackagePublishingHistory', 'DistroSeries'],
            distinct=True))

        if len(sprs) == 0:
            log.debug("No sources releases found.")
            return

        # Find or create the cache entry.
        cache = DistributionSourcePackageCache.selectOne("""
            distribution = %s AND
            archive = %s AND
            sourcepackagename = %s
            """ % sqlvalues(distro, archive, sourcepackagename))
        if cache is None:
            log.debug("Creating new source cache entry.")
            cache = DistributionSourcePackageCache(
                archive=archive,
                distribution=distro,
                sourcepackagename=sourcepackagename)

        # Make sure the name is correct.
        cache.name = sourcepackagename.name

        # Get the sets of binary package names, summaries, descriptions.

        # XXX Julian 2007-04-03:
        # This bit of code needs fixing up, it is doing stuff that
        # really needs to be done in SQL, such as sorting and uniqueness.
        # This would also improve the performance.
        binpkgnames = set()
        binpkgsummaries = set()
        binpkgdescriptions = set()
        sprchangelog = set()
        for spr in sprs:
            log.debug("Considering source version %s" % spr.version)
            # changelog may be empty, in which case we don't want to add it
            # to the set as the join would fail below.
            if spr.changelog_entry is not None:
                sprchangelog.add(spr.changelog_entry)
            binpkgs = BinaryPackageRelease.select("""
                BinaryPackageRelease.build = BinaryPackageBuild.id AND
                BinaryPackageBuild.source_package_release = %s
                """ % sqlvalues(spr.id),
                clauseTables=['BinaryPackageBuild'])
            for binpkg in binpkgs:
                log.debug("Considering binary '%s'" % binpkg.name)
                binpkgnames.add(binpkg.name)
                binpkgsummaries.add(binpkg.summary)
                binpkgdescriptions.add(binpkg.description)

        # Update the caches.
        cache.binpkgnames = ' '.join(sorted(binpkgnames))
        cache.binpkgsummaries = ' '.join(sorted(binpkgsummaries))
        cache.binpkgdescriptions = ' '.join(sorted(binpkgdescriptions))
        cache.changelog = ' '.join(sorted(sprchangelog))

    @classmethod
    def updateAll(cls, distro, archive, log, ztm, commit_chunk=500):
        """Update the source package cache.

        Consider every non-REMOVED sourcepackage and entirely skips updates
        for disabled archives.

        :param archive: target `IArchive`;
        :param log: logger object for printing debug level information;
        :param ztm:  transaction used for partial commits, every chunk of
            'commit_chunk' updates is committed;
        :param commit_chunk: number of updates before commit, defaults to 500.

        :return the number packages updated done
        """
        # Do not create cache entries for disabled archives.
        if not archive.enabled:
            return

        # Get the set of source package names to deal with.
        spns = list(SourcePackageName.select("""
            SourcePackagePublishingHistory.distroseries =
                DistroSeries.id AND
            DistroSeries.distribution = %s AND
            SourcePackagePublishingHistory.archive = %s AND
            SourcePackagePublishingHistory.sourcepackagename =
                SourcePackageName.id AND
            SourcePackagePublishingHistory.dateremoved is NULL
            """ % sqlvalues(distro, archive),
            distinct=True,
            orderBy="name",
            clauseTables=['SourcePackagePublishingHistory', 'DistroSeries']))

        number_of_updates = 0
        chunk_size = 0
        for spn in spns:
            log.debug("Considering source '%s'" % spn.name)
            cls._update(distro, spn, archive, log)
            chunk_size += 1
            number_of_updates += 1
            if chunk_size == commit_chunk:
                chunk_size = 0
                log.debug("Committing")
                ztm.commit()

        return number_of_updates
