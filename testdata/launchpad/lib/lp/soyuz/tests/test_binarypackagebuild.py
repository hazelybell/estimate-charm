# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Build features."""

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from storm.store import Store
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.buildqueue import IBuildQueue
from lp.buildmaster.interfaces.packagebuild import IPackageBuild
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.services.job.model.job import Job
from lp.services.webapp.interaction import ANONYMOUS
from lp.services.webapp.interfaces import OAuthPermission
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.binarypackagebuild import (
    IBinaryPackageBuild,
    IBinaryPackageBuildSet,
    UnparsableDependencies,
    )
from lp.soyuz.interfaces.buildpackagejob import IBuildPackageJob
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.model.buildpackagejob import BuildPackageJob
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    api_url,
    login,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.pages import webservice_for_person


class TestBinaryPackageBuild(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestBinaryPackageBuild, self).setUp()
        self.build = self.factory.makeBinaryPackageBuild(
            archive=self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY))

    def test_providesInterfaces(self):
        # Build provides IPackageBuild and IBuild.
        self.assertProvides(self.build, IPackageBuild)
        self.assertProvides(self.build, IBinaryPackageBuild)

    def test_queueBuild(self):
        # BinaryPackageBuild can create the queue entry for itself.
        bq = self.build.queueBuild()
        self.assertProvides(bq, IBuildQueue)
        self.assertProvides(bq.specific_job, IBuildPackageJob)
        self.assertEqual(self.build.is_virtualized, bq.virtualized)
        self.assertIsNotNone(bq.processor)
        self.assertEqual(bq, self.build.buildqueue_record)

    def test_estimateDuration(self):
        # Without previous builds, a negligable package size estimate is
        # 300s.
        self.assertEqual(300, self.build.estimateDuration().seconds)

    def create_previous_build(self, duration):
        spr = self.build.source_package_release
        build = spr.createBuild(
            distro_arch_series=self.build.distro_arch_series,
            archive=self.build.archive, pocket=self.build.pocket)
        now = datetime.now(pytz.UTC)
        build.updateStatus(
            BuildStatus.BUILDING,
            date_started=now - timedelta(seconds=duration))
        build.updateStatus(BuildStatus.FULLYBUILT, date_finished=now)
        return build

    def test_estimateDuration_with_history(self):
        # Previous builds of the same source are used for estimates.
        self.create_previous_build(335)
        self.assertEqual(335, self.build.estimateDuration().seconds)

    def addFakeBuildLog(self, build):
        build.setLog(self.factory.makeLibraryFileAlias('mybuildlog.txt'))

    def test_log_url(self):
        # The log URL for a binary package build will use
        # the distribution source package release when the context
        # is not a PPA or a copy archive.
        self.addFakeBuildLog(self.build)
        self.assertEqual(
            'http://launchpad.dev/%s/+source/'
            '%s/%s/+build/%d/+files/mybuildlog.txt' % (
                self.build.distribution.name,
                self.build.source_package_release.sourcepackagename.name,
                self.build.source_package_release.version, self.build.id),
            self.build.log_url)

    def test_log_url_ppa(self):
        # On the other hand, ppa or copy builds will have a url in the
        # context of the archive.
        build = self.factory.makeBinaryPackageBuild(
            archive=self.factory.makeArchive(purpose=ArchivePurpose.PPA))
        self.addFakeBuildLog(build)
        self.assertEqual(
            'http://launchpad.dev/~%s/+archive/'
            '%s/+build/%d/+files/mybuildlog.txt' % (
                build.archive.owner.name, build.archive.name, build.id),
            build.log_url)

    def test_getUploader(self):
        # For ACL purposes the uploader is the changes file signer.

        class MockChanges:
            signer = "Somebody <somebody@ubuntu.com>"

        self.assertEqual("Somebody <somebody@ubuntu.com>",
            self.build.getUploader(MockChanges()))

    def test_can_be_cancelled(self):
        # For all states that can be cancelled, assert can_be_cancelled
        # returns True.
        ok_cases = [
            BuildStatus.BUILDING,
            BuildStatus.NEEDSBUILD,
            ]
        for status in BuildStatus:
            if status in ok_cases:
                self.assertTrue(self.build.can_be_cancelled)
            else:
                self.assertFalse(self.build.can_be_cancelled)

    def test_can_be_cancelled_virtuality(self):
        # Both virtual and non-virtual builds can be cancelled.
        bq = removeSecurityProxy(self.build.queueBuild())
        bq.virtualized = True
        self.assertTrue(self.build.can_be_cancelled)
        bq.virtualized = False
        self.assertTrue(self.build.can_be_cancelled)

    def test_cancel_not_in_progress(self):
        # Testing the cancel() method for a pending build should leave
        # it in the CANCELLED state.
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        build = self.factory.makeBinaryPackageBuild(archive=ppa)
        build.queueBuild()
        build.cancel()
        self.assertEqual(BuildStatus.CANCELLED, build.status)
        self.assertIs(None, build.buildqueue_record)

    def test_cancel_in_progress(self):
        # Testing the cancel() method for a building build should leave
        # it in the CANCELLING state.
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        build = self.factory.makeBinaryPackageBuild(archive=ppa)
        bq = build.queueBuild()
        build.updateStatus(BuildStatus.BUILDING)
        build.cancel()
        self.assertEqual(BuildStatus.CANCELLING, build.status)
        self.assertEqual(bq, build.buildqueue_record)


class TestBuildUpdateDependencies(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def _setupSimpleDepwaitContext(self):
        """Use `SoyuzTestPublisher` to setup a simple depwait context.

        Return an `IBinaryPackageBuild` in MANUALDEWAIT state and depending
        on a binary that exists and is reachable.
        """
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        depwait_source = self.publisher.getPubSource(
            sourcename='depwait-source')

        self.publisher.getPubBinaries(
            binaryname='dep-bin',
            status=PackagePublishingStatus.PUBLISHED)

        [depwait_build] = depwait_source.createMissingBuilds()
        depwait_build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': u'dep-bin'})
        return depwait_build

    def testBuildqueueRemoval(self):
        """Test removing buildqueue items.

        Removing a Buildqueue row should also remove its associated
        BuildPackageJob and Job rows.
        """
        # Create a build in depwait.
        depwait_build = self._setupSimpleDepwaitContext()
        depwait_build_id = depwait_build.id

        # Grab the relevant db records for later comparison.
        store = Store.of(depwait_build)
        build_package_job = store.find(
            BuildPackageJob,
            depwait_build.id == BuildPackageJob.build).one()
        build_package_job_id = build_package_job.id
        job_id = store.find(Job, Job.id == build_package_job.job.id).one().id
        build_queue_id = store.find(
            BuildQueue, BuildQueue.job == job_id).one().id

        depwait_build.buildqueue_record.destroySelf()

        # Test that the records above no longer exist in the db.
        self.assertEqual(
            store.find(
                BuildPackageJob,
                BuildPackageJob.id == build_package_job_id).count(),
            0)
        self.assertEqual(
            store.find(Job, Job.id == job_id).count(),
            0)
        self.assertEqual(
            store.find(BuildQueue, BuildQueue.id == build_queue_id).count(),
            0)
        # But the build itself still exists.
        self.assertEqual(
            store.find(
                BinaryPackageBuild,
                BinaryPackageBuild.id == depwait_build_id).count(),
            1)

    def testUpdateDependenciesWorks(self):
        # Calling `IBinaryPackageBuild.updateDependencies` makes the build
        # record ready for dispatch.
        depwait_build = self._setupSimpleDepwaitContext()
        self.layer.txn.commit()
        depwait_build.updateDependencies()
        self.assertEqual(depwait_build.dependencies, '')

    def assertRaisesUnparsableDependencies(self, depwait_build, dependencies):
        depwait_build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': dependencies})
        self.assertRaises(
            UnparsableDependencies, depwait_build.updateDependencies)

    def testInvalidDependencies(self):
        # Calling `IBinaryPackageBuild.updateDependencies` on a build with
        # invalid 'dependencies' raises an AssertionError.
        # Anything not following '<name> [([relation] <version>)][, ...]'
        depwait_build = self._setupSimpleDepwaitContext()

        # None is not a valid dependency values.
        self.assertRaisesUnparsableDependencies(depwait_build, None)

        # Missing 'name'.
        self.assertRaisesUnparsableDependencies(depwait_build, u'(>> version)')

        # Missing 'version'.
        self.assertRaisesUnparsableDependencies(depwait_build, u'name (>>)')

        # Missing comma between dependencies.
        self.assertRaisesUnparsableDependencies(depwait_build, u'name1 name2')

    def testBug378828(self):
        # `IBinaryPackageBuild.updateDependencies` copes with the
        # scenario where the corresponding source publication is not
        # active (deleted) and the source original component is not a
        # valid ubuntu component.
        depwait_build = self._setupSimpleDepwaitContext()

        spr = depwait_build.source_package_release
        depwait_build.current_source_publication.requestDeletion(
            spr.creator)
        contrib = getUtility(IComponentSet).new('contrib')
        removeSecurityProxy(spr).component = contrib

        self.layer.txn.commit()
        depwait_build.updateDependencies()
        self.assertEqual(depwait_build.dependencies, '')

    def testVersionedDependencies(self):
        # `IBinaryPackageBuild.updateDependencies` supports versioned
        # dependencies. A build will not be retried unless the candidate
        # complies with the version restriction.
        # In this case, dep-bin 666 is available. >> 666 isn't
        # satisified, but >= 666 is.
        depwait_build = self._setupSimpleDepwaitContext()
        self.layer.txn.commit()

        depwait_build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': u'dep-bin (>> 666)'})
        depwait_build.updateDependencies()
        self.assertEqual(depwait_build.dependencies, u'dep-bin (>> 666)')
        depwait_build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': u'dep-bin (>= 666)'})
        depwait_build.updateDependencies()
        self.assertEqual(depwait_build.dependencies, u'')

    def testVersionedDependencyOnOldPublication(self):
        # `IBinaryPackageBuild.updateDependencies` doesn't just consider
        # the latest publication. There may be older publications which
        # satisfy the version constraints (in other archives or pockets).
        # In this case, dep-bin 666 and 999 are available, so both = 666
        # and = 999 are satisfied.
        depwait_build = self._setupSimpleDepwaitContext()
        self.publisher.getPubBinaries(
            binaryname='dep-bin', version='999',
            status=PackagePublishingStatus.PUBLISHED)
        self.layer.txn.commit()

        depwait_build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': u'dep-bin (= 666)'})
        depwait_build.updateDependencies()
        self.assertEqual(depwait_build.dependencies, u'')
        depwait_build.updateStatus(
            BuildStatus.MANUALDEPWAIT,
            slave_status={'dependencies': u'dep-bin (= 999)'})
        depwait_build.updateDependencies()
        self.assertEqual(depwait_build.dependencies, u'')


class BaseTestCaseWithThreeBuilds(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Publish some builds for the test archive."""
        super(BaseTestCaseWithThreeBuilds, self).setUp()
        self.ds = self.factory.makeDistroSeries()
        i386_das = self.factory.makeDistroArchSeries(
            distroseries=self.ds, architecturetag='i386')
        hppa_das = self.factory.makeDistroArchSeries(
            distroseries=self.ds, architecturetag='hppa')
        self.builds = [
            self.factory.makeBinaryPackageBuild(
                archive=self.ds.main_archive, distroarchseries=i386_das),
            self.factory.makeBinaryPackageBuild(
                archive=self.ds.main_archive, distroarchseries=i386_das),
            self.factory.makeBinaryPackageBuild(
                archive=self.ds.main_archive, distroarchseries=hppa_das),
            ]
        self.sources = [
            build.current_source_publication for build in self.builds]


class TestBuildSet(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_getByBuildFarmJob_works(self):
        bpb = self.factory.makeBinaryPackageBuild()
        self.assertEqual(
            bpb,
            getUtility(IBinaryPackageBuildSet).getByBuildFarmJob(
                bpb.build_farm_job))

    def test_getByBuildFarmJob_returns_none_when_missing(self):
        sprb = self.factory.makeSourcePackageRecipeBuild()
        self.assertIsNone(
            getUtility(IBinaryPackageBuildSet).getByBuildFarmJob(
                sprb.build_farm_job))

    def test_getByBuildFarmJobs_works(self):
        bpbs = [self.factory.makeBinaryPackageBuild() for i in xrange(10)]
        self.assertContentEqual(
            bpbs,
            getUtility(IBinaryPackageBuildSet).getByBuildFarmJobs(
                [bpb.build_farm_job for bpb in bpbs]))

    def test_getByBuildFarmJobs_works_empty(self):
        self.assertContentEqual(
            [],
            getUtility(IBinaryPackageBuildSet).getByBuildFarmJobs([]))


class TestBuildSetGetBuildsForArchive(BaseTestCaseWithThreeBuilds):

    def setUp(self):
        """Publish some builds for the test archive."""
        super(TestBuildSetGetBuildsForArchive, self).setUp()

        # Short-cuts for our tests.
        self.archive = self.ds.main_archive
        self.build_set = getUtility(IBinaryPackageBuildSet)

    def test_getBuildsForArchive_no_params(self):
        # All builds should be returned when called without filtering
        builds = self.build_set.getBuildsForArchive(self.archive)
        self.assertContentEqual(builds, self.builds)

    def test_getBuildsForArchive_by_arch_tag(self):
        # Results can be filtered by architecture tag.
        i386_builds = self.builds[:2]
        builds = self.build_set.getBuildsForArchive(self.archive,
                                                    arch_tag="i386")
        self.assertContentEqual(builds, i386_builds)


class TestBuildSetGetBuildsForBuilder(BaseTestCaseWithThreeBuilds):

    def setUp(self):
        super(TestBuildSetGetBuildsForBuilder, self).setUp()

        # Short-cuts for our tests.
        self.build_set = getUtility(IBinaryPackageBuildSet)

        # Create a 386 builder
        self.builder = self.factory.makeBuilder()

        # Ensure that our builds were all built by the test builder.
        for build in self.builds:
            build.updateStatus(BuildStatus.FULLYBUILT, builder=self.builder)

    def test_getBuildsForBuilder_no_params(self):
        # All builds should be returned when called without filtering
        builds = self.build_set.getBuildsForBuilder(self.builder.id)
        self.assertContentEqual(builds, self.builds)

    def test_getBuildsForBuilder_by_arch_tag(self):
        # Results can be filtered by architecture tag.
        i386_builds = self.builds[:2]
        builds = self.build_set.getBuildsForBuilder(self.builder.id,
                                                    arch_tag="i386")
        self.assertContentEqual(builds, i386_builds)


class TestBinaryPackageBuildWebservice(TestCaseWithFactory):
    """Test cases for BinaryPackageBuild on the webservice.

    NB. Note that most tests are currently in
    lib/lp/soyuz/stories/webservice/xx-builds.txt but unit tests really
    ought to be here instead.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBinaryPackageBuildWebservice, self).setUp()
        self.ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.build = self.factory.makeBinaryPackageBuild(archive=self.ppa)
        self.webservice = webservice_for_person(
            self.ppa.owner, permission=OAuthPermission.WRITE_PUBLIC)
        login(ANONYMOUS)

    def test_can_be_cancelled_is_exported(self):
        # Check that the can_be_cancelled property is exported.
        expected = self.build.can_be_cancelled
        entry_url = api_url(self.build)
        logout()
        entry = self.webservice.get(entry_url, api_version='devel').jsonBody()
        self.assertEqual(expected, entry['can_be_cancelled'])

    def test_cancel_is_exported(self):
        # Check that the cancel() named op is exported.
        build_url = api_url(self.build)
        self.build.queueBuild()
        logout()
        entry = self.webservice.get(build_url, api_version='devel').jsonBody()
        response = self.webservice.named_post(
            entry['self_link'], 'cancel', api_version='devel')
        self.assertEqual(200, response.status)
        entry = self.webservice.get(build_url, api_version='devel').jsonBody()
        self.assertEqual(BuildStatus.CANCELLED.title, entry['buildstate'])

    def test_cancel_security(self):
        # Check that unauthorised users cannot call cancel()
        build_url = api_url(self.build)
        webservice = webservice_for_person(
            self.factory.makePerson(), permission=OAuthPermission.WRITE_PUBLIC)
        logout()

        entry = webservice.get(build_url, api_version='devel').jsonBody()
        response = webservice.named_post(
            entry['self_link'], 'cancel', api_version='devel')
        self.assertEqual(401, response.status)

    def test_builder_is_exported(self):
        # The builder property is exported.
        self.build.updateStatus(
            BuildStatus.FULLYBUILT, builder=self.factory.makeBuilder())
        build_url = api_url(self.build)
        builder_url = api_url(self.build.builder)
        logout()
        entry = self.webservice.get(build_url, api_version='devel').jsonBody()
        self.assertEndsWith(entry['builder_link'], builder_url)
