# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for source package builds."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
import re

from pytz import utc
from storm.locals import Store
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.errors import NotFoundError
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.buildqueue import IBuildQueue
from lp.buildmaster.model.buildfarmjob import BuildFarmJob
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuild,
    ISourcePackageRecipeBuildJob,
    ISourcePackageRecipeBuildSource,
    )
from lp.code.mail.sourcepackagerecipebuild import (
    SourcePackageRecipeBuildMailer,
    )
from lp.code.model.sourcepackagerecipebuild import SourcePackageRecipeBuild
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.interfaces import IStore
from lp.services.log.logger import BufferLogger
from lp.services.mail.sendmail import format_address
from lp.services.webapp.authorization import check_permission
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.testing import (
    ANONYMOUS,
    login,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class TestSourcePackageRecipeBuild(TestCaseWithFactory):
    """Test the source package build object."""

    layer = LaunchpadFunctionalLayer

    def makeSourcePackageRecipeBuild(self, archive=None):
        """Create a `SourcePackageRecipeBuild` for testing."""
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        distroseries_i386 = distroseries.newArch(
            'i386', getUtility(IProcessorSet).getByName('386'), False, person,
            supports_virtualized=True)
        removeSecurityProxy(distroseries).nominatedarchindep = (
            distroseries_i386)
        if archive is None:
            archive = self.factory.makeArchive()

        return getUtility(ISourcePackageRecipeBuildSource).new(
            distroseries=distroseries,
            recipe=self.factory.makeSourcePackageRecipe(
                distroseries=distroseries),
            archive=archive,
            requester=person)

    def test_providesInterfaces(self):
        # SourcePackageRecipeBuild provides IPackageBuild and
        # ISourcePackageRecipeBuild.
        spb = self.makeSourcePackageRecipeBuild()
        self.assertProvides(spb, ISourcePackageRecipeBuild)

    def test_implements_interface(self):
        build = self.makeSourcePackageRecipeBuild()
        verifyObject(ISourcePackageRecipeBuild, build)

    def test_saves_record(self):
        # A source package recipe build can be stored in the database
        spb = self.makeSourcePackageRecipeBuild()
        transaction.commit()
        self.assertProvides(spb, ISourcePackageRecipeBuild)

    def test_makeJob(self):
        # A build farm job can be obtained from a SourcePackageRecipeBuild
        spb = self.makeSourcePackageRecipeBuild()
        job = spb.makeJob()
        self.assertProvides(job, ISourcePackageRecipeBuildJob)

    def test_queueBuild(self):
        spb = self.makeSourcePackageRecipeBuild()
        bq = spb.queueBuild(spb)

        self.assertProvides(bq, IBuildQueue)
        self.assertProvides(bq.specific_job, ISourcePackageRecipeBuildJob)
        self.assertEqual(True, bq.virtualized)

        # The processor for SourcePackageRecipeBuilds should not be None.
        # They do require specific environments.
        self.assertNotEqual(None, bq.processor)
        self.assertEqual(
            spb.distroseries.nominatedarchindep.processor, bq.processor)
        self.assertEqual(bq, spb.buildqueue_record)

    def test_title(self):
        # A recipe build's title currently consists of the base
        # branch's unique name.
        spb = self.makeSourcePackageRecipeBuild()
        title = "%s recipe build" % spb.recipe.base_branch.unique_name
        self.assertEqual(spb.title, title)

    def test_distribution(self):
        # A source package recipe build has a distribution derived from
        # its series.
        spb = self.makeSourcePackageRecipeBuild()
        self.assertEqual(spb.distroseries.distribution, spb.distribution)

    def test_current_component(self):
        # Since recipes build only into PPAs, they always build in main.
        # PPAs lack indices for other components.
        spb = self.makeSourcePackageRecipeBuild()
        self.assertEqual('main', spb.current_component.name)

    def test_is_private(self):
        # A source package recipe build's is private iff its archive is.
        spb = self.makeSourcePackageRecipeBuild()
        self.assertEqual(False, spb.is_private)
        archive = self.factory.makeArchive(private=True)
        with person_logged_in(archive.owner):
            spb = self.makeSourcePackageRecipeBuild(archive=archive)
            self.assertEqual(True, spb.is_private)

    def test_view_private_branch(self):
        """Recipebuilds with private branches are restricted."""
        owner = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(owner=owner)
        with person_logged_in(owner):
            recipe = self.factory.makeSourcePackageRecipe(branches=[branch])
            build = self.factory.makeSourcePackageRecipeBuild(recipe=recipe)
            job = build.makeJob()
            self.assertTrue(check_permission('launchpad.View', build))
            self.assertTrue(check_permission('launchpad.View', job))
        removeSecurityProxy(branch).information_type = (
            InformationType.USERDATA)
        with person_logged_in(self.factory.makePerson()):
            self.assertFalse(check_permission('launchpad.View', build))
            self.assertFalse(check_permission('launchpad.View', job))
        login(ANONYMOUS)
        self.assertFalse(check_permission('launchpad.View', build))
        self.assertFalse(check_permission('launchpad.View', job))

    def test_view_private_archive(self):
        """Recipebuilds with private branches are restricted."""
        owner = self.factory.makePerson()
        archive = self.factory.makeArchive(owner=owner, private=True)
        with person_logged_in(owner):
            build = self.factory.makeSourcePackageRecipeBuild(archive=archive)
            job = build.makeJob()
            self.assertTrue(check_permission('launchpad.View', build))
            self.assertTrue(check_permission('launchpad.View', job))
        with person_logged_in(self.factory.makePerson()):
            self.assertFalse(check_permission('launchpad.View', build))
            self.assertFalse(check_permission('launchpad.View', job))
        login(ANONYMOUS)
        self.assertFalse(check_permission('launchpad.View', build))
        self.assertFalse(check_permission('launchpad.View', job))

    def test_estimateDuration(self):
        # If there are no successful builds, estimate 10 minutes.
        spb = self.makeSourcePackageRecipeBuild()
        cur_date = self.factory.getUniqueDate()
        self.assertEqual(timedelta(minutes=10), spb.estimateDuration())
        for minutes in [20, 5, 1]:
            build = self.factory.makeSourcePackageRecipeBuild(
                recipe=spb.recipe)
            build.updateStatus(BuildStatus.BUILDING, date_started=cur_date)
            build.updateStatus(
                BuildStatus.FULLYBUILT,
                date_finished=cur_date + timedelta(minutes=minutes))
        self.assertEqual(timedelta(minutes=5), spb.estimateDuration())

    def test_getFileByName(self):
        """getFileByName returns the logs when requested by name."""
        spb = self.factory.makeSourcePackageRecipeBuild()
        spb.setLog(
            self.factory.makeLibraryFileAlias(filename='buildlog.txt.gz'))
        self.assertEqual(spb.log, spb.getFileByName('buildlog.txt.gz'))
        self.assertRaises(NotFoundError, spb.getFileByName, 'foo')
        spb.setLog(self.factory.makeLibraryFileAlias(filename='foo'))
        self.assertEqual(spb.log, spb.getFileByName('foo'))
        self.assertRaises(NotFoundError, spb.getFileByName, 'buildlog.txt.gz')
        spb.storeUploadLog('uploaded')
        self.assertEqual(
            spb.upload_log, spb.getFileByName(spb.upload_log.filename))

    def test_binary_builds(self):
        """The binary_builds property should be populated automatically."""
        spb = self.factory.makeSourcePackageRecipeBuild()
        multiverse = self.factory.makeComponent(name='multiverse')
        spr = self.factory.makeSourcePackageRelease(
            source_package_recipe_build=spb, component=multiverse)
        self.assertEqual([], list(spb.binary_builds))
        binary = self.factory.makeBinaryPackageBuild(spr)
        self.factory.makeBinaryPackageBuild()
        Store.of(binary).flush()
        self.assertEqual([binary], list(spb.binary_builds))

    def test_manifest(self):
        """Manifest should start empty, but accept SourcePackageRecipeData."""
        recipe = self.factory.makeSourcePackageRecipe()
        build = recipe.requestBuild(
            recipe.daily_build_archive, recipe.owner,
            list(recipe.distroseries)[0], PackagePublishingPocket.RELEASE)
        self.assertIs(None, build.manifest)
        self.assertIs(None, build.getManifestText())
        manifest_text = self.factory.makeRecipeText()
        removeSecurityProxy(build).setManifestText(manifest_text)
        self.assertEqual(manifest_text, build.getManifestText())
        self.assertIsNot(None, build.manifest)
        IStore(build).flush()
        manifest_text = self.factory.makeRecipeText()
        removeSecurityProxy(build).setManifestText(manifest_text)
        self.assertEqual(manifest_text, build.getManifestText())
        removeSecurityProxy(build).setManifestText(None)
        self.assertIs(None, build.manifest)

    def test_makeDailyBuilds(self):
        self.assertEqual([], SourcePackageRecipeBuild.makeDailyBuilds())
        recipe = self.factory.makeSourcePackageRecipe(build_daily=True)
        [build] = SourcePackageRecipeBuild.makeDailyBuilds()
        self.assertEqual(recipe, build.recipe)
        self.assertEqual(list(recipe.distroseries), [build.distroseries])

    def test_makeDailyBuilds_skips_missing_archive(self):
        """When creating daily builds, skip ones that are already pending."""
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        with person_logged_in(recipe.owner):
            recipe.daily_build_archive = None
        builds = SourcePackageRecipeBuild.makeDailyBuilds()
        self.assertEqual([], builds)

    def test_makeDailyBuilds_logs_builds(self):
        # If a logger is passed into the makeDailyBuilds method, each recipe
        # that a build is requested for gets logged.
        owner = self.factory.makePerson(name='eric')
        self.factory.makeSourcePackageRecipe(
            owner=owner, name=u'funky-recipe', build_daily=True)
        logger = BufferLogger()
        SourcePackageRecipeBuild.makeDailyBuilds(logger)
        self.assertEqual(
            'DEBUG Recipe eric/funky-recipe is stale\n'
            'DEBUG  - build requested for Warty (4.10)\n',
            logger.getLogBuffer())

    def test_makeDailyBuilds_clears_is_stale(self):
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        SourcePackageRecipeBuild.makeDailyBuilds()[0]
        self.assertFalse(recipe.is_stale)

    def test_makeDailyBuilds_skips_if_built_in_last_24_hours(self):
        # We won't create a build during makeDailyBuilds() if the recipe
        # has been built in the last 24 hours.
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        recipe.requestBuild(
            recipe.daily_build_archive, recipe.owner,
            list(recipe.distroseries)[0], PackagePublishingPocket.RELEASE)
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds()
        self.assertEqual([], daily_builds)

    def test_makeDailyBuilds_skips_non_stale_builds(self):
        # If the recipe isn't stale, makeDailyBuilds() won't create a build.
        self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=False)
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds()
        self.assertEqual([], daily_builds)

    def test_makeDailyBuilds_skips_builds_already_queued(self):
        # If the recipe already has an identical build pending,
        # makeDailyBuilds() won't create a build.
        owner = self.factory.makePerson(name='eric')
        recipe = self.factory.makeSourcePackageRecipe(
            owner=owner, name=u'funky-recipe', build_daily=True,
            is_stale=True)
        series = list(recipe.distroseries)[0]
        self.factory.makeSourcePackageRecipeBuild(
            recipe=recipe, archive=recipe.daily_build_archive,
            requester=recipe.owner, distroseries=series,
            pocket=PackagePublishingPocket.RELEASE,
            date_created=datetime.now(utc) - timedelta(hours=24, seconds=1))
        removeSecurityProxy(recipe).is_stale = True

        logger = BufferLogger()
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds(logger)
        self.assertEqual([], daily_builds)
        self.assertEqual(
            'DEBUG Recipe eric/funky-recipe is stale\n'
            'DEBUG  - build already pending for Warty (4.10)\n',
            logger.getLogBuffer())

    def test_makeDailyBuilds_skips_disabled_archive(self):
        # If the recipe's daily build archive is disabled, makeDailyBuilds()
        # won't create a build.
        owner = self.factory.makePerson(name='eric')
        recipe = self.factory.makeSourcePackageRecipe(
            owner=owner, name=u'funky-recipe', build_daily=True,
            is_stale=True)
        archive = self.factory.makeArchive(owner=recipe.owner, name="ppa")
        removeSecurityProxy(recipe).daily_build_archive = archive
        removeSecurityProxy(archive).disable()

        logger = BufferLogger()
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds(logger)
        self.assertEqual([], daily_builds)
        self.assertEqual(
            'DEBUG Recipe eric/funky-recipe is stale\n'
            'DEBUG  - daily build failed for Warty (4.10): ' +
            "ArchiveDisabled(u'PPA for Eric is disabled.',)\n",
            logger.getLogBuffer())

    def test_makeDailyBuilds_skips_archive_with_no_permission(self):
        # If the recipe's daily build archive cannot be uploaded to due to
        # insufficient permissions, makeDailyBuilds() won't create a build.
        owner = self.factory.makePerson(name='eric')
        recipe = self.factory.makeSourcePackageRecipe(
            owner=owner, name=u'funky-recipe', build_daily=True,
            is_stale=True)
        archive = self.factory.makeArchive(name="ppa")
        removeSecurityProxy(recipe).daily_build_archive = archive

        logger = BufferLogger()
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds(logger)
        self.assertEqual([], daily_builds)
        self.assertEqual(
            'DEBUG Recipe eric/funky-recipe is stale\n'
            'DEBUG  - daily build failed for Warty (4.10): '
            "CannotUploadToPPA('Signer has no upload rights "
            "to this PPA.',)\n",
            logger.getLogBuffer())

    def test_makeDailyBuilds_with_an_older_build(self):
        # If a previous build is more than 24 hours old, and the recipe is
        # stale, we'll fire another off.
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        build = self.factory.makeSourcePackageRecipeBuild(
            recipe=recipe, archive=recipe.daily_build_archive,
            requester=recipe.owner, distroseries=list(recipe.distroseries)[0],
            pocket=PackagePublishingPocket.RELEASE,
            date_created=datetime.now(utc) - timedelta(hours=24, seconds=1),
            status=BuildStatus.FULLYBUILT)
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds()
        self.assertEquals(1, len(daily_builds))
        actual_title = [b.title for b in daily_builds]
        self.assertEquals([build.title], actual_title)

    def test_makeDailyBuilds_with_an_older_and_newer_build(self):
        # If a recipe has been built twice, and the most recent build is
        # within 24 hours, makeDailyBuilds() won't create a build.
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        for timediff in (timedelta(hours=24, seconds=1), timedelta(hours=8)):
            self.factory.makeSourcePackageRecipeBuild(
                recipe=recipe, archive=recipe.daily_build_archive,
                requester=recipe.owner,
                distroseries=list(recipe.distroseries)[0],
                pocket=PackagePublishingPocket.RELEASE,
                date_created=datetime.now(utc) - timediff,
                status=BuildStatus.FULLYBUILT)
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds()
        self.assertEquals([], list(daily_builds))

    def test_makeDailyBuilds_with_new_build_different_archive(self):
        # If a recipe has been built into an archive that isn't the
        # daily_build_archive, we will create a build.
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        archive = self.factory.makeArchive(owner=recipe.owner)
        build = self.factory.makeSourcePackageRecipeBuild(
            recipe=recipe, archive=archive, requester=recipe.owner,
            distroseries=list(recipe.distroseries)[0],
            pocket=PackagePublishingPocket.RELEASE,
            date_created=datetime.now(utc) - timedelta(hours=8),
            status=BuildStatus.FULLYBUILT)
        daily_builds = SourcePackageRecipeBuild.makeDailyBuilds()
        actual_title = [b.title for b in daily_builds]
        self.assertEquals([build.title], actual_title)

    def test_makeDailyBuilds_with_disallowed_series(self):
        # If a recipe is set to build into a disallowed series,
        # makeDailyBuilds won't OOPS.
        recipe = self.factory.makeSourcePackageRecipe(
            build_daily=True, is_stale=True)
        self.factory.makeArchive(owner=recipe.owner)
        logger = BufferLogger()
        distroseries = list(recipe.distroseries)[0]
        removeSecurityProxy(distroseries).status = SeriesStatus.OBSOLETE
        SourcePackageRecipeBuild.makeDailyBuilds(logger)
        self.assertEquals([], self.oopses)
        self.assertIn(
            "DEBUG  - cannot build against Warty (4.10).",
            logger.getLogBuffer())

    def test_getRecentBuilds(self):
        """Recent builds match the same person, series and receipe.

        Builds do not match if they are older than 24 hours, or have a
        different requester, series or recipe.
        """
        requester = self.factory.makePerson()
        recipe = self.factory.makeSourcePackageRecipe()
        series = self.factory.makeDistroSeries()
        now = self.factory.getUniqueDate()
        build = self.factory.makeSourcePackageRecipeBuild(recipe=recipe,
            requester=requester)
        self.factory.makeSourcePackageRecipeBuild(
            recipe=recipe, distroseries=series)
        self.factory.makeSourcePackageRecipeBuild(
            requester=requester, distroseries=series)

        def get_recent():
            Store.of(build).flush()
            return SourcePackageRecipeBuild.getRecentBuilds(
                requester, recipe, series, _now=now)
        self.assertContentEqual([], get_recent())
        yesterday = now - timedelta(days=1)
        self.factory.makeSourcePackageRecipeBuild(
            recipe=recipe, distroseries=series, requester=requester,
            date_created=yesterday)
        self.assertContentEqual([], get_recent())
        more_recent_build = self.factory.makeSourcePackageRecipeBuild(
            recipe=recipe, distroseries=series, requester=requester,
            date_created=yesterday + timedelta(seconds=1))
        self.assertContentEqual([more_recent_build], get_recent())

    def test_destroySelf(self):
        # ISourcePackageRecipeBuild should make sure to remove jobs and build
        # queue entries and then invalidate itself.
        build = self.factory.makeSourcePackageRecipeBuild()
        build.destroySelf()

    def test_destroySelf_clears_release(self):
        # Destroying a sourcepackagerecipebuild removes references to it from
        # its releases.
        build = self.factory.makeSourcePackageRecipeBuild()
        release = self.factory.makeSourcePackageRelease(
            source_package_recipe_build=build)
        self.assertEqual(build, release.source_package_recipe_build)
        build.destroySelf()
        self.assertIs(None, release.source_package_recipe_build)
        transaction.commit()

    def test_destroySelf_destroys_referenced(self):
        # Destroying a sourcepackagerecipebuild also destroys the
        # PackageBuild and BuildFarmJob it references.
        build = self.factory.makeSourcePackageRecipeBuild()
        store = Store.of(build)
        naked_build = removeSecurityProxy(build)
        # Ensure database ids are set.
        store.flush()
        build_farm_job_id = naked_build.build_farm_job_id
        build.destroySelf()
        self.assertIs(None, store.get(BuildFarmJob, build_farm_job_id))

    def test_cancelBuild(self):
        # ISourcePackageRecipeBuild should make sure to remove jobs and build
        # queue entries and then invalidate itself.
        build = self.factory.makeSourcePackageRecipeBuild()
        build.cancelBuild()

        self.assertEqual(
            BuildStatus.SUPERSEDED,
            build.status)

    def test_getUploader(self):
        # For ACL purposes the uploader is the build requester.
        build = self.makeSourcePackageRecipeBuild()
        self.assertEquals(build.requester,
            build.getUploader(None))

    def test_getByBuildFarmJob(self):
        sprb = self.makeSourcePackageRecipeBuild()
        Store.of(sprb).flush()
        self.assertEqual(
            sprb,
            SourcePackageRecipeBuild.getByBuildFarmJob(sprb.build_farm_job))

    def test_getByBuildFarmJobs(self):
        sprbs = [self.makeSourcePackageRecipeBuild() for i in range(10)]
        Store.of(sprbs[0]).flush()
        self.assertContentEqual(
            sprbs,
            SourcePackageRecipeBuild.getByBuildFarmJobs(
                [sprb.build_farm_job for sprb in sprbs]))

    def test_getByBuildFarmJobs_empty(self):
        self.assertContentEqual(
            [],
            SourcePackageRecipeBuild.getByBuildFarmJobs([]))


class TestAsBuildmaster(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_notify(self):
        """We do not send mail on completion of source package recipe builds.

        See bug 778437.
        """
        person = self.factory.makePerson(name='person')
        cake = self.factory.makeSourcePackageRecipe(
            name=u'recipe', owner=person)
        pantry = self.factory.makeArchive(name='ppa')
        secret = self.factory.makeDistroSeries(name=u'distroseries')
        build = self.factory.makeSourcePackageRecipeBuild(
            recipe=cake, distroseries=secret, archive=pantry)
        build.updateStatus(BuildStatus.FULLYBUILT)
        IStore(build).flush()
        build.notify()
        self.assertEquals(0, len(pop_notifications()))

    def assertBuildMessageValid(self, build, message):
        # Not currently used; can be used if we do want to check about any
        # notifications sent in other cases.
        requester = build.requester
        requester_address = format_address(
            requester.displayname, requester.preferredemail.email)
        mailer = SourcePackageRecipeBuildMailer.forStatus(build)
        expected = mailer.generateEmail(
            requester.preferredemail.email, requester)
        self.assertEqual(
            requester_address, re.sub(r'\n\t+', ' ', message['To']))
        self.assertEqual(expected.subject, message['Subject'].replace(
            '\n\t', ' '))
        self.assertEqual(
            expected.body, message.get_payload(decode=True))

    def test_notify_when_recipe_deleted(self):
        """Notify does nothing if recipe has been deleted."""
        person = self.factory.makePerson(name='person')
        cake = self.factory.makeSourcePackageRecipe(
            name=u'recipe', owner=person)
        pantry = self.factory.makeArchive(name='ppa')
        secret = self.factory.makeDistroSeries(name=u'distroseries')
        build = self.factory.makeSourcePackageRecipeBuild(
            recipe=cake, distroseries=secret, archive=pantry)
        build.updateStatus(BuildStatus.FULLYBUILT)
        cake.destroySelf()
        IStore(build).flush()
        build.notify()
        notifications = pop_notifications()
        self.assertEquals(0, len(notifications))
