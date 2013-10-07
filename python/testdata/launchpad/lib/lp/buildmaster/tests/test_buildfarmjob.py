# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `IBuildFarmJob`."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from storm.store import Store
from testtools.matchers import GreaterThan
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.enums import (
    BuildFarmJobType,
    BuildStatus,
    )
from lp.buildmaster.interfaces.buildfarmjob import (
    IBuildFarmJob,
    IBuildFarmJobSet,
    IBuildFarmJobSource,
    )
from lp.buildmaster.model.buildfarmjob import BuildFarmJob
from lp.services.database.sqlbase import flush_database_updates
from lp.testing import (
    admin_logged_in,
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class TestBuildFarmJobBase:

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a build farm job with which to test."""
        super(TestBuildFarmJobBase, self).setUp()
        self.build_farm_job = self.makeBuildFarmJob()

    def makeBuildFarmJob(self, builder=None,
                         job_type=BuildFarmJobType.PACKAGEBUILD,
                         status=BuildStatus.NEEDSBUILD,
                         date_finished=None, archive=None):
        """A factory method for creating PackageBuilds.

        This is not included in the launchpad test factory because
        a build farm job should never be instantiated outside the
        context of a derived class (such as a BinaryPackageBuild
        or eventually a SPRecipeBuild).
        """
        build_farm_job = getUtility(IBuildFarmJobSource).new(
            job_type=job_type, status=status, archive=archive)
        removeSecurityProxy(build_farm_job).builder = builder
        removeSecurityProxy(build_farm_job).date_started = date_finished
        removeSecurityProxy(build_farm_job).date_finished = date_finished
        return build_farm_job


class TestBuildFarmJob(TestBuildFarmJobBase, TestCaseWithFactory):
    """Tests for the build farm job object."""

    def test_saves_record(self):
        # A build farm job can be stored in the database.
        flush_database_updates()
        store = Store.of(self.build_farm_job)
        retrieved_job = store.find(
            BuildFarmJob,
            BuildFarmJob.id == self.build_farm_job.id).one()
        self.assertEqual(self.build_farm_job, retrieved_job)

    def test_default_values(self):
        # We flush the database updates to ensure sql defaults
        # are set for various attributes.
        flush_database_updates()
        bfj = removeSecurityProxy(self.build_farm_job)
        self.assertEqual(
            BuildStatus.NEEDSBUILD, bfj.status)
        # The date_created is set automatically.
        self.assertTrue(bfj.date_created is not None)
        # The job type is required to create a build farm job.
        self.assertEqual(
            BuildFarmJobType.PACKAGEBUILD, bfj.job_type)
        # Other attributes are unset by default.
        self.assertEqual(None, bfj.date_finished)
        self.assertEqual(None, bfj.builder)

    def test_date_created(self):
        # date_created can be passed optionally when creating a
        # bulid farm job to ensure we don't get identical timestamps
        # when transactions are committed.
        ten_years_ago = datetime.now(pytz.UTC) - timedelta(365 * 10)
        build_farm_job = getUtility(IBuildFarmJobSource).new(
            job_type=BuildFarmJobType.PACKAGEBUILD,
            date_created=ten_years_ago)
        self.failUnlessEqual(
            ten_years_ago, removeSecurityProxy(build_farm_job).date_created)


class TestBuildFarmJobMixin(TestCaseWithFactory):
    """Test methods provided by BuildFarmJobMixin."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBuildFarmJobMixin, self).setUp()
        # BuildFarmJobMixin only operates as part of a concrete
        # IBuildFarmJob implementation. Here we use BinaryPackageBuild.
        self.build_farm_job = self.factory.makeBinaryPackageBuild()

    def test_providesInterface(self):
        # BuildFarmJobMixin derivatives provide IBuildFarmJob
        self.assertProvides(self.build_farm_job, IBuildFarmJob)

    def test_duration_none(self):
        # If either finished is none, the duration will be none.
        self.build_farm_job.updateStatus(BuildStatus.BUILDING)
        self.assertIs(None, self.build_farm_job.duration)
        self.build_farm_job.updateStatus(BuildStatus.FULLYBUILT)
        self.assertIsNot(None, self.build_farm_job.duration)

    def test_duration_set(self):
        # If both start and finished are defined, the duration will be
        # returned.
        now = datetime.now(pytz.UTC)
        duration = timedelta(1)
        self.build_farm_job.updateStatus(
            BuildStatus.BUILDING, date_started=now)
        self.build_farm_job.updateStatus(
            BuildStatus.FULLYBUILT, date_finished=now + duration)
        self.failUnlessEqual(duration, self.build_farm_job.duration)

    def test_view_build_farm_job(self):
        # Anonymous access can read public builds, but not edit.
        self.failUnlessEqual(
            BuildStatus.NEEDSBUILD, self.build_farm_job.status)
        self.assertRaises(
            Unauthorized, getattr, self.build_farm_job, 'retry')

    def test_edit_build_farm_job(self):
        # Users with edit access can update attributes.
        login('admin@canonical.com')
        self.assertRaises(AssertionError, self.build_farm_job.retry)

    def test_updateStatus_sets_status(self):
        # updateStatus always sets status.
        self.assertEqual(BuildStatus.NEEDSBUILD, self.build_farm_job.status)
        self.build_farm_job.updateStatus(BuildStatus.FULLYBUILT)
        self.assertEqual(BuildStatus.FULLYBUILT, self.build_farm_job.status)

    def test_updateStatus_sets_builder(self):
        # updateStatus sets builder if it's passed.
        builder = self.factory.makeBuilder()
        self.assertIs(None, self.build_farm_job.builder)
        self.build_farm_job.updateStatus(
            BuildStatus.FULLYBUILT, builder=builder)
        self.assertEqual(builder, self.build_farm_job.builder)

    def test_updateStatus_BUILDING_sets_date_started(self):
        # updateStatus sets date_started on transition to BUILDING.
        # date_first_dispatched is also set if it isn't already.
        self.assertEqual(BuildStatus.NEEDSBUILD, self.build_farm_job.status)
        self.assertIs(None, self.build_farm_job.date_started)
        self.assertIs(None, self.build_farm_job.date_first_dispatched)

        self.build_farm_job.updateStatus(BuildStatus.CANCELLED)
        self.assertIs(None, self.build_farm_job.date_started)
        self.assertIs(None, self.build_farm_job.date_first_dispatched)

        # Setting it to BUILDING for the first time sets date_started
        # and date_first_dispatched.
        self.build_farm_job.updateStatus(BuildStatus.BUILDING)
        self.assertIsNot(None, self.build_farm_job.date_started)
        first = self.build_farm_job.date_started
        self.assertEqual(first, self.build_farm_job.date_first_dispatched)

        self.build_farm_job.updateStatus(BuildStatus.FAILEDTOBUILD)
        with admin_logged_in():
            self.build_farm_job.retry()
        self.assertIs(None, self.build_farm_job.date_started)
        self.assertEqual(first, self.build_farm_job.date_first_dispatched)

        # But BUILDING a second time doesn't change
        # date_first_dispatched.
        self.build_farm_job.updateStatus(BuildStatus.BUILDING)
        self.assertThat(self.build_farm_job.date_started, GreaterThan(first))
        self.assertEqual(first, self.build_farm_job.date_first_dispatched)

    def test_updateStatus_sets_date_finished(self):
        # updateStatus sets date_finished if it's a final state and
        # date_started is set.
        # UPLOADING counts as the end of the job. date_finished doesn't
        # include the upload time.
        for status in (
                BuildStatus.FULLYBUILT, BuildStatus.FAILEDTOBUILD,
                BuildStatus.CHROOTWAIT, BuildStatus.MANUALDEPWAIT,
                BuildStatus.UPLOADING, BuildStatus.FAILEDTOUPLOAD,
                BuildStatus.CANCELLED, BuildStatus.SUPERSEDED):
            build = self.factory.makeBinaryPackageBuild()
            build.updateStatus(status)
            self.assertIs(None, build.date_started)
            self.assertIs(None, build.date_finished)
            build.updateStatus(BuildStatus.BUILDING)
            self.assertIsNot(None, build.date_started)
            self.assertIs(None, build.date_finished)
            build.updateStatus(status)
            self.assertIsNot(None, build.date_started)
            self.assertIsNot(None, build.date_finished)


class TestBuildFarmJobSet(TestBuildFarmJobBase, TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuildFarmJobSet, self).setUp()
        self.builder = self.factory.makeBuilder()
        self.build_farm_job_set = getUtility(IBuildFarmJobSet)

    def test_getBuildsForBuilder_all(self):
        # The default call without arguments returns all builds for the
        # builder, and not those for other builders.
        build1 = self.makeBuildFarmJob(builder=self.builder)
        build2 = self.makeBuildFarmJob(builder=self.builder)
        self.makeBuildFarmJob(builder=self.factory.makeBuilder())

        result = self.build_farm_job_set.getBuildsForBuilder(self.builder)

        self.assertContentEqual([build1, build2], result)

    def test_getBuildsForBuilder_by_status(self):
        # If the status arg is used, the results will be filtered by
        # status.
        successful_builds = [
            self.makeBuildFarmJob(
                builder=self.builder, status=BuildStatus.FULLYBUILT),
            self.makeBuildFarmJob(
                builder=self.builder, status=BuildStatus.FULLYBUILT),
            ]
        self.makeBuildFarmJob(builder=self.builder)

        query_by_status = self.build_farm_job_set.getBuildsForBuilder(
                self.builder, status=BuildStatus.FULLYBUILT)

        self.assertContentEqual(successful_builds, query_by_status)

    def _makePrivateAndNonPrivateBuilds(self, owning_team=None):
        """Return a tuple of a private and non-private build farm job."""
        if owning_team is None:
            owning_team = self.factory.makeTeam()
        archive = self.factory.makeArchive(owner=owning_team, private=True)
        private_build = self.factory.makeBinaryPackageBuild(
            archive=archive, builder=self.builder)
        private_build = removeSecurityProxy(private_build).build_farm_job
        other_build = self.makeBuildFarmJob(builder=self.builder)
        return (private_build, other_build)

    def test_getBuildsForBuilder_hides_private_from_anon(self):
        # If no user is passed, all private builds are filtered out.
        private_build, other_build = self._makePrivateAndNonPrivateBuilds()

        result = self.build_farm_job_set.getBuildsForBuilder(self.builder)

        self.assertContentEqual([other_build], result)

    def test_getBuildsForBuilder_hides_private_other_users(self):
        # Private builds are not returned for users without permission
        # to view them.
        private_build, other_build = self._makePrivateAndNonPrivateBuilds()

        result = self.build_farm_job_set.getBuildsForBuilder(
            self.builder, user=self.factory.makePerson())

        self.assertContentEqual([other_build], result)

    def test_getBuildsForBuilder_shows_private_to_admin(self):
        # Admin users can see private builds.
        admin_team = getUtility(ILaunchpadCelebrities).admin
        private_build, other_build = self._makePrivateAndNonPrivateBuilds()

        result = self.build_farm_job_set.getBuildsForBuilder(
            self.builder, user=admin_team.teamowner)

        self.assertContentEqual([private_build, other_build], result)

    def test_getBuildsForBuilder_shows_private_to_authorised(self):
        # Similarly, if the user is in the owning team they can see it.
        owning_team = self.factory.makeTeam()
        private_build, other_build = self._makePrivateAndNonPrivateBuilds(
            owning_team=owning_team)

        result = self.build_farm_job_set.getBuildsForBuilder(
            self.builder,
            user=owning_team.teamowner)

        self.assertContentEqual([private_build, other_build], result)

    def test_getBuildsForBuilder_ordered_by_date_finished(self):
        # Results are returned with the oldest build last.
        build_1 = self.makeBuildFarmJob(
            builder=self.builder,
            date_finished=datetime(2008, 10, 10, tzinfo=pytz.UTC))
        build_2 = self.makeBuildFarmJob(
            builder=self.builder,
            date_finished=datetime(2008, 11, 10, tzinfo=pytz.UTC))
        build_3 = self.makeBuildFarmJob(
            builder=self.builder,
            date_finished=datetime(2008, 9, 10, tzinfo=pytz.UTC))

        result = self.build_farm_job_set.getBuildsForBuilder(self.builder)
        self.assertEqual([build_2, build_1, build_3], list(result))

    def makeBuildsForArchive(self):
        archive = self.factory.makeArchive()
        builds = [
            self.makeBuildFarmJob(archive=archive),
            self.makeBuildFarmJob(
                archive=archive, status=BuildStatus.BUILDING),
            ]
        return (archive, builds)

    def test_getBuildsForArchive_all(self):
        # The default call without arguments returns all builds for the
        # archive.
        archive, builds = self.makeBuildsForArchive()
        self.assertContentEqual(
            builds, self.build_farm_job_set.getBuildsForArchive(archive))

    def test_getBuildsForArchive_by_status(self):
        # If the status arg is used, the results will be filtered by
        # status.
        archive, builds = self.makeBuildsForArchive()
        self.assertContentEqual(
            builds[1:],
            self.build_farm_job_set.getBuildsForArchive(
                archive, status=BuildStatus.BUILDING))
