# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Logic for bulk copying of source/binary publishing history data."""

__metaclass__ = type

__all__ = [
    'PackageCloner',
    'clone_packages',
    ]


import transaction
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    quote,
    sqlvalues,
    )
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.interfaces.archivearch import IArchiveArchSet
from lp.soyuz.interfaces.packagecloner import IPackageCloner
from lp.soyuz.model.publishing import BinaryPackagePublishingHistory


def clone_packages(origin, destination, distroarchseries_list=None):
    """Copies packages from origin to destination package location.

    Binary packages are only copied for the `DistroArchSeries` pairs
    specified.

    This function is meant to simplify the utilization of the package
    cloning functionality.

    @type origin: PackageLocation
    @param origin: the location from which packages are to be copied.
    @type destination: PackageLocation
    @param destination: the location to which the data is to be copied.
    @type distroarchseries_list: list of pairs of (origin, destination)
        distroarchseries instances.
    @param distroarchseries_list: the binary packages will be copied
        for the distroarchseries pairs specified (if any).
    """
    pkg_cloner = getUtility(IPackageCloner)
    pkg_cloner.clonePackages(origin, destination, distroarchseries_list)


class PackageCloner:
    """Used for copying of various publishing history data across archives.
    """

    implements(IPackageCloner)

    def clonePackages(self, origin, destination, distroarchseries_list=None,
                      processors=None, sourcepackagenames=None,
                      always_create=False):
        """Copies packages from origin to destination package location.

        Binary packages are only copied for the `DistroArchSeries` pairs
        specified.

        @type origin: PackageLocation
        @param origin: the location from which packages are to be copied.
        @type destination: PackageLocation
        @param destination: the location to which the data is to be copied.
        @type distroarchseries_list: list of pairs of (origin, destination)
            distroarchseries instances.
        @param distroarchseries_list: the binary packages will be copied
            for the distroarchseries pairs specified (if any).
        @param processors: the processors to create builds for.
        @type processors: Iterable
        @param sourcepackagenames: the sourcepackages to copy to the
            destination
        @type sourcepackagenames: Iterable
        @param always_create: if we should create builds for every source
            package copied, useful if no binaries are to be copied.
        @type always_create: Boolean
        """
        # First clone the source packages.
        self._clone_source_packages(
            origin, destination, sourcepackagenames)

        # Are we also supposed to clone binary packages from origin to
        # destination distroarchseries pairs?
        if distroarchseries_list is not None:
            for (origin_das, destination_das) in distroarchseries_list:
                self._clone_binary_packages(
                    origin, destination, origin_das, destination_das,
                    sourcepackagenames)

        if processors is None:
            processors = []

        self._create_missing_builds(
            destination.distroseries, destination.archive,
            distroarchseries_list, processors, always_create)

    def _create_missing_builds(self, distroseries, archive,
                               distroarchseries_list, processors,
                               always_create):
        """Create builds for all cloned source packages.

        :param distroseries: the distro series for which to create builds.
        :param archive: the archive for which to create builds.
        :param processors: the list of processors for which to create builds.
        """
        # Avoid circular imports.
        from lp.soyuz.interfaces.publishing import active_publishing_status

        # Listify the architectures to avoid hitting this MultipleJoin
        # multiple times.
        architectures = list(distroseries.architectures)

        # Filter the list of DistroArchSeries so that only the ones
        # specified in processors remain.
        architectures = [architecture for architecture in architectures
             if architecture.processor in processors]

        if len(architectures) == 0:
            return

        # Both, PENDING and PUBLISHED sources will be considered for
        # as PUBLISHED. It's part of the assumptions made in:
        # https://launchpad.net/soyuz/+spec/build-unpublished-source
        sources_published = archive.getPublishedSources(
            distroseries=distroseries, status=active_publishing_status)

        for pubrec in sources_published:
            builds = pubrec.createMissingBuilds(
                architectures_available=architectures)
            # If the last build was sucessful, we should create a new
            # build, since createMissingBuilds() won't.
            if not builds and always_create:
                for arch in architectures:
                    build = pubrec.sourcepackagerelease.createBuild(
                        distro_arch_series=arch, archive=archive,
                        pocket=PackagePublishingPocket.RELEASE)
                    build.queueBuild(suspended=not archive.enabled)
            # Commit to avoid MemoryError: bug 304459
            transaction.commit()

    def _clone_binary_packages(
        self, origin, destination, origin_das, destination_das,
        sourcepackagenames=None):
        """Copy binary publishing data from origin to destination.

        @type origin: PackageLocation
        @param origin: the location from which binary publishing
            records are to be copied.
        @type destination: PackageLocation
        @param destination: the location to which the data is
            to be copied.
        @type origin_das: DistroArchSeries
        @param origin_das: the DistroArchSeries from which to copy
            binary packages
        @type destination_das: DistroArchSeries
        @param destination_das: the DistroArchSeries to which to copy
            binary packages
        @param sourcepackagenames: List of source packages to restrict
            the copy to
        @type sourcepackagenames: Iterable
        """
        use_names = (sourcepackagenames and len(sourcepackagenames) > 0)
        clause_tables = "FROM BinaryPackagePublishingHistory AS bpph"
        if use_names:
            clause_tables += """,
                BinaryPackageRelease AS bpr,
                BinaryPackageBuild AS bpb,
                SourcePackageRelease AS spr,
                SourcePackageName AS spn
                """
        # We do not need to set phased_update_percentage; that is heavily
        # context-dependent and should be set afresh for the new location if
        # required.
        query = """
            INSERT INTO BinaryPackagePublishingHistory (
                binarypackagerelease, distroarchseries, status,
                component, section, priority, archive, datecreated,
                datepublished, pocket, binarypackagename)
            SELECT
                bpph.binarypackagerelease,
                %s as distroarchseries,
                bpph.status,
                bpph.component,
                bpph.section,
                bpph.priority,
                %s as archive,
                %s as datecreated,
                %s as datepublished,
                %s as pocket,
                bpph.binarypackagename
            """ % sqlvalues(
                destination_das, destination.archive, UTC_NOW, UTC_NOW,
                destination.pocket)
        query += clause_tables
        query += """
            WHERE
                bpph.distroarchseries = %s AND
                bpph.status in (%s, %s) AND
                bpph.pocket = %s AND
                bpph.archive = %s
            """ % sqlvalues(
                origin_das,
                PackagePublishingStatus.PENDING,
                PackagePublishingStatus.PUBLISHED,
                origin.pocket, origin.archive)

        if use_names:
            query += """
                AND bpph.binarypackagerelease = bpr.id
                AND bpb.id = bpr.build
                AND bpb.source_package_release = spr.id
                AND spr.sourcepackagename = spn.id
                AND spn.name IN %s
            """ % sqlvalues(sourcepackagenames)

        IStore(BinaryPackagePublishingHistory).execute(query)

    def mergeCopy(self, origin, destination):
        """Please see `IPackageCloner`."""
        # Calculate the package set delta in order to find packages that are
        # obsolete or missing in the target archive.
        self.packageSetDiff(origin, destination)

        # Now copy the fresher or new packages.
        store = IStore(BinaryPackagePublishingHistory)
        store.execute("""
            INSERT INTO SourcePackagePublishingHistory (
                sourcepackagerelease, distroseries, status, component,
                section, archive, datecreated, datepublished, pocket,
                sourcepackagename)
            SELECT
                mcd.s_sourcepackagerelease AS sourcepackagerelease,
                %s AS distroseries, mcd.s_status AS status,
                mcd.s_component AS component, mcd.s_section AS section,
                %s AS archive, %s AS datecreated, %s AS datepublished,
                %s AS pocket,
                sourcepackagename_id
            FROM tmp_merge_copy_data mcd
            WHERE mcd.obsoleted = True OR mcd.missing = True
            """ % sqlvalues(
                destination.distroseries, destination.archive, UTC_NOW,
                UTC_NOW, destination.pocket))

        # Finally set the publishing status for the packages obsoleted in the
        # target archive accordingly (i.e make them superseded).
        store.execute("""
            UPDATE sourcepackagepublishinghistory secsrc
            SET
                status = %s,
                datesuperseded = %s,
                supersededby = mcd.s_sourcepackagerelease
            FROM
                tmp_merge_copy_data mcd
            WHERE
                secsrc.id = mcd.t_sspph AND mcd.obsoleted = True
            """ % sqlvalues(
                PackagePublishingStatus.SUPERSEDED, UTC_NOW))

        processors = [
            removeSecurityProxy(archivearch).processor for archivearch
            in getUtility(IArchiveArchSet).getByArchive(destination.archive)]

        self._create_missing_builds(
            destination.distroseries, destination.archive, (),
            processors, False)

    def _compute_packageset_delta(self, origin):
        """Given a source/target archive find obsolete or missing packages.

        This means finding out which packages in a given source archive are
        fresher or new with respect to a target archive.
        """
        store = IStore(BinaryPackagePublishingHistory)
        # The query below will find all packages in the source archive that
        # are fresher than their counterparts in the target archive.
        find_newer_packages = """
            UPDATE tmp_merge_copy_data mcd SET
                s_sspph = secsrc.id,
                s_sourcepackagerelease = spr.id,
                s_version = spr.version,
                obsoleted = True,
                s_status = secsrc.status,
                s_component = secsrc.component,
                s_section = secsrc.section
            FROM
                SourcePackagePublishingHistory secsrc,
                SourcePackageRelease spr,
                SourcePackageName spn
            WHERE
                secsrc.archive = %s AND secsrc.status IN (%s, %s) AND
                secsrc.distroseries = %s AND secsrc.pocket = %s AND
                secsrc.sourcepackagerelease = spr.id AND
                spr.sourcepackagename = spn.id AND
                spn.name = mcd.sourcepackagename AND
                spr.version > mcd.t_version
        """ % sqlvalues(
                origin.archive,
                PackagePublishingStatus.PENDING,
                PackagePublishingStatus.PUBLISHED,
                origin.distroseries, origin.pocket)

        if origin.component is not None:
            find_newer_packages += (
                " AND secsrc.component = %s" % quote(origin.component))
        store.execute(find_newer_packages)

        # Now find the packages that exist in the source archive but *not* in
        # the target archive.
        find_origin_only_packages = """
            INSERT INTO tmp_merge_copy_data (
                s_sspph, s_sourcepackagerelease, sourcepackagename,
                sourcepackagename_id, s_version, missing, s_status,
                s_component, s_section)
            SELECT
                secsrc.id AS s_sspph,
                secsrc.sourcepackagerelease AS s_sourcepackagerelease,
                spn.name AS sourcepackagename,
                spn.id AS sourcepackagename_id,
                spr.version AS s_version,
                True AS missing,
                secsrc.status AS s_status,
                secsrc.component AS s_component,
                secsrc.section AS s_section
            FROM SourcePackagePublishingHistory secsrc
            JOIN SourcePackageRelease AS spr ON
                spr.id = secsrc.sourcepackagerelease
            JOIN SourcePackageName AS spn ON
                spn.id = spr.sourcepackagename
            WHERE
                secsrc.archive = %s AND
                secsrc.status IN (%s, %s) AND
                secsrc.distroseries = %s AND
                secsrc.pocket = %s AND
                spn.name NOT IN (
                    SELECT sourcepackagename FROM tmp_merge_copy_data)
        """ % sqlvalues(
                origin.archive,
                PackagePublishingStatus.PENDING,
                PackagePublishingStatus.PUBLISHED,
                origin.distroseries, origin.pocket)

        if origin.component is not None:
            find_origin_only_packages += (
                " AND secsrc.component = %s" % quote(origin.component))
        store.execute(find_origin_only_packages)

    def _init_packageset_delta(self, destination):
        """Set up a temp table with data about target archive packages.

        This is a first step in finding out which packages in a given source
        archive are fresher or new with respect to a target archive.

        Merge copying of packages is one of the use cases that requires such a
        package set diff capability.

        In order to find fresher or new packages we first set up a temporary
        table that lists what packages exist in the target archive
        (additionally considering the distroseries, pocket and component).
        """
        store = IStore(BinaryPackagePublishingHistory)
        # Use a temporary table to hold the data needed for the package set
        # delta computation. This will prevent multiple, parallel delta
        # calculations from interfering with each other.
        store.execute("""
            CREATE TEMP TABLE tmp_merge_copy_data (
                -- Source archive package data, only set for packages that
                -- will be copied.
                s_sspph integer,
                s_sourcepackagerelease integer,
                s_version debversion,
                s_status integer,
                s_component integer,
                s_section integer,
                -- Target archive package data, set for all published or
                -- pending packages.
                t_sspph integer,
                t_sourcepackagerelease integer,
                t_version debversion,
                -- Whether a target package became obsolete due to a more
                -- recent source package.
                obsoleted boolean DEFAULT false NOT NULL,
                missing boolean DEFAULT false NOT NULL,
                sourcepackagename text NOT NULL,
                sourcepackagename_id integer NOT NULL
            );
            CREATE INDEX source_name_index
            ON tmp_merge_copy_data USING btree (sourcepackagename);
        """)
        # Populate the temporary table with package data from the target
        # archive considering the distroseries, pocket and component.
        pop_query = """
            INSERT INTO tmp_merge_copy_data (
                t_sspph, t_sourcepackagerelease, sourcepackagename,
                sourcepackagename_id, t_version)
            SELECT
                secsrc.id AS t_sspph,
                secsrc.sourcepackagerelease AS t_sourcepackagerelease,
                spn.name AS sourcepackagerelease,
                spn.id AS sourcepackagename_id,
                spr.version AS t_version
            FROM SourcePackagePublishingHistory secsrc
            JOIN SourcePackageRelease AS spr ON
                spr.id = secsrc.sourcepackagerelease
            JOIN SourcePackageName AS spn ON
                spn.id = spr.sourcepackagename
            WHERE
                secsrc.archive = %s AND
                secsrc.status IN (%s, %s) AND
                secsrc.distroseries = %s AND
                secsrc.pocket = %s
        """ % sqlvalues(
                destination.archive,
                PackagePublishingStatus.PENDING,
                PackagePublishingStatus.PUBLISHED,
                destination.distroseries, destination.pocket)

        if destination.component is not None:
            pop_query += (
                " AND secsrc.component = %s" % quote(destination.component))
        store.execute(pop_query)

    def _clone_source_packages(
            self, origin, destination, sourcepackagenames):
        """Copy source publishing data from origin to destination.

        @type origin: PackageLocation
        @param origin: the location from which source publishing
            records are to be copied.
        @type destination: PackageLocation
        @param destination: the location to which the data is
            to be copied.
        @type sourcepackagenames: Iterable
        @param sourcepackagenames: List of source packages to restrict
            the copy to
        """
        store = IStore(BinaryPackagePublishingHistory)
        query = '''
            INSERT INTO SourcePackagePublishingHistory (
                sourcepackagerelease, distroseries, status, component,
                section, archive, datecreated, datepublished, pocket,
                sourcepackagename)
            SELECT
                spph.sourcepackagerelease,
                %s as distroseries,
                spph.status,
                spph.component,
                spph.section,
                %s as archive,
                %s as datecreated,
                %s as datepublished,
                %s as pocket,
                spph.sourcepackagename
            FROM SourcePackagePublishingHistory AS spph
            WHERE
                spph.distroseries = %s AND
                spph.status in (%s, %s) AND
                spph.pocket = %s AND
                spph.archive = %s
            ''' % sqlvalues(
                destination.distroseries, destination.archive, UTC_NOW,
                UTC_NOW, destination.pocket, origin.distroseries,
                PackagePublishingStatus.PENDING,
                PackagePublishingStatus.PUBLISHED,
                origin.pocket, origin.archive)

        if sourcepackagenames and len(sourcepackagenames) > 0:
            query += '''
                AND spph.sourcepackagerelease IN (
                    SELECT spr.id
                    FROM SourcePackageRelease AS spr
                    JOIN SourcePackageName AS spn ON
                        spn.id = spr.sourcepackagename
                    WHERE spn.name IN %s
                )''' % sqlvalues(sourcepackagenames)

        if origin.packagesets:
            query += '''
                AND spph.sourcepackagerelease IN (
                    SELECT spr.id
                    FROM SourcePackageRelease AS spr
                    JOIN PackagesetSources AS pss ON
                        PSS.sourcepackagename = spr.sourcepackagename
                    JOIN FlatPackagesetInclusion AS fpsi ON
                        fpsi.child = pss.packageset
                    WHERE fpsi.parent in %s
                )
                     ''' % sqlvalues([p.id for p in origin.packagesets])

        if origin.component:
            query += "and spph.component = %s" % sqlvalues(origin.component)

        store.execute(query)

    def packageSetDiff(self, origin, destination, logger=None):
        """Please see `IPackageCloner`."""
        # Find packages that are obsolete or missing in the target archive.
        store = IStore(BinaryPackagePublishingHistory)
        self._init_packageset_delta(destination)
        self._compute_packageset_delta(origin)

        # Get the list of SourcePackagePublishingHistory keys for
        # source packages that are fresher in the origin archive.
        fresher_packages = store.execute("""
            SELECT s_sspph FROM tmp_merge_copy_data WHERE obsoleted = True;
        """)

        # Get the list of SourcePackagePublishingHistory keys for
        # source packages that are new in the origin archive.
        new_packages = store.execute("""
            SELECT s_sspph FROM tmp_merge_copy_data WHERE missing = True;
        """)

        if logger is not None:
            self._print_diagnostics(logger, store)

        return (
            [package for [package] in fresher_packages],
            [package for [package] in new_packages],
            )

    def _print_diagnostics(self, logger, store):
        """Print details of source packages that are fresher or new.

        Details of packages that are fresher or new in the origin archive
        are logged using the supplied 'logger' instance. This data is only
        available after a package set delta has been computed (see
        packageSetDiff()).
        """
        fresher_info = sorted(store.execute("""
            SELECT sourcepackagename, s_version, t_version
            FROM tmp_merge_copy_data
            WHERE obsoleted = True;
        """))
        logger.info('Fresher packages: %d' % len(fresher_info))
        for info in fresher_info:
            logger.info('* %s (%s > %s)' % info)
        new_info = sorted(store.execute("""
            SELECT sourcepackagename, s_version
            FROM tmp_merge_copy_data
            WHERE missing = True;
        """))
        logger.info('New packages: %d' % len(new_info))
        for info in new_info:
            logger.info('* %s (%s)' % info)
