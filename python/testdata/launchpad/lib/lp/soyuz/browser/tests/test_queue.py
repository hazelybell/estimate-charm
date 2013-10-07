# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for QueueItemsView."""

__metaclass__ = type

from lxml import html
import soupmatchers
from storm.store import Store
from testtools.matchers import Equals
import transaction
from zope.component import (
    getUtility,
    queryMultiAdapter,
    )

from lp.archiveuploader.tests import datadir
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.browser.queue import CompletePackageUpload
from lp.soyuz.enums import PackageUploadStatus
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.queue import IPackageUploadSet
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    login,
    login_person,
    logout,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.sampledata import ADMIN_EMAIL
from lp.testing.views import create_initialized_view


class TestAcceptRejectQueueUploads(TestCaseWithFactory):
    """Uploads can be accepted or rejected with the relevant permissions."""

    layer = LaunchpadFunctionalLayer

    def makeSPR(self, sourcename, component, archive, changes_file_content,
                pocket=None, distroseries=None):
        if pocket is None:
            pocket = PackagePublishingPocket.RELEASE
        if distroseries is None:
            distroseries = self.test_publisher.distroseries
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=sourcename, component=component, archive=archive,
            distroseries=distroseries)
        packageupload = self.factory.makePackageUpload(
            archive=archive, pocket=pocket, distroseries=distroseries,
            changes_file_content=changes_file_content)
        packageupload.addSource(spr)
        return spr

    def setUp(self):
        """Create two new uploads in the new state and a person with
        permission to upload to the partner archive."""
        super(TestAcceptRejectQueueUploads, self).setUp()
        login('admin@canonical.com')
        self.test_publisher = SoyuzTestPublisher()
        self.test_publisher.prepareBreezyAutotest()
        distribution = self.test_publisher.distroseries.distribution
        self.second_series = self.factory.makeDistroSeries(
            distribution=distribution)
        self.factory.makeComponentSelection(self.second_series, 'main')
        self.main_archive = distribution.getArchiveByComponent('main')
        self.partner_archive = distribution.getArchiveByComponent('partner')

        # Get some sample changes file content for the new uploads.
        with open(datadir('suite/bar_1.0-1/bar_1.0-1_source.changes')) as cf:
            changes_file_content = cf.read()

        self.partner_spr = self.makeSPR(
            'partner-upload', 'partner', self.partner_archive,
            changes_file_content,
            distroseries=self.test_publisher.distroseries)
        self.main_spr = self.makeSPR(
            'main-upload', 'main', self.main_archive, changes_file_content,
            distroseries=self.test_publisher.distroseries)
        self.proposed_spr = self.makeSPR(
            'proposed-upload', 'main', self.main_archive, changes_file_content,
            pocket=PackagePublishingPocket.PROPOSED,
            distroseries=self.test_publisher.distroseries)
        self.proposed_series_spr = self.makeSPR(
            'proposed-series-upload', 'main', self.main_archive,
            changes_file_content, pocket=PackagePublishingPocket.PROPOSED,
            distroseries=self.second_series)

        # Define the form that will be used to post to the view.
        self.form = {
            'queue_state': PackageUploadStatus.NEW.value,
            'Accept': 'Accept',
            }

        # Create a user with queue admin rights for main, and a separate
        # user with queue admin rights for partner (on the partner
        # archive).
        self.main_queue_admin = self.factory.makePerson()
        getUtility(IArchivePermissionSet).newQueueAdmin(
            distribution.getArchiveByComponent('main'),
            self.main_queue_admin, self.main_spr.component)
        self.partner_queue_admin = self.factory.makePerson()
        getUtility(IArchivePermissionSet).newQueueAdmin(
            distribution.getArchiveByComponent('partner'),
            self.partner_queue_admin, self.partner_spr.component)

        # Create users with various pocket queue admin rights.
        self.proposed_queue_admin = self.factory.makePerson()
        getUtility(IArchivePermissionSet).newPocketQueueAdmin(
            self.main_archive, self.proposed_queue_admin,
            PackagePublishingPocket.PROPOSED)
        self.proposed_series_queue_admin = self.factory.makePerson()
        getUtility(IArchivePermissionSet).newPocketQueueAdmin(
            self.main_archive, self.proposed_series_queue_admin,
            PackagePublishingPocket.PROPOSED, distroseries=self.second_series)

        # We need to commit to ensure the changes file exists in the
        # librarian.
        transaction.commit()
        logout()

    def setupQueueView(self, request, series=None):
        """A helper to create and setup the view for testing."""
        if series is None:
            series = self.test_publisher.distroseries
        view = queryMultiAdapter((series, request), name="+queue")
        view.setupQueueList()
        view.performQueueAction()
        return view

    def assertStatus(self, package_upload_id, status):
        self.assertEqual(
            status,
            getUtility(IPackageUploadSet).get(package_upload_id).status)

    def test_main_admin_can_accept_main_upload(self):
        # A person with queue admin access for main
        # can accept uploads to the main archive.
        login_person(self.main_queue_admin)
        self.assertTrue(
            self.main_archive.canAdministerQueue(
                self.main_queue_admin, self.main_spr.component))

        package_upload_id = self.main_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        self.setupQueueView(request)
        self.assertStatus(package_upload_id, PackageUploadStatus.DONE)

    def test_main_admin_cannot_accept_partner_upload(self):
        # A person with queue admin access for main cannot necessarily
        # accept uploads to partner.
        login_person(self.main_queue_admin)
        self.assertFalse(
            self.partner_archive.canAdministerQueue(
                self.main_queue_admin, self.partner_spr.component))

        package_upload_id = self.partner_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        view = self.setupQueueView(request)

        self.assertEquals(
            html_escape(
                "FAILED: partner-upload (You have no rights to accept "
                "component(s) 'partner')"),
            view.request.response.notifications[0].message)
        self.assertStatus(package_upload_id, PackageUploadStatus.NEW)

    def test_admin_can_accept_partner_upload(self):
        # An admin can always accept packages, even for the
        # partner archive (note, this is *not* an archive admin).
        login('admin@canonical.com')

        package_upload_id = self.partner_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        self.setupQueueView(request)
        self.assertStatus(package_upload_id, PackageUploadStatus.DONE)

    def test_partner_admin_can_accept_partner_upload(self):
        # A person with queue admin access for partner
        # can accept uploads to the partner archive.
        login_person(self.partner_queue_admin)
        self.assertTrue(
            self.partner_archive.canAdministerQueue(
                self.partner_queue_admin, self.partner_spr.component))

        package_upload_id = self.partner_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        self.setupQueueView(request)
        self.assertStatus(package_upload_id, PackageUploadStatus.DONE)

    def test_partner_admin_cannot_accept_main_upload(self):
        # A person with queue admin access for partner cannot necessarily
        # accept uploads to main.
        login_person(self.partner_queue_admin)
        self.assertFalse(
            self.main_archive.canAdministerQueue(
                self.partner_queue_admin, self.main_spr.component))

        package_upload_id = self.main_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        view = self.setupQueueView(request)

        self.assertEquals(
            html_escape(
                "FAILED: main-upload (You have no rights to accept "
                "component(s) 'main')"),
            view.request.response.notifications[0].message)
        self.assertStatus(package_upload_id, PackageUploadStatus.NEW)

    def test_proposed_admin_can_accept_proposed_upload(self):
        # A person with queue admin access for proposed can accept uploads
        # to the proposed pocket for any series.
        login_person(self.proposed_queue_admin)
        self.assertTrue(
            self.main_archive.canAdministerQueue(
                self.proposed_queue_admin,
                pocket=PackagePublishingPocket.PROPOSED))
        for distroseries in self.test_publisher.distroseries.distribution:
            self.assertTrue(
                self.main_archive.canAdministerQueue(
                    self.proposed_queue_admin,
                    pocket=PackagePublishingPocket.PROPOSED,
                    distroseries=distroseries))

        for spr in (self.proposed_spr, self.proposed_series_spr):
            package_upload_id = spr.package_upload.id
            self.form['QUEUE_ID'] = [package_upload_id]
            request = LaunchpadTestRequest(form=self.form)
            request.method = 'POST'
            self.setupQueueView(request, series=spr.upload_distroseries)
            self.assertStatus(package_upload_id, PackageUploadStatus.DONE)

    def test_proposed_admin_cannot_accept_release_upload(self):
        # A person with queue admin access for proposed cannot necessarly
        # accept uploads to the release pocket.
        login_person(self.proposed_queue_admin)
        self.assertFalse(
            self.main_archive.canAdministerQueue(
                self.proposed_queue_admin,
                pocket=PackagePublishingPocket.RELEASE))

        package_upload_id = self.main_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        view = self.setupQueueView(request)

        self.assertEqual(
            html_escape(
                "FAILED: main-upload (You have no rights to accept "
                "component(s) 'main')"),
            view.request.response.notifications[0].message)
        self.assertStatus(package_upload_id, PackageUploadStatus.NEW)

    def test_proposed_series_admin_can_accept_that_series_upload(self):
        # A person with queue admin access for proposed for one series can
        # accept uploads to that series.
        login_person(self.proposed_series_queue_admin)
        self.assertTrue(
            self.main_archive.canAdministerQueue(
                self.proposed_series_queue_admin,
                pocket=PackagePublishingPocket.PROPOSED,
                distroseries=self.second_series))

        package_upload_id = self.proposed_series_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        self.setupQueueView(request, series=self.second_series)
        self.assertStatus(package_upload_id, PackageUploadStatus.DONE)

    def test_proposed_series_admin_cannot_accept_other_series_upload(self):
        # A person with queue admin access for proposed for one series
        # cannot necessarily accept uploads to other series.
        login_person(self.proposed_series_queue_admin)
        self.assertFalse(
            self.main_archive.canAdministerQueue(
                self.proposed_series_queue_admin,
                pocket=PackagePublishingPocket.PROPOSED,
                distroseries=self.test_publisher.distroseries))

        package_upload_id = self.proposed_spr.package_upload.id
        self.form['QUEUE_ID'] = [package_upload_id]
        request = LaunchpadTestRequest(form=self.form)
        request.method = 'POST'
        view = self.setupQueueView(request)

        self.assertEqual(
            "You do not have permission to act on queue items.", view.error)
        self.assertStatus(package_upload_id, PackageUploadStatus.NEW)

    def test_cannot_reject_without_comment(self):
        login_person(self.proposed_queue_admin)
        package_upload_id = self.proposed_spr.package_upload.id
        form = {
            'Reject': 'Reject',
            'QUEUE_ID': [package_upload_id]}
        request = LaunchpadTestRequest(form=form)
        request.method = 'POST'
        view = self.setupQueueView(request)
        self.assertEqual('Rejection comment required.', view.error)
        self.assertStatus(package_upload_id, PackageUploadStatus.NEW)

    def test_reject_with_comment(self):
       login_person(self.proposed_queue_admin)
       package_upload_id = self.proposed_spr.package_upload.id
       form = {
           'Reject': 'Reject',
           'rejection_comment': 'Because I can.',
           'QUEUE_ID': [package_upload_id]}
       request = LaunchpadTestRequest(form=form)
       request.method = 'POST'
       self.setupQueueView(request)
       self.assertStatus(package_upload_id, PackageUploadStatus.REJECTED)


class TestQueueItemsView(TestCaseWithFactory):
    """Unit tests for `QueueItemsView`."""

    layer = LaunchpadFunctionalLayer

    def makeView(self, distroseries, user):
        """Create a queue view."""
        return create_initialized_view(
            distroseries, name='+queue', principal=user)

    def test_view_renders_source_upload(self):
        login(ADMIN_EMAIL)
        upload = self.factory.makeSourcePackageUpload()
        queue_admin = self.factory.makeArchiveAdmin(
            upload.distroseries.main_archive)
        with person_logged_in(queue_admin):
            view = self.makeView(upload.distroseries, queue_admin)
            html_text = view()
        self.assertIn(upload.package_name, html_text)

    def test_view_renders_build_upload(self):
        login(ADMIN_EMAIL)
        upload = self.factory.makeBuildPackageUpload()
        queue_admin = self.factory.makeArchiveAdmin(
            upload.distroseries.main_archive)
        with person_logged_in(queue_admin):
            view = self.makeView(upload.distroseries, queue_admin)
            html_text = view()
        self.assertIn(upload.package_name, html_text)

    def test_view_renders_copy_upload(self):
        login(ADMIN_EMAIL)
        upload = self.factory.makeCopyJobPackageUpload()
        queue_admin = self.factory.makeArchiveAdmin(
            upload.distroseries.main_archive)
        with person_logged_in(queue_admin):
            view = self.makeView(upload.distroseries, queue_admin)
            html_text = view()
        self.assertIn(upload.package_name, html_text)
        # The details section states the sync's origin and requester.
        archive = upload.package_copy_job.source_archive
        url = canonical_url(archive.distribution, path_only_if_possible=True)
        self.assertThat(html_text, soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "link", "a", text=archive.displayname, attrs={"href": url}),
            ))
        self.assertIn(
            upload.package_copy_job.job.requester.displayname, html_text)

    def test_view_renders_copy_upload_from_private_archive(self):
        login(ADMIN_EMAIL)
        p3a = self.factory.makeArchive(private=True)
        upload = self.factory.makeCopyJobPackageUpload(source_archive=p3a)
        queue_admin = self.factory.makeArchiveAdmin(
            upload.distroseries.main_archive)
        with person_logged_in(queue_admin):
            view = self.makeView(upload.distroseries, queue_admin)
            html_text = view()
        self.assertIn(upload.package_name, html_text)
        # The details section states the sync's origin and requester.
        self.assertTextMatchesExpressionIgnoreWhitespace(
            "Sync from <span>private archive</span>,", html_text)
        self.assertIn(
            upload.package_copy_job.job.requester.displayname, html_text)

    def test_query_count(self):
        login(ADMIN_EMAIL)
        uploads = []
        sprs = []
        distroseries = self.factory.makeDistroSeries()
        dsc = self.factory.makeLibraryFileAlias(filename='foo_0.1.dsc')
        deb = self.factory.makeLibraryFileAlias(filename='foo.deb')
        transaction.commit()
        for i in range(5):
            uploads.append(self.factory.makeSourcePackageUpload(distroseries))
            sprs.append(uploads[-1].sources[0].sourcepackagerelease)
            sprs[-1].addFile(dsc)
            uploads.append(self.factory.makeCustomPackageUpload(distroseries))
            uploads.append(self.factory.makeCopyJobPackageUpload(distroseries))
            uploads.append(self.factory.makeCopyJobPackageUpload(
                distroseries, source_archive=self.factory.makeArchive()))
        self.factory.makePackageset(
            packages=(sprs[0].sourcepackagename, sprs[2].sourcepackagename,
                sprs[4].sourcepackagename),
            distroseries=distroseries)
        self.factory.makePackageset(
            packages=(sprs[1].sourcepackagename,), distroseries=distroseries)
        self.factory.makePackageset(
            packages=(sprs[3].sourcepackagename,), distroseries=distroseries)
        for i in (0, 2, 3):
            self.factory.makePackageDiff(to_source=sprs[i])
        for i in range(15):
            uploads.append(self.factory.makeBuildPackageUpload(distroseries))
            uploads[-1].builds[0].build.binarypackages[0].addFile(deb)
        queue_admin = self.factory.makeArchiveAdmin(distroseries.main_archive)
        Store.of(uploads[0]).invalidate()
        with person_logged_in(queue_admin):
            with StormStatementRecorder() as recorder:
                view = self.makeView(distroseries, queue_admin)
                view()
        self.assertThat(recorder, HasQueryCount(Equals(56)))


class TestCompletePackageUpload(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def makeCompletePackageUpload(self, upload=None, build_upload_files=None,
                                  source_upload_files=None, package_sets=None):
        if upload is None:
            upload = self.factory.makeSourcePackageUpload()
        if build_upload_files is None:
            build_upload_files = {}
        if source_upload_files is None:
            source_upload_files = {}
        if package_sets is None:
            package_sets = {}
        return CompletePackageUpload(
            upload, build_upload_files, source_upload_files, package_sets)

    def mapPackageSets(self, upload, package_sets=None):
        if package_sets is None:
            package_sets = [self.factory.makePackageset(
                distroseries=upload.distroseries)]
        spn = upload.sourcepackagerelease.sourcepackagename
        return {spn.id: package_sets}

    def test_display_package_sets_returns_source_upload_packagesets(self):
        upload = self.factory.makeSourcePackageUpload()
        package_sets = self.mapPackageSets(upload)
        complete_upload = self.makeCompletePackageUpload(
            upload, package_sets=package_sets)
        self.assertEqual(
            package_sets.values()[0][0].name,
            complete_upload.display_package_sets)

    def test_display_package_sets_returns_empty_for_other_upload(self):
        upload = self.factory.makeBuildPackageUpload()
        complete_upload = self.makeCompletePackageUpload(
            upload, package_sets=self.mapPackageSets(upload))
        self.assertEqual("", complete_upload.display_package_sets)

    def test_display_package_sets_sorts_by_name(self):
        complete_upload = self.makeCompletePackageUpload()
        distroseries = complete_upload.distroseries
        complete_upload.package_sets = [
            self.factory.makePackageset(distroseries=distroseries, name=name)
            for name in [u'ccc', u'aaa', u'bbb']]
        self.assertEqual("aaa bbb ccc", complete_upload.display_package_sets)

    def test_display_component_returns_source_upload_component_name(self):
        upload = self.factory.makeSourcePackageUpload()
        complete_upload = self.makeCompletePackageUpload(upload)
        self.assertEqual(
            upload.sourcepackagerelease.component.name.lower(),
            complete_upload.display_component)

    def test_display_component_returns_copy_job_upload_component_name(self):
        copy_job_upload = self.factory.makeCopyJobPackageUpload()
        complete_upload = self.makeCompletePackageUpload(copy_job_upload)
        self.assertEqual(
            copy_job_upload.component_name.lower(),
            complete_upload.display_component)

    def test_display_component_returns_empty_for_other_upload(self):
        complete_upload = self.makeCompletePackageUpload(
            self.factory.makeBuildPackageUpload())
        self.assertEqual('', complete_upload.display_component)

    def test_display_section_returns_source_upload_section_name(self):
        upload = self.factory.makeSourcePackageUpload()
        complete_upload = self.makeCompletePackageUpload(upload)
        self.assertEqual(
            upload.sourcepackagerelease.section.name.lower(),
            complete_upload.display_section)

    def test_display_section_returns_copy_job_upload_section_name(self):
        copy_job_upload = self.factory.makeCopyJobPackageUpload()
        complete_upload = self.makeCompletePackageUpload(copy_job_upload)
        self.assertEqual(
            copy_job_upload.section_name.lower(),
            complete_upload.display_section)

    def test_display_section_returns_empty_for_other_upload(self):
        complete_upload = self.makeCompletePackageUpload(
            self.factory.makeBuildPackageUpload())
        self.assertEqual('', complete_upload.display_section)

    def test_display_priority_returns_source_upload_priority(self):
        upload = self.factory.makeSourcePackageUpload()
        complete_upload = self.makeCompletePackageUpload(upload)
        self.assertEqual(
            upload.sourcepackagerelease.urgency.name.lower(),
            complete_upload.display_priority)

    def test_display_priority_returns_empty_for_other_upload(self):
        complete_upload = self.makeCompletePackageUpload(
            self.factory.makeBuildPackageUpload())
        self.assertEqual('', complete_upload.display_priority)

    def test_composeIcon_produces_image_tag(self):
        alt = self.factory.getUniqueString()
        icon = self.factory.getUniqueString() + ".png"
        title = self.factory.getUniqueString()
        html_text = html_escape(
            self.makeCompletePackageUpload().composeIcon(alt, icon, title))
        img = html.fromstring(html_text)
        self.assertEqual("img", img.tag)
        self.assertEqual("[%s]" % alt, img.get("alt"))
        self.assertEqual("/@@/" + icon, img.get("src"))
        self.assertEqual(title, img.get("title"))

    def test_composeIcon_title_defaults_to_alt_text(self):
        alt = self.factory.getUniqueString()
        icon = self.factory.getUniqueString() + ".png"
        html_text = html_escape(
            self.makeCompletePackageUpload().composeIcon(alt, icon))
        img = html.fromstring(html_text)
        self.assertEqual(alt, img.get("title"))

    def test_composeIcon_escapes_alt_and_title(self):
        alt = 'alt"&'
        icon = self.factory.getUniqueString() + ".png"
        title = 'title"&'
        html_text = html_escape(
            self.makeCompletePackageUpload().composeIcon(alt, icon, title))
        img = html.fromstring(html_text)
        self.assertEqual("[%s]" % alt, img.get("alt"))
        self.assertEqual(title, img.get("title"))

    def test_composeIconList_produces_icons(self):
        icons = self.makeCompletePackageUpload().composeIconList()
        self.assertNotEqual([], icons)
        self.assertEqual('img', html.fromstring(html_escape(icons[0])).tag)

    def test_composeIconList_produces_icons_conditionally(self):
        complete_upload = self.makeCompletePackageUpload()
        base_count = len(complete_upload.composeIconList())
        complete_upload.contains_build = True
        new_count = len(complete_upload.composeIconList())
        self.assertEqual(base_count + 1, new_count)

    def test_composeNameAndChangesLink_does_not_link_if_no_changes_file(self):
        upload = self.factory.makeCopyJobPackageUpload()
        complete_upload = self.makeCompletePackageUpload(upload)
        self.assertEqual(
            complete_upload.displayname,
            complete_upload.composeNameAndChangesLink())

    def test_composeNameAndChangesLink_links_to_changes_file(self):
        complete_upload = self.makeCompletePackageUpload()
        link = html.fromstring(
            html_escape(complete_upload.composeNameAndChangesLink()))
        self.assertEqual(
            complete_upload.changesfile.http_url, link.get("href"))

    def test_composeNameAndChangesLink_escapes_nonlinked_display_name(self):
        filename = 'name"&name'
        upload = self.factory.makeCustomPackageUpload(filename=filename)
        # Stop nameAndChangesLink from producing a link.
        upload.changesfile = None
        complete_upload = self.makeCompletePackageUpload(upload)
        self.assertIn(
            html_escape(filename),
            html_escape(complete_upload.composeNameAndChangesLink()))

    def test_composeNameAndChangesLink_escapes_name_in_link(self):
        filename = 'name"&name'
        upload = self.factory.makeCustomPackageUpload(filename=filename)
        complete_upload = self.makeCompletePackageUpload(upload)
        link = html.fromstring(
            html_escape(complete_upload.composeNameAndChangesLink()))
        self.assertIn(filename, link.get("title"))
        self.assertEqual(filename, link.text)

    def test_icons_and_name_composes_icons_and_link_and_archs(self):
        complete_upload = self.makeCompletePackageUpload()
        icons_and_name = html.fromstring(complete_upload.icons_and_name)
        self.assertNotEqual(None, icons_and_name.find("img"))
        self.assertNotEqual(None, icons_and_name.find("a"))
        self.assertIn(
            complete_upload.displayarchs, ' '.join(icons_and_name.itertext()))
