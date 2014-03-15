# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'DistroSeriesPackageCache',
    ]

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from storm.locals import (
    Desc,
    RawStr,
    )
from zope.interface import implements

from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.soyuz.interfaces.distroseriespackagecache import (
    IDistroSeriesPackageCache,
    )
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.publishing import BinaryPackagePublishingHistory


class DistroSeriesPackageCache(SQLBase):
    implements(IDistroSeriesPackageCache)
    _table = 'DistroSeriesPackageCache'

    archive = ForeignKey(dbName='archive',
        foreignKey='Archive', notNull=True)
    distroseries = ForeignKey(dbName='distroseries',
        foreignKey='DistroSeries', notNull=True)
    binarypackagename = ForeignKey(dbName='binarypackagename',
        foreignKey='BinaryPackageName', notNull=True)

    fti = RawStr(allow_none=True, default=None)
    name = StringCol(notNull=False, default=None)
    summary = StringCol(notNull=False, default=None)
    description = StringCol(notNull=False, default=None)
    summaries = StringCol(notNull=False, default=None)
    descriptions = StringCol(notNull=False, default=None)

    @classmethod
    def _find(cls, distroseries, archive=None):
        """All of the cached binary package records for this distroseries.

        If 'archive' is not given it will return all caches stored for the
        distroseries main archives (PRIMARY and PARTNER).
        """
        if archive is not None:
            archives = [archive.id]
        else:
            archives = distroseries.distribution.all_distro_archive_ids

        return IStore(cls).find(
            cls,
            cls.distroseries == distroseries,
            cls.archiveID.is_in(archives)).order_by(cls.name)

    @classmethod
    def removeOld(cls, distroseries, archive, log):
        """Delete any records that are no longer applicable.

        Consider all binarypackages marked as REMOVED.

        Also purges all existing cache records for disabled archives.

        :param archive: target `IArchive`.
        :param log: the context logger object able to print DEBUG level
            messages.
        """
        # get the set of package names that should be there
        bpns = set(BinaryPackageName.select("""
            BinaryPackagePublishingHistory.distroarchseries =
                DistroArchSeries.id AND
            DistroArchSeries.distroseries = %s AND
            Archive.id = %s AND
            BinaryPackagePublishingHistory.archive = Archive.id AND
            BinaryPackagePublishingHistory.binarypackagerelease =
                BinaryPackageRelease.id AND
            BinaryPackagePublishingHistory.binarypackagename =
                BinaryPackageName.id AND
            BinaryPackagePublishingHistory.dateremoved is NULL AND
            Archive.enabled = TRUE
            """ % sqlvalues(distroseries.id, archive.id),
            distinct=True,
            clauseTables=[
                'Archive',
                'DistroArchSeries',
                'BinaryPackagePublishingHistory',
                'BinaryPackageRelease']))

        # remove the cache entries for binary packages we no longer want
        for cache in cls._find(distroseries, archive):
            if cache.binarypackagename not in bpns:
                log.debug(
                    "Removing binary cache for '%s' (%s)"
                    % (cache.name, cache.id))
                cache.destroySelf()

    @classmethod
    def _update(cls, distroseries, binarypackagename, archive, log):
        """Update the package cache for a given IBinaryPackageName

        'log' is required, it should be a logger object able to print
        DEBUG level messages.
        'ztm' is the current trasaction manager used for partial commits
        (in full batches of 100 elements)
        """
        # get the set of published binarypackagereleases
        bprs = IStore(BinaryPackageRelease).find(
            BinaryPackageRelease,
            BinaryPackageRelease.id ==
                BinaryPackagePublishingHistory.binarypackagereleaseID,
            BinaryPackagePublishingHistory.binarypackagename ==
                binarypackagename,
            BinaryPackagePublishingHistory.distroarchseriesID ==
                DistroArchSeries.id,
            DistroArchSeries.distroseries == distroseries,
            BinaryPackagePublishingHistory.archive == archive,
            BinaryPackagePublishingHistory.dateremoved == None)
        bprs = bprs.order_by(Desc(BinaryPackageRelease.datecreated))
        bprs = bprs.config(distinct=True)

        if bprs.count() == 0:
            log.debug("No binary releases found.")
            return

        # find or create the cache entry
        cache = cls.selectOne("""
            distroseries = %s AND
            archive = %s AND
            binarypackagename = %s
            """ % sqlvalues(distroseries, archive, binarypackagename))
        if cache is None:
            log.debug("Creating new binary cache entry.")
            cache = cls(
                archive=archive,
                distroseries=distroseries,
                binarypackagename=binarypackagename)

        # make sure the cached name, summary and description are correct
        cache.name = binarypackagename.name
        cache.summary = bprs[0].summary
        cache.description = bprs[0].description

        # get the sets of binary package summaries, descriptions. there is
        # likely only one, but just in case...

        summaries = set()
        descriptions = set()
        for bpr in bprs:
            log.debug("Considering binary version %s" % bpr.version)
            summaries.add(bpr.summary)
            descriptions.add(bpr.description)

        # and update the caches
        cache.summaries = ' '.join(sorted(summaries))
        cache.descriptions = ' '.join(sorted(descriptions))

    @classmethod
    def updateAll(cls, distroseries, archive, log, ztm, commit_chunk=500):
        """Update the binary package cache

        Consider all binary package names published in this distro series
        and entirely skips updates for disabled archives

        :param archive: target `IArchive`;
        :param log: logger object for printing debug level information;
        :param ztm:  transaction used for partial commits, every chunk of
            'commit_chunk' updates is committed;
        :param commit_chunk: number of updates before commit, defaults to 500.

        :return the number of packages updated.
        """
        # Do not create cache entries for disabled archives.
        if not archive.enabled:
            return

        # Get the set of package names to deal with.
        bpns = IStore(BinaryPackageName).find(
            BinaryPackageName,
            DistroArchSeries.distroseries == distroseries,
            BinaryPackagePublishingHistory.distroarchseriesID ==
                DistroArchSeries.id,
            BinaryPackagePublishingHistory.archive == archive,
            BinaryPackagePublishingHistory.binarypackagename ==
                BinaryPackageName.id,
            BinaryPackagePublishingHistory.dateremoved == None).config(
                distinct=True).order_by(BinaryPackageName.name)

        number_of_updates = 0
        chunk_size = 0
        for bpn in bpns:
            log.debug("Considering binary '%s'" % bpn.name)
            cls._update(distroseries, bpn, archive, log)
            number_of_updates += 1
            chunk_size += 1
            if chunk_size == commit_chunk:
                chunk_size = 0
                log.debug("Committing")
                ztm.commit()

        return number_of_updates
