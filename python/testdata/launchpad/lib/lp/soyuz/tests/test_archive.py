# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Archive features."""

from datetime import (
    date,
    datetime,
    timedelta,
    )
import doctest

from pytz import UTC
from testtools.matchers import (
    DocTestMatches,
    MatchesRegex,
    MatchesStructure,
    )
from testtools.testcase import ExpectedException
import transaction
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.enums import BuildStatus
from lp.registry.enums import (
    PersonVisibility,
    TeamMembershipPolicy,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import sqlvalues
from lp.services.job.interfaces.job import JobStatus
from lp.services.propertycache import clear_property_cache
from lp.services.worlddata.interfaces.country import ICountrySet
from lp.soyuz.adapters.archivedependencies import (
    get_sources_list_for_building,
    )
from lp.soyuz.enums import (
    ArchivePermissionType,
    ArchivePurpose,
    ArchiveStatus,
    PackageCopyPolicy,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.archive import (
    ArchiveDependencyError,
    ArchiveDisabled,
    CannotCopy,
    CannotUploadToPocket,
    CannotUploadToPPA,
    CannotUploadToSeries,
    IArchiveSet,
    InsufficientUploadRights,
    InvalidPocketForPartnerArchive,
    InvalidPocketForPPA,
    NoRightsForArchive,
    NoRightsForComponent,
    NoSuchPPA,
    RedirectedPocket,
    VersionRequiresName,
    )
from lp.soyuz.interfaces.archivearch import IArchiveArchSet
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.binarypackagebuild import BuildSetStatus
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageNameSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.model.archive import (
    Archive,
    validate_ppa,
    )
from lp.soyuz.model.archivepermission import (
    ArchivePermission,
    ArchivePermissionSet,
    )
from lp.soyuz.model.binarypackagerelease import (
    BinaryPackageReleaseDownloadCount,
    )
from lp.soyuz.model.component import ComponentSelection
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    ANONYMOUS,
    celebrity_logged_in,
    login,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestGetPublicationsInArchive(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeArchivesForOneDistribution(self, count=3):
        distribution = self.factory.makeDistribution()
        archives = []
        for i in range(count):
            archives.append(
                self.factory.makeArchive(distribution=distribution))
        return archives

    def makeArchivesWithPublications(self, count=3):
        archives = self.makeArchivesForOneDistribution(count=count)
        sourcepackagename = self.factory.makeSourcePackageName()
        for archive in archives:
            self.factory.makeSourcePackagePublishingHistory(
                sourcepackagename=sourcepackagename, archive=archive,
                status=PackagePublishingStatus.PUBLISHED,
                )
        return archives, sourcepackagename

    def getPublications(self, sourcepackagename, archives, distribution):
        return getUtility(IArchiveSet).getPublicationsInArchives(
            sourcepackagename, archives, distribution=distribution)

    def test_getPublications_returns_all_published_publications(self):
        # Returns all currently published publications for archives
        archives, sourcepackagename = self.makeArchivesWithPublications()
        results = self.getPublications(
            sourcepackagename, archives, archives[0].distribution)
        self.assertEqual(3, results.count())

    def test_getPublications_empty_list_of_archives(self):
        # Passing an empty list of archives will result in an empty
        # resultset.
        archives, sourcepackagename = self.makeArchivesWithPublications()
        results = self.getPublications(
            sourcepackagename, [], archives[0].distribution)
        self.assertEqual([], list(results))

    def assertPublicationsFromArchives(self, publications, archives):
        self.assertEqual(len(archives), publications.count())
        for publication, archive in zip(publications, archives):
            self.assertEqual(archive, publication.archive)

    def test_getPublications_returns_only_for_given_archives(self):
        # Returns only publications for the specified archives
        archives, sourcepackagename = self.makeArchivesWithPublications()
        results = self.getPublications(
            sourcepackagename, [archives[0]], archives[0].distribution)
        self.assertPublicationsFromArchives(results, [archives[0]])

    def test_getPublications_returns_only_published_publications(self):
        # Publications that are not published will not be returned.
        archive = self.factory.makeArchive()
        sourcepackagename = self.factory.makeSourcePackageName()
        self.factory.makeSourcePackagePublishingHistory(
            archive=archive, sourcepackagename=sourcepackagename,
            status=PackagePublishingStatus.PENDING)
        results = self.getPublications(
            sourcepackagename, [archive], archive.distribution)
        self.assertEqual([], list(results))

    def publishSourceInNewArchive(self, sourcepackagename):
        distribution = self.factory.makeDistribution()
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        archive = self.factory.makeArchive(distribution=distribution)
        self.factory.makeSourcePackagePublishingHistory(
            archive=archive, sourcepackagename=sourcepackagename,
            distroseries=distroseries,
            status=PackagePublishingStatus.PUBLISHED)
        return archive

    def test_getPublications_for_specific_distro(self):
        # Results can be filtered for specific distributions.
        sourcepackagename = self.factory.makeSourcePackageName()
        archive = self.publishSourceInNewArchive(sourcepackagename)
        other_archive = self.publishSourceInNewArchive(sourcepackagename)
        # We don't get the results for other_distribution
        results = self.getPublications(
            sourcepackagename, [archive, other_archive],
            distribution=archive.distribution)
        self.assertPublicationsFromArchives(results, [archive])


class TestArchiveRepositorySize(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_empty_ppa_has_zero_binaries_size(self):
        # An empty PPA has no binaries so has zero binaries_size.
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertEqual(0, ppa.binaries_size)

    def test_sources_size_on_empty_archive(self):
        # Zero is returned for an archive without sources.
        archive = self.factory.makeArchive()
        self.assertEqual(0, archive.sources_size)

    def publishSourceFile(self, archive, library_file):
        """Publish a source package with the given content to the archive.

        :param archive: the IArchive to publish to.
        :param library_file: a LibraryFileAlias for the content of the
            source file.
        """
        sourcepackagerelease = self.factory.makeSourcePackageRelease()
        self.factory.makeSourcePackagePublishingHistory(
            archive=archive, sourcepackagerelease=sourcepackagerelease,
            status=PackagePublishingStatus.PUBLISHED)
        self.factory.makeSourcePackageReleaseFile(
            sourcepackagerelease=sourcepackagerelease,
            library_file=library_file)

    def test_sources_size_does_not_count_duplicated_files(self):
        # If there are multiple copies of the same file name/size
        # only one will be counted.
        archive = self.factory.makeArchive()
        library_file = self.factory.makeLibraryFileAlias()
        self.publishSourceFile(archive, library_file)
        self.assertEqual(library_file.content.filesize, archive.sources_size)

        self.publishSourceFile(archive, library_file)
        self.assertEqual(library_file.content.filesize, archive.sources_size)


class TestSeriesWithSources(TestCaseWithFactory):
    """Create some sources in different series."""

    layer = DatabaseFunctionalLayer

    def test_series_with_sources_returns_all_series(self):
        # Calling series_with_sources returns all series with publishings.
        distribution = self.factory.makeDistribution()
        archive = self.factory.makeArchive(distribution=distribution)
        self.factory.makeDistroSeries(
            distribution=distribution, version="0.5")
        series_with_sources1 = self.factory.makeDistroSeries(
            distribution=distribution, version="1")
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series_with_sources1, archive=archive,
            status=PackagePublishingStatus.PUBLISHED)
        series_with_sources2 = self.factory.makeDistroSeries(
            distribution=distribution, version="2")
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series_with_sources2, archive=archive,
            status=PackagePublishingStatus.PENDING)
        self.assertEqual(
            [series_with_sources2, series_with_sources1],
            archive.series_with_sources)

    def test_series_with_sources_ignore_non_published_records(self):
        # If all publishings in a series are deleted or superseded
        # the series will not be returned.
        series = self.factory.makeDistroSeries()
        archive = self.factory.makeArchive(distribution=series.distribution)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series, archive=archive,
            status=PackagePublishingStatus.DELETED)
        self.assertEqual([], archive.series_with_sources)

    def test_series_with_sources_ordered_by_version(self):
        # The returned series are ordered by the distroseries version.
        distribution = self.factory.makeDistribution()
        archive = self.factory.makeArchive(distribution=distribution)
        series1 = self.factory.makeDistroSeries(
            version="1", distribution=distribution)
        series2 = self.factory.makeDistroSeries(
            version="2", distribution=distribution)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series1, archive=archive,
            status=PackagePublishingStatus.PUBLISHED)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series2, archive=archive,
            status=PackagePublishingStatus.PUBLISHED)
        self.assertEqual([series2, series1], archive.series_with_sources)
        # Change the version such that they should order differently
        removeSecurityProxy(series2).version = "0.5"
        # ... and check that they do
        self.assertEqual([series1, series2], archive.series_with_sources)


class TestArchiveEnableDisable(TestCaseWithFactory):
    """Test the enable and disable methods of Archive."""

    layer = DatabaseFunctionalLayer

    def _getBuildJobsByStatus(self, archive, status):
        # Return the count for archive build jobs with the given status.
        query = """
            SELECT COUNT(Job.id)
            FROM BinaryPackageBuild, BuildPackageJob, BuildQueue, Job
            WHERE
                BuildPackageJob.build = BinaryPackageBuild.id
                AND BuildPackageJob.job = BuildQueue.job
                AND Job.id = BuildQueue.job
                AND BinaryPackageBuild.archive = %s
                AND BinaryPackageBuild.status = %s
                AND Job.status = %s;
        """ % sqlvalues(archive, BuildStatus.NEEDSBUILD, status)

        return IStore(Archive).execute(query).get_one()[0]

    def assertNoBuildJobsHaveStatus(self, archive, status):
        # Check that that the jobs attached to this archive do not have this
        # status.
        self.assertEqual(self._getBuildJobsByStatus(archive, status), 0)

    def assertHasBuildJobsWithStatus(self, archive, status, count):
        # Check that that there are jobs attached to this archive that have
        # the specified status.
        self.assertEqual(self._getBuildJobsByStatus(archive, status), count)

    def test_enableArchive(self):
        # Enabling an archive should set all the Archive's suspended builds to
        # WAITING.
        archive = self.factory.makeArchive(enabled=True)
        build = self.factory.makeBinaryPackageBuild(
            archive=archive, status=BuildStatus.NEEDSBUILD)
        build.queueBuild()
        # disable the archive, as it is currently enabled
        removeSecurityProxy(archive).disable()
        self.assertHasBuildJobsWithStatus(archive, JobStatus.SUSPENDED, 1)
        removeSecurityProxy(archive).enable()
        self.assertNoBuildJobsHaveStatus(archive, JobStatus.SUSPENDED)
        self.assertTrue(archive.enabled)

    def test_enableArchiveAlreadyEnabled(self):
        # Enabling an already enabled Archive should raise an AssertionError.
        archive = self.factory.makeArchive(enabled=True)
        self.assertRaises(AssertionError, removeSecurityProxy(archive).enable)

    def test_disableArchive(self):
        # Disabling an archive should set all the Archive's pending bulds to
        # SUSPENDED.
        archive = self.factory.makeArchive(enabled=True)
        build = self.factory.makeBinaryPackageBuild(
            archive=archive, status=BuildStatus.NEEDSBUILD)
        build.queueBuild()
        self.assertHasBuildJobsWithStatus(archive, JobStatus.WAITING, 1)
        removeSecurityProxy(archive).disable()
        self.assertNoBuildJobsHaveStatus(archive, JobStatus.WAITING)
        self.assertFalse(archive.enabled)

    def test_disableArchiveAlreadyDisabled(self):
        # Disabling an already disabled Archive should raise an
        # AssertionError.
        archive = self.factory.makeArchive(enabled=False)
        self.assertRaises(AssertionError, removeSecurityProxy(archive).disable)


class TestCollectLatestPublishedSources(TestCaseWithFactory):
    """Ensure that the private helper method works as expected."""

    layer = DatabaseFunctionalLayer

    def makePublishedSources(self, archive, statuses, versions, names):
        for status, version, name in zip(statuses, versions, names):
            self.factory.makeSourcePackagePublishingHistory(
                sourcepackagename=name, archive=archive,
                version=version, status=status)

    def test_collectLatestPublishedSources_returns_latest(self):
        sourcepackagename = self.factory.makeSourcePackageName(name="foo")
        other_spn = self.factory.makeSourcePackageName(name="bar")
        archive = self.factory.makeArchive()
        self.makePublishedSources(archive,
            [PackagePublishingStatus.PUBLISHED] * 3,
            ["1.0", "1.1", "2.0"],
            [sourcepackagename, sourcepackagename, other_spn])
        pubs = removeSecurityProxy(archive)._collectLatestPublishedSources(
            archive, None, ["foo"])
        self.assertEqual(1, len(pubs))
        self.assertEqual('1.1', pubs[0].source_package_version)

    def test_collectLatestPublishedSources_returns_published_only(self):
        # Set the status of the latest pub to DELETED and ensure that it
        # is not returned.
        sourcepackagename = self.factory.makeSourcePackageName(name="foo")
        other_spn = self.factory.makeSourcePackageName(name="bar")
        archive = self.factory.makeArchive()
        self.makePublishedSources(archive,
            [PackagePublishingStatus.PUBLISHED,
                PackagePublishingStatus.DELETED,
                PackagePublishingStatus.PUBLISHED],
            ["1.0", "1.1", "2.0"],
            [sourcepackagename, sourcepackagename, other_spn])
        pubs = removeSecurityProxy(archive)._collectLatestPublishedSources(
            archive, None, ["foo"])
        self.assertEqual(1, len(pubs))
        self.assertEqual('1.0', pubs[0].source_package_version)

    def test_collectLatestPublishedSources_multiple_distroseries(self):
        # The helper method selects the correct publication from multiple
        # distroseries.
        sourcepackagename = self.factory.makeSourcePackageName(name="foo")
        archive = self.factory.makeArchive()
        distroseries_one = self.factory.makeDistroSeries(
            distribution=archive.distribution)
        distroseries_two = self.factory.makeDistroSeries(
            distribution=archive.distribution)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackagename, archive=archive,
            distroseries=distroseries_one, version="1.0",
            status=PackagePublishingStatus.PUBLISHED)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=sourcepackagename, archive=archive,
            distroseries=distroseries_two, version="1.1",
            status=PackagePublishingStatus.PUBLISHED)
        pubs = removeSecurityProxy(archive)._collectLatestPublishedSources(
            archive, distroseries_one.name, ["foo"])
        self.assertEqual(1, len(pubs))
        self.assertEqual("1.0", pubs[0].source_package_version)


class TestArchiveCanUpload(TestCaseWithFactory):
    """Test the various methods that verify whether uploads are allowed to
    happen."""

    layer = DatabaseFunctionalLayer

    def test_checkArchivePermission_by_PPA_owner(self):
        # Uploading to a PPA should be allowed for a user that is the owner
        owner = self.factory.makePerson(name="somebody")
        archive = self.factory.makeArchive(owner=owner)
        self.assertTrue(archive.checkArchivePermission(owner))
        someone_unrelated = self.factory.makePerson(name="somebody-unrelated")
        self.assertFalse(archive.checkArchivePermission(someone_unrelated))

    def test_checkArchivePermission_distro_archive(self):
        # Regular users can not upload to ubuntu
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        # The factory sets the archive owner the same as the distro owner,
        # change that here to ensure the security adapter checks are right.
        removeSecurityProxy(archive).owner = self.factory.makePerson()
        main = getUtility(IComponentSet)["main"]
        # A regular user doesn't have access
        somebody = self.factory.makePerson()
        self.assertFalse(archive.checkArchivePermission(somebody, main))
        # An ubuntu core developer does have access
        coredev = self.factory.makePerson()
        with person_logged_in(archive.distribution.owner):
            archive.newComponentUploader(coredev, main.name)
        self.assertTrue(archive.checkArchivePermission(coredev, main))

    def test_checkArchivePermission_ppa(self):
        owner = self.factory.makePerson()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA,
                                           owner=owner)
        somebody = self.factory.makePerson()
        # The owner has access
        self.assertTrue(archive.checkArchivePermission(owner))
        # Somebody unrelated does not
        self.assertFalse(archive.checkArchivePermission(somebody))

    def makeArchiveAndActiveDistroSeries(self, purpose=ArchivePurpose.PRIMARY,
                                         status=SeriesStatus.DEVELOPMENT):
        archive = self.factory.makeArchive(purpose=purpose)
        distroseries = self.factory.makeDistroSeries(
            distribution=archive.distribution, status=status)
        return archive, distroseries

    def makePersonWithComponentPermission(self, archive):
        person = self.factory.makePerson()
        component = self.factory.makeComponent()
        removeSecurityProxy(archive).newComponentUploader(
            person, component)
        return person, component

    def checkUpload(self, archive, person, sourcepackagename,
                    distroseries=None, component=None,
                    pocket=None, strict_component=False):
        if distroseries is None:
            distroseries = self.factory.makeDistroSeries()
        if component is None:
            component = self.factory.makeComponent()
        if pocket is None:
            pocket = PackagePublishingPocket.RELEASE
        return archive.checkUpload(
            person, distroseries, sourcepackagename, component, pocket,
            strict_component=strict_component)

    def assertCanUpload(self, archive, person, sourcepackagename,
                        distroseries=None, component=None,
                        pocket=None, strict_component=False):
        """Assert an upload to 'archive' will be accepted."""
        self.assertIsNone(
            self.checkUpload(
                archive, person, sourcepackagename,
                distroseries=distroseries, component=component,
                pocket=pocket, strict_component=strict_component))

    def assertCannotUpload(self, reason, archive, person, sourcepackagename,
                           distroseries=None, component=None, pocket=None,
                           strict_component=False):
        """Assert that upload to 'archive' will be rejected.

        :param reason: The expected reason for not being able to upload. A
            class.
        """
        self.assertIsInstance(
            self.checkUpload(
                archive, person, sourcepackagename,
                distroseries=distroseries, component=component,
                pocket=pocket, strict_component=strict_component),
            reason)

    def test_checkUpload_partner_invalid_pocket(self):
        # Partner archives only have release and proposed pockets
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PARTNER)
        self.assertCannotUpload(
            InvalidPocketForPartnerArchive, archive,
            self.factory.makePerson(), self.factory.makeSourcePackageName(),
            pocket=PackagePublishingPocket.UPDATES,
            distroseries=distroseries)

    def test_checkUpload_ppa_invalid_pocket(self):
        # PPA archives only have release pockets
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PPA)
        self.assertCannotUpload(
            InvalidPocketForPPA, archive,
            self.factory.makePerson(), self.factory.makeSourcePackageName(),
            pocket=PackagePublishingPocket.PROPOSED,
            distroseries=distroseries)

    def test_checkUpload_invalid_pocket_for_series_state(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        self.assertCannotUpload(
            CannotUploadToPocket, archive,
            self.factory.makePerson(), self.factory.makeSourcePackageName(),
            pocket=PackagePublishingPocket.UPDATES,
            distroseries=distroseries)

    def test_checkUpload_primary_proposed_development(self):
        # It should be possible to upload to the PROPOSED pocket while the
        # distroseries is in the DEVELOPMENT status.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newPackageUploader(
            person, sourcepackagename)
        self.assertCanUpload(
            archive, person, sourcepackagename,
            pocket=PackagePublishingPocket.PROPOSED,
            distroseries=distroseries)

    def test_checkUpload_backports_development(self):
        # It should be possible to upload to the BACKPORTS pocket while the
        # distroseries is in the DEVELOPMENT status.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newPackageUploader(
            person, sourcepackagename)
        self.assertCanUpload(
            archive, person, sourcepackagename,
            pocket=PackagePublishingPocket.BACKPORTS,
            distroseries=distroseries)

    def test_checkUpload_disabled_archive(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        archive = removeSecurityProxy(archive)
        archive.disable()
        self.assertCannotUpload(
            ArchiveDisabled, archive, self.factory.makePerson(),
            self.factory.makeSourcePackageName(),
            distroseries=distroseries)

    def test_checkUpload_ppa_owner(self):
        person = self.factory.makePerson()
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, owner=person)
        self.assertCanUpload(
            archive, person, self.factory.makeSourcePackageName())

    def test_checkUpload_ppa_with_permission(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newComponentUploader(person, "main")
        # component is ignored
        self.assertCanUpload(
            archive, person, self.factory.makeSourcePackageName(),
            component=self.factory.makeComponent(name="universe"))

    def test_checkUpload_ppa_with_no_permission(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        person = self.factory.makePerson()
        self.assertCannotUpload(
            CannotUploadToPPA, archive, person,
            self.factory.makeSourcePackageName())

    def test_owner_can_upload_to_ppa_no_sourcepackage(self):
        # The owner can upload to PPAs even if the source package doesn't
        # exist yet.
        team = self.factory.makeTeam()
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, owner=team)
        person = self.factory.makePerson()
        removeSecurityProxy(team).addMember(person, team.teamowner)
        self.assertCanUpload(archive, person, None)

    def test_can_upload_to_ppa_for_old_series(self):
        # You can upload whatever you want to a PPA, regardless of the upload
        # policy.
        person = self.factory.makePerson()
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, owner=person)
        spn = self.factory.makeSourcePackageName()
        distroseries = self.factory.makeDistroSeries(
            status=SeriesStatus.CURRENT)
        self.assertCanUpload(archive, person, spn, distroseries=distroseries)

    def test_checkUpload_copy_archive_no_permission(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.COPY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newPackageUploader(
            person, sourcepackagename)
        self.assertCannotUpload(
            NoRightsForArchive, archive, person, sourcepackagename,
            distroseries=distroseries)

    def test_checkUploadToPocket_for_released_distroseries_copy_archive(self):
        # Uploading to the release pocket in a released COPY archive
        # should be allowed.  This is mainly so that rebuilds that are
        # running during the release process don't suddenly cause
        # exceptions in the buildd-manager.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.COPY)
        distroseries = self.factory.makeDistroSeries(
            distribution=archive.distribution,
            status=SeriesStatus.CURRENT)
        self.assertIsNone(
            archive.checkUploadToPocket(
                distroseries, PackagePublishingPocket.RELEASE))

    def test_checkUploadToPocket_handles_redirects(self):
        # Uploading to the release pocket is disallowed if
        # Distribution.redirect_release_uploads is set.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        with person_logged_in(archive.distribution.owner):
            archive.distribution.redirect_release_uploads = True
        person = self.factory.makePerson()
        self.assertIsInstance(
            archive.checkUploadToPocket(
                distroseries, PackagePublishingPocket.RELEASE, person=person),
            RedirectedPocket)
        # The proposed pocket is unaffected.
        self.assertIsNone(
            archive.checkUploadToPocket(
                distroseries, PackagePublishingPocket.PROPOSED, person=person))
        # Queue admins bypass this check.
        with person_logged_in(archive.distribution.owner):
            archive.newQueueAdmin(person, "main")
        self.assertIsNone(
            archive.checkUploadToPocket(
                distroseries, PackagePublishingPocket.RELEASE, person=person))

    def test_checkUpload_package_permission(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newPackageUploader(
            person, sourcepackagename)
        self.assertCanUpload(
            archive, person, sourcepackagename, distroseries=distroseries)

    def makePersonWithPocketPermission(self, archive, pocket):
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newPocketUploader(person, pocket)
        return person

    def test_checkUpload_pocket_permission(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY, status=SeriesStatus.CURRENT)
        sourcepackagename = self.factory.makeSourcePackageName()
        pocket = PackagePublishingPocket.SECURITY
        person = self.makePersonWithPocketPermission(archive, pocket)
        self.assertCanUpload(
            archive, person, sourcepackagename, distroseries=distroseries,
            pocket=pocket)

    def make_person_with_packageset_permission(self, archive, distroseries,
                                               packages=()):
        packageset = self.factory.makePackageset(
            distroseries=distroseries, packages=packages)
        person = self.factory.makePerson()
        with person_logged_in(archive.distribution.owner):
            archive.newPackagesetUploader(person, packageset)
        return person, packageset

    def test_checkUpload_packageset_permission(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person, packageset = self.make_person_with_packageset_permission(
            archive, distroseries, packages=[sourcepackagename])
        self.assertCanUpload(
            archive, person, sourcepackagename, distroseries=distroseries)

    def test_checkUpload_packageset_wrong_distroseries(self):
        # A person with rights to upload to the package set in distro
        # series K may not upload with these same rights to a different
        # distro series L.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person, packageset = self.make_person_with_packageset_permission(
            archive, distroseries, packages=[sourcepackagename])
        other_distroseries = self.factory.makeDistroSeries()
        self.assertCannotUpload(
            InsufficientUploadRights, archive, person, sourcepackagename,
            distroseries=other_distroseries)

    def test_checkUpload_component_permission(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person, component = self.makePersonWithComponentPermission(
            archive)
        self.assertCanUpload(
            archive, person, sourcepackagename, distroseries=distroseries,
            component=component)

    def test_checkUpload_no_permissions(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person = self.factory.makePerson()
        self.assertCannotUpload(
            NoRightsForArchive, archive, person, sourcepackagename,
            distroseries=distroseries)

    def test_checkUpload_insufficient_permissions(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person, packageset = self.make_person_with_packageset_permission(
            archive, distroseries)
        self.assertCannotUpload(
            InsufficientUploadRights, archive, person, sourcepackagename,
            distroseries=distroseries)

    def test_checkUpload_without_strict_component(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person, component = self.makePersonWithComponentPermission(
            archive)
        other_component = self.factory.makeComponent()
        self.assertCanUpload(
            archive, person, sourcepackagename, distroseries=distroseries,
            component=other_component, strict_component=False)

    def test_checkUpload_with_strict_component(self):
        archive, distroseries = self.makeArchiveAndActiveDistroSeries(
            purpose=ArchivePurpose.PRIMARY)
        sourcepackagename = self.factory.makeSourcePackageName()
        person, component = self.makePersonWithComponentPermission(
            archive)
        other_component = self.factory.makeComponent()
        self.assertCannotUpload(
            NoRightsForComponent, archive, person, sourcepackagename,
            distroseries=distroseries, component=other_component,
            strict_component=True)

    def test_checkUpload_component_rights_no_package(self):
        # A person allowed to upload to a particular component of an archive
        # can upload basically whatever they want to that component, even if
        # the package doesn't exist yet.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        person, component = self.makePersonWithComponentPermission(archive)
        self.assertCanUpload(archive, person, None, component=component)

    def test_checkUpload_obsolete_series(self):
        distroseries = self.factory.makeDistroSeries(
            status=SeriesStatus.OBSOLETE)
        self.assertCannotUpload(
            CannotUploadToSeries, distroseries.distribution.main_archive,
            self.factory.makePerson(), None, distroseries=distroseries)

    def test_checkUpload_obsolete_series_with_flag(self):
        distroseries = self.factory.makeDistroSeries(
            status=SeriesStatus.OBSOLETE)
        archive = distroseries.distribution.main_archive
        person, component = self.makePersonWithComponentPermission(archive)
        removeSecurityProxy(archive).permit_obsolete_series_uploads = True
        self.assertCanUpload(
            archive, person, None, distroseries=distroseries,
            component=component)

    def makePackageToUpload(self, distroseries):
        sourcepackagename = self.factory.makeSourcePackageName()
        return self.factory.makeSuiteSourcePackage(
            pocket=PackagePublishingPocket.RELEASE,
            sourcepackagename=sourcepackagename,
            distroseries=distroseries)

    def test_canUploadSuiteSourcePackage_invalid_pocket(self):
        # Test that canUploadSuiteSourcePackage calls checkUpload for
        # the pocket checks.
        person = self.factory.makePerson()
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, owner=person)
        suitesourcepackage = self.factory.makeSuiteSourcePackage(
            pocket=PackagePublishingPocket.PROPOSED)
        self.assertFalse(
            archive.canUploadSuiteSourcePackage(person, suitesourcepackage))

    def test_canUploadSuiteSourcePackage_no_permission(self):
        # Test that canUploadSuiteSourcePackage calls verifyUpload for
        # the permission checks.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        suitesourcepackage = self.factory.makeSuiteSourcePackage(
            pocket=PackagePublishingPocket.RELEASE)
        person = self.factory.makePerson()
        self.assertFalse(
            archive.canUploadSuiteSourcePackage(person, suitesourcepackage))

    def test_canUploadSuiteSourcePackage_package_permission(self):
        # Test that a package permission is enough to upload a new
        # package.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries()
        suitesourcepackage = self.makePackageToUpload(distroseries)
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newPackageUploader(
            person, suitesourcepackage.sourcepackagename)
        self.assertTrue(
            archive.canUploadSuiteSourcePackage(person, suitesourcepackage))

    def test_canUploadSuiteSourcePackage_component_permission(self):
        # Test that component upload permission is enough to be
        # allowed to upload a new package.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries()
        suitesourcepackage = self.makePackageToUpload(distroseries)
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newComponentUploader(person, "universe")
        self.assertTrue(
            archive.canUploadSuiteSourcePackage(person, suitesourcepackage))

    def test_canUploadSuiteSourcePackage_strict_component(self):
        # Test that canUploadSuiteSourcePackage uses strict component
        # checking.
        archive, distroseries = self.makeArchiveAndActiveDistroSeries()
        suitesourcepackage = self.makePackageToUpload(distroseries)
        main_component = self.factory.makeComponent(name="main")
        self.factory.makeSourcePackagePublishingHistory(
            archive=archive, distroseries=distroseries,
            sourcepackagename=suitesourcepackage.sourcepackagename,
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE,
            component=main_component)
        person = self.factory.makePerson()
        removeSecurityProxy(archive).newComponentUploader(person, "universe")
        # This time the user can't upload as there has been a
        # publication and they don't have permission for the component
        # the package is published in.
        self.assertFalse(
            archive.canUploadSuiteSourcePackage(person, suitesourcepackage))

    def test_hasAnyPermission(self):
        # hasAnyPermission returns true if the person is the member of a
        # team with any kind of permission on the archive.
        archive = self.factory.makeArchive()
        person = self.factory.makePerson()
        team = self.factory.makeTeam()
        main = getUtility(IComponentSet)["main"]
        ArchivePermission(
            archive=archive, person=team, component=main,
            permission=ArchivePermissionType.UPLOAD)

        self.assertFalse(archive.hasAnyPermission(person))
        with celebrity_logged_in('admin'):
            team.addMember(person, team.teamowner)
        self.assertTrue(archive.hasAnyPermission(person))


class TestUpdatePackageDownloadCount(TestCaseWithFactory):
    """Ensure that updatePackageDownloadCount works as expected."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestUpdatePackageDownloadCount, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        self.store = IStore(Archive)

        self.archive = self.factory.makeArchive()
        self.bpr_1 = self.publisher.getPubBinaries(
                archive=self.archive)[0].binarypackagerelease
        self.bpr_2 = self.publisher.getPubBinaries(
                archive=self.archive)[0].binarypackagerelease

        country_set = getUtility(ICountrySet)
        self.australia = country_set['AU']
        self.new_zealand = country_set['NZ']

    def assertCount(self, count, archive, bpr, day, country):
        self.assertEqual(count, self.store.find(
            BinaryPackageReleaseDownloadCount,
            archive=archive, binary_package_release=bpr,
            day=day, country=country).one().count)

    def test_creates_new_entry(self):
        # The first update for a particular archive, package, day and
        # country will create a new BinaryPackageReleaseDownloadCount
        # entry.
        day = date(2010, 2, 20)
        self.assertIsNone(self.store.find(
            BinaryPackageReleaseDownloadCount,
            archive=self.archive, binary_package_release=self.bpr_1,
            day=day, country=self.australia).one())
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 10)
        self.assertCount(10, self.archive, self.bpr_1, day, self.australia)
        self.assertEqual(10, self.archive.getPackageDownloadTotal(self.bpr_1))

    def test_reuses_existing_entry(self):
        # A second update will simply add to the count on the existing
        # BPRDC.
        day = date(2010, 2, 20)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 10)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 3)
        self.assertCount(13, self.archive, self.bpr_1, day, self.australia)
        self.assertEqual(13, self.archive.getPackageDownloadTotal(self.bpr_1))

    def test_differentiates_between_countries(self):
        # A different country will cause a new entry to be created.
        day = date(2010, 2, 20)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 10)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.new_zealand, 3)

        self.assertCount(10, self.archive, self.bpr_1, day, self.australia)
        self.assertCount(3, self.archive, self.bpr_1, day, self.new_zealand)
        self.assertEqual(13, self.archive.getPackageDownloadTotal(self.bpr_1))

    def test_country_can_be_none(self):
        # The country can be None, indicating that it is unknown.
        day = date(2010, 2, 20)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 10)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, None, 3)

        self.assertCount(10, self.archive, self.bpr_1, day, self.australia)
        self.assertCount(3, self.archive, self.bpr_1, day, None)
        self.assertEqual(13, self.archive.getPackageDownloadTotal(self.bpr_1))

    def test_differentiates_between_days(self):
        # A different date will also cause a new entry to be created.
        day = date(2010, 2, 20)
        another_day = date(2010, 2, 21)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 10)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, another_day, self.australia, 3)

        self.assertCount(10, self.archive, self.bpr_1, day, self.australia)
        self.assertCount(
            3, self.archive, self.bpr_1, another_day, self.australia)
        self.assertEqual(13, self.archive.getPackageDownloadTotal(self.bpr_1))

    def test_differentiates_between_bprs(self):
        # And even a different package will create a new entry.
        day = date(2010, 2, 20)
        self.archive.updatePackageDownloadCount(
            self.bpr_1, day, self.australia, 10)
        self.archive.updatePackageDownloadCount(
            self.bpr_2, day, self.australia, 3)

        self.assertCount(10, self.archive, self.bpr_1, day, self.australia)
        self.assertCount(3, self.archive, self.bpr_2, day, self.australia)
        self.assertEqual(10, self.archive.getPackageDownloadTotal(self.bpr_1))
        self.assertEqual(3, self.archive.getPackageDownloadTotal(self.bpr_2))


class TestEnabledRestrictedBuilds(TestCaseWithFactory):
    """Ensure that restricted architectures builds can be allowed and
    disallowed correctly."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Setup an archive with relevant publications."""
        super(TestEnabledRestrictedBuilds, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()
        self.archive = self.factory.makeArchive()
        self.archive_arch_set = getUtility(IArchiveArchSet)
        self.arm = self.factory.makeProcessor(name='arm', restricted=True)

    def test_default(self):
        """By default, ARM builds are not allowed as ARM is restricted."""
        self.assertEqual(0,
            self.archive_arch_set.getByArchive(
                self.archive, self.arm).count())
        self.assertContentEqual([], self.archive.enabled_restricted_processors)

    def test_get_uses_archivearch(self):
        """Adding an entry to ArchiveArch for ARM and an archive will
        enable enabled_restricted_processors for arm for that archive."""
        self.assertContentEqual([], self.archive.enabled_restricted_processors)
        self.archive_arch_set.new(self.archive, self.arm)
        self.assertEqual(
            [self.arm], list(self.archive.enabled_restricted_processors))

    def test_get_returns_restricted_only(self):
        """Adding an entry to ArchiveArch for something that is not
        restricted does not make it show up in enabled_restricted_processors.
        """
        self.assertContentEqual([], self.archive.enabled_restricted_processors)
        self.archive_arch_set.new(
            self.archive, getUtility(IProcessorSet).getByName('amd64'))
        self.assertContentEqual([], self.archive.enabled_restricted_processors)

    def test_set(self):
        """The property remembers its value correctly and sets ArchiveArch."""
        self.archive.enabled_restricted_processors = [self.arm]
        allowed_restricted_processors = self.archive_arch_set.getByArchive(
            self.archive, self.arm)
        self.assertEqual(1, allowed_restricted_processors.count())
        self.assertEqual(
            self.arm, allowed_restricted_processors[0].processor)
        self.assertEqual(
            [self.arm], self.archive.enabled_restricted_processors)
        self.archive.enabled_restricted_processors = []
        self.assertEqual(
            0,
            self.archive_arch_set.getByArchive(self.archive, self.arm).count())
        self.assertContentEqual([], self.archive.enabled_restricted_processors)


class TestBuilddSecret(TestCaseWithFactory):
    """Test buildd_secret security.

    The buildd_secret is used by the slave scanner when generating a
    sources.list entry for the builder to access a private archive.  It is
    essentially the password to the archive for the builder.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBuilddSecret, self).setUp()
        self.archive = self.factory.makeArchive()

    def test_anonymous_cannot_set_buildd_secret(self):
        login(ANONYMOUS)
        e = self.assertRaises(
            Unauthorized, setattr, self.archive, "buildd_secret", "boing")
        self.assertEqual("launchpad.Admin", e.args[2])

    def test_commercial_admin_can_set_buildd_secret(self):
        with celebrity_logged_in("commercial_admin"):
            self.archive.buildd_secret = "not so secret at all"

    def test_admin_can_set_buildd_secret(self):
        with celebrity_logged_in("admin"):
            self.archive.buildd_secret = "not so secret"

    def test_public_archive_has_public_buildd_secret(self):
        # In a public PPA, the buildd "secret" is visible to anyone.
        with celebrity_logged_in("admin"):
            self.archive.buildd_secret = "not so secret"
        login(ANONYMOUS)
        self.assertFalse(self.archive.private)
        self.assertEqual("not so secret", self.archive.buildd_secret)

    def test_private_archive_has_private_buildd_secret(self):
        # In a private PPA, the buildd secret can only be read by users with
        # launchpad.View on the archive.
        with celebrity_logged_in("admin"):
            self.archive.buildd_secret = "really secret"
            self.archive.private = True
        login(ANONYMOUS)
        e = self.assertRaises(
            Unauthorized, getattr, self.archive, "buildd_secret")
        self.assertEqual("launchpad.View", e.args[2])
        with person_logged_in(self.archive.owner):
            self.assertEqual("really secret", self.archive.buildd_secret)


class TestArchiveTokens(TestCaseWithFactory):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestArchiveTokens, self).setUp()
        owner = self.factory.makePerson()
        self.private_ppa = self.factory.makeArchive(owner=owner, private=True)
        self.joe = self.factory.makePerson(name='joe')
        self.private_ppa.newSubscription(self.joe, owner)

    def test_getAuthToken_with_no_token(self):
        token = self.private_ppa.getAuthToken(self.joe)
        self.assertEqual(token, None)

    def test_getAuthToken_with_token(self):
        token = self.private_ppa.newAuthToken(self.joe)
        self.assertEqual(self.private_ppa.getAuthToken(self.joe), token)

    def test_getArchiveSubscriptionURL(self):
        url = self.joe.getArchiveSubscriptionURL(self.joe, self.private_ppa)
        token = self.private_ppa.getAuthToken(self.joe)
        self.assertEqual(token.archive_url, url)


class TestGetBinaryPackageRelease(TestCaseWithFactory):
    """Ensure that getBinaryPackageRelease works as expected."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Setup an archive with relevant publications."""
        super(TestGetBinaryPackageRelease, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        self.archive = self.factory.makeArchive()
        self.archive.require_virtualized = False

        self.i386_pub, self.hppa_pub = self.publisher.getPubBinaries(
            version="1.2.3-4", archive=self.archive, binaryname="foo-bin",
            status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True)

        self.i386_indep_pub, self.hppa_indep_pub = (
            self.publisher.getPubBinaries(
                version="1.2.3-4", archive=self.archive, binaryname="bar-bin",
                status=PackagePublishingStatus.PUBLISHED))

        self.bpns = getUtility(IBinaryPackageNameSet)

    def test_returns_matching_binarypackagerelease(self):
        # The BPR with a file by the given name should be returned.
        self.assertEqual(
            self.i386_pub.binarypackagerelease,
            self.archive.getBinaryPackageRelease(
                self.bpns['foo-bin'], '1.2.3-4', 'i386'))

    def test_returns_correct_architecture(self):
        # The architecture is taken into account correctly.
        self.assertEqual(
            self.hppa_pub.binarypackagerelease,
            self.archive.getBinaryPackageRelease(
                self.bpns['foo-bin'], '1.2.3-4', 'hppa'))

    def test_works_with_architecture_independent_binaries(self):
        # Architecture independent binaries with multiple publishings
        # are found properly.
        # We use 'i386' as the arch tag here, since what we have in the DB
        # is the *build* arch tag, not the one in the filename ('all').
        self.assertEqual(
            self.i386_indep_pub.binarypackagerelease,
            self.archive.getBinaryPackageRelease(
                self.bpns['bar-bin'], '1.2.3-4', 'i386'))

    def test_returns_none_for_nonexistent_binary(self):
        # Non-existent files return None.
        self.assertIsNone(
            self.archive.getBinaryPackageRelease(
                self.bpns['cdrkit'], '1.2.3-4', 'i386'))

    def test_returns_none_for_duplicate_file(self):
        # In the unlikely case of multiple BPRs in this archive with the same
        # name (hopefully impossible, but it still happens occasionally due
        # to bugs), None is returned.

        # Publish the same binaries again. Evil.
        self.publisher.getPubBinaries(
            version="1.2.3-4", archive=self.archive, binaryname="foo-bin",
            status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True)

        self.assertIsNone(
            self.archive.getBinaryPackageRelease(
                self.bpns['foo-bin'], '1.2.3-4', 'i386'))

    def test_returns_none_from_another_archive(self):
        # Cross-archive searches are not performed.
        self.assertIsNone(
            self.factory.makeArchive().getBinaryPackageRelease(
                self.bpns['foo-bin'], '1.2.3-4', 'i386'))


class TestGetBinaryPackageReleaseByFileName(TestCaseWithFactory):
    """Ensure that getBinaryPackageReleaseByFileName works as expected."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Setup an archive with relevant publications."""
        super(TestGetBinaryPackageReleaseByFileName, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        self.archive = self.factory.makeArchive()
        self.archive.require_virtualized = False

        self.i386_pub, self.hppa_pub = self.publisher.getPubBinaries(
            version="1.2.3-4", archive=self.archive, binaryname="foo-bin",
            status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True)

        self.i386_indep_pub, self.hppa_indep_pub = (
            self.publisher.getPubBinaries(
                version="1.2.3-4", archive=self.archive, binaryname="bar-bin",
                status=PackagePublishingStatus.PUBLISHED))

    def test_returns_matching_binarypackagerelease(self):
        # The BPR with a file by the given name should be returned.
        self.assertEqual(
            self.i386_pub.binarypackagerelease,
            self.archive.getBinaryPackageReleaseByFileName(
                "foo-bin_1.2.3-4_i386.deb"))

    def test_returns_correct_architecture(self):
        # The architecture is taken into account correctly.
        self.assertEqual(
            self.hppa_pub.binarypackagerelease,
            self.archive.getBinaryPackageReleaseByFileName(
                "foo-bin_1.2.3-4_hppa.deb"))

    def test_works_with_architecture_independent_binaries(self):
        # Architecture independent binaries with multiple publishings
        # are found properly.
        self.assertEqual(
            self.i386_indep_pub.binarypackagerelease,
            self.archive.getBinaryPackageReleaseByFileName(
                "bar-bin_1.2.3-4_all.deb"))

    def test_returns_none_for_source_file(self):
        # None is returned if the file is a source component instead.
        self.assertIsNone(
            self.archive.getBinaryPackageReleaseByFileName(
                "foo_1.2.3-4.dsc"))

    def test_returns_none_for_nonexistent_file(self):
        # Non-existent files return None.
        self.assertIsNone(
            self.archive.getBinaryPackageReleaseByFileName(
                "this-is-not-real_1.2.3-4_all.deb"))

    def test_returns_latest_for_duplicate_file(self):
        # In the unlikely case of multiple BPRs in this archive with the same
        # name (hopefully impossible, but it still happens occasionally due
        # to bugs), the latest is returned.

        # Publish the same binaries again. Evil.
        new_pubs = self.publisher.getPubBinaries(
            version="1.2.3-4", archive=self.archive, binaryname="foo-bin",
            status=PackagePublishingStatus.PUBLISHED,
            architecturespecific=True)

        self.assertEqual(
            new_pubs[0].binarypackagerelease,
            self.archive.getBinaryPackageReleaseByFileName(
                "foo-bin_1.2.3-4_i386.deb"))

    def test_returns_none_from_another_archive(self):
        # Cross-archive searches are not performed.
        self.assertIsNone(
            self.factory.makeArchive().getBinaryPackageReleaseByFileName(
                "foo-bin_1.2.3-4_i386.deb"))


class TestArchiveDelete(TestCaseWithFactory):
    """Edge-case tests for PPA deletion.

    PPA deletion is also documented in lp/soyuz/doc/archive-deletion.txt.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a test archive and login as the owner."""
        super(TestArchiveDelete, self).setUp()
        self.archive = self.factory.makeArchive()
        login_person(self.archive.owner)

    def test_delete(self):
        # Sanity check for the unit-test.
        self.archive.delete(deleted_by=self.archive.owner)
        self.assertEqual(ArchiveStatus.DELETING, self.archive.status)

    def test_delete_when_disabled(self):
        # A disabled archive can also be deleted (bug 574246).
        self.archive.disable()
        self.archive.delete(deleted_by=self.archive.owner)
        self.assertEqual(ArchiveStatus.DELETING, self.archive.status)


class TestSuppressSubscription(TestCaseWithFactory):
    """Tests relating to suppressing subscription."""

    layer = DatabaseFunctionalLayer

    def test_set_and_get_suppress(self):
        # Basic set and get of the suppress_subscription_notifications
        # property.  Anyone can read it and it defaults to False.
        archive = self.factory.makeArchive()
        with person_logged_in(archive.owner):
            self.assertFalse(archive.suppress_subscription_notifications)

            # The archive owner can change the value.
            archive.suppress_subscription_notifications = True
            self.assertTrue(archive.suppress_subscription_notifications)

    def test_most_users_cant_set_suppress(self):
        # Basic set and get of the suppress_subscription_notifications
        # property.  Anyone can read it and it defaults to False.
        archive = self.factory.makeArchive()
        with person_logged_in(self.factory.makePerson()):
            self.assertFalse(archive.suppress_subscription_notifications)
            self.assertRaises(Unauthorized,
                setattr, archive, 'suppress_subscription_notifications', True)


class TestBuildDebugSymbols(TestCaseWithFactory):
    """Tests relating to the build_debug_symbols flag."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBuildDebugSymbols, self).setUp()
        self.archive = self.factory.makeArchive()

    def setBuildDebugSymbols(self, archive, build_debug_symbols):
        """Helper function."""
        archive.build_debug_symbols = build_debug_symbols

    def test_build_debug_symbols_is_public(self):
        # Anyone can see the attribute.
        login(ANONYMOUS)
        self.assertFalse(self.archive.build_debug_symbols)

    def test_owner_cannot_set_build_debug_symbols(self):
        # The archive owner cannot set it.
        login_person(self.archive.owner)
        self.assertRaises(
            Unauthorized, self.setBuildDebugSymbols, self.archive, True)

    def test_commercial_admin_can_set_build_debug_symbols(self):
        # A commercial admin can set it.
        with celebrity_logged_in('commercial_admin'):
            self.setBuildDebugSymbols(self.archive, True)
            self.assertTrue(self.archive.build_debug_symbols)


class TestAddArchiveDependencies(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_add_hidden_dependency(self):
        # The user cannot add a dependency on an archive they cannot see.
        archive = self.factory.makeArchive(private=True)
        dependency = self.factory.makeArchive(private=True)
        with person_logged_in(archive.owner):
            with ExpectedException(
                ArchiveDependencyError,
                "You don't have permission to use this dependency."):
                archive.addArchiveDependency(dependency, 'foo')

    def test_private_dependency_public_archive(self):
        # A public archive may not depend on a private archive.
        archive = self.factory.makeArchive()
        dependency = self.factory.makeArchive(
            private=True, owner=archive.owner)
        with person_logged_in(archive.owner):
            with ExpectedException(
                ArchiveDependencyError,
                "Public PPAs cannot depend on private ones."):
                archive.addArchiveDependency(dependency, 'foo')

    def test_add_private_dependency(self):
        # The user can add a dependency on private archive they can see.
        archive = self.factory.makeArchive(private=True)
        dependency = self.factory.makeArchive(
            private=True, owner=archive.owner)
        with person_logged_in(archive.owner):
            archive_dependency = archive.addArchiveDependency(dependency,
                PackagePublishingPocket.RELEASE)
            self.assertContentEqual(archive.dependencies, [archive_dependency])


class TestArchiveDependencies(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_private_sources_list(self):
        """Entries for private dependencies include credentials."""
        p3a = self.factory.makeArchive(name='p3a', private=True)
        dependency = self.factory.makeArchive(
            name='dependency', private=True, owner=p3a.owner)
        with person_logged_in(p3a.owner):
            bpph = self.factory.makeBinaryPackagePublishingHistory(
                archive=dependency, status=PackagePublishingStatus.PUBLISHED)
            p3a.addArchiveDependency(dependency,
                PackagePublishingPocket.RELEASE)
            build = self.factory.makeBinaryPackageBuild(archive=p3a,
                distroarchseries=bpph.distroarchseries)
            sources_list = get_sources_list_for_building(
                build, build.distro_arch_series,
                build.source_package_release.name)
            matches = MatchesRegex(
                "deb http://buildd:sekrit@private-ppa.launchpad.dev/"
                "person-name-.*/dependency/ubuntu distroseries-.* main")
            self.assertThat(sources_list[0], matches)


class TestFindDepCandidates(TestCaseWithFactory):
    """Tests for Archive.findDepCandidates."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestFindDepCandidates, self).setUp()
        self.archive = self.factory.makeArchive()
        self.publisher = SoyuzTestPublisher()
        login('admin@canonical.com')
        self.publisher.prepareBreezyAutotest()

    def assertDep(self, arch_tag, name, expected, archive=None,
                  pocket=PackagePublishingPocket.RELEASE, component=None,
                  source_package_name='something-new'):
        """Helper to check that findDepCandidates works.

        Searches for the given dependency name in the given architecture and
        archive, and compares it to the given expected value.
        The archive defaults to self.archive.

        Also commits, since findDepCandidates uses the slave store.
        """
        transaction.commit()

        if component is None:
            component = getUtility(IComponentSet)['main']
        if archive is None:
            archive = self.archive

        self.assertEqual(
            expected,
            list(archive.findDepCandidates(
                self.publisher.distroseries[arch_tag], pocket, component,
                source_package_name, name)))

    def test_finds_candidate_in_same_archive(self):
        # A published candidate in the same archive should be found.
        bins = self.publisher.getPubBinaries(
            binaryname='foo', archive=self.archive,
            status=PackagePublishingStatus.PUBLISHED)
        self.assertDep('i386', 'foo', [bins[0]])
        self.assertDep('hppa', 'foo', [bins[1]])

    def test_does_not_find_pending_publication(self):
        # A pending candidate in the same archive should not be found.
        self.publisher.getPubBinaries(
            binaryname='foo', archive=self.archive)
        self.assertDep('i386', 'foo', [])

    def test_ppa_searches_primary_archive(self):
        # PPA searches implicitly look in the primary archive too.
        self.assertEqual(self.archive.purpose, ArchivePurpose.PPA)
        self.assertDep('i386', 'foo', [])

        bins = self.publisher.getPubBinaries(
            binaryname='foo', archive=self.archive.distribution.main_archive,
            status=PackagePublishingStatus.PUBLISHED)

        self.assertDep('i386', 'foo', [bins[0]])

    def test_searches_dependencies(self):
        # Candidates from archives on which the target explicitly depends
        # should be found.
        bins = self.publisher.getPubBinaries(
            binaryname='foo', archive=self.archive,
            status=PackagePublishingStatus.PUBLISHED)
        other_archive = self.factory.makeArchive()
        self.assertDep('i386', 'foo', [], archive=other_archive)

        other_archive.addArchiveDependency(
            self.archive, PackagePublishingPocket.RELEASE)
        self.assertDep('i386', 'foo', [bins[0]], archive=other_archive)

    def test_obeys_dependency_pockets(self):
        # Only packages published in a pocket matching the dependency should
        # be found.
        release_bins = self.publisher.getPubBinaries(
            binaryname='foo-release', archive=self.archive,
            status=PackagePublishingStatus.PUBLISHED)
        updates_bins = self.publisher.getPubBinaries(
            binaryname='foo-updates', archive=self.archive,
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.UPDATES)
        proposed_bins = self.publisher.getPubBinaries(
            binaryname='foo-proposed', archive=self.archive,
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.PROPOSED)

        # Temporarily turn our test PPA into a copy archive, so we can
        # add non-RELEASE dependencies on it.
        removeSecurityProxy(self.archive).purpose = ArchivePurpose.COPY

        other_archive = self.factory.makeArchive()
        other_archive.addArchiveDependency(
            self.archive, PackagePublishingPocket.UPDATES)
        self.assertDep(
            'i386', 'foo-release', [release_bins[0]], archive=other_archive)
        self.assertDep(
            'i386', 'foo-updates', [updates_bins[0]], archive=other_archive)
        self.assertDep('i386', 'foo-proposed', [], archive=other_archive)

        other_archive.removeArchiveDependency(self.archive)
        other_archive.addArchiveDependency(
            self.archive, PackagePublishingPocket.PROPOSED)
        self.assertDep(
            'i386', 'foo-proposed', [proposed_bins[0]], archive=other_archive)

    def test_obeys_dependency_components(self):
        # Only packages published in a component matching the dependency
        # should be found.
        primary = self.archive.distribution.main_archive
        main_bins = self.publisher.getPubBinaries(
            binaryname='foo-main', archive=primary, component='main',
            status=PackagePublishingStatus.PUBLISHED)
        universe_bins = self.publisher.getPubBinaries(
            binaryname='foo-universe', archive=primary,
            component='universe',
            status=PackagePublishingStatus.PUBLISHED)

        self.archive.addArchiveDependency(
            primary, PackagePublishingPocket.RELEASE,
            component=getUtility(IComponentSet)['main'])
        self.assertDep('i386', 'foo-main', [main_bins[0]])
        self.assertDep('i386', 'foo-universe', [])

        self.archive.removeArchiveDependency(primary)
        self.archive.addArchiveDependency(
            primary, PackagePublishingPocket.RELEASE,
            component=getUtility(IComponentSet)['universe'])
        self.assertDep('i386', 'foo-main', [main_bins[0]])
        self.assertDep('i386', 'foo-universe', [universe_bins[0]])


class TestOverlays(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def _createDep(self, derived_series, parent_series,
                   parent_distro, component_name=None, pocket=None,
                   overlay=True, arch_tag='i386',
                   publish_base_url=u'http://archive.launchpad.dev/'):
        # Helper to create a parent/child relationshipi.
        if type(parent_distro) == str:
            depdistro = self.factory.makeDistribution(parent_distro,
                publish_base_url=publish_base_url)
        else:
            depdistro = parent_distro
        if type(parent_series) == str:
            depseries = self.factory.makeDistroSeries(
                name=parent_series, distribution=depdistro)
            self.factory.makeDistroArchSeries(
                distroseries=depseries, architecturetag=arch_tag)
        else:
            depseries = parent_series
        if component_name is not None:
            component = getUtility(IComponentSet)[component_name]
        else:
            component = None

        self.factory.makeDistroSeriesParent(
            derived_series=derived_series, parent_series=depseries,
            initialized=True, is_overlay=overlay, pocket=pocket,
            component=component)
        return depseries, depdistro

    def test_overlay_dependencies(self):
        # sources.list is properly generated for a complex overlay structure.
        # Pocket dependencies and component dependencies are taken into
        # account when generating sources.list.
        #
        #            breezy               type of relation:
        #               |                    |           |
        #    -----------------------         |           o
        #    |          |          |         |           |
        #    o          o          |      no overlay  overlay
        #    |          |          |
        # series11  series21   series31
        #    |
        #    o
        #    |
        # series12
        #
        test_publisher = SoyuzTestPublisher()
        test_publisher.prepareBreezyAutotest()
        breezy = test_publisher.breezy_autotest
        pub_source = test_publisher.getPubSource(
            version='1.1', archive=breezy.main_archive)
        [build] = pub_source.createMissingBuilds()
        series11, depdistro = self._createDep(
            breezy, 'series11', 'depdistro', 'universe',
            PackagePublishingPocket.SECURITY)
        self._createDep(
            breezy, 'series21', 'depdistro2', 'multiverse',
            PackagePublishingPocket.UPDATES)
        self._createDep(breezy, 'series31', 'depdistro3', overlay=False)
        self._createDep(
            series11, 'series12', 'depdistro4', 'multiverse',
            PackagePublishingPocket.UPDATES)
        sources_list = get_sources_list_for_building(build,
            build.distro_arch_series, build.source_package_release.name)

        self.assertThat(
            "\n".join(sources_list),
            DocTestMatches(
                ".../ubuntutest breezy-autotest main\n"
                ".../depdistro series11 main universe\n"
                ".../depdistro series11-security main universe\n"
                ".../depdistro2 series21 "
                    "main restricted universe multiverse\n"
                ".../depdistro2 series21-security "
                    "main restricted universe multiverse\n"
                ".../depdistro2 series21-updates "
                   "main restricted universe multiverse\n"
                ".../depdistro4 series12 main restricted "
                    "universe multiverse\n"
                ".../depdistro4 series12-security main "
                    "restricted universe multiverse\n"
                ".../depdistro4 series12-updates "
                    "main restricted universe multiverse\n",
                doctest.ELLIPSIS))


class TestComponents(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_no_components_for_arbitrary_person(self):
        # By default, a person cannot upload to any component of an archive.
        archive = self.factory.makeArchive()
        person = self.factory.makePerson()
        self.assertFalse(set(archive.getComponentsForUploader(person)))

    def test_components_for_person_with_permissions(self):
        # If a person has been explicitly granted upload permissions to a
        # particular component, then those components are included in
        # IArchive.getComponentsForUploader.
        archive = self.factory.makeArchive()
        component = self.factory.makeComponent()
        person = self.factory.makePerson()
        # Only admins or techboard members can add permissions normally. That
        # restriction isn't relevant to this test.
        ap_set = removeSecurityProxy(getUtility(IArchivePermissionSet))
        ap = ap_set.newComponentUploader(archive, person, component)
        self.assertEqual(set([ap]),
            set(archive.getComponentsForUploader(person)))


class TestPockets(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_no_pockets_for_arbitrary_person(self):
        # By default, a person cannot upload to any pocket of an archive.
        archive = self.factory.makeArchive()
        person = self.factory.makePerson()
        self.assertEqual(set(), set(archive.getPocketsForUploader(person)))

    def test_pockets_for_person_with_permissions(self):
        # If a person has been explicitly granted upload permissions to a
        # particular pocket, then those pockets are included in
        # IArchive.getPocketsForUploader.
        archive = self.factory.makeArchive()
        person = self.factory.makePerson()
        # Only admins or techboard members can add permissions normally. That
        # restriction isn't relevant to this test.
        ap_set = removeSecurityProxy(getUtility(IArchivePermissionSet))
        ap = ap_set.newPocketUploader(
            archive, person, PackagePublishingPocket.SECURITY)
        self.assertEqual(set([ap]), set(archive.getPocketsForUploader(person)))


class TestValidatePPA(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_open_teams(self):
        team = self.factory.makeTeam()
        self.assertEqual(
            'Open teams cannot have PPAs.', validate_ppa(team, None))

    def test_distribution_name(self):
        ppa_owner = self.factory.makePerson()
        self.assertEqual(
            'A PPA cannot have the same name as its distribution.',
            validate_ppa(ppa_owner, 'ubuntu'))

    def test_private_ppa_standard_user(self):
        ppa_owner = self.factory.makePerson()
        with person_logged_in(ppa_owner):
            errors = validate_ppa(
                ppa_owner, self.factory.getUniqueString(), private=True)
        self.assertEqual(
            '%s is not allowed to make private PPAs' % (ppa_owner.name,),
            errors)

    def test_private_ppa_commercial_subscription(self):
        owner = self.factory.makePerson()
        self.factory.grantCommercialSubscription(owner)
        with person_logged_in(owner):
            errors = validate_ppa(owner, 'ppa', private=True)
        self.assertIsNone(errors)

    def test_private_ppa_commercial_admin(self):
        ppa_owner = self.factory.makePerson()
        with celebrity_logged_in('admin'):
            comm = getUtility(ILaunchpadCelebrities).commercial_admin
            comm.addMember(ppa_owner, comm.teamowner)
        with person_logged_in(ppa_owner):
            self.assertIsNone(
                validate_ppa(
                    ppa_owner, self.factory.getUniqueString(), private=True))

    def test_private_ppa_admin(self):
        ppa_owner = self.factory.makeAdministrator()
        with person_logged_in(ppa_owner):
            self.assertIsNone(
                validate_ppa(
                    ppa_owner, self.factory.getUniqueString(), private=True))

    def test_two_ppas(self):
        ppa = self.factory.makeArchive(name='ppa')
        self.assertEqual(
            "You already have a PPA named 'ppa'.",
            validate_ppa(ppa.owner, 'ppa'))

    def test_two_ppas_with_team(self):
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED)
        self.factory.makeArchive(owner=team, name='ppa')
        self.assertEqual(
            "%s already has a PPA named 'ppa'." % team.displayname,
            validate_ppa(team, 'ppa'))

    def test_valid_ppa(self):
        ppa_owner = self.factory.makePerson()
        self.assertIsNone(validate_ppa(ppa_owner, None))

    def test_private_team_private_ppa(self):
        # Folk with launchpad.Edit on a private team can make private PPAs for
        # that team, regardless of whether they have super-powers.a
        team_owner = self.factory.makePerson()
        private_team = self.factory.makeTeam(
            owner=team_owner, visibility=PersonVisibility.PRIVATE,
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        team_admin = self.factory.makePerson()
        with person_logged_in(team_owner):
            private_team.addMember(
                team_admin, team_owner, status=TeamMembershipStatus.ADMIN)
        with person_logged_in(team_admin):
            result = validate_ppa(private_team, 'ppa', private=True)
        self.assertIsNone(result)

    def test_private_team_public_ppa(self):
        # No one can make a public PPA for a private team.
        team_owner = self.factory.makePerson()
        private_team = self.factory.makeTeam(
            owner=team_owner, visibility=PersonVisibility.PRIVATE,
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        team_admin = self.factory.makePerson()
        with person_logged_in(team_owner):
            private_team.addMember(
                team_admin, team_owner, status=TeamMembershipStatus.ADMIN)
        with person_logged_in(team_admin):
            result = validate_ppa(private_team, 'ppa', private=False)
        self.assertEqual(
            'Private teams may not have public archives.', result)


class TestGetComponentsForSeries(TestCaseWithFactory):
    """Tests for Archive.getComponentsForSeries."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGetComponentsForSeries, self).setUp()
        self.series = self.factory.makeDistroSeries()
        self.comp1 = self.factory.makeComponent()
        self.comp2 = self.factory.makeComponent()

    def test_series_components_for_primary_archive(self):
        # The primary archive uses the series' defined components.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        self.assertEqual(0, len(archive.getComponentsForSeries(self.series)))

        ComponentSelection(distroseries=self.series, component=self.comp1)
        ComponentSelection(distroseries=self.series, component=self.comp2)
        clear_property_cache(self.series)

        self.assertEqual(
            set((self.comp1, self.comp2)),
            set(archive.getComponentsForSeries(self.series)))

    def test_partner_component_for_partner_archive(self):
        # The partner archive always uses only the 'partner' component.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PARTNER)
        ComponentSelection(distroseries=self.series, component=self.comp1)
        partner_comp = getUtility(IComponentSet)['partner']
        self.assertEqual(
            [partner_comp],
            list(archive.getComponentsForSeries(self.series)))

    def test_component_for_ppas(self):
        # PPAs only use 'main'.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        ComponentSelection(distroseries=self.series, component=self.comp1)
        main_comp = getUtility(IComponentSet)['main']
        self.assertEqual(
            [main_comp], list(archive.getComponentsForSeries(self.series)))


class TestDefaultComponent(TestCaseWithFactory):
    """Tests for Archive.default_component."""

    layer = DatabaseFunctionalLayer

    def test_default_component_for_other_archives(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        self.assertIsNone(archive.default_component)

    def test_default_component_for_partner(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PARTNER)
        self.assertEqual(
            getUtility(IComponentSet)['partner'], archive.default_component)

    def test_default_component_for_ppas(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertEqual(
            getUtility(IComponentSet)['main'], archive.default_component)


class TestGetPockets(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_getPockets_for_other_archives(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        self.assertEqual(
            list(PackagePublishingPocket.items), archive.getPockets())

    def test_getPockets_for_PPAs(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertEqual(
            [PackagePublishingPocket.RELEASE], archive.getPockets())


class TestGetFileByName(TestCaseWithFactory):
    """Tests for Archive.getFileByName."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestGetFileByName, self).setUp()
        self.archive = self.factory.makeArchive()

    def test_unknown_file_is_not_found(self):
        # A file with an unsupported extension is not found.
        self.assertRaises(NotFoundError, self.archive.getFileByName, 'a.bar')

    def test_source_file_is_found(self):
        # A file from a published source package can be retrieved.
        pub = self.factory.makeSourcePackagePublishingHistory(
            archive=self.archive)
        dsc = self.factory.makeLibraryFileAlias(filename='foo_1.0.dsc')
        self.assertRaises(
            NotFoundError, self.archive.getFileByName, dsc.filename)
        pub.sourcepackagerelease.addFile(dsc)
        self.assertEqual(dsc, self.archive.getFileByName(dsc.filename))

    def test_nonexistent_source_file_is_not_found(self):
        # Something that looks like a source file but isn't is not
        # found.
        self.assertRaises(
            NotFoundError, self.archive.getFileByName, 'foo_1.0.dsc')

    def test_binary_file_is_found(self):
        # A file from a published binary package can be retrieved.
        pub = self.factory.makeBinaryPackagePublishingHistory(
            archive=self.archive)
        deb = self.factory.makeLibraryFileAlias(filename='foo_1.0_all.deb')
        self.assertRaises(
            NotFoundError, self.archive.getFileByName, deb.filename)
        pub.binarypackagerelease.addFile(deb)
        self.assertEqual(deb, self.archive.getFileByName(deb.filename))

    def test_nonexistent_binary_file_is_not_found(self):
        # Something that looks like a binary file but isn't is not
        # found.
        self.assertRaises(
            NotFoundError, self.archive.getFileByName, 'foo_1.0_all.deb')

    def test_source_changes_file_is_found(self):
        # A .changes file from a published source can be retrieved.
        pub = self.factory.makeSourcePackagePublishingHistory(
            archive=self.archive)
        pu = self.factory.makePackageUpload(
            changes_filename='foo_1.0_source.changes')
        pu.setDone()
        self.assertRaises(
            NotFoundError, self.archive.getFileByName, pu.changesfile.filename)
        pu.addSource(pub.sourcepackagerelease)
        self.assertEqual(
            pu.changesfile,
            self.archive.getFileByName(pu.changesfile.filename))

    def test_nonexistent_source_changes_file_is_not_found(self):
        # Something that looks like a source .changes file but isn't is not
        # found.
        self.assertRaises(
            NotFoundError, self.archive.getFileByName,
            'foo_1.0_source.changes')

    def test_package_diff_is_found(self):
        # A .diff.gz from a package diff can be retrieved.
        pub = self.factory.makeSourcePackagePublishingHistory(
            archive=self.archive)
        diff = self.factory.makePackageDiff(
            to_source=pub.sourcepackagerelease,
            diff_filename='foo_1.0.diff.gz')
        self.assertEqual(
            diff.diff_content,
            self.archive.getFileByName(diff.diff_content.filename))

    def test_expired_files_are_skipped(self):
        # Expired files are ignored.
        pub = self.factory.makeSourcePackagePublishingHistory(
            archive=self.archive)
        dsc = self.factory.makeLibraryFileAlias(filename='foo_1.0.dsc')
        pub.sourcepackagerelease.addFile(dsc)

        # The file is initially found without trouble.
        self.assertEqual(dsc, self.archive.getFileByName(dsc.filename))

        # But after expiry it is not.
        removeSecurityProxy(dsc).content = None
        self.assertRaises(
            NotFoundError, self.archive.getFileByName, dsc.filename)

        # It reappears if we create a new one.
        new_dsc = self.factory.makeLibraryFileAlias(filename=dsc.filename)
        pub.sourcepackagerelease.addFile(new_dsc)
        self.assertEqual(new_dsc, self.archive.getFileByName(dsc.filename))

    def test_oddly_named_files_are_found(self):
        pub = self.factory.makeSourcePackagePublishingHistory(
            archive=self.archive)
        pu = self.factory.makePackageUpload(
            changes_filename='foo-bar-baz_amd64.changes')
        pu.setDone()
        pu.addSource(pub.sourcepackagerelease)
        self.assertEqual(
            pu.changesfile,
            self.archive.getFileByName(pu.changesfile.filename))


class TestGetPublishedSources(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_getPublishedSources_comprehensive(self):
        # The doctests for getPublishedSources migrated from a doctest for
        # better testing.
        cprov = getUtility(IPersonSet).getByName('cprov')
        cprov_archive = cprov.archive
        # There are three published sources by default - no args returns all
        # publications.
        self.assertEqual(3, cprov_archive.getPublishedSources().count())
        # Various filters.
        active_status = [PackagePublishingStatus.PENDING,
                         PackagePublishingStatus.PUBLISHED]
        inactive_status = [PackagePublishingStatus.SUPERSEDED,
                           PackagePublishingStatus.DELETED]
        warty = cprov_archive.distribution['warty']
        hoary = cprov_archive.distribution['hoary']
        breezy_autotest = cprov_archive.distribution['breezy-autotest']
        all_sources = cprov_archive.getPublishedSources()
        expected = [('cdrkit - 1.0', 'breezy-autotest'),
            ('iceweasel - 1.0', 'warty'),
            ('pmount - 0.1-1', 'warty'),
            ]
        found = []
        for pub in all_sources:
            title = pub.sourcepackagerelease.title
            pub_ds = pub.distroseries.name
            found.append((title, pub_ds))
        self.assertEqual(expected, found)
        self.assertEqual(1,
            cprov_archive.getPublishedSources(name=u'cd').count())
        self.assertEqual(1,
            cprov_archive.getPublishedSources(name=u'ice').count())
        self.assertEqual(1, cprov_archive.getPublishedSources(
            name=u'iceweasel', exact_match=True).count())
        self.assertEqual(0, cprov_archive.getPublishedSources(
            name=u'ice', exact_match=True).count())
        self.assertRaises(VersionRequiresName,
            cprov_archive.getPublishedSources,
            version='1.0')
        self.assertEqual(1, cprov_archive.getPublishedSources(
            name=u'ice', version='1.0').count())
        self.assertEqual(0, cprov_archive.getPublishedSources(
            name=u'ice', version='666').count())
        self.assertEqual(3, cprov_archive.getPublishedSources(
            status=PackagePublishingStatus.PUBLISHED).count())
        self.assertEqual(3, cprov_archive.getPublishedSources(
            status=active_status).count())
        self.assertEqual(0, cprov_archive.getPublishedSources(
            status=inactive_status).count())
        self.assertEqual(2, cprov_archive.getPublishedSources(
            distroseries=warty).count())
        self.assertEqual(0, cprov_archive.getPublishedSources(
            distroseries=hoary).count())
        self.assertEqual(1, cprov_archive.getPublishedSources(
            distroseries=breezy_autotest).count())
        self.assertEqual(2, cprov_archive.getPublishedSources(
            distroseries=warty,
            pocket=PackagePublishingPocket.RELEASE).count())
        self.assertEqual(0, cprov_archive.getPublishedSources(
            distroseries=warty,
            pocket=PackagePublishingPocket.UPDATES).count())
        self.assertEqual(1, cprov_archive.getPublishedSources(
            name=u'ice', distroseries=warty).count())
        self.assertEqual(0, cprov_archive.getPublishedSources(
            name=u'ice', distroseries=breezy_autotest).count())
        mid_2007 = datetime(year=2007, month=7, day=9, hour=14, tzinfo=UTC)
        self.assertEqual(0, cprov_archive.getPublishedSources(
            created_since_date=mid_2007).count())
        one_hour_step = timedelta(hours=1)
        one_hour_earlier = mid_2007 - one_hour_step
        self.assertEqual(1, cprov_archive.getPublishedSources(
             created_since_date=one_hour_earlier).count())
        two_hours_earlier = one_hour_earlier - one_hour_step
        self.assertEqual(3, cprov_archive.getPublishedSources(
            created_since_date=two_hours_earlier).count())

    def test_getPublishedSources_name(self):
        # The name parameter allows filtering with a list of
        # names.
        distroseries = self.factory.makeDistroSeries()
        # Create some SourcePackagePublishingHistory.
        for package_name in ['package1', 'package2', 'package3']:
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries,
                archive=distroseries.main_archive,
                sourcepackagename=self.factory.makeSourcePackageName(
                    package_name))
        filtered_sources = distroseries.main_archive.getPublishedSources(
            name=['package1', 'package2'])

        self.assertEqual(
            3, distroseries.main_archive.getPublishedSources().count())
        self.assertEqual(2, filtered_sources.count())
        self.assertContentEqual(
            ['package1', 'package2'],
            [filtered_source.sourcepackagerelease.name for filtered_source in
            filtered_sources])

    def test_getPublishedSources_multi_pockets(self):
        # Passing an iterable of pockets should return publications
        # with any of them in.
        distroseries = self.factory.makeDistroSeries()
        pockets = [
            PackagePublishingPocket.RELEASE,
            PackagePublishingPocket.UPDATES,
            PackagePublishingPocket.BACKPORTS,
            ]
        for pocket in pockets:
            self.factory.makeSourcePackagePublishingHistory(
                sourcepackagename=pocket.name.lower(),
                distroseries=distroseries,
                archive=distroseries.main_archive,
                pocket=pocket)
        required_pockets = [
            PackagePublishingPocket.RELEASE,
            PackagePublishingPocket.UPDATES,
            ]
        filtered = distroseries.main_archive.getPublishedSources(
            pocket=required_pockets)

        self.assertContentEqual(
            [PackagePublishingPocket.RELEASE,
             PackagePublishingPocket.UPDATES],
            [source.pocket for source in filtered])

    def test_filter_by_component_name(self):
        # getPublishedSources() can be filtered by component name.
        distroseries = self.factory.makeDistroSeries()
        for component in getUtility(IComponentSet):
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=distroseries,
                component=component,
                )
        [filtered] = distroseries.main_archive.getPublishedSources(
            component_name='universe')
        self.assertEqual('universe', filtered.component.name)


class TestCopyPackage(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def _setup_copy_data(self, source_distribution=None, source_private=False,
                         target_purpose=None,
                         target_status=SeriesStatus.DEVELOPMENT):
        if target_purpose is None:
            target_purpose = ArchivePurpose.PPA
        source_archive = self.factory.makeArchive(
            distribution=source_distribution, private=source_private)
        target_archive = self.factory.makeArchive(purpose=target_purpose)
        source = self.factory.makeSourcePackagePublishingHistory(
            archive=source_archive, status=PackagePublishingStatus.PUBLISHED)
        with person_logged_in(source_archive.owner):
            source_name = source.source_package_name
            version = source.source_package_version
        to_pocket = PackagePublishingPocket.RELEASE
        to_series = self.factory.makeDistroSeries(
            distribution=target_archive.distribution, status=target_status)
        return (source, source_archive, source_name, target_archive,
                to_pocket, to_series, version)

    def test_copyPackage_creates_packagecopyjob(self):
        # The copyPackage method should create a PCJ with the appropriate
        # parameters.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        sponsored = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.copyPackage(
                source_name, version, source_archive, to_pocket.name,
                to_series=to_series.name, include_binaries=False,
                person=target_archive.owner, sponsored=sponsored,
                phased_update_percentage=30)

        # The source should not be published yet in the target_archive.
        published = target_archive.getPublishedSources(
            name=source.source_package_name).any()
        self.assertIsNone(published)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()

        # Its data should reflect the requested copy.
        self.assertThat(copy_job, MatchesStructure.byEquality(
            package_name=source_name,
            package_version=version,
            target_archive=target_archive,
            source_archive=source_archive,
            target_distroseries=to_series,
            target_pocket=to_pocket,
            include_binaries=False,
            sponsored=sponsored,
            copy_policy=PackageCopyPolicy.INSECURE,
            phased_update_percentage=30))

    def test_copyPackage_disallows_non_primary_archive_uploaders(self):
        # If copying to a primary archive and you're not an uploader for
        # the package then you can't copy.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        person = self.factory.makePerson()
        self.assertRaises(
            CannotCopy,
            target_archive.copyPackage, source_name, version, source_archive,
            to_pocket.name, to_series=to_series.name, include_binaries=False,
            person=person)

    def test_copyPackage_allows_primary_archive_uploaders(self):
        # Copying to a primary archive if you're already an uploader is OK.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newComponentUploader(person, "universe")
        target_archive.copyPackage(
            source_name, version, source_archive, to_pocket.name,
            to_series=to_series.name, include_binaries=False,
            person=person)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(target_archive, copy_job.target_archive)

    def test_copyPackage_disallows_non_PPA_owners(self):
        # Only people with launchpad.Append are allowed to call copyPackage.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        person = self.factory.makePerson()
        self.assertTrue(target_archive.is_ppa)
        self.assertRaises(
            CannotCopy,
            target_archive.copyPackage, source_name, version, source_archive,
            to_pocket.name, to_series=to_series.name, include_binaries=False,
            person=person)

    def test_copyPackage_allows_queue_admins_for_new_packages(self):
        # If a package does not exist in the target archive and series,
        # people with queue admin permissions to any component may copy it.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newQueueAdmin(person, "universe")
        target_archive.copyPackage(
            source_name, version, source_archive, to_pocket.name,
            to_series=to_series.name, include_binaries=False,
            person=person)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(target_archive, copy_job.target_archive)

    def test_copyPackage_allows_queue_admins_for_correct_component(self):
        # If a package already exists in the target archive and series,
        # queue admins of its component may copy it.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=to_series, archive=target_archive,
            status=PackagePublishingStatus.PUBLISHED,
            sourcepackagename=source_name, version="%s~" % version,
            component="main")
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newQueueAdmin(person, "main")
        target_archive.copyPackage(
            source_name, version, source_archive, to_pocket.name,
            to_series=to_series.name, include_binaries=False,
            person=person)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(target_archive, copy_job.target_archive)

    def test_copyPackage_disallows_queue_admins_for_incorrect_component(self):
        # If a package already exists in the target archive and series,
        # people who only have queue admin permissions to some other
        # component may not copy it.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=to_series, archive=target_archive,
            status=PackagePublishingStatus.PUBLISHED,
            sourcepackagename=source_name, version="%s~" % version,
            component="main")
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newQueueAdmin(person, "universe")
        self.assertRaises(
            CannotCopy,
            target_archive.copyPackage, source_name, version, source_archive,
            to_pocket.name, to_series=to_series.name, include_binaries=False,
            person=person)

    def test_copyPackage_disallows_non_release_target_pocket_for_PPA(self):
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        to_pocket = PackagePublishingPocket.UPDATES
        self.assertTrue(target_archive.is_ppa)
        self.assertRaises(
            CannotCopy,
            target_archive.copyPackage, source_name, version, source_archive,
            to_pocket.name, to_series=to_series.name, include_binaries=False,
            person=target_archive.owner)

    def test_copyPackage_unembargo_creates_unembargo_job(self):
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            source_private=True, target_purpose=ArchivePurpose.PRIMARY,
            target_status=SeriesStatus.CURRENT)
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newComponentUploader(
                source_archive.owner, "universe")
        to_pocket = PackagePublishingPocket.SECURITY
        with person_logged_in(source_archive.owner):
            target_archive.copyPackage(
                source_name, version, source_archive, to_pocket.name,
                to_series=to_series.name, include_binaries=False,
                person=source_archive.owner, unembargo=True)

        # There should be one copy job, with the unembargo flag set.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(target_archive, copy_job.target_archive)
        self.assertTrue(copy_job.unembargo)

    def test_copyPackage_with_default_distroseries(self):
        # If to_series is None, copyPackage copies into the same series as
        # the source in the target archive.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        with person_logged_in(target_archive.owner):
            target_archive.copyPackage(
                source_name, version, source_archive, to_pocket.name,
                include_binaries=False, person=target_archive.owner)

        # There should be one copy job with the correct target series.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_jobs = job_source.getActiveJobs(target_archive)
        self.assertEqual(1, copy_jobs.count())
        self.assertEqual(source.distroseries, copy_jobs[0].target_distroseries)

    def test_copyPackage_unpublished_source(self):
        # If the given source name is not published in the source archive,
        # we get a CannotCopy exception.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        with person_logged_in(target_archive.owner):
            expected_error = (
                "%s is not published in %s." %
                (source_name, target_archive.displayname))
            self.assertRaisesWithContent(
                CannotCopy, expected_error, target_archive.copyPackage,
                source_name, version, target_archive, to_pocket.name,
                target_archive.owner)

    def test_copyPackage_with_source_series_and_pocket(self):
        # The from_series and from_pocket parameters cause copyPackage to
        # select a matching source publication.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            source_distribution=self.factory.makeDistribution())
        other_series = self.factory.makeDistroSeries(
            distribution=source_archive.distribution,
            status=SeriesStatus.DEVELOPMENT)
        with person_logged_in(source_archive.owner):
            source.copyTo(
                other_series, PackagePublishingPocket.UPDATES, source_archive)
            source.requestDeletion(source_archive.owner)
        with person_logged_in(target_archive.owner):
            target_archive.copyPackage(
                source_name, version, source_archive, to_pocket.name,
                include_binaries=False, person=target_archive.owner,
                from_series=source.distroseries.name,
                from_pocket=source.pocket.name)

        # There should be one copy job, with the source distroseries and
        # pocket set.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(source.distroseries, copy_job.source_distroseries)
        self.assertEqual(source.pocket, copy_job.source_pocket)

    def test_copyPackages_with_single_package(self):
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()

        sponsored = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.copyPackages(
                [source_name], source_archive, to_pocket.name,
                to_series=to_series.name, include_binaries=False,
                person=target_archive.owner, sponsored=sponsored)

        # The source should not be published yet in the target_archive.
        published = target_archive.getPublishedSources(
            name=source.source_package_name).any()
        self.assertIsNone(published)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertThat(copy_job, MatchesStructure.byEquality(
            package_name=source_name,
            package_version=version,
            target_archive=target_archive,
            source_archive=source_archive,
            target_distroseries=to_series,
            target_pocket=to_pocket,
            include_binaries=False,
            sponsored=sponsored,
            copy_policy=PackageCopyPolicy.MASS_SYNC))

    def test_copyPackages_with_multiple_packages(self):
        # PENDING and PUBLISHED packages should both be copied.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        sources = [source]
        sources.append(self.factory.makeSourcePackagePublishingHistory(
            archive=source_archive,
            status=PackagePublishingStatus.PENDING))
        sources.append(self.factory.makeSourcePackagePublishingHistory(
            archive=source_archive,
            status=PackagePublishingStatus.PUBLISHED))
        names = [source.sourcepackagerelease.sourcepackagename.name
                 for source in sources]

        with person_logged_in(target_archive.owner):
            target_archive.copyPackages(
                names, source_archive, to_pocket.name,
                to_series=to_series.name, include_binaries=False,
                person=target_archive.owner)

        # Make sure three copy jobs exist.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_jobs = job_source.getActiveJobs(target_archive)
        self.assertEqual(3, copy_jobs.count())

    def test_copyPackages_disallows_non_primary_archive_uploaders(self):
        # If copying to a primary archive and you're not an uploader for
        # the package then you can't copy.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        person = self.factory.makePerson()
        self.assertRaises(
            CannotCopy,
            target_archive.copyPackages, [source_name], source_archive,
            to_pocket.name, to_series=to_series.name, include_binaries=False,
            person=person)

    def test_copyPackages_allows_primary_archive_uploaders(self):
        # Copying to a primary archive if you're already an uploader is OK.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newComponentUploader(person, "universe")
        target_archive.copyPackages(
            [source_name], source_archive, to_pocket.name,
            to_series=to_series.name, include_binaries=False,
            person=person)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(target_archive, copy_job.target_archive)

    def test_copyPackages_disallows_non_PPA_owners(self):
        # Only people with launchpad.Append are allowed to call copyPackages.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        person = self.factory.makePerson()
        self.assertTrue(target_archive.is_ppa)
        self.assertRaises(
            CannotCopy,
            target_archive.copyPackages, [source_name], source_archive,
            to_pocket.name, to_series=to_series.name, include_binaries=False,
            person=person)

    def test_copyPackages_allows_queue_admins(self):
        # Queue admins without upload permissions may still copy packages.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newQueueAdmin(person, "universe")
        target_archive.copyPackages(
            [source_name], source_archive, to_pocket.name,
            to_series=to_series.name, include_binaries=False,
            person=person)

        # There should be one copy job.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(target_archive, copy_job.target_archive)

    def test_copyPackages_with_multiple_distroseries(self):
        # The from_series parameter selects a source distroseries.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        new_distroseries = self.factory.makeDistroSeries(
            distribution=source_archive.distribution)
        new_version = "%s.1" % version
        new_spr = self.factory.makeSourcePackageRelease(
            archive=source_archive, distroseries=new_distroseries,
            sourcepackagename=source_name, version=new_version)
        self.factory.makeSourcePackagePublishingHistory(
            archive=source_archive, distroseries=new_distroseries,
            sourcepackagerelease=new_spr)

        with person_logged_in(target_archive.owner):
            target_archive.copyPackages(
                [source_name], source_archive, to_pocket.name,
                to_series=to_series.name,
                from_series=source.distroseries.name, include_binaries=False,
                person=target_archive.owner)

        # There should be one copy job with the correct version.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(version, copy_job.package_version)

        # If we now do another copy without the from_series parameter, it
        # selects the newest version in the source archive.
        with person_logged_in(target_archive.owner):
            target_archive.copyPackages(
                [source_name], source_archive, to_pocket.name,
                to_series=to_series.name, include_binaries=False,
                person=target_archive.owner)

        copy_jobs = job_source.getActiveJobs(target_archive)
        self.assertEqual(2, copy_jobs.count())
        self.assertEqual(copy_job, copy_jobs[0])
        self.assertEqual(new_version, copy_jobs[1].package_version)

    def test_copyPackages_with_default_distroseries(self):
        # If to_series is None, copyPackages copies into the same series as
        # each source in the target archive.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        sources = [source]
        other_series = self.factory.makeDistroSeries(
            distribution=target_archive.distribution)
        sources.append(self.factory.makeSourcePackagePublishingHistory(
            distroseries=other_series, archive=source_archive,
            status=PackagePublishingStatus.PUBLISHED))
        names = [source.sourcepackagerelease.sourcepackagename.name
                 for source in sources]

        with person_logged_in(target_archive.owner):
            target_archive.copyPackages(
                names, source_archive, to_pocket.name, include_binaries=False,
                person=target_archive.owner)

        # There should be two copy jobs with the correct target series.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_jobs = job_source.getActiveJobs(target_archive)
        self.assertEqual(2, copy_jobs.count())
        self.assertContentEqual(
            [source.distroseries for source in sources],
            [copy_job.target_distroseries for copy_job in copy_jobs])

    def test_copyPackages_with_default_distroseries_and_override(self):
        # If to_series is None, copyPackages checks permissions based on the
        # component in the target archive, not the component in the source
        # archive.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        sources = [source]
        uploader = self.factory.makePerson()
        main = self.factory.makeComponent(name="main")
        universe = self.factory.makeComponent(name="universe")
        ComponentSelection(distroseries=to_series, component=main)
        ComponentSelection(distroseries=to_series, component=universe)
        with person_logged_in(target_archive.owner):
            target_archive.newComponentUploader(uploader, universe)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=source.distroseries, archive=target_archive,
            pocket=to_pocket, status=PackagePublishingStatus.PUBLISHED,
            sourcepackagename=source_name, version="%s~1" % version,
            component=universe)
        names = [source.sourcepackagerelease.sourcepackagename.name
                 for source in sources]

        with person_logged_in(uploader):
            target_archive.copyPackages(
                names, source_archive, to_pocket.name, include_binaries=False,
                person=uploader)

        # There should be a copy job with the correct target series.
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(source.distroseries, copy_job.target_distroseries)

    def test_copyPackages_unpublished_source(self):
        # If none of the given source names are published in the source
        # archive, we get a CannotCopy exception.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data()
        with person_logged_in(target_archive.owner):
            expected_error = (
                "None of the supplied package names are published in %s." %
                target_archive.displayname)
            self.assertRaisesWithContent(
                CannotCopy, expected_error, target_archive.copyPackages,
                [source_name], target_archive, to_pocket.name,
                target_archive.owner)

    def test_copyPackages_to_pocket(self):
        # copyPackages respects the to_pocket parameter.
        (source, source_archive, source_name, target_archive, to_pocket,
         to_series, version) = self._setup_copy_data(
            target_purpose=ArchivePurpose.PRIMARY)
        to_pocket = PackagePublishingPocket.PROPOSED
        person = self.factory.makePerson()
        with person_logged_in(target_archive.distribution.owner):
            target_archive.newComponentUploader(person, "universe")
        target_archive.copyPackages(
            [source_name], source_archive, to_pocket.name,
            to_series=to_series.name, include_binaries=False, person=person)
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_job = job_source.getActiveJobs(target_archive).one()
        self.assertEqual(to_pocket, copy_job.target_pocket)


class TestgetAllPublishedBinaries(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_returns_publication(self):
        archive = self.factory.makeArchive()
        publication = self.factory.makeBinaryPackagePublishingHistory(
            archive=archive)
        publications = archive.getAllPublishedBinaries()
        self.assertEqual(1, publications.count())
        self.assertEqual(publication, publications[0])

    def test_created_since_date_newer(self):
        archive = self.factory.makeArchive()
        datecreated = self.factory.getUniqueDate()
        self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=datecreated)
        later_date = datecreated + timedelta(minutes=1)
        publications = archive.getAllPublishedBinaries(
            created_since_date=later_date)
        self.assertEqual(0, publications.count())

    def test_created_since_date_older(self):
        archive = self.factory.makeArchive()
        datecreated = self.factory.getUniqueDate()
        publication = self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=datecreated)
        earlier_date = datecreated - timedelta(minutes=1)
        publications = archive.getAllPublishedBinaries(
            created_since_date=earlier_date)
        self.assertEqual(1, publications.count())
        self.assertEqual(publication, publications[0])

    def test_created_since_date_middle(self):
        archive = self.factory.makeArchive()
        datecreated = self.factory.getUniqueDate()
        self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=datecreated)
        middle_date = datecreated + timedelta(minutes=1)
        later_date = middle_date + timedelta(minutes=1)
        later_publication = self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=later_date)
        publications = archive.getAllPublishedBinaries(
            created_since_date=middle_date)
        self.assertEqual(1, publications.count())
        self.assertEqual(later_publication, publications[0])

    def test_unordered_results(self):
        archive = self.factory.makeArchive()
        datecreated = self.factory.getUniqueDate()
        middle_date = datecreated + timedelta(minutes=1)
        later_date = middle_date + timedelta(minutes=1)

        # Create three publications whose ID ordering doesn't match the
        # date ordering.
        first_publication = self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=datecreated)
        middle_publication = self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=later_date)
        later_publication = self.factory.makeBinaryPackagePublishingHistory(
            archive=archive, datecreated=middle_date)

        # We can't test for no ordering as it's not deterministic; but
        # we can make sure that all the publications are returned.
        publications = archive.getAllPublishedBinaries(ordered=False)
        self.assertContentEqual(
            publications,
            [first_publication, middle_publication, later_publication])


class TestRemovingPermissions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_remove_permission_is_none(self):
        # Several API functions remove permissions if they are not already
        # removed.  This verifies that the underlying utility function does
        # not generate an error if the permission is None.
        ap_set = ArchivePermissionSet()
        ap_set._remove_permission(None)


class TestRemovingCopyNotifications(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeJob(self):
        distroseries = self.factory.makeDistroSeries()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name="foo", source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=True,
            requester=requester)
        return (distroseries, archive1, archive2, requester, job)

    def test_removeCopyNotification(self):
        distroseries, archive1, archive2, requester, job = self.makeJob()
        job.start()
        job.fail()

        with person_logged_in(archive2.owner):
            archive2.removeCopyNotification(job.id)

        source = getUtility(IPlainPackageCopyJobSource)
        found_jobs = source.getIncompleteJobsForArchive(archive2)
        self.assertIsNone(found_jobs.any())

    def test_removeCopyNotification_raises_for_not_failed(self):
        distroseries, archive1, archive2, requester, job = self.makeJob()

        self.assertNotEqual(JobStatus.FAILED, job.status)
        with person_logged_in(archive2.owner):
            self.assertRaises(
                AssertionError, archive2.removeCopyNotification, job.id)

    def test_removeCopyNotification_raises_for_wrong_archive(self):
        # If the job ID supplied is not for the context archive, an
        # error should be raised.
        distroseries, archive1, archive2, requester, job = self.makeJob()
        job.start()
        job.fail()

        # Set up a second job in the other archive.
        source = getUtility(IPlainPackageCopyJobSource)
        job2 = source.create(
            package_name="foo", source_archive=archive2,
            target_archive=archive1, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=True,
            requester=requester)

        with person_logged_in(archive2.owner):
            self.assertRaises(
                AssertionError, archive2.removeCopyNotification, job2.id)


class TestPublishFlag(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_primary_archive_published_by_default(self):
        distribution = self.factory.makeDistribution()
        self.assertTrue(distribution.main_archive.publish)

    def test_partner_archive_published_by_default(self):
        partner = self.factory.makeArchive(purpose=ArchivePurpose.PARTNER)
        self.assertTrue(partner.publish)

    def test_ppa_published_by_default(self):
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertTrue(ppa.publish)

    def test_copy_archive_not_published_by_default(self):
        copy = self.factory.makeArchive(purpose=ArchivePurpose.COPY)
        self.assertFalse(copy.publish)


class TestPPANaming(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_unique_copy_archive_name(self):
        # Non-PPA archive names must be unique for a given distribution.
        uber = self.factory.makeDistribution()
        self.factory.makeArchive(
            purpose=ArchivePurpose.COPY, distribution=uber, name="uber-copy")
        self.assertRaises(
            AssertionError, self.factory.makeArchive,
            purpose=ArchivePurpose.COPY, distribution=uber, name="uber-copy")

    def test_unique_partner_archive_name(self):
        # Partner archive names must be unique for a given distribution.
        uber = self.factory.makeDistribution()
        self.factory.makeArchive(
            purpose=ArchivePurpose.PARTNER, distribution=uber,
            name="uber-partner")
        self.assertRaises(
            AssertionError, self.factory.makeArchive,
            purpose=ArchivePurpose.PARTNER, distribution=uber,
            name="uber-partner")

    def test_unique_ppa_name_per_owner_and_distribution(self):
        person = self.factory.makePerson()
        self.factory.makeArchive(owner=person, name="ppa")
        self.assertEqual(
            "PPA for %s" % person.displayname, person.archive.displayname)
        self.assertEqual("ppa", person.archive.name)
        self.assertRaises(
            AssertionError, self.factory.makeArchive, owner=person, name="ppa")

    def test_default_archive(self):
        # Creating multiple PPAs does not affect the existing traversal from
        # IPerson to a single IArchive.
        person = self.factory.makePerson()
        ppa = self.factory.makeArchive(owner=person, name="ppa")
        self.factory.makeArchive(owner=person, name="nightly")
        self.assertEqual(ppa, person.archive)

    def test_non_default_ppas_have_different_displayname(self):
        person = self.factory.makePerson()
        another_ppa = self.factory.makeArchive(owner=person, name="nightly")
        self.assertEqual(
            "PPA named nightly for %s" % person.displayname,
            another_ppa.displayname)

    def test_archives_cannot_have_same_name_as_distribution(self):
        boingolinux = self.factory.makeDistribution(name="boingolinux")
        self.assertRaises(
            AssertionError, getUtility(IArchiveSet).new,
            owner=self.factory.makePerson(), purpose=ArchivePurpose.PRIMARY,
            distribution=boingolinux, name=boingolinux.name)


class TestPPALookup(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPPALookup, self).setUp()
        self.person = self.factory.makePerson()
        self.factory.makeArchive(owner=self.person, name="ppa")
        self.nightly = self.factory.makeArchive(
            owner=self.person, name="nightly")

    def test_ppas(self):
        # IPerson.ppas returns all owned PPAs ordered by name.
        self.assertEqual(
            ["nightly", "ppa"], [ppa.name for ppa in self.person.ppas])

    def test_getPPAByName(self):
        default_ppa = self.person.getPPAByName("ppa")
        self.assertEqual(self.person.archive, default_ppa)
        nightly_ppa = self.person.getPPAByName("nightly")
        self.assertEqual(self.nightly, nightly_ppa)

    def test_NoSuchPPA(self):
        self.assertRaises(NoSuchPPA, self.person.getPPAByName, "not-found")


class TestDisplayName(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_default(self):
        # If 'displayname' is omitted when creating the archive, there is a
        # sensible default.
        archive = self.factory.makeArchive(name="test-ppa")
        self.assertEqual(
            "PPA named test-ppa for %s" % archive.owner.displayname,
            archive.displayname)

    def test_provided(self):
        # If 'displayname' is provided, it is used.
        archive = self.factory.makeArchive(
            purpose=ArchivePurpose.COPY,
            displayname="Rock and roll with rebuilds!", name="test-rebuild")
        self.assertEqual("Rock and roll with rebuilds!", archive.displayname)

    def test_editable(self):
        # Anyone with edit permission on the archive can change displayname.
        archive = self.factory.makeArchive(name="test-ppa")
        login("no-priv@canonical.com")
        e = self.assertRaises(
            Unauthorized, setattr, archive, "displayname", "No-way!")
        self.assertEqual("launchpad.Edit", e.args[2])
        with person_logged_in(archive.owner):
            archive.displayname = "My testing packages"


class TestSigningKeyPropagation(TestCaseWithFactory):
    """Signing keys are shared between PPAs owned by the same person/team."""

    layer = DatabaseFunctionalLayer

    def test_ppa_created_with_no_signing_key(self):
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertIsNone(ppa.signing_key)

    def test_default_signing_key_propagated_to_new_ppa(self):
        person = self.factory.makePerson()
        ppa = self.factory.makeArchive(
            owner=person, purpose=ArchivePurpose.PPA, name="ppa")
        self.assertEqual(ppa, person.archive)
        self.factory.makeGPGKey(person)
        removeSecurityProxy(person.archive).signing_key = person.gpg_keys[0]
        ppa_with_key = self.factory.makeArchive(
            owner=person, purpose=ArchivePurpose.PPA)
        self.assertEqual(person.gpg_keys[0], ppa_with_key.signing_key)


class TestCountersAndSummaries(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def assertDictEqual(self, one, two):
        self.assertContentEqual(one.items(), two.items())

    def test_cprov_build_counters_in_sampledata(self):
        cprov_archive = getUtility(IPersonSet).getByName("cprov").archive
        expected_counters = {
            "failed": 1,
            "pending": 0,
            "succeeded": 3,
            "superseded": 0,
            "total": 4,
            }
        self.assertDictEqual(
            expected_counters, cprov_archive.getBuildCounters())

    def test_ubuntu_build_counters_in_sampledata(self):
        ubuntu_archive = getUtility(IDistributionSet)["ubuntu"].main_archive
        expected_counters = {
            "failed": 5,
            "pending": 2,
            "succeeded": 8,
            "superseded": 3,
            "total": 18,
            }
        self.assertDictEqual(
            expected_counters, ubuntu_archive.getBuildCounters())
        # include_needsbuild=False excludes builds in status NEEDSBUILD.
        expected_counters["pending"] -= 1
        expected_counters["total"] -= 1
        self.assertDictEqual(
            expected_counters,
            ubuntu_archive.getBuildCounters(include_needsbuild=False))

    def assertBuildSummaryMatches(self, status, builds, summary):
        self.assertEqual(status, summary["status"])
        self.assertContentEqual(
            builds, [build.title for build in summary["builds"]])

    def test_build_summaries_in_sampledata(self):
        ubuntu = getUtility(IDistributionSet)["ubuntu"]
        firefox_source = ubuntu.getSourcePackage("mozilla-firefox")
        firefox_source_pub = firefox_source.publishing_history[0]
        foobar = ubuntu.getSourcePackage("foobar")
        foobar_pub = foobar.publishing_history[0]
        build_summaries = ubuntu.main_archive.getBuildSummariesForSourceIds(
            [firefox_source_pub.id, foobar_pub.id])
        self.assertEqual(2, len(build_summaries))
        expected_firefox_builds = [
            "hppa build of mozilla-firefox 0.9 in ubuntu warty RELEASE",
            "i386 build of mozilla-firefox 0.9 in ubuntu warty RELEASE",
            ]
        self.assertBuildSummaryMatches(
            BuildSetStatus.FULLYBUILT, expected_firefox_builds,
            build_summaries[firefox_source_pub.id])
        expected_foobar_builds = [
            "i386 build of foobar 1.0 in ubuntu warty RELEASE",
            ]
        self.assertBuildSummaryMatches(
            BuildSetStatus.FAILEDTOBUILD, expected_foobar_builds,
            build_summaries[foobar_pub.id])

    def test_private_archives_have_private_counters_and_summaries(self):
        archive = self.factory.makeArchive()
        distroseries = self.factory.makeDistroSeries(
            distribution=archive.distribution)
        with celebrity_logged_in("admin"):
            archive.private = True
            publisher = SoyuzTestPublisher()
            publisher.setUpDefaultDistroSeries(distroseries)
            publisher.addFakeChroots(distroseries)
            publisher.getPubBinaries(archive=archive)
            source_id = archive.getPublishedSources()[0].id

            # An admin can see the counters and build summaries.
            archive.getBuildCounters()["total"]
            archive.getBuildSummariesForSourceIds([source_id])

        # The archive owner can see the counters and build summaries.
        with person_logged_in(archive.owner):
            archive.getBuildCounters()["total"]
            archive.getBuildSummariesForSourceIds([source_id])

        # The public cannot.
        login("no-priv@canonical.com")
        e = self.assertRaises(
            Unauthorized, getattr, archive, "getBuildCounters")
        self.assertEqual("launchpad.View", e.args[2])
        e = self.assertRaises(
            Unauthorized, getattr, archive, "getBuildSummariesForSourceIds")
        self.assertEqual("launchpad.View", e.args[2])
