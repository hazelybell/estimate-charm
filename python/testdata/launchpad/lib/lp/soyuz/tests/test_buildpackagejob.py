# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test BuildQueue features."""

from datetime import timedelta

from simplejson import dumps
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.builder import IBuilderSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import SourcePackageUrgency
from lp.services.database.interfaces import IStore
from lp.services.log.logger import DevNullLogger
from lp.services.webapp.interfaces import OAuthPermission
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.buildfarmbuildjob import IBuildFarmBuildJob
from lp.soyuz.interfaces.buildpackagejob import (
    COPY_ARCHIVE_SCORE_PENALTY,
    IBuildPackageJob,
    PRIVATE_ARCHIVE_SCORE_BONUS,
    SCORE_BY_COMPONENT,
    SCORE_BY_POCKET,
    SCORE_BY_URGENCY,
    )
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.model.buildpackagejob import BuildPackageJob
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    anonymous_logged_in,
    api_url,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.pages import webservice_for_person


def find_job(test, name, processor='386'):
    """Find build and queue instance for the given source and processor."""
    for build in test.builds:
        if (build.source_package_release.name == name
            and build.processor.name == processor):
            return (build, build.buildqueue_record)
    return (None, None)


def builder_key(build):
    """Return processor and virtualization for the given build."""
    return (build.processor.id, build.is_virtualized)


def assign_to_builder(test, job_name, builder_number, processor='386'):
    """Simulate assigning a build to a builder."""
    def nth_builder(test, build, n):
        """Get builder #n for the given build processor and virtualization."""
        builder = None
        builders = test.builders.get(builder_key(build), [])
        try:
            builder = builders[n - 1]
        except IndexError:
            pass
        return builder

    build, bq = find_job(test, job_name, processor)
    builder = nth_builder(test, build, builder_number)
    bq.markAsBuilding(builder)


class TestBuildJobBase(TestCaseWithFactory):
    """Setup the test publisher and some builders."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestBuildJobBase, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        self.i8 = self.factory.makeBuilder(name='i386-n-8', virtualized=False)
        self.i9 = self.factory.makeBuilder(name='i386-n-9', virtualized=False)

        processor = getUtility(IProcessorSet).getByName('hppa')
        self.h6 = self.factory.makeBuilder(
            name='hppa-n-6', processor=processor, virtualized=False)
        self.h7 = self.factory.makeBuilder(
            name='hppa-n-7', processor=processor, virtualized=False)

        self.builders = dict()
        # x86 native
        self.builders[(1, False)] = [self.i8, self.i9]

        # hppa native
        self.builders[(3, True)] = [self.h6, self.h7]

        # Ensure all builders are operational.
        for builders in self.builders.values():
            for builder in builders:
                builder.builderok = True
                builder.manual = False

        # Disable the sample data builders.
        getUtility(IBuilderSet)['bob'].builderok = False
        getUtility(IBuilderSet)['frog'].builderok = False


class TestBuildPackageJob(TestBuildJobBase):
    """Test dispatch time estimates for binary builds (i.e. single build
    farm job type) targetting a single processor architecture and the primary
    archive.
    """

    def setUp(self):
        """Set up some native x86 builds for the test archive."""
        super(TestBuildPackageJob, self).setUp()
        # The builds will be set up as follows:
        #
        # j: 3        gedit p: hppa v:False e:0:01:00 *** s: 1001
        # j: 4        gedit p:  386 v:False e:0:02:00 *** s: 1002
        # j: 5      firefox p: hppa v:False e:0:03:00 *** s: 1003
        # j: 6      firefox p:  386 v:False e:0:04:00 *** s: 1004
        # j: 7     cobblers p: hppa v:False e:0:05:00 *** s: 1005
        # j: 8     cobblers p:  386 v:False e:0:06:00 *** s: 1006
        # j: 9 thunderpants p: hppa v:False e:0:07:00 *** s: 1007
        # j:10 thunderpants p:  386 v:False e:0:08:00 *** s: 1008
        # j:11          apg p: hppa v:False e:0:09:00 *** s: 1009
        # j:12          apg p:  386 v:False e:0:10:00 *** s: 1010
        # j:13          vim p: hppa v:False e:0:11:00 *** s: 1011
        # j:14          vim p:  386 v:False e:0:12:00 *** s: 1012
        # j:15          gcc p: hppa v:False e:0:13:00 *** s: 1013
        # j:16          gcc p:  386 v:False e:0:14:00 *** s: 1014
        # j:17        bison p: hppa v:False e:0:15:00 *** s: 1015
        # j:18        bison p:  386 v:False e:0:16:00 *** s: 1016
        # j:19         flex p: hppa v:False e:0:17:00 *** s: 1017
        # j:20         flex p:  386 v:False e:0:18:00 *** s: 1018
        # j:21     postgres p: hppa v:False e:0:19:00 *** s: 1019
        # j:22     postgres p:  386 v:False e:0:20:00 *** s: 1020
        #
        # j=job, p=processor, v=virtualized, e=estimated_duration, s=score

        # First mark all builds in the sample data as already built.
        store = IStore(BinaryPackageBuild)
        sample_data = store.find(BinaryPackageBuild)
        for build in sample_data:
            build.buildstate = BuildStatus.FULLYBUILT
        store.flush()

        # We test builds that target a primary archive.
        self.non_ppa = self.factory.makeArchive(
            name="primary", purpose=ArchivePurpose.PRIMARY)
        self.non_ppa.require_virtualized = False

        self.builds = []
        sourcenames = [
            "gedit",
            "firefox",
            "cobblers",
            "thunderpants",
            "apg",
            "vim",
            "gcc",
            "bison",
            "flex",
            "postgres",
            ]
        for sourcename in sourcenames:
            self.builds.extend(
                self.publisher.getPubSource(
                    sourcename=sourcename,
                    status=PackagePublishingStatus.PUBLISHED,
                    archive=self.non_ppa,
                    architecturehintlist='any').createMissingBuilds())

        # We want the builds to have a lot of variety when it comes to score
        # and estimated duration etc. so that the queries under test get
        # exercised properly.
        score = 1000
        duration = 0
        for build in self.builds:
            score += 1
            duration += 60
            bq = build.buildqueue_record
            bq.lastscore = score
            removeSecurityProxy(bq).estimated_duration = timedelta(
                seconds=duration)

    def test_processor(self):
        # Test that BuildPackageJob returns the correct processor.
        build, bq = find_job(self, 'gcc', '386')
        bpj = bq.specific_job
        self.assertEqual(bpj.processor.id, 1)
        build, bq = find_job(self, 'bison', 'hppa')
        bpj = bq.specific_job
        self.assertEqual(bpj.processor.id, 3)

    def test_virtualized(self):
        # Test that BuildPackageJob returns the correct virtualized flag.
        build, bq = find_job(self, 'apg', '386')
        bpj = bq.specific_job
        self.assertEqual(bpj.virtualized, False)
        build, bq = find_job(self, 'flex', 'hppa')
        bpj = bq.specific_job
        self.assertEqual(bpj.virtualized, False)

    def test_providesInterfaces(self):
        # Ensure that a BuildPackageJob generates an appropriate cookie.
        build, bq = find_job(self, 'gcc', '386')
        build_farm_job = bq.specific_job
        self.assertProvides(build_farm_job, IBuildPackageJob)
        self.assertProvides(build_farm_job, IBuildFarmBuildJob)

    def test_jobStarted(self):
        # Starting a build updates the status.
        build, bq = find_job(self, 'gcc', '386')
        build_package_job = bq.specific_job
        build_package_job.jobStarted()
        self.assertEqual(
            BuildStatus.BUILDING, build_package_job.build.status)
        self.assertIsNot(None, build_package_job.build.date_started)
        self.assertIsNot(None, build_package_job.build.date_first_dispatched)
        self.assertIs(None, build_package_job.build.date_finished)


class TestBuildPackageJobScore(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeBuildJob(self, purpose=None, private=False, component="main",
                     urgency="high", pocket="RELEASE", section_name=None):
        if purpose is not None or private:
            archive = self.factory.makeArchive(
                purpose=purpose, private=private)
        else:
            archive = None
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=archive, component=component, urgency=urgency,
            section_name=section_name)
        naked_spph = removeSecurityProxy(spph)  # needed for private archives
        build = self.factory.makeBinaryPackageBuild(
            source_package_release=naked_spph.sourcepackagerelease,
            pocket=pocket)
        return removeSecurityProxy(build).makeJob()

    # The defaults for pocket, component, and urgency here match those in
    # makeBuildJob.
    def assertCorrectScore(self, job, pocket="RELEASE", component="main",
                           urgency="high", other_bonus=0):
        self.assertEqual(
            (SCORE_BY_POCKET[PackagePublishingPocket.items[pocket.upper()]] +
             SCORE_BY_COMPONENT[component] +
             SCORE_BY_URGENCY[SourcePackageUrgency.items[urgency.upper()]] +
             other_bonus), job.score())

    def test_score_unusual_component(self):
        spph = self.factory.makeSourcePackagePublishingHistory(
            component="unusual")
        build = self.factory.makeBinaryPackageBuild(
            source_package_release=spph.sourcepackagerelease)
        build.queueBuild()
        job = build.buildqueue_record.specific_job
        # For now just test that it doesn't raise an Exception
        job.score()

    def test_main_release_low_score(self):
        # 1500 (RELEASE) + 1000 (main) + 5 (low) = 2505.
        job = self.makeBuildJob(component="main", urgency="low")
        self.assertCorrectScore(job, "RELEASE", "main", "low")

    def test_copy_archive_main_release_low_score(self):
        # 1500 (RELEASE) + 1000 (main) + 5 (low) - 2600 (copy archive) = -95.
        # With this penalty, even language-packs and build retries will be
        # built before copy archives.
        job = self.makeBuildJob(
            purpose="COPY", component="main", urgency="low")
        self.assertCorrectScore(
            job, "RELEASE", "main", "low", -COPY_ARCHIVE_SCORE_PENALTY)

    def test_copy_archive_relative_score_is_applied(self):
        # Per-archive relative build scores are applied, in this case
        # exactly offsetting the copy-archive penalty.
        job = self.makeBuildJob(
            purpose="COPY", component="main", urgency="low")
        removeSecurityProxy(job.build.archive).relative_build_score = 2600
        self.assertCorrectScore(
            job, "RELEASE", "main", "low", -COPY_ARCHIVE_SCORE_PENALTY + 2600)

    def test_archive_negative_relative_score_is_applied(self):
        # Negative per-archive relative build scores are allowed.
        job = self.makeBuildJob(component="main", urgency="low")
        removeSecurityProxy(job.build.archive).relative_build_score = -100
        self.assertCorrectScore(job, "RELEASE", "main", "low", -100)

    def test_private_archive_bonus_is_applied(self):
        # Private archives get a bonus of 10000.
        job = self.makeBuildJob(private=True, component="main", urgency="high")
        self.assertCorrectScore(
            job, "RELEASE", "main", "high", PRIVATE_ARCHIVE_SCORE_BONUS)

    def test_main_release_low_recent_score(self):
        # 1500 (RELEASE) + 1000 (main) + 5 (low) = 2505.
        job = self.makeBuildJob(component="main", urgency="low")
        self.assertCorrectScore(job, "RELEASE", "main", "low")

    def test_universe_release_high_five_minutes_score(self):
        # 1500 (RELEASE) + 250 (universe) + 15 (high) = 1765.
        job = self.makeBuildJob(component="universe", urgency="high")
        self.assertCorrectScore(job, "RELEASE", "universe", "high")

    def test_multiverse_release_medium_fifteen_minutes_score(self):
        # 1500 (RELEASE) + 0 (multiverse) + 10 (medium) = 1510.
        job = self.makeBuildJob(component="multiverse", urgency="medium")
        self.assertCorrectScore(job, "RELEASE", "multiverse", "medium")

    def test_main_release_emergency_thirty_minutes_score(self):
        # 1500 (RELEASE) + 1000 (main) + 20 (emergency) = 2520.
        job = self.makeBuildJob(component="main", urgency="emergency")
        self.assertCorrectScore(job, "RELEASE", "main", "emergency")

    def test_restricted_release_low_one_hour_score(self):
        # 1500 (RELEASE) + 750 (restricted) + 5 (low) = 2255.
        job = self.makeBuildJob(component="restricted", urgency="low")
        self.assertCorrectScore(job, "RELEASE", "restricted", "low")

    def test_backports_score(self):
        # BACKPORTS is the lowest-priority pocket.
        job = self.makeBuildJob(pocket="BACKPORTS")
        self.assertCorrectScore(job, "BACKPORTS")

    def test_release_score(self):
        # RELEASE ranks next above BACKPORTS.
        job = self.makeBuildJob(pocket="RELEASE")
        self.assertCorrectScore(job, "RELEASE")

    def test_proposed_updates_score(self):
        # PROPOSED and UPDATES both rank next above RELEASE.  The reason why
        # PROPOSED and UPDATES have the same priority is because sources in
        # both pockets are submitted to the same policy and should reach
        # their audience as soon as possible (see more information about
        # this decision in bug #372491).
        proposed_job = self.makeBuildJob(pocket="PROPOSED")
        self.assertCorrectScore(proposed_job, "PROPOSED")
        updates_job = self.makeBuildJob(pocket="UPDATES")
        self.assertCorrectScore(updates_job, "UPDATES")

    def test_security_updates_score(self):
        # SECURITY is the top-ranked pocket.
        job = self.makeBuildJob(pocket="SECURITY")
        self.assertCorrectScore(job, "SECURITY")

    def test_score_packageset(self):
        # Package sets alter the score of official packages for their
        # series.
        job = self.makeBuildJob(
            component="main", urgency="low", purpose=ArchivePurpose.PRIMARY)
        packageset = self.factory.makePackageset(
            distroseries=job.build.distro_series)
        removeSecurityProxy(packageset).add(
            [job.build.source_package_release.sourcepackagename])
        removeSecurityProxy(packageset).relative_build_score = 100
        self.assertCorrectScore(job, "RELEASE", "main", "low", 100)

    def test_score_packageset_in_ppa(self):
        # Package set score boosts don't affect PPA packages.
        job = self.makeBuildJob(
            component="main", urgency="low", purpose=ArchivePurpose.PPA)
        packageset = self.factory.makePackageset(
            distroseries=job.build.distro_series)
        removeSecurityProxy(packageset).add(
            [job.build.source_package_release.sourcepackagename])
        removeSecurityProxy(packageset).relative_build_score = 100
        self.assertCorrectScore(job, "RELEASE", "main", "low", 0)

    def test_translations_score(self):
        # Language packs (the translations section) don't get any
        # package-specific score bumps. They always have the archive's
        # base score.
        job = self.makeBuildJob(section_name='translations')
        removeSecurityProxy(job.build.archive).relative_build_score = 666
        self.assertEqual(666, job.score())

    def assertScoreReadableByAnyone(self, obj):
        """An object's build score is readable by anyone."""
        with person_logged_in(obj.owner):
            obj_url = api_url(obj)
        removeSecurityProxy(obj).relative_build_score = 100
        webservice = webservice_for_person(
            self.factory.makePerson(), permission=OAuthPermission.WRITE_PUBLIC)
        entry = webservice.get(obj_url, api_version="devel").jsonBody()
        self.assertEqual(100, entry["relative_build_score"])

    def assertScoreNotWriteableByOwner(self, obj):
        """Being an object's owner does not allow changing its build score.

        This affects a site-wide resource, and is thus restricted to
        launchpad-buildd-admins.
        """
        with person_logged_in(obj.owner):
            obj_url = api_url(obj)
        webservice = webservice_for_person(
            obj.owner, permission=OAuthPermission.WRITE_PUBLIC)
        entry = webservice.get(obj_url, api_version="devel").jsonBody()
        response = webservice.patch(
            entry["self_link"], "application/json",
            dumps(dict(relative_build_score=100)))
        self.assertEqual(401, response.status)
        new_entry = webservice.get(obj_url, api_version="devel").jsonBody()
        self.assertEqual(0, new_entry["relative_build_score"])

    def assertScoreWriteableByTeam(self, obj, team):
        """Members of TEAM can change an object's build score."""
        with person_logged_in(obj.owner):
            obj_url = api_url(obj)
        person = self.factory.makePerson(member_of=[team])
        webservice = webservice_for_person(
            person, permission=OAuthPermission.WRITE_PUBLIC)
        entry = webservice.get(obj_url, api_version="devel").jsonBody()
        response = webservice.patch(
            entry["self_link"], "application/json",
            dumps(dict(relative_build_score=100)))
        self.assertEqual(209, response.status)
        self.assertEqual(100, response.jsonBody()["relative_build_score"])

    def test_score_packageset_readable(self):
        # A packageset's build score is readable by anyone.
        packageset = self.factory.makePackageset()
        self.assertScoreReadableByAnyone(packageset)

    def test_score_packageset_forbids_non_buildd_admin(self):
        # Being the owner of a packageset is not enough to allow changing
        # its build score, since this affects a site-wide resource.
        packageset = self.factory.makePackageset()
        self.assertScoreNotWriteableByOwner(packageset)

    def test_score_packageset_allows_buildd_admin(self):
        # Buildd admins can change a packageset's build score.
        packageset = self.factory.makePackageset()
        self.assertScoreWriteableByTeam(
            packageset, getUtility(ILaunchpadCelebrities).buildd_admin)

    def test_score_archive_readable(self):
        # An archive's build score is readable by anyone.
        archive = self.factory.makeArchive()
        self.assertScoreReadableByAnyone(archive)

    def test_score_archive_forbids_non_buildd_admin(self):
        # Being the owner of an archive is not enough to allow changing its
        # build score, since this affects a site-wide resource.
        archive = self.factory.makeArchive()
        self.assertScoreNotWriteableByOwner(archive)

    def test_score_archive_allows_buildd_and_commercial_admin(self):
        # Buildd and commercial admins can change an archive's build score.
        archive = self.factory.makeArchive()
        self.assertScoreWriteableByTeam(
            archive, getUtility(ILaunchpadCelebrities).buildd_admin)
        with anonymous_logged_in():
            self.assertScoreWriteableByTeam(
                archive, getUtility(ILaunchpadCelebrities).commercial_admin)


class TestBuildPackageJobPostProcess(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeBuildJob(self, pocket="RELEASE"):
        build = self.factory.makeBinaryPackageBuild(pocket=pocket)
        return build.queueBuild()

    def test_release_job(self):
        job = self.makeBuildJob()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(job)
        self.assertTrue(BuildPackageJob.postprocessCandidate(job, None))
        self.assertEqual(BuildStatus.NEEDSBUILD, build.status)

    def test_security_job_is_failed(self):
        job = self.makeBuildJob(pocket="SECURITY")
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(job)
        BuildPackageJob.postprocessCandidate(job, DevNullLogger())
        self.assertEqual(BuildStatus.FAILEDTOBUILD, build.status)

    def test_obsolete_job_without_flag_is_failed(self):
        job = self.makeBuildJob()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(job)
        distroseries = build.distro_arch_series.distroseries
        removeSecurityProxy(distroseries).status = SeriesStatus.OBSOLETE
        BuildPackageJob.postprocessCandidate(job, DevNullLogger())
        self.assertEqual(BuildStatus.FAILEDTOBUILD, build.status)

    def test_obsolete_job_with_flag_is_not_failed(self):
        job = self.makeBuildJob()
        build = getUtility(IBinaryPackageBuildSet).getByQueueEntry(job)
        distroseries = build.distro_arch_series.distroseries
        archive = build.archive
        removeSecurityProxy(distroseries).status = SeriesStatus.OBSOLETE
        removeSecurityProxy(archive).permit_obsolete_series_uploads = True
        BuildPackageJob.postprocessCandidate(job, DevNullLogger())
        self.assertEqual(BuildStatus.NEEDSBUILD, build.status)
