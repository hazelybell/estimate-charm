# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'SourcePackageRelease',
    '_filter_ubuntu_translation_file',
    ]


import datetime
import operator
import re
from StringIO import StringIO

import apt_pkg
from debian.changelog import (
    Changelog,
    ChangelogCreateError,
    ChangelogParseError,
    )
import pytz
import simplejson
from sqlobject import (
    ForeignKey,
    SQLMultipleJoin,
    StringCol,
    )
from storm.expr import Join
from storm.info import ClassAlias
from storm.locals import (
    Desc,
    Int,
    Reference,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archiveuploader.utils import determine_source_file_type
from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.sourcepackage import (
    SourcePackageType,
    SourcePackageUrgency,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import (
    cursor,
    SQLBase,
    sqlvalues,
    )
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileContent,
    )
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.soyuz.enums import PackageDiffStatus
from lp.soyuz.interfaces.archive import MAIN_ARCHIVE_PURPOSES
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.packagediff import PackageDiffAlreadyRequested
from lp.soyuz.interfaces.packagediffjob import IPackageDiffJobSource
from lp.soyuz.interfaces.queue import QueueInconsistentStateError
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.model.files import SourcePackageReleaseFile
from lp.soyuz.model.packagediff import PackageDiff
from lp.soyuz.model.queue import (
    PackageUpload,
    PackageUploadSource,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )


def _filter_ubuntu_translation_file(filename):
    """Filter for translation filenames in tarball.

    Grooms filenames of translation files in tarball, returning None or
    empty string for files that should be ignored.

    Passed to `ITranslationImportQueue.addOrUpdateEntriesFromTarball`.
    """
    source_prefix = 'source/'
    if not filename.startswith(source_prefix):
        return None

    filename = filename[len(source_prefix):]

    blocked_prefixes = [
        # Translations for use by debconf--not used in Ubuntu.
        'debian/po/',
        # Debian Installer translations--treated separately.
        'd-i/',
        # Documentation--not translatable in Launchpad.
        'help/',
        'man/po/',
        'man/po4a/',
        ]

    for prefix in blocked_prefixes:
        if filename.startswith(prefix):
            return None

    return filename


class SourcePackageRelease(SQLBase):
    implements(ISourcePackageRelease)
    _table = 'SourcePackageRelease'

    section = ForeignKey(foreignKey='Section', dbName='section')
    creator = ForeignKey(
        dbName='creator', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    component = ForeignKey(foreignKey='Component', dbName='component')
    sourcepackagename = ForeignKey(foreignKey='SourcePackageName',
        dbName='sourcepackagename', notNull=True)
    maintainer = ForeignKey(
        dbName='maintainer', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    dscsigningkey = ForeignKey(foreignKey='GPGKey', dbName='dscsigningkey')
    urgency = EnumCol(dbName='urgency', schema=SourcePackageUrgency,
        default=SourcePackageUrgency.LOW, notNull=True)
    dateuploaded = UtcDateTimeCol(dbName='dateuploaded', notNull=True,
        default=UTC_NOW)
    dsc = StringCol(dbName='dsc')
    version = StringCol(dbName='version', notNull=True)
    changelog = ForeignKey(foreignKey='LibraryFileAlias', dbName='changelog')
    changelog_entry = StringCol(dbName='changelog_entry')
    builddepends = StringCol(dbName='builddepends')
    builddependsindep = StringCol(dbName='builddependsindep')
    build_conflicts = StringCol(dbName='build_conflicts')
    build_conflicts_indep = StringCol(dbName='build_conflicts_indep')
    architecturehintlist = StringCol(dbName='architecturehintlist')
    homepage = StringCol(dbName='homepage')
    format = EnumCol(dbName='format', schema=SourcePackageType,
        default=SourcePackageType.DPKG, notNull=True)
    upload_distroseries = ForeignKey(foreignKey='DistroSeries',
        dbName='upload_distroseries')
    upload_archive = ForeignKey(
        foreignKey='Archive', dbName='upload_archive', notNull=True)

    source_package_recipe_build_id = Int(name='sourcepackage_recipe_build')
    source_package_recipe_build = Reference(
        source_package_recipe_build_id, 'SourcePackageRecipeBuild.id')

    # XXX cprov 2006-09-26: Those fields are set as notNull and required in
    # ISourcePackageRelease, however they can't be not NULL in DB since old
    # records doesn't satisfy this condition. We will sort it before using
    # 'NoMoreAptFtparchive' implementation for PRIMARY archive. For PPA
    # (primary target) we don't need to populate old records.
    dsc_maintainer_rfc822 = StringCol(dbName='dsc_maintainer_rfc822')
    dsc_standards_version = StringCol(dbName='dsc_standards_version')
    dsc_format = StringCol(dbName='dsc_format')
    dsc_binaries = StringCol(dbName='dsc_binaries')

    # MultipleJoins
    files = SQLMultipleJoin('SourcePackageReleaseFile',
        joinColumn='sourcepackagerelease', orderBy="libraryfile")
    publishings = SQLMultipleJoin('SourcePackagePublishingHistory',
        joinColumn='sourcepackagerelease', orderBy="-datecreated")

    _user_defined_fields = StringCol(dbName='user_defined_fields')

    def __init__(self, *args, **kwargs):
        if 'user_defined_fields' in kwargs:
            kwargs['_user_defined_fields'] = simplejson.dumps(
                kwargs['user_defined_fields'])
            del kwargs['user_defined_fields']
        # copyright isn't on the Storm class, since we don't want it
        # loaded every time. Set it separately.
        if 'copyright' in kwargs:
            copyright = kwargs.pop('copyright')
        super(SourcePackageRelease, self).__init__(*args, **kwargs)
        self.copyright = copyright

    @property
    def copyright(self):
        """See `ISourcePackageRelease`."""
        store = Store.of(self)
        store.flush()
        return store.execute(
            "SELECT copyright FROM sourcepackagerelease WHERE id=%s",
            (self.id,)).get_one()[0]

    @copyright.setter
    def copyright(self, content):
        """See `ISourcePackageRelease`."""
        store = Store.of(self)
        store.flush()
        if content is not None:
            content = unicode(content)
        store.execute(
            "UPDATE sourcepackagerelease SET copyright=%s WHERE id=%s",
            (content, self.id))

    @property
    def user_defined_fields(self):
        """See `IBinaryPackageRelease`."""
        if self._user_defined_fields is None:
            return []
        return simplejson.loads(self._user_defined_fields)

    @cachedproperty
    def package_diffs(self):
        return list(Store.of(self).find(
            PackageDiff, to_source=self).order_by(
                Desc(PackageDiff.date_requested)))

    @property
    def builds(self):
        """See `ISourcePackageRelease`."""
        # Excluding PPA builds may seem like a strange thing to do, but,
        # since Archive.copyPackage can copy packages across archives, a
        # build may well have a different archive to the corresponding
        # sourcepackagerelease.
        return BinaryPackageBuild.select("""
            source_package_release = %s AND
            archive.id = binarypackagebuild.archive AND
            archive.purpose IN %s
            """ % sqlvalues(self.id, MAIN_ARCHIVE_PURPOSES),
            orderBy=['-date_created', 'id'],
            clauseTables=['Archive'])

    @property
    def age(self):
        """See ISourcePackageRelease."""
        now = datetime.datetime.now(pytz.timezone('UTC'))
        return now - self.dateuploaded

    @property
    def latest_build(self):
        builds = self._cached_builds
        if len(builds) > 0:
            return builds[0]
        return None

    def failed_builds(self):
        return [build for build in self._cached_builds
                if build.buildstate == BuildStatus.FAILEDTOBUILD]

    @property
    def needs_building(self):
        for build in self._cached_builds:
            if build.status in [BuildStatus.NEEDSBUILD,
                                    BuildStatus.MANUALDEPWAIT,
                                    BuildStatus.CHROOTWAIT]:
                return True
        return False

    @cachedproperty
    def _cached_builds(self):
        # The reason we have this as a cachedproperty is that all the
        # *build* methods here need access to it; better not to
        # recalculate it multiple times.
        return list(self.builds)

    @property
    def name(self):
        return self.sourcepackagename.name

    @property
    def sourcepackage(self):
        """See ISourcePackageRelease."""
        # By supplying the sourcepackagename instead of its string name,
        # we avoid doing an extra query doing getSourcepackage.
        # XXX 2008-06-16 mpt bug=241298: cprov says this property "won't be as
        # useful as it looks once we start supporting derivation ... [It] is
        # dangerous and should be renamed (or removed)".
        series = self.upload_distroseries
        return series.getSourcePackage(self.sourcepackagename)

    @property
    def distrosourcepackage(self):
        """See ISourcePackageRelease."""
        # By supplying the sourcepackagename instead of its string name,
        # we avoid doing an extra query doing getSourcepackage
        distribution = self.upload_distroseries.distribution
        return distribution.getSourcePackage(self.sourcepackagename)

    @property
    def title(self):
        return '%s - %s' % (self.sourcepackagename.name, self.version)

    @property
    def current_publishings(self):
        """See ISourcePackageRelease."""
        from lp.soyuz.model.distroseriessourcepackagerelease import (
            DistroSeriesSourcePackageRelease)
        return [DistroSeriesSourcePackageRelease(pub.distroseries, self)
                for pub in self.publishings]

    @cachedproperty
    def published_archives(self):
        archives = set(
            pub.archive for pub in self.publishings.prejoin(['archive']))
        return sorted(archives, key=operator.attrgetter('id'))

    def addFile(self, file):
        """See ISourcePackageRelease."""
        return SourcePackageReleaseFile(
            sourcepackagerelease=self,
            filetype=determine_source_file_type(file.filename),
            libraryfile=file)

    def getFileByName(self, filename):
        """See `ISourcePackageRelease`."""
        sprf = Store.of(self).find(
            SourcePackageReleaseFile,
            SourcePackageReleaseFile.sourcepackagerelease == self.id,
            LibraryFileAlias.id == SourcePackageReleaseFile.libraryfileID,
            LibraryFileAlias.filename == filename).one()
        if sprf:
            return sprf.libraryfile
        else:
            raise NotFoundError(filename)

    def getPackageSize(self):
        """See ISourcePackageRelease."""
        size_query = """
            SELECT
                SUM(LibraryFileContent.filesize)/1024.0
            FROM
                SourcePackagereLease
                JOIN SourcePackageReleaseFile ON
                    SourcePackageReleaseFile.sourcepackagerelease =
                    SourcePackageRelease.id
                JOIN LibraryFileAlias ON
                    SourcePackageReleaseFile.libraryfile =
                    LibraryFileAlias.id
                JOIN LibraryFileContent ON
                    LibraryFileAlias.content = LibraryFileContent.id
            WHERE
                SourcePackageRelease.id = %s
            """ % sqlvalues(self)

        cur = cursor()
        cur.execute(size_query)
        results = cur.fetchone()

        if len(results) == 1 and results[0] is not None:
            return float(results[0])
        else:
            return 0.0

    def createBuild(self, distro_arch_series, pocket, archive, processor=None,
                    status=None):
        """See ISourcePackageRelease."""
        # If a processor is not provided, use the DAS' processor.
        if processor is None:
            processor = distro_arch_series.processor

        if status is None:
            status = BuildStatus.NEEDSBUILD

        # Force the current timestamp instead of the default
        # UTC_NOW for the transaction, avoid several row with
        # same datecreated.
        date_created = datetime.datetime.now(pytz.timezone('UTC'))

        return getUtility(IBinaryPackageBuildSet).new(
            distro_arch_series=distro_arch_series,
            source_package_release=self,
            processor=processor,
            status=status,
            date_created=date_created,
            pocket=pocket,
            archive=archive)

    def findBuildsByArchitecture(self, distroseries, archive):
        """Find associated builds, by architecture.

        Looks for `BinaryPackageBuild` records for this source package
        release, with publication records in the distroseries associated with
        `distroarchseries`.  There should be at most one of these per
        architecture.

        :param distroarchseries: `DistroArchSeries` to look for.
        :return: A dict mapping architecture tags (in string form,
            e.g. 'i386') to `BinaryPackageBuild`s for that build.
        """
        # Avoid circular imports.
        from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
        from lp.soyuz.model.distroarchseries import DistroArchSeries
        from lp.soyuz.model.publishing import BinaryPackagePublishingHistory

        BuildDAS = ClassAlias(DistroArchSeries, 'BuildDAS')
        PublishDAS = ClassAlias(DistroArchSeries, 'PublishDAS')

        query = Store.of(self).find(
            (BuildDAS.architecturetag, BinaryPackageBuild),
            BinaryPackageBuild.source_package_release == self,
            BinaryPackageRelease.buildID == BinaryPackageBuild.id,
            BuildDAS.id == BinaryPackageBuild.distro_arch_series_id,
            BinaryPackagePublishingHistory.binarypackagereleaseID ==
                BinaryPackageRelease.id,
            BinaryPackagePublishingHistory.archiveID == archive.id,
            PublishDAS.id ==
                BinaryPackagePublishingHistory.distroarchseriesID,
            PublishDAS.distroseriesID == distroseries.id,
            # Architecture-independent binary package releases are built
            # in the nominated arch-indep architecture but published in
            # all architectures.  This condition makes sure we consider
            # only builds that have been published in their own
            # architecture.
            PublishDAS.architecturetag == BuildDAS.architecturetag)
        results = list(query.config(distinct=True))
        mapped_results = dict(results)
        assert len(mapped_results) == len(results), (
            "Found multiple build candidates per architecture: %s.  "
            "This may mean that we have a serious problem in our DB model.  "
            "Further investigation is required."
            % [(tag, build.id) for tag, build in results])
        return mapped_results

    def getBuildByArch(self, distroarchseries, archive):
        """See ISourcePackageRelease."""
        # First we try to follow any binaries built from the given source
        # in a distroarchseries with the given architecturetag and published
        # in the given (distroarchseries, archive) location.
        # (Querying all architectures and then picking the right one out
        # of the result turns out to be much faster than querying for
        # just the architecture we want).
        builds_by_arch = self.findBuildsByArchitecture(
            distroarchseries.distroseries, archive)
        build = builds_by_arch.get(distroarchseries.architecturetag)
        if build is not None:
            # If there was any published binary we can use its original build.
            # This case covers the situations when both source and binaries
            # got copied from another location.
            return build

        # If there was no published binary we have to try to find a
        # suitable build in all possible location across the distroseries
        # inheritance tree. See below.
        clause_tables = ['DistroArchSeries']
        queries = [
            "DistroArchSeries.id = BinaryPackageBuild.distro_arch_series AND "
            "BinaryPackageBuild.archive = %s AND "
            "DistroArchSeries.architecturetag = %s AND "
            "BinaryPackageBuild.source_package_release = %s" % (
            sqlvalues(archive.id, distroarchseries.architecturetag, self))]

        # Query only the last build record for this sourcerelease
        # across all possible locations.
        query = " AND ".join(queries)

        return BinaryPackageBuild.selectFirst(
            query, clauseTables=clause_tables,
            orderBy=['-date_created'])

    def override(self, component=None, section=None, urgency=None):
        """See ISourcePackageRelease."""
        if component is not None:
            self.component = component
            # See if the new component requires a new archive:
            distribution = self.upload_distroseries.distribution
            new_archive = distribution.getArchiveByComponent(component.name)
            if new_archive is not None:
                self.upload_archive = new_archive
            else:
                raise QueueInconsistentStateError(
                    "New component '%s' requires a non-existent archive.")
        if section is not None:
            self.section = section
        if urgency is not None:
            self.urgency = urgency

    @property
    def upload_changesfile(self):
        """See `ISourcePackageRelease`."""
        package_upload = self.package_upload
        # Cope with `SourcePackageRelease`s imported by gina, they do not
        # have a corresponding `PackageUpload` record.
        if package_upload is None:
            return None
        return package_upload.changesfile

    @property
    def package_upload(self):
        """See `ISourcepackageRelease`."""
        store = Store.of(self)
        # The join on 'changesfile' is used for pre-fetching the
        # corresponding library file, so callsites don't have to issue an
        # extra query.
        origin = [
            PackageUploadSource,
            Join(PackageUpload,
                 PackageUploadSource.packageuploadID == PackageUpload.id),
            Join(LibraryFileAlias,
                 LibraryFileAlias.id == PackageUpload.changes_file_id),
            Join(LibraryFileContent,
                 LibraryFileContent.id == LibraryFileAlias.contentID),
            ]
        results = store.using(*origin).find(
            (PackageUpload, LibraryFileAlias, LibraryFileContent),
            PackageUploadSource.sourcepackagerelease == self,
            PackageUpload.archive == self.upload_archive,
            PackageUpload.distroseries == self.upload_distroseries)

        # Return the unique `PackageUpload` record that corresponds to the
        # upload of this `SourcePackageRelease`, load the `LibraryFileAlias`
        # and the `LibraryFileContent` in cache because it's most likely
        # they will be needed.
        return DecoratedResultSet(results, operator.itemgetter(0)).one()

    @property
    def uploader(self):
        """See `ISourcePackageRelease`"""
        if self.source_package_recipe_build is not None:
            return self.source_package_recipe_build.requester
        if self.dscsigningkey is not None:
            return self.dscsigningkey.owner
        return None

    @property
    def change_summary(self):
        """See ISourcePackageRelease"""
        # this regex is copied from apt-listchanges.py courtesy of MDZ
        new_stanza_line = re.compile(
            '^\S+ \((?P<version>.*)\) .*;.*urgency=(?P<urgency>\w+).*')
        logfile = StringIO(self.changelog_entry)
        change = ''
        top_stanza = False
        for line in logfile.readlines():
            match = new_stanza_line.match(line)
            if match:
                if top_stanza:
                    break
                top_stanza = True
            change += line

        return change

    def attachTranslationFiles(self, tarball_alias, by_maintainer,
                               importer=None):
        """See ISourcePackageRelease."""
        tarball = tarball_alias.read()

        if importer is None:
            importer = getUtility(ILaunchpadCelebrities).rosetta_experts

        queue = getUtility(ITranslationImportQueue)

        only_templates = self.sourcepackage.has_sharing_translation_templates
        queue.addOrUpdateEntriesFromTarball(
            tarball, by_maintainer, importer,
            sourcepackagename=self.sourcepackagename,
            distroseries=self.upload_distroseries,
            filename_filter=_filter_ubuntu_translation_file,
            only_templates=only_templates)

    def getDiffTo(self, to_sourcepackagerelease):
        """See ISourcePackageRelease."""
        return PackageDiff.selectOneBy(
            from_source=self, to_source=to_sourcepackagerelease)

    def requestDiffTo(self, requester, to_sourcepackagerelease):
        """See ISourcePackageRelease."""
        candidate = self.getDiffTo(to_sourcepackagerelease)

        if candidate is not None:
            raise PackageDiffAlreadyRequested(
                "%s has already been requested" % candidate.title)

        if self.sourcepackagename.name == 'udev':
            # XXX 2009-11-23 Julian bug=314436
            # Currently diff output for udev will fill disks.  It's
            # disabled until diffutils is fixed in that bug.
            status = PackageDiffStatus.FAILED
        else:
            status = PackageDiffStatus.PENDING

        Store.of(to_sourcepackagerelease).flush()
        del get_property_cache(to_sourcepackagerelease).package_diffs
        packagediff = PackageDiff(
            from_source=self, to_source=to_sourcepackagerelease,
            requester=requester, status=status)
        if status == PackageDiffStatus.PENDING:
            getUtility(IPackageDiffJobSource).create(packagediff)
        return packagediff

    def aggregate_changelog(self, since_version):
        """See `ISourcePackagePublishingHistory`."""
        if self.changelog is None:
            return None

        apt_pkg.init_system()
        chunks = []
        changelog = self.changelog
        # The python-debian API for parsing changelogs is pretty awful. The
        # only useful way of extracting info is to use the iterator on
        # Changelog and then compare versions.
        try:
            changelog_text = changelog.read().decode("UTF-8", "replace")
            for block in Changelog(changelog_text):
                version = block._raw_version
                if (since_version and
                    apt_pkg.version_compare(version, since_version) <= 0):
                    break
                # Poking in private attributes is not nice but again the
                # API is terrible.  We want to ensure that the name/date
                # line is omitted from these composite changelogs.
                block._no_trailer = True
                try:
                    # python-debian adds an extra blank line to the chunks
                    # so we'll have to sort this out.
                    chunks.append(str(block).rstrip())
                except ChangelogCreateError:
                    continue
                if not since_version:
                    # If a particular version was not requested we just
                    # return the most recent changelog entry.
                    break
        except ChangelogParseError:
            return None

        output = "\n\n".join(chunks)
        return output.decode("utf-8", "replace")

    def getActiveArchSpecificPublications(self, archive, distroseries,
                                          pocket):
        """Find architecture-specific binary publications for this release.

        For example, say source package release contains binary packages of:
         * "foo" for i386 (pending in i386)
         * "foo" for amd64 (published in amd64)
         * "foo-common" for the "all" architecture (pending or published in
           various real processor architectures)

        In that case, this search will return foo(i386) and foo(amd64).  The
        dominator uses this when figuring out whether foo-common can be
        superseded: we don't track dependency graphs, but we know that the
        architecture-specific "foo" releases are likely to depend on the
        architecture-independent foo-common release.

        :param archive: The `Archive` to search.
        :param distroseries: The `DistroSeries` to search.
        :param pocket: The `PackagePublishingPocket` to search.
        :return: A Storm result set of active, architecture-specific
            `BinaryPackagePublishingHistory` objects for this source package
            release and the given `archive`, `distroseries`, and `pocket`.
        """
        # Avoid circular imports.
        from lp.soyuz.interfaces.publishing import active_publishing_status
        from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
        from lp.soyuz.model.distroarchseries import DistroArchSeries
        from lp.soyuz.model.publishing import BinaryPackagePublishingHistory

        return Store.of(self).find(
            BinaryPackagePublishingHistory,
            BinaryPackageBuild.source_package_release_id == self.id,
            BinaryPackageRelease.build == BinaryPackageBuild.id,
            BinaryPackagePublishingHistory.binarypackagereleaseID ==
                BinaryPackageRelease.id,
            BinaryPackagePublishingHistory.archiveID == archive.id,
            BinaryPackagePublishingHistory.distroarchseriesID ==
                DistroArchSeries.id,
            DistroArchSeries.distroseriesID == distroseries.id,
            BinaryPackagePublishingHistory.pocket == pocket,
            BinaryPackagePublishingHistory.status.is_in(
                active_publishing_status),
            BinaryPackageRelease.architecturespecific == True)
