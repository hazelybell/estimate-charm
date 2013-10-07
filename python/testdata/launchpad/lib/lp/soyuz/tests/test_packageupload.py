# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test Build features."""

from datetime import timedelta
from urllib2 import (
    HTTPError,
    urlopen,
    )

from debian.deb822 import Changes
from lazr.restfulclient.errors import (
    BadRequest,
    Unauthorized,
    )
from testtools.matchers import Equals
import transaction
from zope.component import getUtility
from zope.schema import getFields
from zope.security.interfaces import Unauthorized as ZopeUnauthorized
from zope.security.proxy import removeSecurityProxy
from zope.testbrowser.browser import Browser
from zope.testbrowser.testing import PublisherMechanizeBrowser

from lp.archiveuploader.tests import datadir
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.job.interfaces.job import JobStatus
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.mail import stub
from lp.services.mail.sendmail import format_address_for_person
from lp.soyuz.adapters.overrides import SourceOverride
from lp.soyuz.enums import (
    PackageUploadCustomFormat,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.queue import (
    IPackageUpload,
    IPackageUploadSet,
    QueueAdminUnauthorizedError,
    QueueInconsistentStateError,
    )
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.model.packagecopyjob import IPackageCopyJobSource
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    admin_logged_in,
    api_url,
    launchpadlib_for,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import (
    HasQueryCount,
    Provides,
    )


class PackageUploadTestCase(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer
    dbuser = config.uploadqueue.dbuser

    def setUp(self):
        super(PackageUploadTestCase, self).setUp()
        self.test_publisher = SoyuzTestPublisher()

    def test_realiseUpload_for_overridden_component_archive(self):
        # If the component of an upload is overridden to 'Partner' for
        # example, then the new publishing record should be for the
        # partner archive.
        self.test_publisher.prepareBreezyAutotest()

        # Get some sample changes file content for the new upload.
        changes_file = open(
            datadir('suite/bar_1.0-1/bar_1.0-1_source.changes'))
        changes_file_content = changes_file.read()
        changes_file.close()

        main_upload_release = self.test_publisher.getPubSource(
            sourcename='main-upload', spr_only=True,
            component='main', changes_file_content=changes_file_content)
        package_upload = main_upload_release.package_upload

        self.assertEqual("primary", main_upload_release.upload_archive.name)

        # Override the upload to partner and verify the change.
        partner_component = getUtility(IComponentSet)['partner']
        main_component = getUtility(IComponentSet)['main']
        package_upload.overrideSource(
            partner_component, None, [partner_component, main_component])
        self.assertEqual(
            "partner", main_upload_release.upload_archive.name)

        # Now realise the upload and verify that the publishing is for
        # the partner archive.
        pub = package_upload.realiseUpload()[0]
        self.assertEqual("partner", pub.archive.name)

    def test_package_name_and_version(self):
        # The PackageUpload knows the name and version of the package
        # being uploaded.  Internally, it gets this information from the
        # SourcePackageRelease.
        upload = self.factory.makePackageUpload()
        spr = self.factory.makeSourcePackageRelease()
        upload.addSource(spr)
        self.assertEqual(spr.sourcepackagename.name, upload.package_name)
        self.assertEqual(spr.version, upload.package_version)
        self.assertEqual(spr.name, upload.searchable_names)
        self.assertContentEqual([spr.version], upload.searchable_versions)

    def test_publish_sets_packageupload(self):
        # Publishing a PackageUploadSource will pass itself to the source
        # publication that was created.
        upload = self.factory.makeSourcePackageUpload()
        self.factory.makeComponentSelection(
            upload.distroseries, upload.sourcepackagerelease.component)
        upload.setAccepted()
        [spph] = upload.realiseUpload()
        self.assertEqual(spph.packageupload, upload)

    def test_overrideSource_ignores_None_component_change(self):
        # overrideSource accepts None as a component; it will not object
        # based on permissions for the new component.
        upload = self.factory.makeSourcePackageUpload()
        spr = upload.sourcepackagerelease
        current_component = spr.component
        new_section = self.factory.makeSection()
        upload.overrideSource(None, new_section, [current_component])
        self.assertEqual(current_component, spr.component)
        self.assertEqual(new_section, spr.section)

    def makeSourcePackageUpload(self, pocket=None, sourcepackagename=None,
                                section_name=None, changes_dict=None):
        """Make a useful source package upload for queue tests."""
        distroseries = self.test_publisher.distroseries
        distroseries.changeslist = "autotest_changes@ubuntu.com"
        uploader = self.factory.makePerson()
        key = self.factory.makeGPGKey(owner=uploader)
        changes = Changes({"Changed-By": uploader.preferredemail.email})
        if changes_dict is not None:
            changes.update(changes_dict)
        upload = self.factory.makePackageUpload(
            archive=distroseries.main_archive, distroseries=distroseries,
            pocket=pocket, changes_file_content=changes.dump().encode("UTF-8"),
            signing_key=key)
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=sourcepackagename, distroseries=distroseries,
            component="main", section_name=section_name,
            changelog_entry="dummy")
        upload.addSource(spr)
        spr.addFile(self.factory.makeLibraryFileAlias(
            filename="%s_%s.dsc" % (spr.name, spr.version)))
        transaction.commit()
        return upload, uploader

    def makeBuildPackageUpload(self):
        """Make a useful build package upload for queue tests."""
        distroseries = self.test_publisher.distroseries
        distroseries.changeslist = "autotest_changes@ubuntu.com"
        uploader = self.factory.makePerson()
        key = self.factory.makeGPGKey(owner=uploader)
        changes = Changes({"Changed-By": uploader.preferredemail.email})
        upload = self.factory.makePackageUpload(
            archive=distroseries.main_archive, distroseries=distroseries,
            changes_file_content=changes.dump().encode("UTF-8"),
            signing_key=key)
        build = self.factory.makeBinaryPackageBuild(
            distroarchseries=self.test_publisher.breezy_autotest_i386)
        upload.addBuild(build)
        bpr = self.factory.makeBinaryPackageRelease(build=build)
        bpr.addFile(self.factory.makeLibraryFileAlias(
            filename="%s_%s_i386.deb" % (bpr.name, bpr.version)))
        transaction.commit()
        return upload, uploader

    def assertEmail(self, expected_to_addrs):
        """Pop an email from the stub queue and check its recipients."""
        _, to_addrs, _ = stub.test_emails.pop()
        self.assertEqual(expected_to_addrs, to_addrs)

    def test_acceptFromQueue_source_sends_email(self):
        # Accepting a source package sends emails to the announcement list
        # and the uploader.
        self.test_publisher.prepareBreezyAutotest()
        upload, uploader = self.makeSourcePackageUpload()
        upload.acceptFromQueue()
        self.assertEqual(2, len(stub.test_emails))
        # Emails sent are the announcement and the uploader's notification:
        self.assertEmail(["autotest_changes@ubuntu.com"])
        self.assertEmail([format_address_for_person(uploader)])

    def test_acceptFromQueue_source_backports_sends_no_announcement(self):
        # Accepting a source package into BACKPORTS does not send an
        # announcement email to the distroseries changeslist (see bug
        # #59443).  It still sends an acknowledgement to the uploader.
        self.test_publisher.prepareBreezyAutotest()
        self.test_publisher.distroseries.status = SeriesStatus.CURRENT
        upload, uploader = self.makeSourcePackageUpload(
            pocket=PackagePublishingPocket.BACKPORTS)
        upload.acceptFromQueue()
        self.assertEqual(1, len(stub.test_emails))
        # Only one email is sent, to the person in the changed-by field.  No
        # announcement email is sent.
        self.assertEmail([format_address_for_person(uploader)])

    def test_acceptFromQueue_source_translations_sends_no_email(self):
        # Accepting source packages in the "translations" section (i.e.
        # language packs) does not send any email.  See bug #57708.
        self.test_publisher.prepareBreezyAutotest()
        self.test_publisher.distroseries.status = SeriesStatus.CURRENT
        upload, _ = self.makeSourcePackageUpload(
            pocket=PackagePublishingPocket.PROPOSED,
            section_name="translations")
        upload.acceptFromQueue()
        self.assertEqual("DONE", upload.status.name)
        self.assertEqual(0, len(stub.test_emails))

    def test_acceptFromQueue_source_creates_builds(self):
        # Accepting a source package creates build records.
        self.test_publisher.prepareBreezyAutotest()
        upload, _ = self.makeSourcePackageUpload()
        upload.acceptFromQueue()
        spr = upload.sourcepackagerelease
        [build] = spr.builds
        self.assertEqual(
            "i386 build of %s %s in ubuntutest breezy-autotest RELEASE" % (
                spr.name, spr.version),
            build.title)

    def test_acceptFromQueue_source_closes_bug(self):
        # Accepting a source package closes bugs appropriately.
        self.test_publisher.prepareBreezyAutotest()

        # Upload the first version of a package.
        upload_one, _ = self.makeSourcePackageUpload()
        upload_one.setAccepted()
        upload_one.realiseUpload()
        spr = upload_one.sourcepackagerelease

        # Make a new bug task for this package.  It starts life as NEW.
        dsp = self.test_publisher.ubuntutest.getSourcePackage(spr.name)
        task = self.factory.makeBugTask(target=dsp, publish=False)
        self.assertEqual("NEW", task.status.name)

        # Upload the next version of the same package, closing this bug.
        changes = Changes({"Launchpad-Bugs-Fixed": str(task.bug.id)})
        upload_two, _ = self.makeSourcePackageUpload(
            sourcepackagename=spr.sourcepackagename, changes_dict=changes)

        # Accept the new upload.  It should reach the DONE state, and should
        # close the bug.
        upload_two.acceptFromQueue()
        self.assertEqual("DONE", upload_two.status.name)
        self.assertEqual("FIXRELEASED", task.status.name)

    def test_acceptFromQueue_binary_sends_no_email(self):
        # Accepting a binary package does not send email.
        self.test_publisher.prepareBreezyAutotest()
        upload, _ = self.makeBuildPackageUpload()
        upload.acceptFromQueue()
        self.assertEqual(0, len(stub.test_emails))

    def test_acceptFromQueue_handles_duplicates(self):
        # Duplicate queue entries are handled sensibly.
        self.test_publisher.prepareBreezyAutotest()
        distroseries = self.test_publisher.distroseries
        upload_one = self.factory.makePackageUpload(
            archive=distroseries.main_archive, distroseries=distroseries)
        upload_one.addSource(self.factory.makeSourcePackageRelease(
            sourcepackagename="cnews", distroseries=distroseries,
            component="main", version="1.0"))
        upload_two = self.factory.makePackageUpload(
            archive=distroseries.main_archive, distroseries=distroseries)
        upload_two.addSource(self.factory.makeSourcePackageRelease(
            sourcepackagename="cnews", distroseries=distroseries,
            component="main", version="1.0"))
        transaction.commit()
        upload_one.setUnapproved()
        upload_one.syncUpdate()
        upload_two.setUnapproved()
        upload_two.syncUpdate()

        # There are now duplicate uploads in UNAPPROVED.
        unapproved = distroseries.getPackageUploads(
            status=PackageUploadStatus.UNAPPROVED, name=u"cnews")
        self.assertEqual(2, unapproved.count())

        # Accepting one of them works.  (Since it's a single source upload,
        # it goes straight to DONE.)
        upload_one.acceptFromQueue()
        self.assertEqual("DONE", upload_one.status.name)
        transaction.commit()

        # Trying to accept the second fails.
        self.assertRaises(
            QueueInconsistentStateError, upload_two.acceptFromQueue)
        self.assertEqual("UNAPPROVED", upload_two.status.name)

        # Rejecting the second upload works.
        upload_two.rejectFromQueue(self.factory.makePerson())
        self.assertEqual("REJECTED", upload_two.status.name)

    def test_rejectFromQueue_source_sends_email(self):
        # Rejecting a source package sends an email to the uploader.
        self.test_publisher.prepareBreezyAutotest()
        upload, uploader = self.makeSourcePackageUpload()
        upload.rejectFromQueue(self.factory.makePerson())
        self.assertEqual(1, len(stub.test_emails))
        self.assertEmail([format_address_for_person(uploader)])

    def test_rejectFromQueue_binary_sends_email(self):
        # Rejecting a binary package sends an email to the uploader.
        self.test_publisher.prepareBreezyAutotest()
        upload, uploader = self.makeBuildPackageUpload()
        upload.rejectFromQueue(self.factory.makePerson())
        self.assertEqual(1, len(stub.test_emails))
        self.assertEmail([format_address_for_person(uploader)])

    def test_rejectFromQueue_source_translations_sends_no_email(self):
        # Rejecting a language pack sends no email.
        self.test_publisher.prepareBreezyAutotest()
        self.test_publisher.distroseries.status = SeriesStatus.CURRENT
        upload, _ = self.makeSourcePackageUpload(
            pocket=PackagePublishingPocket.PROPOSED,
            section_name="translations")
        upload.rejectFromQueue(self.factory.makePerson())
        self.assertEqual(0, len(stub.test_emails))

    def test_rejectFromQueue_source_with_reason(self):
        # Rejecting a source package with a reason includes it in the email to
        # the uploader.
        self.test_publisher.prepareBreezyAutotest()
        upload, uploader = self.makeSourcePackageUpload()
        person = self.factory.makePerson()
        upload.rejectFromQueue(user=person, comment='Because.')
        self.assertEqual(1, len(stub.test_emails))
        self.assertIn(
            'Rejected:\nRejected by %s: Because.' % person.displayname,
            stub.test_emails[0][-1])


class TestPackageUploadPrivacy(TestCaseWithFactory):
    """Test PackageUpload security."""

    layer = LaunchpadFunctionalLayer

    def test_private_archives_have_private_uploads(self):
        # Only users with access to a private archive can see uploads to it.
        owner = self.factory.makePerson()
        archive = self.factory.makeArchive(owner=owner, private=True)
        upload = self.factory.makePackageUpload(archive=archive)
        # The private archive owner can see this upload.
        with person_logged_in(owner):
            self.assertFalse(upload.contains_source)
        # But other users cannot.
        with person_logged_in(self.factory.makePerson()):
            self.assertRaises(
                ZopeUnauthorized, getattr, upload, "contains_source")


class TestPackageUploadWithPackageCopyJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer
    dbuser = config.uploadqueue.dbuser

    def makeUploadWithPackageCopyJob(self, sourcepackagename=None):
        """Create a `PackageUpload` plus attached `PlainPackageCopyJob`."""
        upload = self.factory.makeCopyJobPackageUpload(
            sourcepackagename=sourcepackagename)
        return upload, getUtility(IPackageCopyJobSource).wrap(
            upload.package_copy_job)

    def test_package_copy_job_property(self):
        # Test that we can set and get package_copy_job.
        pu, pcj = self.makeUploadWithPackageCopyJob()
        self.assertEqual(
            removeSecurityProxy(pcj).context, pu.package_copy_job)

    def test_getByPackageCopyJobIDs(self):
        # getByPackageCopyJobIDs retrieves the right PackageCopyJob.
        pu, pcj = self.makeUploadWithPackageCopyJob()
        result = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [pcj.id])
        self.assertEqual(pu, result.one())

    def test_overrideSource_with_copy_job(self):
        # The overrides should be stored in the job's metadata.
        pu, pcj = self.makeUploadWithPackageCopyJob()
        old_component = getUtility(IComponentSet)[pcj.component_name]
        component = getUtility(IComponentSet)['restricted']
        section = getUtility(ISectionSet)['games']

        expected_metadata = {}
        expected_metadata.update(pcj.metadata)
        expected_metadata.update({
            'component_override': component.name,
            'section_override': section.name,
            })

        result = pu.overrideSource(
            component, section, allowed_components=[component, old_component])

        self.assertTrue(result)
        self.assertEqual(expected_metadata, pcj.metadata)

    def test_overrideSource_checks_permission_for_old_component(self):
        pu = self.factory.makeCopyJobPackageUpload()
        only_allowed_component = self.factory.makeComponent()
        section = self.factory.makeSection()
        self.assertRaises(
            QueueAdminUnauthorizedError, pu.overrideSource,
            only_allowed_component, section, [only_allowed_component])

    def test_overrideSource_checks_permission_for_new_component(self):
        pu, pcj = self.makeUploadWithPackageCopyJob()
        current_component = getUtility(IComponentSet)[pcj.component_name]
        disallowed_component = self.factory.makeComponent()
        section = self.factory.makeSection()
        self.assertRaises(
            QueueAdminUnauthorizedError, pu.overrideSource,
            disallowed_component, section, [current_component])

    def test_overrideSource_ignores_None_component_change(self):
        # overrideSource accepts None as a component; it will not object
        # based on permissions for the new component.
        pu, pcj = self.makeUploadWithPackageCopyJob()
        current_component = getUtility(IComponentSet)[pcj.component_name]
        new_section = self.factory.makeSection()
        pu.overrideSource(None, new_section, [current_component])
        self.assertEqual(current_component.name, pcj.component_name)
        self.assertEqual(new_section.name, pcj.section_name)

    def test_acceptFromQueue_with_copy_job(self):
        # acceptFromQueue should accept the upload and resume the copy
        # job.
        pu, pcj = self.makeUploadWithPackageCopyJob()
        pu.pocket = PackagePublishingPocket.RELEASE
        self.assertEqual(PackageUploadStatus.NEW, pu.status)

        pu.acceptFromQueue()

        self.assertEqual(PackageUploadStatus.ACCEPTED, pu.status)
        self.assertEqual(JobStatus.WAITING, pcj.status)

    def test_rejectFromQueue_with_copy_job(self):
        # rejectFromQueue will reject the upload and fail the copy job.
        pu, pcj = self.makeUploadWithPackageCopyJob()

        pu.rejectFromQueue(self.factory.makePerson())

        self.assertEqual(PackageUploadStatus.REJECTED, pu.status)
        self.assertEqual(JobStatus.FAILED, pcj.status)

        # It cannot be resurrected after rejection.
        self.assertRaises(
            QueueInconsistentStateError, pu.acceptFromQueue, None)

    def test_package_name_and_version_are_as_in_job(self):
        # The PackageUpload knows the name and version of the package
        # being uploaded.  It gets this information from the
        # PlainPackageCopyJob.
        upload, job = self.makeUploadWithPackageCopyJob()
        self.assertEqual(job.package_name, upload.package_name)
        self.assertEqual(job.package_version, upload.package_version)
        self.assertEqual(job.package_name, upload.searchable_names)
        self.assertContentEqual(
            [job.package_version], upload.searchable_versions)

    def test_searchables_for_builds(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeBuildPackageUpload(distroseries)
        build = self.factory.makeBinaryPackageBuild()
        self.factory.makeBinaryPackageRelease(build=build)
        upload.addBuild(build)
        name_array = [
            b.build.binarypackages[0].name for b in upload.builds]
        name_array.extend(
            [b.build.source_package_release.name for b in upload.builds])
        names = ' '.join(sorted(name_array))
        self.assertEqual(names, upload.searchable_names)
        self.assertContentEqual(
            [b.build.binarypackages[0].version for b in upload.builds],
            upload.searchable_versions)

    def test_searchables_for_builds_duplication(self):
        distroseries = self.factory.makeDistroSeries()
        spr = self.factory.makeSourcePackageRelease()
        bpn = self.factory.makeBinaryPackageName(name=spr.name)
        binary = self.factory.makeBuildPackageUpload(
            distroseries=distroseries, binarypackagename=bpn,
            source_package_release=spr)
        self.assertEqual(spr.name, binary.searchable_names)

    def test_searchables_for_custom(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeCustomPackageUpload(distroseries)
        self.assertEqual(
            upload.searchable_names,
            upload.customfiles[0].libraryfilealias.filename)
        self.assertEqual([], upload.searchable_versions)

    def test_displayarchs_for_copy_job_is_sync(self):
        # For copy jobs, displayarchs is "sync."
        upload, job = self.makeUploadWithPackageCopyJob()
        self.assertEqual('sync', upload.displayarchs)

    def test_component_and_section_name(self):
        # An upload with a copy job takes its component and section
        # names from the job.
        spn = self.factory.makeSourcePackageName()
        upload, pcj = self.makeUploadWithPackageCopyJob(sourcepackagename=spn)
        component = self.factory.makeComponent()
        section = self.factory.makeSection()
        pcj.addSourceOverride(SourceOverride(spn, component, section))
        self.assertEqual(component.name, upload.component_name)

    def test_displayname_is_package_name(self):
        # An upload with a copy job uses the package name for its
        # display name.
        spn = self.factory.makeSourcePackageName()
        upload, job = self.makeUploadWithPackageCopyJob(sourcepackagename=spn)
        self.assertEqual(spn.name, upload.displayname)

    def test_upload_with_copy_job_has_no_source_package_release(self):
        # A copy job does not provide the upload with a
        # SourcePackageRelease.
        pu, pcj = self.makeUploadWithPackageCopyJob()
        self.assertIs(None, pu.sourcepackagerelease)


class TestPackageUploadSet(TestCaseWithFactory):
    """Unit tests for `PackageUploadSet`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestPackageUploadSet, self).setUp()
        self.upload_set = getUtility(IPackageUploadSet)

    def test_PackageUploadSet_implements_IPackageUploadSet(self):
        self.assertThat(self.upload_set, Provides(IPackageUploadSet))

    def test_getAll_returns_source_upload(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        self.assertContentEqual([upload], self.upload_set.getAll(distroseries))

    def test_getAll_returns_build_upload(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeBuildPackageUpload(distroseries)
        self.assertContentEqual([upload], self.upload_set.getAll(distroseries))

    def test_getAll_returns_custom_upload(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeCustomPackageUpload(distroseries)
        self.assertContentEqual([upload], self.upload_set.getAll(distroseries))

    def test_getAll_returns_copy_job_upload(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeCopyJobPackageUpload(distroseries)
        self.assertContentEqual([upload], self.upload_set.getAll(distroseries))

    def test_getAll_filters_by_distroseries(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeSourcePackageUpload(distroseries)
        other_series = self.factory.makeDistroSeries()
        self.assertContentEqual([], self.upload_set.getAll(other_series))

    def test_getAll_matches_created_since_date(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        yesterday = upload.date_created - timedelta(1)
        self.assertContentEqual(
            [upload],
            self.upload_set.getAll(distroseries, created_since_date=yesterday))

    def test_getAll_filters_by_created_since_date(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        tomorrow = upload.date_created + timedelta(1)
        self.assertContentEqual(
            [],
            self.upload_set.getAll(distroseries, created_since_date=tomorrow))

    def test_getAll_matches_status(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        status = upload.status
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, status=status))

    def test_getAll_filters_by_status(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeSourcePackageUpload(distroseries)
        status = PackageUploadStatus.DONE
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, status=status))

    def test_getAll_matches_pocket(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        pocket = upload.pocket
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, pocket=pocket))

    def test_getAll_filters_by_pocket(self):
        def find_different_pocket_than(pocket):
            for other_pocket in PackagePublishingPocket.items:
                if other_pocket != pocket:
                    return other_pocket

        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        pocket = find_different_pocket_than(upload.pocket)
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, pocket=pocket))

    def test_getAll_matches_custom_type(self):
        distroseries = self.factory.makeDistroSeries()
        custom_type = PackageUploadCustomFormat.DDTP_TARBALL
        upload = self.factory.makeCustomPackageUpload(
            distroseries, custom_type=custom_type)
        self.assertContentEqual(
            [upload],
            self.upload_set.getAll(distroseries, custom_type=custom_type))

    def test_getAll_filters_by_custom_type(self):
        distroseries = self.factory.makeDistroSeries()
        one_type = PackageUploadCustomFormat.DIST_UPGRADER
        other_type = PackageUploadCustomFormat.ROSETTA_TRANSLATIONS
        self.factory.makeCustomPackageUpload(
            distroseries, custom_type=one_type)
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, custom_type=other_type))

    def test_getAll_matches_source_upload_by_package_name(self):
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName()
        upload = self.factory.makeSourcePackageUpload(
            distroseries, sourcepackagename=spn)
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, name=spn.name))

    def test_getAll_filters_source_upload_by_package_name(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeSourcePackageUpload(distroseries)
        other_name = self.factory.makeSourcePackageName().name
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, name=other_name))

    def test_getAll_matches_build_upload_by_package_name(self):
        distroseries = self.factory.makeDistroSeries()
        bpn = self.factory.makeBinaryPackageName()
        upload = self.factory.makeBuildPackageUpload(
            distroseries, binarypackagename=bpn)
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, name=bpn.name))

    def test_getAll_filters_build_upload_by_package_name(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeBuildPackageUpload(distroseries)
        other_name = self.factory.makeBinaryPackageName().name
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, name=other_name))

    def test_getAll_matches_custom_upload_by_file_name(self):
        distroseries = self.factory.makeDistroSeries()
        filename = self.factory.getUniqueUnicode()
        upload = self.factory.makeCustomPackageUpload(
            distroseries, filename=filename)
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, name=filename))

    def test_getAll_filters_custom_upload_by_file_name(self):
        distroseries = self.factory.makeDistroSeries()
        filename = self.factory.getUniqueString()
        self.factory.makeCustomPackageUpload(distroseries, filename=filename)
        other_name = self.factory.getUniqueUnicode()
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, name=other_name))

    def test_getAll_matches_copy_job_upload_by_package_name(self):
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName()
        upload = self.factory.makeCopyJobPackageUpload(
            distroseries, sourcepackagename=spn)
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, name=spn.name))

    def test_getAll_filters_copy_job_upload_by_package_name(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeCopyJobPackageUpload(distroseries)
        other_name = self.factory.makeSourcePackageName().name
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, name=other_name))

    def test_getAll_without_exact_match_matches_substring_of_name(self):
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName()
        upload = self.factory.makeSourcePackageUpload(
            distroseries, sourcepackagename=spn)
        partial_name = spn.name[:-1]
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, name=partial_name))

    def test_getAll_with_exact_match_matches_exact_name(self):
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName()
        upload = self.factory.makeSourcePackageUpload(
            distroseries, sourcepackagename=spn)
        self.assertContentEqual(
            [upload],
            self.upload_set.getAll(
                distroseries, name=spn.name, exact_match=True))

    def test_getAll_with_exact_match_does_not_match_substring_of_name(self):
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName()
        self.factory.makeSourcePackageUpload(
            distroseries, sourcepackagename=spn)
        partial_name = spn.name[:-1]
        self.assertContentEqual(
            [],
            self.upload_set.getAll(
                distroseries, name=partial_name, exact_match=True))

    def test_getAll_without_exact_match_escapes_name(self):
        distroseries = self.factory.makeDistroSeries()
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, name=u"'"))

    def test_getAll_with_exact_match_escapes_name(self):
        distroseries = self.factory.makeDistroSeries()
        self.assertContentEqual(
            [], self.upload_set.getAll(
                distroseries, name=u"'", exact_match=True))

    def test_getAll_matches_source_upload_by_version(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        version = upload.displayversion
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, version=version))

    def test_getAll_filters_source_upload_by_version(self):
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeSourcePackageUpload(distroseries)
        other_version = self.factory.getUniqueUnicode()
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, version=other_version))

    def test_getAll_matches_build_upload_by_version(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeBuildPackageUpload(distroseries)
        version = upload.displayversion
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, version=version))

    def test_getAll_filters_build_upload_by_version(self):
        distroseries = self.factory.makeDistroSeries()
        other_version = self.factory.getUniqueUnicode()
        self.factory.makeBuildPackageUpload(distroseries)
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, version=other_version))

    def test_getAll_version_filter_ignores_custom_uploads(self):
        distroseries = self.factory.makeDistroSeries()
        other_version = self.factory.getUniqueUnicode()
        self.factory.makeCustomPackageUpload(distroseries)
        self.assertContentEqual(
            [], self.upload_set.getAll(distroseries, version=other_version))

    def test_getAll_version_filter_finds_copy_job_uploads(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeCopyJobPackageUpload(distroseries)
        version = upload.package_copy_job.package_version
        self.assertContentEqual(
            [upload], self.upload_set.getAll(distroseries, version=version))

    def test_getAll_with_exact_match_matches_exact_version(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        version = upload.displayversion
        self.assertContentEqual(
            [upload],
            self.upload_set.getAll(
                distroseries, version=version, exact_match=True))

    def test_getAll_w_exact_match_does_not_match_substring_of_version(self):
        distroseries = self.factory.makeDistroSeries()
        upload = self.factory.makeSourcePackageUpload(distroseries)
        version = upload.displayversion[1:-1]
        self.assertContentEqual(
            [],
            self.upload_set.getAll(
                distroseries, version=version, exact_match=True))

    def test_getAll_can_combine_version_and_name(self):
        distroseries = self.factory.makeDistroSeries()
        spn = self.factory.makeSourcePackageName()
        upload = self.factory.makeSourcePackageUpload(
            distroseries, sourcepackagename=spn)
        self.assertContentEqual(
            [upload],
            self.upload_set.getAll(
                distroseries, name=spn.name, version=upload.displayversion))

    def test_getAll_orders_in_reverse_historical_order(self):
        # The results from getAll are returned in order of creation,
        # newest to oldest, regardless of upload type.
        series = self.factory.makeDistroSeries()
        store = IStore(series)
        ordered_uploads = []
        ordered_uploads.append(self.factory.makeCopyJobPackageUpload(series))
        store.flush()
        ordered_uploads.append(self.factory.makeBuildPackageUpload(series))
        store.flush()
        ordered_uploads.append(self.factory.makeSourcePackageUpload(series))
        store.flush()
        ordered_uploads.append(self.factory.makeCustomPackageUpload(series))
        store.flush()
        ordered_uploads.append(self.factory.makeCopyJobPackageUpload(series))
        store.flush()
        ordered_uploads.append(self.factory.makeSourcePackageUpload(series))
        store.flush()
        self.assertEqual(
            list(reversed(ordered_uploads)),
            list(getUtility(IPackageUploadSet).getAll(series)))

    def test_getAll_can_preload_exported_properties(self):
        # getAll preloads everything exported on the webservice.
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeSourcePackageUpload(distroseries=distroseries)
        self.factory.makeBuildPackageUpload(distroseries=distroseries)
        self.factory.makeCustomPackageUpload(distroseries=distroseries)
        uploads = list(getUtility(IPackageUploadSet).getAll(distroseries))
        with StormStatementRecorder() as recorder:
            for name, field in getFields(IPackageUpload).items():
                if field.queryTaggedValue("lazr.restful.exported") is not None:
                    for upload in uploads:
                        getattr(upload, name)
        self.assertThat(recorder, HasQueryCount(Equals(0)))

    def test_rejectFromQueue_no_changes_file(self):
        # If the PackageUpload has no changesfile, we can still reject it.
        pu = self.factory.makePackageUpload()
        pu.changesfile = None
        pu.rejectFromQueue(self.factory.makePerson())
        self.assertEqual(PackageUploadStatus.REJECTED, pu.status)


class NonRedirectingMechanizeBrowser(PublisherMechanizeBrowser):
    """A `mechanize.Browser` that does not handle redirects."""

    default_features = [
        feature for feature in PublisherMechanizeBrowser.default_features
        if feature != "_redirect"]


class TestPackageUploadWebservice(TestCaseWithFactory):
    """Test the exposure of queue methods to the web service."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestPackageUploadWebservice, self).setUp()
        self.webservice = None
        self.distroseries = self.factory.makeDistroSeries()
        self.main = self.factory.makeComponent("main")
        self.factory.makeComponentSelection(
            distroseries=self.distroseries, component=self.main)
        self.universe = self.factory.makeComponent("universe")
        self.factory.makeComponentSelection(
            distroseries=self.distroseries, component=self.universe)

    def makeQueueAdmin(self, components):
        person = self.factory.makePerson()
        for component in components:
            getUtility(IArchivePermissionSet).newQueueAdmin(
                self.distroseries.main_archive, person, component)
        return person

    def load(self, obj, person=None):
        if person is None:
            with admin_logged_in():
                person = self.factory.makePerson()
        if self.webservice is None:
            self.webservice = launchpadlib_for("testing", person)
        with person_logged_in(person):
            url = api_url(obj)
        return self.webservice.load(url)

    def makeSourcePackageUpload(self, person, **kwargs):
        with person_logged_in(person):
            upload = self.factory.makeSourcePackageUpload(
                distroseries=self.distroseries, **kwargs)
            transaction.commit()
            spr = upload.sourcepackagerelease
            for extension in ("dsc", "tar.gz"):
                filename = "%s_%s.%s" % (spr.name, spr.version, extension)
                lfa = self.factory.makeLibraryFileAlias(filename=filename)
                spr.addFile(lfa)
        transaction.commit()
        return upload, self.load(upload, person)

    def makeCopyJobPackageUpload(self, person, **kwargs):
        with person_logged_in(person):
            upload = self.factory.makeCopyJobPackageUpload(
                distroseries=self.distroseries, **kwargs)
        transaction.commit()
        return upload, self.load(upload, person)

    def makeBinaryPackageUpload(self, person, binarypackagename=None,
                                component=None):
        with person_logged_in(person):
            upload = self.factory.makeBuildPackageUpload(
                distroseries=self.distroseries,
                binarypackagename=binarypackagename, component=component)
            self.factory.makeBinaryPackageRelease(
                build=upload.builds[0].build, component=component)
            transaction.commit()
            for build in upload.builds:
                for bpr in build.build.binarypackages:
                    filename = "%s_%s_%s.deb" % (
                        bpr.name, bpr.version, bpr.build.arch_tag)
                    lfa = self.factory.makeLibraryFileAlias(filename=filename)
                    bpr.addFile(lfa)
        transaction.commit()
        return upload, self.load(upload, person)

    def makeCustomPackageUpload(self, person, **kwargs):
        with person_logged_in(person):
            upload = self.factory.makeCustomPackageUpload(
                distroseries=self.distroseries, **kwargs)
        transaction.commit()
        return upload, self.load(upload, person)

    def makeNonRedirectingBrowser(self, person):
        # The test browser can only work with the appserver, not the
        # librarian, so follow one layer of redirection through the
        # appserver and then ask the librarian for the real file.
        browser = Browser(mech_browser=NonRedirectingMechanizeBrowser())
        browser.handleErrors = False
        with person_logged_in(person):
            browser.addHeader(
                "Authorization", "Basic %s:test" % person.preferredemail.email)
        return browser

    def assertCanOpenRedirectedUrl(self, browser, url):
        redirection = self.assertRaises(HTTPError, browser.open, url)
        self.assertEqual(303, redirection.code)
        urlopen(redirection.hdrs["Location"]).close()

    def assertRequiresEdit(self, method_name, **kwargs):
        """Test that a web service queue method requires launchpad.Edit."""
        with admin_logged_in():
            upload = self.factory.makeSourcePackageUpload()
        transaction.commit()
        ws_upload = self.load(upload)
        self.assertRaises(
            Unauthorized, getattr(ws_upload, method_name), **kwargs)

    def test_edit_permissions(self):
        self.assertRequiresEdit("acceptFromQueue")
        self.assertRequiresEdit("rejectFromQueue")
        self.assertRequiresEdit("overrideSource", new_component="main")
        self.assertRequiresEdit(
            "overrideBinaries", changes=[{"component": "main"}])

    def test_acceptFromQueue_archive_admin(self):
        # acceptFromQueue as an archive admin accepts the upload.
        person = self.makeQueueAdmin([self.main])
        upload, ws_upload = self.makeSourcePackageUpload(
            person, component=self.main)

        self.assertEqual("New", ws_upload.status)
        ws_upload.acceptFromQueue()
        self.assertEqual("Done", ws_upload.status)

    def test_double_accept_raises_BadRequest(self):
        # Trying to accept an upload twice returns 400 instead of OOPSing.
        person = self.makeQueueAdmin([self.main])
        upload, _ = self.makeSourcePackageUpload(person, component=self.main)

        with person_logged_in(person):
            upload.setAccepted()
        ws_upload = self.load(upload, person)
        self.assertEqual("Accepted", ws_upload.status)
        self.assertRaises(BadRequest, ws_upload.acceptFromQueue)

    def test_rejectFromQueue_archive_admin(self):
        # rejectFromQueue as an archive admin rejects the upload.
        person = self.makeQueueAdmin([self.main])
        upload, ws_upload = self.makeSourcePackageUpload(
            person, component=self.main)

        self.assertEqual("New", ws_upload.status)
        ws_upload.rejectFromQueue()
        self.assertEqual("Rejected", ws_upload.status)

    def test_source_info(self):
        # API clients can inspect properties of source uploads.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeSourcePackageUpload(
            person, sourcepackagename="hello", component=self.universe)

        self.assertTrue(ws_upload.contains_source)
        self.assertFalse(ws_upload.contains_build)
        self.assertFalse(ws_upload.contains_copy)
        self.assertEqual("hello", ws_upload.display_name)
        self.assertEqual("source", ws_upload.display_arches)
        self.assertEqual("hello", ws_upload.package_name)
        self.assertEqual("universe", ws_upload.component_name)
        with person_logged_in(person):
            self.assertEqual(upload.package_version, ws_upload.display_version)
            self.assertEqual(upload.package_version, ws_upload.package_version)
            self.assertEqual(upload.section_name, ws_upload.section_name)

    def test_source_fetch(self):
        # API clients can fetch files attached to source uploads.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeSourcePackageUpload(
            person, component=self.universe)

        ws_source_file_urls = ws_upload.sourceFileUrls()
        self.assertNotEqual(0, len(ws_source_file_urls))
        with person_logged_in(person):
            source_file_urls = [
                ProxiedLibraryFileAlias(file.libraryfile, upload).http_url
                for file in upload.sourcepackagerelease.files]
        self.assertContentEqual(source_file_urls, ws_source_file_urls)

        browser = self.makeNonRedirectingBrowser(person)
        for ws_source_file_url in ws_source_file_urls:
            self.assertCanOpenRedirectedUrl(browser, ws_source_file_url)
        self.assertCanOpenRedirectedUrl(browser, ws_upload.changes_file_url)

    def test_overrideSource_limited_component_permissions(self):
        # Overriding between two components requires queue admin of both.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeSourcePackageUpload(
            person, component=self.universe)

        self.assertEqual("New", ws_upload.status)
        self.assertEqual("universe", ws_upload.component_name)
        self.assertRaises(Unauthorized, ws_upload.overrideSource,
                          new_component="main")

        with admin_logged_in():
            upload.overrideSource(
                new_component=self.main,
                allowed_components=[self.main, self.universe])
        transaction.commit()
        with person_logged_in(person):
            self.assertEqual("main", upload.component_name)
        self.assertRaises(Unauthorized, ws_upload.overrideSource,
                          new_component="universe")

    def test_overrideSource_changes_properties(self):
        # Running overrideSource changes the corresponding properties.
        person = self.makeQueueAdmin([self.main, self.universe])
        upload, ws_upload = self.makeSourcePackageUpload(
            person, component=self.universe)
        with person_logged_in(person):
            new_section = self.factory.makeSection()
        transaction.commit()

        self.assertEqual("New", ws_upload.status)
        self.assertEqual("universe", ws_upload.component_name)
        self.assertNotEqual(new_section.name, ws_upload.section_name)
        ws_upload.overrideSource(
            new_component="main", new_section=new_section.name)
        self.assertEqual("main", ws_upload.component_name)
        self.assertEqual(new_section.name, ws_upload.section_name)
        ws_upload.overrideSource(new_component="universe")
        self.assertEqual("universe", ws_upload.component_name)

    def assertBinaryPropertiesMatch(self, arch, bpr, ws_binary):
        expected_binary = {
            "is_new": True,
            "name": bpr.name,
            "version": bpr.version,
            "architecture": arch,
            "component": "universe",
            "section": bpr.section.name,
            "priority": bpr.priority.name,
            }
        self.assertEqual(expected_binary, ws_binary)

    def test_binary_info(self):
        # API clients can inspect properties of binary uploads.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeBinaryPackageUpload(
            person, component=self.universe)
        with person_logged_in(person):
            arch = upload.builds[0].build.arch_tag
            bprs = upload.builds[0].build.binarypackages

        self.assertFalse(ws_upload.contains_source)
        self.assertTrue(ws_upload.contains_build)
        ws_binaries = ws_upload.getBinaryProperties()
        self.assertEqual(len(list(bprs)), len(ws_binaries))
        for bpr, ws_binary in zip(bprs, ws_binaries):
            self.assertBinaryPropertiesMatch(arch, bpr, ws_binary)

    def test_binary_fetch(self):
        # API clients can fetch files attached to binary uploads.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeBinaryPackageUpload(
            person, component=self.universe)

        ws_binary_file_urls = ws_upload.binaryFileUrls()
        self.assertNotEqual(0, len(ws_binary_file_urls))
        with person_logged_in(person):
            binary_file_urls = [
                ProxiedLibraryFileAlias(file.libraryfile, build.build).http_url
                for build in upload.builds
                for bpr in build.build.binarypackages
                for file in bpr.files]
        self.assertContentEqual(binary_file_urls, ws_binary_file_urls)

        browser = self.makeNonRedirectingBrowser(person)
        for ws_binary_file_url in ws_binary_file_urls:
            self.assertCanOpenRedirectedUrl(browser, ws_binary_file_url)
        self.assertCanOpenRedirectedUrl(browser, ws_upload.changes_file_url)

    def test_overrideBinaries_limited_component_permissions(self):
        # Overriding between two components requires queue admin of both.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeBinaryPackageUpload(
            person, binarypackagename="hello", component=self.universe)

        self.assertEqual("New", ws_upload.status)
        self.assertEqual(
            set(["universe"]),
            set(binary["component"]
                for binary in ws_upload.getBinaryProperties()))
        self.assertRaises(
            Unauthorized, ws_upload.overrideBinaries,
            changes=[{"component": "main"}])

        with admin_logged_in():
            upload.overrideBinaries(
                [{"component": self.main}],
                allowed_components=[self.main, self.universe])
        transaction.commit()

        self.assertEqual(
            set(["main"]),
            set(binary["component"]
                for binary in ws_upload.getBinaryProperties()))
        self.assertRaises(
            Unauthorized, ws_upload.overrideBinaries,
            changes=[{"component": "universe"}])

    def test_overrideBinaries_disallows_new_archive(self):
        # overrideBinaries refuses to override the component to something
        # that requires a different archive.
        partner = self.factory.makeComponent("partner")
        self.factory.makeComponentSelection(
            distroseries=self.distroseries, component=partner)
        person = self.makeQueueAdmin([self.universe, partner])
        upload, ws_upload = self.makeBinaryPackageUpload(
            person, component=self.universe)

        self.assertEqual(
            "universe", ws_upload.getBinaryProperties()[0]["component"])
        self.assertRaises(
            BadRequest, ws_upload.overrideBinaries,
            changes=[{"component": "partner"}])

    def test_overrideBinaries_without_name_changes_all_properties(self):
        # Running overrideBinaries with a change entry containing no "name"
        # field changes the corresponding properties of all binaries.
        person = self.makeQueueAdmin([self.main, self.universe])
        upload, ws_upload = self.makeBinaryPackageUpload(
            person, component=self.universe)
        with person_logged_in(person):
            new_section = self.factory.makeSection()
        transaction.commit()

        self.assertEqual("New", ws_upload.status)
        for binary in ws_upload.getBinaryProperties():
            self.assertEqual("universe", binary["component"])
            self.assertNotEqual(new_section.name, binary["section"])
            self.assertEqual("OPTIONAL", binary["priority"])
        changes = [{
            "component": "main",
            "section": new_section.name,
            "priority": "extra",
            }]
        ws_upload.overrideBinaries(changes=changes)
        for binary in ws_upload.getBinaryProperties():
            self.assertEqual("main", binary["component"])
            self.assertEqual(new_section.name, binary["section"])
            self.assertEqual("EXTRA", binary["priority"])

    def test_overrideBinaries_with_name_changes_selected_properties(self):
        # Running overrideBinaries with change entries containing "name"
        # fields changes the corresponding properties of only the selected
        # binaries.
        person = self.makeQueueAdmin([self.main, self.universe])
        upload, ws_upload = self.makeBinaryPackageUpload(
            person, component=self.universe)
        with person_logged_in(person):
            new_section = self.factory.makeSection()
        transaction.commit()

        self.assertEqual("New", ws_upload.status)
        ws_binaries = ws_upload.getBinaryProperties()
        for binary in ws_binaries:
            self.assertEqual("universe", binary["component"])
            self.assertNotEqual(new_section.name, binary["section"])
            self.assertEqual("OPTIONAL", binary["priority"])
        change_one = {
            "name": ws_binaries[0]["name"],
            "component": "main",
            "priority": "standard",
            }
        change_two = {
            "name": ws_binaries[1]["name"],
            "section": new_section.name,
            }
        ws_upload.overrideBinaries(changes=[change_one, change_two])
        ws_binaries = ws_upload.getBinaryProperties()
        self.assertEqual("main", ws_binaries[0]["component"])
        self.assertNotEqual(new_section.name, ws_binaries[0]["section"])
        self.assertEqual("STANDARD", ws_binaries[0]["priority"])
        self.assertEqual("universe", ws_binaries[1]["component"])
        self.assertEqual(new_section.name, ws_binaries[1]["section"])
        self.assertEqual("OPTIONAL", ws_binaries[1]["priority"])

    def test_custom_info(self):
        # API clients can inspect properties of custom uploads.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeCustomPackageUpload(
            person, custom_type=PackageUploadCustomFormat.DEBIAN_INSTALLER,
            filename="debian-installer-images_1.tar.gz")

        self.assertFalse(ws_upload.contains_source)
        self.assertFalse(ws_upload.contains_build)
        self.assertFalse(ws_upload.contains_copy)
        self.assertEqual(
            "debian-installer-images_1.tar.gz", ws_upload.display_name)
        self.assertEqual("-", ws_upload.display_version)
        self.assertEqual("raw-installer", ws_upload.display_arches)
        ws_binaries = ws_upload.getBinaryProperties()
        self.assertEqual(1, len(ws_binaries))
        expected_binary = {
            "name": "debian-installer-images_1.tar.gz",
            "customformat": "raw-installer",
            }
        self.assertEqual(expected_binary, ws_binaries[0])

    def test_custom_fetch(self):
        # API clients can fetch files attached to custom uploads.
        person = self.makeQueueAdmin([self.universe])
        upload, ws_upload = self.makeCustomPackageUpload(
            person, custom_type=PackageUploadCustomFormat.DEBIAN_INSTALLER,
            filename="debian-installer-images_1.tar.gz")

        ws_custom_file_urls = ws_upload.customFileUrls()
        self.assertNotEqual(0, len(ws_custom_file_urls))
        with person_logged_in(person):
            custom_file_urls = [
                ProxiedLibraryFileAlias(file.libraryfilealias, upload).http_url
                for file in upload.customfiles]
        self.assertContentEqual(custom_file_urls, ws_custom_file_urls)

        browser = self.makeNonRedirectingBrowser(person)
        for ws_custom_file_url in ws_custom_file_urls:
            self.assertCanOpenRedirectedUrl(browser, ws_custom_file_url)
        self.assertCanOpenRedirectedUrl(browser, ws_upload.changes_file_url)

    def test_binary_and_custom_info(self):
        # API clients can inspect properties of uploads containing both
        # ordinary binaries and custom upload files.
        person = self.makeQueueAdmin([self.universe])
        upload, _ = self.makeBinaryPackageUpload(
            person, binarypackagename="foo", component=self.universe)
        with person_logged_in(person):
            arch = upload.builds[0].build.arch_tag
            bprs = upload.builds[0].build.binarypackages
            version = bprs[0].version
            lfa = self.factory.makeLibraryFileAlias(
                filename="foo_%s_%s_translations.tar.gz" % (version, arch))
            upload.addCustom(
                lfa, PackageUploadCustomFormat.ROSETTA_TRANSLATIONS)
        transaction.commit()
        ws_upload = self.load(upload, person)

        self.assertFalse(ws_upload.contains_source)
        self.assertTrue(ws_upload.contains_build)
        ws_binaries = ws_upload.getBinaryProperties()
        self.assertEqual(len(list(bprs)) + 1, len(ws_binaries))
        for bpr, ws_binary in zip(bprs, ws_binaries):
            self.assertBinaryPropertiesMatch(arch, bpr, ws_binary)
        expected_custom = {
            "name": "foo_%s_%s_translations.tar.gz" % (version, arch),
            "customformat": "raw-translations",
            }
        self.assertEqual(expected_custom, ws_binaries[-1])

    def test_copy_info(self):
        # API clients can inspect properties of copies, including the source
        # archive.
        person = self.makeQueueAdmin([self.universe])
        archive = self.factory.makeArchive()
        upload, ws_upload = self.makeCopyJobPackageUpload(
            person, sourcepackagename="hello", source_archive=archive)

        self.assertFalse(ws_upload.contains_source)
        self.assertFalse(ws_upload.contains_build)
        self.assertTrue(ws_upload.contains_copy)
        self.assertEqual("hello", ws_upload.display_name)
        self.assertEqual("sync", ws_upload.display_arches)
        self.assertEqual("hello", ws_upload.package_name)
        with person_logged_in(person):
            archive_url = api_url(archive)
        self.assertEndsWith(ws_upload.copy_source_archive_link, archive_url)

    def test_getPackageUploads_query_count(self):
        person = self.makeQueueAdmin([self.universe])
        uploads = []
        for i in range(5):
            upload, _ = self.makeBinaryPackageUpload(
                person, component=self.universe)
            uploads.append(upload)
        ws_distroseries = self.load(self.distroseries, person)
        IStore(uploads[0].__class__).invalidate()
        with StormStatementRecorder() as recorder:
            ws_distroseries.getPackageUploads()
        self.assertThat(recorder, HasQueryCount(Equals(32)))
