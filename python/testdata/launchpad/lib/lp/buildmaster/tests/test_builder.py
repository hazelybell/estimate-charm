# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Builder features."""

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.builder import (
    IBuilder,
    IBuilderSet,
    )
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.buildmaster.tests.mock_slaves import make_publisher
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import flush_database_updates
from lp.services.job.interfaces.job import JobStatus
from lp.services.log.logger import BufferLogger
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestBuilder(TestCaseWithFactory):
    """Basic unit tests for `Builder`."""

    layer = DatabaseFunctionalLayer

    def test_providesInterface(self):
        # Builder provides IBuilder
        builder = self.factory.makeBuilder()
        self.assertProvides(builder, IBuilder)

    def test_default_values(self):
        builder = self.factory.makeBuilder()
        # Make sure the Storm cache gets the values that the database
        # initializes.
        flush_database_updates()
        self.assertEqual(0, builder.failure_count)

    def test_setting_builderok_resets_failure_count(self):
        builder = removeSecurityProxy(self.factory.makeBuilder())
        builder.failure_count = 1
        builder.builderok = False
        self.assertEqual(1, builder.failure_count)
        builder.builderok = True
        self.assertEqual(0, builder.failure_count)

    def test_handleFailure_increments_failure_count(self):
        builder = self.factory.makeBuilder()
        self.assertEqual(0, builder.failure_count)
        builder.handleFailure(BufferLogger())
        self.assertEqual(1, builder.failure_count)


class TestFindBuildCandidateBase(TestCaseWithFactory):
    """Setup the test publisher and some builders."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestFindBuildCandidateBase, self).setUp()
        self.publisher = make_publisher()
        self.publisher.prepareBreezyAutotest()

        # Create some i386 builders ready to build PPA builds.  Two
        # already exist in sampledata so we'll use those first.
        self.builder1 = getUtility(IBuilderSet)['bob']
        self.frog_builder = getUtility(IBuilderSet)['frog']
        self.builder3 = self.factory.makeBuilder(name='builder3')
        self.builder4 = self.factory.makeBuilder(name='builder4')
        self.builder5 = self.factory.makeBuilder(name='builder5')
        self.builders = [
            self.builder1,
            self.frog_builder,
            self.builder3,
            self.builder4,
            self.builder5,
            ]

        # Ensure all builders are operational.
        for builder in self.builders:
            builder.builderok = True
            builder.manual = False


class TestFindBuildCandidateGeneralCases(TestFindBuildCandidateBase):
    # Test usage of findBuildCandidate not specific to any archive type.

    def test_findBuildCandidate_supersedes_builds(self):
        # IBuilder._findBuildCandidate identifies if there are builds
        # for superseded source package releases in the queue and marks
        # the corresponding build record as SUPERSEDED.
        archive = self.factory.makeArchive()
        self.publisher.getPubSource(
            sourcename="gedit", status=PackagePublishingStatus.PUBLISHED,
            archive=archive).createMissingBuilds()
        old_candidate = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()

        # The candidate starts off as NEEDSBUILD:
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(
            old_candidate)
        self.assertEqual(BuildStatus.NEEDSBUILD, build.status)

        # Now supersede the source package:
        publication = build.current_source_publication
        publication.status = PackagePublishingStatus.SUPERSEDED

        # The candidate returned is now a different one:
        new_candidate = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()
        self.assertNotEqual(new_candidate, old_candidate)

        # And the old_candidate is superseded:
        self.assertEqual(BuildStatus.SUPERSEDED, build.status)

    def test_acquireBuildCandidate_marks_building(self):
        # acquireBuildCandidate() should call _findBuildCandidate and
        # mark the build as building.
        archive = self.factory.makeArchive()
        self.publisher.getPubSource(
            sourcename="gedit", status=PackagePublishingStatus.PUBLISHED,
            archive=archive).createMissingBuilds()
        candidate = removeSecurityProxy(
            self.frog_builder).acquireBuildCandidate()
        self.assertEqual(JobStatus.RUNNING, candidate.job.status)


class TestFindBuildCandidatePPAWithSingleBuilder(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestFindBuildCandidatePPAWithSingleBuilder, self).setUp()
        self.publisher = make_publisher()
        self.publisher.prepareBreezyAutotest()

        self.bob_builder = getUtility(IBuilderSet)['bob']
        self.frog_builder = getUtility(IBuilderSet)['frog']

        # Disable bob so only frog is available.
        self.bob_builder.manual = True
        self.bob_builder.builderok = True
        self.frog_builder.manual = False
        self.frog_builder.builderok = True

        # Make a new PPA and give it some builds.
        self.ppa_joe = self.factory.makeArchive(name="joesppa")
        self.publisher.getPubSource(
            sourcename="gedit", status=PackagePublishingStatus.PUBLISHED,
            archive=self.ppa_joe).createMissingBuilds()

    def test_findBuildCandidate_first_build_started(self):
        # The allocation rule for PPA dispatching doesn't apply when
        # there's only one builder available.

        # Asking frog to find a candidate should give us the joesppa build.
        next_job = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(next_job)
        self.assertEqual('joesppa', build.archive.name)

        # If bob is in a failed state the joesppa build is still
        # returned.
        self.bob_builder.builderok = False
        self.bob_builder.manual = False
        next_job = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(next_job)
        self.assertEqual('joesppa', build.archive.name)


class TestFindBuildCandidatePPABase(TestFindBuildCandidateBase):

    ppa_joe_private = False
    ppa_jim_private = False

    def _setBuildsBuildingForArch(self, builds_list, num_builds,
                                  archtag="i386"):
        """Helper function.

        Set the first `num_builds` in `builds_list` with `archtag` as
        BUILDING.
        """
        count = 0
        for build in builds_list[:num_builds]:
            if build.distro_arch_series.architecturetag == archtag:
                build.updateStatus(
                    BuildStatus.BUILDING, builder=self.builders[count])
            count += 1

    def setUp(self):
        """Publish some builds for the test archive."""
        super(TestFindBuildCandidatePPABase, self).setUp()

        # Create two PPAs and add some builds to each.
        self.ppa_joe = self.factory.makeArchive(
            name="joesppa", private=self.ppa_joe_private)
        self.ppa_jim = self.factory.makeArchive(
            name="jimsppa", private=self.ppa_jim_private)

        self.joe_builds = []
        self.joe_builds.extend(
            self.publisher.getPubSource(
                sourcename="gedit", status=PackagePublishingStatus.PUBLISHED,
                archive=self.ppa_joe).createMissingBuilds())
        self.joe_builds.extend(
            self.publisher.getPubSource(
                sourcename="firefox",
                status=PackagePublishingStatus.PUBLISHED,
                archive=self.ppa_joe).createMissingBuilds())
        self.joe_builds.extend(
            self.publisher.getPubSource(
                sourcename="cobblers",
                status=PackagePublishingStatus.PUBLISHED,
                archive=self.ppa_joe).createMissingBuilds())
        self.joe_builds.extend(
            self.publisher.getPubSource(
                sourcename="thunderpants",
                status=PackagePublishingStatus.PUBLISHED,
                archive=self.ppa_joe).createMissingBuilds())

        self.jim_builds = []
        self.jim_builds.extend(
            self.publisher.getPubSource(
                sourcename="gedit",
                status=PackagePublishingStatus.PUBLISHED,
                archive=self.ppa_jim).createMissingBuilds())
        self.jim_builds.extend(
            self.publisher.getPubSource(
                sourcename="firefox",
                status=PackagePublishingStatus.PUBLISHED,
                archive=self.ppa_jim).createMissingBuilds())

        # Set the first three builds in joe's PPA as building, which
        # leaves two builders free.
        self._setBuildsBuildingForArch(self.joe_builds, 3)
        num_active_builders = len(
            [build for build in self.joe_builds if build.builder is not None])
        num_free_builders = len(self.builders) - num_active_builders
        self.assertEqual(num_free_builders, 2)


class TestFindBuildCandidatePPA(TestFindBuildCandidatePPABase):

    def test_findBuildCandidate(self):
        # joe's fourth i386 build will be the next build candidate.
        next_job = removeSecurityProxy(self.builder4)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(next_job)
        self.assertEqual('joesppa', build.archive.name)

    def test_findBuildCandidate_with_disabled_archive(self):
        # Disabled archives should not be considered for dispatching
        # builds.
        disabled_job = removeSecurityProxy(self.builder4)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(
            disabled_job)
        build.archive.disable()
        next_job = removeSecurityProxy(self.builder4)._findBuildCandidate()
        self.assertNotEqual(disabled_job, next_job)


class TestFindBuildCandidatePrivatePPA(TestFindBuildCandidatePPABase):

    ppa_joe_private = True

    def test_findBuildCandidate_for_private_ppa(self):
        # joe's fourth i386 build will be the next build candidate.
        next_job = removeSecurityProxy(self.builder4)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(next_job)
        self.assertEqual('joesppa', build.archive.name)

        # If the source for the build is still pending, it won't be
        # dispatched because the builder has to fetch the source files
        # from the (password protected) repo area, not the librarian.
        pub = build.current_source_publication
        pub.status = PackagePublishingStatus.PENDING
        candidate = removeSecurityProxy(self.builder4)._findBuildCandidate()
        self.assertNotEqual(next_job.id, candidate.id)


class TestFindBuildCandidateDistroArchive(TestFindBuildCandidateBase):

    def setUp(self):
        """Publish some builds for the test archive."""
        super(TestFindBuildCandidateDistroArchive, self).setUp()
        # Create a primary archive and publish some builds for the
        # queue.
        self.non_ppa = self.factory.makeArchive(
            name="primary", purpose=ArchivePurpose.PRIMARY)

        self.gedit_build = self.publisher.getPubSource(
            sourcename="gedit", status=PackagePublishingStatus.PUBLISHED,
            archive=self.non_ppa).createMissingBuilds()[0]
        self.firefox_build = self.publisher.getPubSource(
            sourcename="firefox", status=PackagePublishingStatus.PUBLISHED,
            archive=self.non_ppa).createMissingBuilds()[0]

    def test_findBuildCandidate_for_non_ppa(self):
        # Normal archives are not restricted to serial builds per
        # arch.

        next_job = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(next_job)
        self.failUnlessEqual('primary', build.archive.name)
        self.failUnlessEqual('gedit', build.source_package_release.name)

        # Now even if we set the build building, we'll still get the
        # second non-ppa build for the same archive as the next candidate.
        build.updateStatus(BuildStatus.BUILDING, builder=self.frog_builder)
        next_job = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(next_job)
        self.failUnlessEqual('primary', build.archive.name)
        self.failUnlessEqual('firefox', build.source_package_release.name)

    def test_findBuildCandidate_for_recipe_build(self):
        # Recipe builds with a higher score are selected first.
        # This test is run in a context with mixed recipe and binary builds.

        self.assertIsNot(self.frog_builder.processor, None)
        self.assertEqual(self.frog_builder.virtualized, True)

        self.assertEqual(self.gedit_build.buildqueue_record.lastscore, 2505)
        self.assertEqual(self.firefox_build.buildqueue_record.lastscore, 2505)

        recipe_build_job = self.factory.makeSourcePackageRecipeBuildJob(9999)

        self.assertEqual(recipe_build_job.lastscore, 9999)

        next_job = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()

        self.failUnlessEqual(recipe_build_job, next_job)


class TestFindRecipeBuildCandidates(TestFindBuildCandidateBase):
    # These tests operate in a "recipe builds only" setting.
    # Please see also bug #507782.

    def clearBuildQueue(self):
        """Delete all `BuildQueue`, XXXJOb and `Job` instances."""
        for bq in IStore(BuildQueue).find(BuildQueue):
            bq.destroySelf()

    def setUp(self):
        """Publish some builds for the test archive."""
        super(TestFindRecipeBuildCandidates, self).setUp()
        # Create a primary archive and publish some builds for the
        # queue.
        self.non_ppa = self.factory.makeArchive(
            name="primary", purpose=ArchivePurpose.PRIMARY)

        self.clearBuildQueue()
        self.bq1 = self.factory.makeSourcePackageRecipeBuildJob(3333)
        self.bq2 = self.factory.makeSourcePackageRecipeBuildJob(4333)

    def test_findBuildCandidate_with_highest_score(self):
        # The recipe build with the highest score is selected first.
        # This test is run in a "recipe builds only" context.

        self.assertIsNot(self.frog_builder.processor, None)
        self.assertEqual(self.frog_builder.virtualized, True)

        next_job = removeSecurityProxy(
            self.frog_builder)._findBuildCandidate()

        self.failUnlessEqual(self.bq2, next_job)
