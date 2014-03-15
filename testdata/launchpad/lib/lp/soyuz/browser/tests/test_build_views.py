# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import soupmatchers
from testtools.matchers import (
    MatchesException,
    Not,
    Raises,
    )
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.sqlbase import flush_database_caches
from lp.services.job.interfaces.job import JobStatus
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import StormRangeFactoryError
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.browser.build import BuildContextMenu
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.packageset import IPackagesetSet
from lp.soyuz.model.queue import PackageUploadBuild
from lp.testing import (
    admin_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class TestBuildViews(TestCaseWithFactory):
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBuildViews, self).setUp()
        self.empty_request = LaunchpadTestRequest(form={})
        self.admin = getUtility(IPersonSet).getByEmail(ADMIN_EMAIL)

    def assertBuildViewRetryIsExpected(self, build, person, expected):
        with person_logged_in(person):
            build_view = getMultiAdapter(
                (build, self.empty_request), name="+index")
            self.assertEquals(build_view.user_can_retry_build, expected)

    def test_view_with_component(self):
        # The component name is provided when the component is known.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        removeSecurityProxy(archive).require_virtualized = False
        build = self.factory.makeBinaryPackageBuild(archive=archive)
        view = create_initialized_view(build, name="+index")
        self.assertEqual('multiverse', view.component_name)

    def test_view_without_component(self):
        # Production has some buggy builds without source publications.
        # current_component used by the view returns None in that case.
        spph = self.factory.makeSourcePackagePublishingHistory()
        other_das = self.factory.makeDistroArchSeries()
        build = spph.sourcepackagerelease.createBuild(
            other_das, PackagePublishingPocket.RELEASE, spph.archive)
        view = create_initialized_view(build, name="+index")
        self.assertEqual('unknown', view.component_name)

    def test_build_menu_primary(self):
        # The menu presented in the build page depends on the targeted
        # archive. For instance the 'PPA' action-menu link is not enabled
        # for builds targeted to the PRIMARY archive.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        removeSecurityProxy(archive).require_virtualized = False
        build = self.factory.makeBinaryPackageBuild(archive=archive)
        build_menu = BuildContextMenu(build)
        self.assertEquals(
            build_menu.links,
            ['ppa', 'records', 'retry', 'rescore', 'cancel'])
        self.assertFalse(build_menu.is_ppa_build)
        self.assertFalse(build_menu.ppa().enabled)
        # Cancel is not enabled on non-virtual builds.
        self.assertFalse(build_menu.cancel().enabled)

    def test_build_menu_ppa(self):
        # The 'PPA' action-menu item will be enabled if we target the build
        # to a PPA.
        ppa = self.factory.makeArchive(
            purpose=ArchivePurpose.PPA, virtualized=True)
        build = self.factory.makeBinaryPackageBuild(archive=ppa)
        build.queueBuild()
        build_menu = BuildContextMenu(build)
        self.assertEquals(
            build_menu.links,
            ['ppa', 'records', 'retry', 'rescore', 'cancel'])
        self.assertTrue(build_menu.is_ppa_build)
        self.assertTrue(build_menu.ppa().enabled)
        # Cancel is enabled on virtual builds if the user is in the
        # owning archive's team.
        with person_logged_in(ppa.owner):
            self.assertTrue(build_menu.cancel().enabled)

    def test_cannot_retry_stable_distroseries(self):
        # 'BuildView.user_can_retry_build' property checks not only the
        # user's permissions to retry but also if a build is in a status
        # that it can be retried.
        # The build cannot be retried (see IBuild) because it's targeted to a
        # released distroseries.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        build = self.factory.makeBinaryPackageBuild(
            archive=archive, status=BuildStatus.FAILEDTOBUILD)
        distroseries = build.distro_arch_series.distroseries
        with person_logged_in(self.admin):
            distroseries.status = SeriesStatus.CURRENT
        build_view = getMultiAdapter(
            (build, self.empty_request), name="+index")
        self.assertFalse(build_view.is_ppa)
        self.assertEquals(build_view.buildqueue, None)
        self.assertEquals(build_view.component_name, 'multiverse')
        self.assertFalse(build.can_be_retried)
        self.assertFalse(build_view.user_can_retry_build)

    def test_retry_ppa_builds(self):
        # PPA builds can always be retried, no matter what status the
        # distroseries has.
        build = self.factory.makeBinaryPackageBuild(
            status=BuildStatus.FAILEDTOBUILD)
        build_view = getMultiAdapter(
            (build, self.empty_request), name="+index")
        self.assertTrue(build.can_be_retried)
        # Anonymous, therefore supposed to be disallowed
        self.assertFalse(build_view.user_can_retry_build)
        self.assertBuildViewRetryIsExpected(build, build.archive.owner, True)

    def test_buildd_admins_retry_builds(self):
        # Buildd admins can retry any build as long is it's in a state that
        # permits it to be re-tried.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        build = self.factory.makeBinaryPackageBuild(
            archive=archive, status=BuildStatus.FAILEDTOBUILD)
        with person_logged_in(self.admin):
            self.assertTrue(build.can_be_retried)
        nopriv = getUtility(IPersonSet).getByName("no-priv")
        # Mr no privileges can't retry
        self.assertBuildViewRetryIsExpected(build, nopriv, False)
        # But he can as a member of launchpad-buildd-admins
        buildd_admins = getUtility(IPersonSet).getByName(
            "launchpad-buildd-admins")
        with person_logged_in(self.admin):
            buildd_admins.addMember(nopriv, nopriv)
        self.assertBuildViewRetryIsExpected(build, nopriv, True)

    def test_packageset_upload_retry(self):
        # A person in a team that has rights to upload to a packageset can
        # also retry failed builds of contained source packages.
        team = self.factory.makeTeam()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        build = self.factory.makeBinaryPackageBuild(
            archive=archive, status=BuildStatus.FAILEDTOBUILD)
        with person_logged_in(self.admin):
            packageset = getUtility(IPackagesetSet).new(
                u'rebuild', u'test', team,
                distroseries=build.distro_arch_series.distroseries)
            packageset.add((build.source_package_release.sourcepackagename,))
        # The team doesn't have permission until we grant it
        self.assertBuildViewRetryIsExpected(build, team.teamowner, False)
        with person_logged_in(self.admin):
            getUtility(IArchivePermissionSet).newPackagesetUploader(
                archive, team, packageset)
        self.assertBuildViewRetryIsExpected(build, team.teamowner, True)

    def test_build_view_package_upload(self):
        # `BuildView.package_upload` returns the cached `PackageUpload`
        # record corresponding to this build. It's None if the binaries for
        # a build were not yet collected.
        build = self.factory.makeBinaryPackageBuild()
        build_view = getMultiAdapter(
            (build, self.empty_request), name="+index")
        self.assertEquals(build_view.package_upload, None)
        self.assertFalse(build_view.has_published_binaries)
        package_upload = build.distro_series.createQueueEntry(
            PackagePublishingPocket.UPDATES, build.archive,
            'changes.txt', 'my changes')
        # Old SQL Object: creating it, adds it automatically to the store.
        PackageUploadBuild(packageupload=package_upload, build=build)
        self.assertEquals(package_upload.status.name, 'NEW')
        build_view = getMultiAdapter(
            (build, self.empty_request), name="+index")
        self.assertEquals(build_view.package_upload.status.name, 'NEW')
        self.assertFalse(build_view.has_published_binaries)
        with person_logged_in(self.admin):
            package_upload.setDone()
        build_view = getMultiAdapter(
            (build, self.empty_request), name="+index")
        self.assertEquals(build_view.package_upload.status.name, 'DONE')
        self.assertTrue(build_view.has_published_binaries)

    def test_build_view_files_helper(self):
        # The BuildIndex view also has a files helper which returns
        # all the files from the related binary package releases.
        build = self.factory.makeBinaryPackageBuild(
            status=BuildStatus.FULLYBUILT)
        bpr = self.factory.makeBinaryPackageRelease(build=build)
        bprf = self.factory.makeBinaryPackageFile(binarypackagerelease=bpr)
        build_view = create_initialized_view(build, '+index')
        deb_file = build_view.files[0]
        self.assertEquals(deb_file.filename, bprf.libraryfile.filename)
        # Deleted files won't be included
        self.assertFalse(deb_file.deleted)
        removeSecurityProxy(deb_file.context).content = None
        self.assertTrue(deb_file.deleted)
        build_view = create_initialized_view(build, '+index')
        self.assertEquals(len(build_view.files), 0)

    def test_build_rescoring_view(self):
        # `BuildRescoringView` is used for setting new values to the
        # corresponding `BuildQueue.lastscore` record for a `Build`.
        # It redirects users to the `Build` page when the build cannot be
        # rescored.
        build = self.factory.makeBinaryPackageBuild(
            status=BuildStatus.FAILEDTOBUILD)
        self.assertFalse(build.can_be_rescored)
        view = create_initialized_view(build, name='+rescore')
        self.assertEquals(view.request.response.getStatus(), 302)
        self.assertEquals(view.request.response.getHeader('Location'),
            canonical_url(build))
        pending_build = self.factory.makeBinaryPackageBuild()
        view = create_initialized_view(pending_build, name='+rescore')
        self.assertEquals(view.cancel_url, canonical_url(pending_build))

    def test_rescore_value_too_large(self):
        build = self.factory.makeBinaryPackageBuild()
        view = create_initialized_view(
            build, name="+rescore", form={
                'field.priority': str(2 ** 31 + 1),
                'field.actions.rescore': 'Rescore'})
        self.assertEquals(view.errors[0].widget_title, "Priority")
        self.assertEquals(view.errors[0].doc(), "Value is too big")

    def test_rescore_value_too_small(self):
        build = self.factory.makeBinaryPackageBuild()
        view = create_initialized_view(
            build, name="+rescore", form={
                'field.priority': '-' + str(2 ** 31 + 1),
                'field.actions.rescore': 'Rescore'})
        self.assertEquals(view.errors[0].widget_title, "Priority")
        self.assertEquals(view.errors[0].doc(), "Value is too small")

    def test_rescore(self):
        pending_build = self.factory.makeBinaryPackageBuild()
        pending_build.queueBuild()
        with person_logged_in(self.admin):
            view = create_initialized_view(
                pending_build, name="+rescore", form={
                    'field.priority': '0',
                    'field.actions.rescore': 'Rescore'})
        notification = view.request.response.notifications[0]
        self.assertEquals(notification.message, "Build rescored to 0.")
        self.assertEquals(pending_build.buildqueue_record.lastscore, 0)

    def test_build_page_has_cancel_link(self):
        build = self.factory.makeBinaryPackageBuild()
        build.queueBuild()
        person = build.archive.owner
        with person_logged_in(person):
            build_view = create_initialized_view(
                build, "+index", principal=person)
            page = build_view()
        url = canonical_url(build) + "/+cancel"
        matches_cancel_link = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "CANCEL_LINK", "a", attrs=dict(href=url)))
        self.assertThat(page, matches_cancel_link)

    def test_cancelling_pending_build(self):
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        pending_build = self.factory.makeBinaryPackageBuild(archive=ppa)
        pending_build.queueBuild()
        with person_logged_in(ppa.owner):
            view = create_initialized_view(
                pending_build, name="+cancel", form={
                    'field.actions.cancel': 'Cancel'})
        notification = view.request.response.notifications[0]
        self.assertEqual(notification.message, "Build cancelled.")
        self.assertEqual(BuildStatus.CANCELLED, pending_build.status)

    def test_cancelling_building_build(self):
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        pending_build = self.factory.makeBinaryPackageBuild(archive=ppa)
        pending_build.queueBuild()
        pending_build.updateStatus(BuildStatus.BUILDING)
        with person_logged_in(ppa.owner):
            view = create_initialized_view(
                pending_build, name="+cancel", form={
                    'field.actions.cancel': 'Cancel'})
        notification = view.request.response.notifications[0]
        self.assertEqual(
            notification.message, "Build cancellation in progress.")
        self.assertEqual(BuildStatus.CANCELLING, pending_build.status)

    def test_cancelling_uncancellable_build(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        pending_build = self.factory.makeBinaryPackageBuild(archive=archive)
        pending_build.queueBuild()
        pending_build.updateStatus(BuildStatus.FAILEDTOBUILD)
        with person_logged_in(archive.owner):
            view = create_initialized_view(
                pending_build, name="+cancel", form={
                    'field.actions.cancel': 'Cancel'})
        notification = view.request.response.notifications[0]
        self.assertEqual(
            notification.message, "Unable to cancel build.")
        self.assertEqual(BuildStatus.FAILEDTOBUILD, pending_build.status)

    def test_build_records_view(self):
        # The BuildRecordsView can also be used to filter by architecture tag.
        distroseries = self.factory.makeDistroSeries()
        arch_list = []
        for i in range(5):
            das = self.factory.makeDistroArchSeries(distroseries=distroseries)
            arch_list.append(das.architecturetag)
            build = self.factory.makeBinaryPackageBuild(
                distroarchseries=das, archive=distroseries.main_archive,
                status=BuildStatus.NEEDSBUILD)
            build.updateStatus(BuildStatus.BUILDING)
            build.updateStatus(BuildStatus.FULLYBUILT)
        view = create_initialized_view(
            distroseries, name="+builds", form={'build_state': 'all'})
        view.setupBuildList()
        build_arches = [build.arch_tag for build in view.complete_builds]
        self.assertEquals(arch_list.sort(), build_arches.sort())
        view = create_initialized_view(
            distroseries, name="+builds", form={
                'build_state': 'all', 'arch_tag': arch_list[0]})
        view.setupBuildList()
        self.assertEquals(len(view.complete_builds), 1)
        self.assertEquals(view.complete_builds[0].arch_tag, arch_list[0])
        # There is an extra entry for 'All architectures'
        self.assertEquals(len(view.architecture_options), len(arch_list) + 1)
        selected = []
        option_arches = []
        for option in view.architecture_options:
            option_arches.append(option['name'])
            if option['selected'] is not None:
                selected.append(option['name'])
        self.assertEquals(option_arches.sort(), arch_list.sort())
        self.assertTrue(len(selected), 1)
        self.assertEquals(selected, [arch_list[0]])

    def test_dispatch_estimate(self):
        # A dispatch time estimate is available for pending binary builds
        # that have not been suspended.
        build = self.factory.makeBinaryPackageBuild()
        build.queueBuild()
        view = create_initialized_view(build, name="+index")
        job = view.context.buildqueue_record.job
        self.assertTrue(view.dispatch_time_estimate_available)
        self.assertEquals(view.context.status, BuildStatus.NEEDSBUILD)
        self.assertEquals(job.status, JobStatus.WAITING)
        # If we suspend the job, there is no estimate available
        job.suspend()
        self.assertEquals(job.status, JobStatus.SUSPENDED)
        self.assertFalse(view.dispatch_time_estimate_available)

    def test_old_url_redirection(self):
        # When users go to the old build URLs, they are redirected to the
        # equivalent new URLs.
        build = self.factory.makeBinaryPackageBuild()
        build.queueBuild()
        url = "http://launchpad.dev/+builds/+build/%s" % build.id
        expected_url = canonical_url(build)
        browser = self.getUserBrowser(url)
        self.assertEquals(expected_url, browser.url)

    def test_DistributionBuildRecordsView__range_factory(self):
        # DistributionBuildRecordsView works with StormRangeFactory:
        # StormRangeFactory requires result sets where the sort order
        # is specified by Storm Column objects or by Desc(storm_column).
        # DistributionBuildRecordsView gets its resultset from
        # IDistribution.getBuildRecords(); the sort order of the
        # result set depends on the parameter build_state.
        # The order expressions for all possible values of build_state
        # are usable by StormRangeFactory.
        distroseries = self.factory.makeDistroSeries()
        distribution = distroseries.distribution
        das = self.factory.makeDistroArchSeries(distroseries=distroseries)
        for status in BuildStatus.items:
            build = self.factory.makeBinaryPackageBuild(
                distroarchseries=das, archive=distroseries.main_archive,
                status=status)
            # BPBs in certain states need a bit tweaking to appear in
            # the result of getBuildRecords().
            if status == BuildStatus.FULLYBUILT:
                build.updateStatus(BuildStatus.BUILDING)
                build.updateStatus(BuildStatus.FULLYBUILT)
            elif status in (BuildStatus.NEEDSBUILD, BuildStatus.BUILDING):
                build.queueBuild()
        for status in ('built', 'failed', 'depwait', 'chrootwait',
                       'superseded', 'uploadfail', 'all', 'building',
                       'pending'):
            view = create_initialized_view(
                distribution, name="+builds", form={'build_state': status})
            view.setupBuildList()
            range_factory = view.batchnav.batch.range_factory

            def test_range_factory():
                row = range_factory.resultset.get_plain_result_set()[0]
                range_factory.getOrderValuesFor(row)

            self.assertThat(
                test_range_factory,
                Not(Raises(MatchesException(StormRangeFactoryError))))

    def test_name_filter_with_storm_range_factory(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeDistroArchSeries(distroseries=distroseries)
        view = create_initialized_view(
            distroseries.distribution, name="+builds",
            form={
                'build_state': 'built',
                'build_text': u'foo',
                'start': 75,
                'memo': '["2012-01-01T01:01:01", 0]'})
        view.setupBuildList()

    def test_eta(self):
        # BuildView.eta returns a non-None value when it should, or None
        # when there's no start time.
        build = self.factory.makeBinaryPackageBuild()
        build.queueBuild()
        self.factory.makeBuilder(processor=build.processor, virtualized=True)
        self.assertIsNot(None, create_initialized_view(build, '+index').eta)
        with admin_logged_in():
            build.archive.disable()
        flush_database_caches()
        self.assertIs(None, create_initialized_view(build, '+index').eta)
