# -*- coding: utf-8 -*-
# NOTE: The first line above must stay first; do not move the copyright
# notice to the top.  See http://www.python.org/dev/peps/pep-0263/.
#
# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for uploadprocessor.py."""

__metaclass__ = type

from email import message_from_string
import os
import shutil

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.archiveuploader.tests.test_uploadprocessor import (
    TestUploadProcessorBase,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.mail import stub
from lp.soyuz.enums import (
    PackagePublishingStatus,
    PackageUploadStatus,
    SourcePackageFormat,
    )
from lp.soyuz.interfaces.queue import NonBuildableSourceUploadError
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.component import Component
from lp.soyuz.model.publishing import BinaryPackagePublishingHistory
from lp.soyuz.tests.fakepackager import FakePackager
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing.dbuser import switch_dbuser


class TestPPAUploadProcessorBase(TestUploadProcessorBase):
    """Help class for functional tests for uploadprocessor.py and PPA."""

    def setUp(self):
        """Setup infrastructure for PPA tests.

        Additionally to the TestUploadProcessorBase.setUp, set 'breezy'
        distroseries and an new uploadprocessor instance.
        """
        super(TestPPAUploadProcessorBase, self).setUp()
        self.build_uploadprocessor = self.getUploadProcessor(
            self.layer.txn, builds=True)
        self.ubuntu = getUtility(IDistributionSet).getByName('ubuntu')

        # create name16 PPA
        self.name16 = getUtility(IPersonSet).getByName("name16")
        self.name16_ppa = self.makeArchive(self.name16)
        # Extra setup for breezy and allowing PPA builds on breezy/i386.
        self.setupBreezy()
        self.breezy['i386'].supports_virtualized = True
        transaction.commit()

        # Set up the uploadprocessor with appropriate options and logger
        self.options.context = 'insecure'
        self.uploadprocessor = self.getUploadProcessor(self.layer.txn)

    def makeArchive(self, owner):
        return self.factory.makeArchive(owner=owner, name='ppa')

    def assertEmail(self, contents=None, recipients=None, ppa_header='name16'):
        """Check email last upload notification attributes.

        :param: contents: can be a list of one or more lines, if passed
            they will be checked against the lines in Subject + Body.
        :param: recipients: can be a list of recipients lines, it defaults
            to 'Foo Bar <foo.bar@canonical.com>' (name16 account) and
            should match the email To: header content.
        :param: ppa_header: is the content of the 'X-Launchpad-PPA' header,
            it defaults to 'name16' and should be explicitly set to None for
            non-PPA or rejection notifications.
        """
        if not recipients:
            recipients = [self.name16_recipient]

        if not contents:
            contents = []

        queue_size = len(stub.test_emails)
        messages = "\n".join(m for f, t, m in stub.test_emails)
        self.assertEqual(
            queue_size, 1, 'Unexpected number of emails sent: %s\n%s'
            % (queue_size, messages))

        from_addr, to_addrs, raw_msg = stub.test_emails.pop()
        msg = message_from_string(raw_msg)

        # This is now a MIMEMultipart message.
        body = msg.get_payload(0)
        body = body.get_payload(decode=True)

        clean_recipients = [r.strip() for r in to_addrs]
        for recipient in list(recipients):
            self.assertTrue(
                recipient in clean_recipients,
                "%s not in %s" % (recipient, clean_recipients))
        self.assertEqual(
            len(recipients), len(clean_recipients),
            "Email recipients do not match exactly. Expected %s, got %s" %
                (recipients, clean_recipients))

        subject = "Subject: %s\n" % msg['Subject']
        body = subject + body

        for content in list(contents):
            self.assertIn(content, body)

        if ppa_header is not None:
            self.assertIn('X-Launchpad-PPA', msg.keys())
            self.assertEqual(msg['X-Launchpad-PPA'], ppa_header)

    def checkFilesRestrictedInLibrarian(self, queue_item, condition):
        """Check the libraryfilealias restricted flag.

        For the files associated with the queue_item, check that the
        libraryfilealiases' restricted flags are the same as 'condition'.
        """
        self.assertEqual(queue_item.changesfile.restricted, condition)

        for source in queue_item.sources:
            for source_file in source.sourcepackagerelease.files:
                self.assertEqual(
                    source_file.libraryfile.restricted, condition)

        for build in queue_item.builds:
            for binarypackage in build.build.binarypackages:
                for binary_file in binarypackage.files:
                    self.assertEqual(
                        binary_file.libraryfile.restricted, condition)

        for custom in queue_item.customfiles:
            custom_file = custom.libraryfilealias
            self.assertEqual(custom_file.restricted, condition)


class TestPPAUploadProcessor(TestPPAUploadProcessorBase):
    """Functional tests for uploadprocessor.py in PPA operation."""

    def testUploadToPPA(self):
        """Upload to a PPA gets there.

        Email announcement is sent and package is on queue DONE even if
        the source is NEW (PPA Auto-Approves everything), so PPA uploads
        will immediately result in a PENDING source publishing record (
        thus visible in the UI) and a NEEDSBUILD build record ready to be
        dispatched.

        Also test IDistribution.getPendingPublicationPPAs() and check if
        it returns the just-modified archive.
        """
        #
        # Step 1: Upload the source bar_1.0-1, start a new source series
        # Ensure the 'new' source is auto-accepted, auto-published in
        # 'main' component and the PPA in question is 'pending-publication'.
        #
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.DONE, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)

        self.assertEqual(queue_item.archive, self.name16.archive)
        self.assertEqual(queue_item.pocket, PackagePublishingPocket.RELEASE)

        # The changes file and the source's files must all be in the non-
        # restricted librarian as this is not a private PPA.
        self.checkFilesRestrictedInLibrarian(queue_item, False)

        pending_ppas = self.breezy.distribution.getPendingPublicationPPAs()
        self.assertEqual(pending_ppas.count(), 1)
        self.assertEqual(pending_ppas[0], self.name16.archive)

        pub_bar = self.name16.archive.getPublishedSources(name=u'bar').one()

        self.assertEqual(pub_bar.sourcepackagerelease.version, u'1.0-1')
        self.assertEqual(pub_bar.status, PackagePublishingStatus.PENDING)
        self.assertEqual(pub_bar.component.name, 'main')

        [build] = self.name16.archive.getBuildRecords(name=u'bar')
        self.assertEqual(
            build.title, 'i386 build of bar 1.0-1 in ubuntu breezy RELEASE')
        self.assertEqual(build.status.name, 'NEEDSBUILD')
        self.assertNotEqual(0, build.buildqueue_record.lastscore)

        #
        # Step 2: Upload a new version of bar to component universe (see
        # changesfile encoded in the upload notification). It should be
        # auto-accepted, auto-published and have its component overridden
        # to 'main' in the publishing record.
        #
        upload_dir = self.queueUpload("bar_1.0-10", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        pub_sources = self.name16.archive.getPublishedSources(name=u'bar')
        [pub_bar_10, pub_bar] = pub_sources

        self.assertEqual(pub_bar_10.sourcepackagerelease.version, u'1.0-10')
        self.assertEqual(pub_bar_10.status, PackagePublishingStatus.PENDING)
        self.assertEqual(pub_bar_10.component.name, 'main')

        [build, build_old] = self.name16.archive.getBuildRecords(name=u'bar')
        self.assertEqual(
            build.title, 'i386 build of bar 1.0-10 in ubuntu breezy RELEASE')
        self.assertEqual(build.status.name, 'NEEDSBUILD')
        self.assertNotEqual(0, build.buildqueue_record.lastscore)

        #
        # Step 3: Check if a lower version upload gets rejected and the
        # notification points to the right ancestry.
        #
        upload_dir = self.queueUpload("bar_1.0-2", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.rejection_message,
            u'bar_1.0-2.dsc: Version older than that in the archive. '
            u'1.0-2 <= 1.0-10')

    def testNamedPPAUploadDefault(self):
        """Test PPA uploads to the default PPA."""
        # Upload to the default PPA, using the named-ppa path syntax.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ppa/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        queue_root = self.uploadprocessor.last_processed_upload.queue_root
        self.assertEqual(queue_root.archive, self.name16.archive)
        self.assertEqual(queue_root.status, PackageUploadStatus.DONE)
        self.assertEqual(queue_root.distroseries.name, "breezy")

        # Subject and PPA emails header contain the owner name since
        # it's the default PPA.
        contents = [
            "Subject: [PPA name16] [ubuntu/breezy] bar 1.0-1 (Accepted)"]
        self.assertEmail(contents, ppa_header='name16')

    def testNamedPPAUploadNonDefault(self):
        """Test PPA uploads to a named PPA."""
        other_ppa = self.factory.makeArchive(owner=self.name16, name='testing')

        # Upload to a named PPA.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/testing/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        queue_root = self.uploadprocessor.last_processed_upload.queue_root
        self.assertEqual(queue_root.archive, other_ppa)
        self.assertEqual(queue_root.status, PackageUploadStatus.DONE)
        self.assertEqual(queue_root.distroseries.name, "breezy")

        # Subject and PPA email-header are specific for this named-ppa.
        contents = [
            "Subject: [PPA name16-testing] [ubuntu/breezy] bar 1.0-1 "
                "(Accepted)"]
        self.assertEmail(contents, ppa_header='name16-testing')

    def testNamedPPAUploadWithSeries(self):
        """Test PPA uploads to a named PPA location and with a distroseries.

        As per testNamedPPAUpload above, but we override the distroseries.
        """
        # The 'bar' package already targets 'breezy' as can be seen from
        # the test above, so we'll set up a new distroseries called
        # farty and override to use that.
        self.setupBreezy(name="farty")
        # Allow PPA builds.
        self.breezy['i386'].supports_virtualized = True
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ppa/ubuntu/farty")
        self.processUpload(self.uploadprocessor, upload_dir)

        queue_root = self.uploadprocessor.last_processed_upload.queue_root
        self.assertEqual(queue_root.status, PackageUploadStatus.DONE)
        self.assertEqual(queue_root.distroseries.name, "farty")

    def testPPAPublisherOverrides(self):
        """Check that PPA components override to main at publishing time,

        To preserve the original upload data, PPA uploads are not overridden
        until they are published.  This means that the SourcePackageRelease
        and BinaryPackageRelease keep the uploaded data, but the publishing
        tables have the overridden data.
        """
        # bar_1.0-1_universe is targeted to universe.
        upload_dir = self.queueUpload("bar_1.0-1_universe", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)
        # Consume the test email so the assertion futher down does not fail.
        _from_addr, _to_addrs, _raw_msg = stub.test_emails.pop()

        # The SourcePackageRelease still has a component of universe:
        pub_foo = self.name16.archive.getPublishedSources(name=u"bar").one()
        self.assertEqual(
            pub_foo.sourcepackagerelease.component.name, "universe")

        # But the publishing record has main:
        self.assertEqual(pub_foo.component.name, 'main')

        # Continue with a binary upload:
        [build] = self.name16.archive.getBuildRecords(name=u"bar")
        self.options.context = 'buildd'
        upload_dir = self.queueUpload(
            "bar_1.0-1_binary_universe", "~name16/ubuntu")
        self.processUpload(
            self.build_uploadprocessor, upload_dir, build=build)

        # No mails are sent for successful binary uploads.
        self.assertEqual(len(stub.test_emails), 0,
                         "Unexpected email generated on binary upload.")

        # Publish the binary.
        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)
        self.switchToAdmin()
        queue_item.realiseUpload()
        self.switchToUploader()

        for binary_package in build.binarypackages:
            self.assertEqual(binary_package.component.name, "universe")
            [binary_pub] = BinaryPackagePublishingHistory.selectBy(
                binarypackagerelease=binary_package,
                archive=self.name16.archive)
            self.assertEqual(binary_pub.component.name, "main")

    def testPPABinaryUploads(self):
        """Check the usual binary upload life-cycle for PPAs."""
        # Source upload.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Source publication and build record for breezy-i386
        # distroarchseries were created as expected. The source is ready
        # to receive the binary upload.
        pub_bar = self.name16.archive.getPublishedSources(name=u'bar').one()
        self.assertEqual(pub_bar.sourcepackagerelease.version, u'1.0-1')
        self.assertEqual(pub_bar.status, PackagePublishingStatus.PENDING)
        self.assertEqual(pub_bar.component.name, 'main')

        [build] = self.name16.archive.getBuildRecords(name=u'bar')
        self.assertEqual(
            build.title, 'i386 build of bar 1.0-1 in ubuntu breezy RELEASE')
        self.assertEqual(build.status.name, 'NEEDSBUILD')
        self.assertNotEqual(0, build.buildqueue_record.lastscore)

        # Binary upload to the just-created build record.
        self.options.context = 'buildd'
        upload_dir = self.queueUpload("bar_1.0-1_binary", "~name16/ubuntu")
        self.processUpload(
            self.build_uploadprocessor, upload_dir, build=build)

        # The binary upload was accepted and it's waiting in the queue.
        queue_items = self.breezy.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)
        self.assertEqual(queue_items.count(), 1)

        # All the files associated with this binary upload must be in the
        # non-restricted librarian as the PPA is not private.
        [queue_item] = queue_items
        self.checkFilesRestrictedInLibrarian(queue_item, False)

    def testNamedPPABinaryUploads(self):
        """Check the usual binary upload life-cycle for named PPAs."""
        # Source upload.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ppa/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        queue_root = self.uploadprocessor.last_processed_upload.queue_root
        self.assertEqual(queue_root.archive, self.name16.archive)
        self.assertEqual(queue_root.status, PackageUploadStatus.DONE)
        self.assertEqual(queue_root.distroseries.name, "breezy")

    def testPPACopiedSources(self):
        """Check PPA binary uploads for copied sources."""
        # Source upload to name16 PPA.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Copy source uploaded to name16 PPA to cprov's PPA.
        name16_pub_bar = self.name16.archive.getPublishedSources(
            name=u'bar').one()
        cprov = getUtility(IPersonSet).getByName("cprov")
        cprov_pub_bar = name16_pub_bar.copyTo(
            self.breezy, PackagePublishingPocket.RELEASE, cprov.archive)
        self.assertEqual(
            cprov_pub_bar.sourcepackagerelease.upload_archive.displayname,
            'PPA for Foo Bar')

        # Create a build record for source bar for breezy-i386
        # distroarchseries in cprov PPA.
        build_bar_i386 = cprov_pub_bar.sourcepackagerelease.createBuild(
            self.breezy['i386'], PackagePublishingPocket.RELEASE,
            cprov.archive)

        # Binary upload to the just-created build record.
        self.options.context = 'buildd'
        upload_dir = self.queueUpload("bar_1.0-1_binary", "~cprov/ubuntu")
        self.processUpload(
            self.build_uploadprocessor, upload_dir, build=build_bar_i386)

        # The binary upload was accepted and it's waiting in the queue.
        queue_items = self.breezy.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=cprov.archive)
        self.assertEqual(queue_items.count(), 1)

    def testUploadDoesNotEmailMaintainerOrChangedBy(self):
        """PPA uploads must not email the maintainer or changed-by person.

        The package metadata must not influence the email addresses,
        it's the uploader only who gets emailed.
        """
        upload_dir = self.queueUpload(
            "bar_1.0-1_valid_maintainer", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        # name16 is Foo Bar, who signed the upload.  The package that was
        # uploaded also contains two other valid (in sampledata) email
        # addresses for maintainer and changed-by which must be ignored.
        self.assertEmail()

    def testUploadSendsEmailToPeopleInArchivePermissions(self):
        """PPA uploads result in notifications to ArchivePermission uploaders.

        Anyone listed as an uploader in ArchivePermissions will automatically
        get an upload notification email.

        See https://bugs.launchpad.net/soyuz/+bug/397077
        """
        # Create the extra permissions. We're making an extra team and
        # adding it to cprov's upload permission, plus name12.
        self.switchToAdmin()
        cprov = getUtility(IPersonSet).getByName("cprov")
        email = "contact@example.com"
        name = "Team"
        team = self.factory.makeTeam(email=email, displayname=name)
        transaction.commit()
        name12 = getUtility(IPersonSet).getByName("name12")
        cprov.archive.newComponentUploader(name12, "main")
        cprov.archive.newComponentUploader(team, "main")
        self.switchToUploader()

        # Process the upload.
        upload_dir = self.queueUpload("bar_1.0-1", "~cprov/ppa/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        name12_email = "%s <%s>" % (
            name12.displayname, name12.preferredemail.email)
        team_email = "%s <%s>" % (team.displayname, team.preferredemail.email)

        # We expect the recipients to be:
        #  - the package signer (name15),
        #  - the team in the extra permissions,
        #  - name12 who is in the extra permissions.
        expected_recipients = (
            self.name16_recipient, name12_email, team_email)
        self.assertEmail(ppa_header="cprov", recipients=expected_recipients)

    def testPPADistroSeriesOverrides(self):
        """It's possible to override target distroseries of PPA uploads.

        Similar to usual PPA uploads:

         * Email notification is sent
         * The upload is auto-accepted in the overridden target distroseries.
         * The modified PPA is found by getPendingPublicationPPA() lookup.
        """
        self.switchToAdmin()
        hoary = self.ubuntu['hoary']
        fake_chroot = self.addMockFile('fake_chroot.tar.gz')
        hoary['i386'].addOrUpdateChroot(fake_chroot)
        self.switchToUploader()

        upload_dir = self.queueUpload(
            "bar_1.0-1", "~name16/ubuntu/hoary")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        [queue_item] = hoary.getPackageUploads(
            status=PackageUploadStatus.DONE, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)

        self.assertEqual(queue_item.archive, self.name16.archive)
        self.assertEqual(
            queue_item.pocket, PackagePublishingPocket.RELEASE)

        pending_ppas = self.ubuntu.getPendingPublicationPPAs()
        self.assertEqual(pending_ppas.count(), 1)
        self.assertEqual(pending_ppas[0], self.name16.archive)

    def testUploadToTeamPPA(self):
        """Upload to a team PPA also gets there.

        See testUploadToPPA.
        """
        ubuntu_team = getUtility(IPersonSet).getByName("ubuntu-team")
        self.makeArchive(owner=ubuntu_team)
        transaction.commit()

        upload_dir = self.queueUpload("bar_1.0-1", "~ubuntu-team/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        queue_items = self.breezy.getPackageUploads(
            status=PackageUploadStatus.DONE, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=ubuntu_team.archive)
        self.assertEqual(queue_items.count(), 1)

        pending_ppas = self.ubuntu.getPendingPublicationPPAs()
        self.assertEqual(pending_ppas.count(), 1)
        self.assertEqual(pending_ppas[0], ubuntu_team.archive)

        [build] = ubuntu_team.archive.getBuildRecords(name=u'bar')
        self.assertEqual(
            build.title, 'i386 build of bar 1.0-1 in ubuntu breezy RELEASE')
        self.assertEqual(build.status.name, 'NEEDSBUILD')
        self.assertNotEqual(0, build.buildqueue_record.lastscore)

    def testNotMemberUploadToTeamPPA(self):
        """Upload to a team PPA is rejected when the uploader is not member.

        Also test IArchiveSet.getPendingPublicationPPAs(), no archives should
        be returned since nothing was accepted.
        """
        ubuntu_translators = getUtility(IPersonSet).getByName(
            "ubuntu-translators")
        self.makeArchive(owner=ubuntu_translators)
        transaction.commit()

        upload_dir = self.queueUpload(
            "bar_1.0-1", "~ubuntu-translators/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        pending_ppas = self.ubuntu.getPendingPublicationPPAs()
        self.assertEqual(pending_ppas.count(), 0)

    def testUploadToSomeoneElsePPA(self):
        """Upload to a someone else's PPA gets rejected."""
        kinnison = getUtility(IPersonSet).getByName("kinnison")
        self.makeArchive(owner=kinnison)
        transaction.commit()

        upload_dir = self.queueUpload("bar_1.0-1", "~kinnison/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.rejection_message,
            "Signer has no upload rights to this PPA.")

    def testPPAPartnerUpload(self):
        """Upload a partner package to a PPA and ensure it's not rejected."""
        upload_dir = self.queueUpload("foocomm_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        # Check it's been successfully accepted.
        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # We rely on the fact that the component on the source package
        # release is unmodified, only the publishing component is
        # changed to 'main'.  This allows the package to get copied to
        # the main archive later where it would be published using the
        # source's component if the standard auto-overrides don't match
        # an existing publication.
        pub_foocomm = self.name16.archive.getPublishedSources(
            name=u'foocomm').one()
        self.assertEqual(
            pub_foocomm.sourcepackagerelease.component.name, 'partner')
        self.assertEqual(pub_foocomm.component.name, 'main')

    def testMixedUpload(self):
        """Mixed PPA uploads are rejected with a appropriate message."""
        upload_dir = self.queueUpload(
            "bar_1.0-1-mixed", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertIn(
            'Source/binary (i.e. mixed) uploads are not allowed.',
            self.uploadprocessor.last_processed_upload.rejection_message)

    def testPGPSignatureNotPreserved(self):
        """PGP signatures should be removed from PPA .changes files.

        Email notifications and the librarian file for .changes file should
        both have the PGP signature removed.
        """
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        self.PGPSignatureNotPreserved(archive=self.name16.archive)

    def doCustomUploadToPPA(self):
        """Helper method to do a custom upload to a PPA.

        :return: The queue items that were uploaded.
        """
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        [build] = self.name16.archive.getBuildRecords(name=u"bar")

        test_files_dir = os.path.join(
            config.root, "lib/lp/archiveuploader/tests/data/")
        self.options.context = "buildd"
        upload_dir = self.queueUpload(
            "debian-installer", "~name16/ubuntu/breezy",
            test_files_dir=test_files_dir)
        self.processUpload(self.build_uploadprocessor, upload_dir, build=build)

        [queue_item] = self.breezy.getPackageUploads(
            name=u"debian-installer", status=PackageUploadStatus.ACCEPTED,
            archive=self.name16.archive)
        return queue_item

    def testCustomUploadToPPA(self):
        """Test a custom upload to a PPA.

        For now, we just test that the right librarian is used as all
        of the existing custom upload tests use doc/distroseriesqueue-*.
        """
        queue_item = self.doCustomUploadToPPA()
        self.checkFilesRestrictedInLibrarian(queue_item, False)

    def testCustomUploadToPrivatePPA(self):
        """Test a custom upload to a private PPA.

        Make sure that the files are placed in the restricted librarian.
        """
        self.name16.archive.buildd_secret = "secret"
        self.name16.archive.private = True
        queue_item = self.doCustomUploadToPPA()
        self.checkFilesRestrictedInLibrarian(queue_item, True)

    def testUploadToPrivatePPA(self):
        """Test a source and binary upload to a private PPA.

        Make sure that the files are placed in the restricted librarian.
        """
        self.name16.archive.buildd_secret = "secret"
        self.name16.archive.private = True

        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.DONE, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)

        self.checkFilesRestrictedInLibrarian(queue_item, True)

        # Now that we have source uploaded, we can upload a build.
        [build] = self.name16.archive.getBuildRecords(name=u'bar')
        self.options.context = 'buildd'
        upload_dir = self.queueUpload("bar_1.0-1_binary", "~name16/ubuntu")
        self.processUpload(
            self.build_uploadprocessor, upload_dir, build=build)

        # The binary upload was accepted and it's waiting in the queue.
        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)

        # All the files associated with this binary upload must be in the
        # restricted librarian as the PPA is private.
        self.checkFilesRestrictedInLibrarian(queue_item, True)

    def testPPAInvalidComponentUpload(self):
        """Upload source and binary packages with invalid components.

        Components invalid in the distroseries should be ignored since
        PPAs are always published in "main".
        """
        # The component contrib does not exist in the sample data, so
        # add it here.
        Component(name='contrib')

        # Upload a source package first.
        upload_dir = self.queueUpload(
            "bar_1.0-1_contrib_component", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.DONE, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)

        # The upload was accepted despite the fact that it does
        # not have a valid component:
        self.assertTrue(
            queue_item.sourcepackagerelease.component not in
            self.breezy.upload_components)

        # Binary uploads should exhibit the same behaviour:
        [build] = self.name16.archive.getBuildRecords(name=u"bar")
        self.options.context = 'buildd'
        upload_dir = self.queueUpload(
            "bar_1.0-1_contrib_binary", "~name16/ubuntu")
        self.processUpload(
            self.build_uploadprocessor, upload_dir, build=build)
        queue_items = self.breezy.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)

        # The binary is accepted despite the fact that it does not have
        # a valid component:
        self.assertEqual(queue_items.count(), 1)
        [queue_item] = queue_items
        [build] = queue_item.builds
        for binary in build.build.binarypackages:
            self.assertTrue(
                binary.component not in self.breezy.upload_components)

    def testPPAUploadResultingInNoBuilds(self):
        """Source uploads resulting in no builds are rejected.

        If a PPA source upload results in no builds, it will be rejected.

        It usually happens for sources targeted to architectures not
        supported in the PPA subsystem.

        This way we don't create false expectations accepting sources that
        won't be ever built.
        """
        # First upload gets in because breezy/i386 is supported in PPA.
        packager = FakePackager(
            'biscuit', '1.0', 'foo.bar@canonical.com-passwordless.sec')
        packager.buildUpstream(suite=self.breezy.name, arch="i386")
        packager.buildSource()
        biscuit_pub = packager.uploadSourceVersion(
            '1.0-1', archive=self.name16.archive)
        self.assertEqual(biscuit_pub.status, PackagePublishingStatus.PENDING)

        # Remove breezy/i386 PPA support.
        self.switchToAdmin()
        self.breezy['i386'].supports_virtualized = False
        self.switchToUploader()

        # Next version can't be accepted because it can't be built.
        packager.buildVersion('1.0-2', suite=self.breezy.name, arch="i386")
        packager.buildSource()
        upload = packager.uploadSourceVersion(
            '1.0-2', archive=self.name16.archive, auto_accept=False)

        error = self.assertRaisesAndReturnError(
            NonBuildableSourceUploadError, upload.storeObjectsInDatabase)
        self.assertEqual(
            str(error),
            "Cannot build any of the architectures requested: i386")

    def testUploadPathErrorIntendedForHumans(self):
        # PPA upload path errors are augmented with documentation
        # references and get included in the rejection email along
        # with a reference to the 'launchpad-users' mailinglist and
        # the reason why the message was sent to the current
        # recipients.
        upload_dir = self.queueUpload("bar_1.0-1", "~boing/ppa")
        self.processUpload(self.uploadprocessor, upload_dir)
        rejection_message = (
            self.uploadprocessor.last_processed_upload.rejection_message)
        self.assertEqual(
            ["Launchpad failed to process the upload path '~boing/ppa':",
             '',
             "Could not find person or team named 'boing'.",
             '',
             'It is likely that you have a configuration problem with '
                 'dput/dupload.',
             'Please check the documentation at '
                 'https://help.launchpad.net/Packaging/PPA#Uploading '
                 'and update your configuration.',
             '',
             'Further error processing not possible because of a critical '
                 'previous error.'], rejection_message.splitlines())

        contents = [
            "Subject: [PPA cprov] bar_1.0-1_source.changes rejected",
            "Could not find person or team named 'boing'",
            "https://help.launchpad.net/Packaging/PPA#Uploading",
            "If you don't understand why your files were rejected please "
                "send an email",
            ("to %s for help (requires membership)."
             % config.launchpad.users_address),
            "You are receiving this email because you are the uploader "
                "of the above",
            "PPA package."]
        self.assertEmail(contents, ppa_header=None)


class TestPPAUploadProcessorFileLookups(TestPPAUploadProcessorBase):
    """Functional test for uploadprocessor.py file-lookups in PPA."""
    # XXX cprov 20071204: the DSCFile tests are not yet implemented, this
    # issue should be addressed by bug #106084, while implementing those
    # tests we should revisit this test-suite checking if we have a
    # satisfactory coverage.

    def uploadNewBarToUbuntu(self):
        """Upload a 'bar' source containing a unseen orig.tar.gz in ubuntu.

        Accept and publish the NEW source, so it becomes available to
        the rest of the system.
        """
        upload_dir = self.queueUpload("bar_1.0-1")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.NEW)

        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.NEW, name=u"bar",
            version=u"1.0-1", exact_match=True)
        queue_item.setAccepted()
        queue_item.realiseUpload()
        transaction.commit()

    def uploadHigherBarToUbuntu(self):
        """Upload the same higher version of 'bar' to the ubuntu.

        We expect the official orig.tar.gz to be already available in the
        system.
        """
        try:
            self.ubuntu.main_archive.getFileByName('bar_1.0.orig.tar.gz')
        except NotFoundError:
            self.fail('bar_1.0.orig.tar.gz is not yet published.')

        # Please note: this upload goes to the Ubuntu main archive.
        upload_dir = self.queueUpload("bar_1.0-10")
        self.processUpload(self.uploadprocessor, upload_dir)
        # Discard the announcement email and check the acceptance message
        # content.
        stub.test_emails.pop()

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

    def testPPAReusingOrigFromUbuntu(self):
        """Official 'orig.tar.gz' can be reused for PPA uploads."""
        # Make the official bar orig.tar.gz available in the system.
        self.uploadNewBarToUbuntu()

        # Please note: the upload goes to the PPA.
        # Upload a higher version of 'bar' to a PPA that relies on the
        # availability of orig.tar.gz published in ubuntu.
        upload_dir = self.queueUpload("bar_1.0-10", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Cleanup queue directory in order to re-upload the same source.
        shutil.rmtree(
            os.path.join(self.queue_folder, 'incoming', 'bar_1.0-10'))

        # Upload a higher version of bar that relies on the official
        # orig.tar.gz availability.
        self.uploadHigherBarToUbuntu()

    def testNoPublishingOverrides(self):
        """Make sure publishing overrides are not applied for PPA uploads."""
        # Create a fake "bar" package and publish it in section "web".
        self.switchToAdmin()
        publisher = SoyuzTestPublisher()
        publisher.prepareBreezyAutotest()
        publisher.getPubSource(
            sourcename="bar", version="1.0-1", section="web",
            archive=self.name16_ppa, distroseries=self.breezy,
            status=PackagePublishingStatus.PUBLISHED)
        self.switchToUploader()

        # Now upload bar 1.0-3, which has section "devel".
        # (I am using this version because it's got a .orig required for
        # the upload).
        upload_dir = self.queueUpload("bar_1.0-3_valid", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # The published section should be "devel" and not "web".
        pub_sources = self.name16.archive.getPublishedSources(name=u'bar')
        [pub_bar2, pub_bar1] = pub_sources

        section = pub_bar2.section.name
        self.assertEqual(
            section, 'devel',
            "Expected a section of 'devel', actually got '%s'" % section)

    def testPPAOrigGetsPrecedence(self):
        """When available, the PPA overridden 'orig.tar.gz' gets precedence.

        This test is required to guarantee the system will continue to cope
        with possibly different 'orig.tar.gz' contents already uploaded to
        PPAs.
        """
        # Upload a initial version of 'bar' source introducing a 'orig.tar.gz'
        # different than the official one. It emulates the origs already
        # uploaded to PPAs before bug #139619 got fixed.
        # It's only possible to do such thing in the current codeline when
        # the *tainted* upload reaches the system before the 'official' orig
        # is published in the primary archive, if uploaded after the official
        # orig is published in primary archive it would fail due to different
        # file contents.
        upload_dir = self.queueUpload("bar_1.0-1-ppa-orig", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Make the official bar orig.tar.gz available in the system.
        self.uploadNewBarToUbuntu()

        # Please note: the upload goes to the PPA.
        # Upload a higher version of 'bar' to a PPA that relies on the
        # availability of orig.tar.gz published in the PPA itself.
        upload_dir = self.queueUpload("bar_1.0-10-ppa-orig", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Upload a higher version of bar that relies on the official
        # orig.tar.gz availability.
        self.uploadHigherBarToUbuntu()

    def testErrorMessagesWithUnicode(self):
        """Check that unicode errors messages are handled correctly.

        Some error messages can contain the PPA display name, which may
        sometimes contain unicode characters.  There was a bug
        https://bugs.launchpad.net/bugs/275509 reported about getting
        upload errors related to unicode.  This only happened when the
        uploder was attaching a .orig.tar.gz file with different contents
        than the one already in the PPA.
        """
        # Ensure the displayname of the PPA has got unicode in it.
        self.name16.archive.displayname = u"unicode PPA name: áří"

        # Upload the first version.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # The same 'bar' version will fail due to the conflicting
        # file contents.
        upload_dir = self.queueUpload("bar_1.0-1-ppa-orig", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        # The error message should be sane, and not one about unicode
        # errors.
        self.assertEqual(
            self.uploadprocessor.last_processed_upload.rejection_message,
            u'File bar_1.0.orig.tar.gz already exists in unicode PPA name: '
            u'áří, but uploaded version has different '
            u'contents. See more information about this error in '
            u'https://help.launchpad.net/Packaging/UploadErrors.\n'
            u'File bar_1.0-1.diff.gz already exists in unicode PPA name: '
            u'áří, but uploaded version has different contents. See more '
            u'information about this error in '
            u'https://help.launchpad.net/Packaging/UploadErrors.\n'
            u'Files specified in DSC are broken or missing, skipping package '
            u'unpack verification.')

        # Also, the email generated should be sane.
        from_addr, to_addrs, raw_msg = stub.test_emails.pop()
        msg = message_from_string(raw_msg)
        body = msg.get_payload(0)
        body = body.get_payload(decode=True)

        self.assertTrue(
            "File bar_1.0.orig.tar.gz already exists in unicode PPA name: "
            "áří" in body)

    def testPPAConflictingOrigFiles(self):
        """When available, the official 'orig.tar.gz' restricts PPA uploads.

        This test guarantee that when not previously overridden in the
        context PPA, users will be forced to use the offical 'orig.tar.gz'
        from primary archive.
        """
        # Make the official bar orig.tar.gz available in the system.
        self.uploadNewBarToUbuntu()

        # Upload of version of 'bar' to a PPA that relies on the
        # availability of orig.tar.gz published in the PPA itself.

        # The same 'bar' version will fail due to the conflicting
        # 'orig.tar.gz' contents.
        upload_dir = self.queueUpload("bar_1.0-1-ppa-orig", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.rejection_message,
            'File bar_1.0.orig.tar.gz already exists in Primary Archive '
            'for Ubuntu Linux, but uploaded version has different '
            'contents. See more information about this error in '
            'https://help.launchpad.net/Packaging/UploadErrors.\nFiles '
            'specified in DSC are broken or missing, skipping package '
            'unpack verification.')

        # The same happens with higher versions of 'bar' depending on the
        # unofficial 'orig.tar.gz'.
        upload_dir = self.queueUpload("bar_1.0-10-ppa-orig", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.rejection_message,
            'File bar_1.0.orig.tar.gz already exists in Primary Archive for '
            'Ubuntu Linux, but uploaded version has different contents. See '
            'more information about this error in '
            'https://help.launchpad.net/Packaging/UploadErrors.\nFiles '
            'specified in DSC are broken or missing, skipping package unpack '
            'verification.')

        # Cleanup queue directory in order to re-upload the same source.
        shutil.rmtree(
            os.path.join(self.queue_folder, 'incoming', 'bar_1.0-1'))

        # Only versions of 'bar' matching the official 'orig.tar.gz' will
        # be accepted.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        upload_dir = self.queueUpload("bar_1.0-10", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

    def test_conflicting_deleted_orig_file(self):
        # Uploading a conflicting orig file should be disallowed even if
        # the existing one was deleted from disk.
        upload_dir = self.queueUpload("bar_1.0-1-ppa-orig", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Delete the published file.
        self.switchToAdmin()
        bar_src = self.name16.archive.getPublishedSources(name=u"bar").one()
        bar_src.requestDeletion(self.name16)
        bar_src.dateremoved = UTC_NOW
        self.switchToUploader()

        # bar_1.0-3 contains an orig file of the same version with
        # different contents than the one we previously uploaded.
        upload_dir = self.queueUpload("bar_1.0-3", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        self.assertTrue(
            self.uploadprocessor.last_processed_upload.is_rejected)
        self.assertIn(
            'File bar_1.0.orig.tar.gz already exists in ',
            self.uploadprocessor.last_processed_upload.rejection_message)

    def test30QuiltMultipleReusedOrigs(self):
        """Official orig*.tar.* can be reused for PPA uploads.

        The 3.0 (quilt) format supports multiple original tarballs. In a
        PPA upload, any number of these can be reused from the primary
        archive.
        """
        # We need to accept unsigned .changes and .dscs, and 3.0 (quilt)
        # sources.
        self.switchToAdmin()
        self.options.context = 'absolutely-anything'
        getUtility(ISourcePackageFormatSelectionSet).add(
            self.breezy, SourcePackageFormat.FORMAT_3_0_QUILT)
        self.switchToUploader()

        # First upload a complete 3.0 (quilt) source to the primary
        # archive.
        upload_dir = self.queueUpload("bar_1.0-1_3.0-quilt")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.NEW)

        [queue_item] = self.breezy.getPackageUploads(
            status=PackageUploadStatus.NEW, name=u"bar",
            version=u"1.0-1", exact_match=True)
        queue_item.setAccepted()
        queue_item.realiseUpload()
        transaction.commit()
        stub.test_emails.pop()

        # Now upload a 3.0 (quilt) source with missing orig*.tar.* to a
        # PPA. All of the missing files will be retrieved from the
        # primary archive.
        upload_dir = self.queueUpload(
            "bar_1.0-2_3.0-quilt_without_orig", "~name16/ubuntu")
        self.assertEquals(
            self.processUpload(self.uploadprocessor, upload_dir),
            ['accepted'])

        queue_item = self.uploadprocessor.last_processed_upload.queue_root

        self.assertEqual(queue_item.status, PackageUploadStatus.DONE)
        self.assertEqual(
            queue_item.sources[0].sourcepackagerelease.files.count(), 5)


class TestPPAUploadProcessorQuotaChecks(TestPPAUploadProcessorBase):
    """Functional test for uploadprocessor.py quota checks in PPA."""

    def _fillArchive(self, archive, size):
        """Create content in the given archive which the given size.

        Create a source package publication in the given archive totalizing
        the given size in bytes.

        Uses `SoyuzTestPublisher` class to create the corresponding publishing
        record, then switch_dbuser as 'librariangc' and update the size of the
        source file to the given value.
        """
        self.switchToAdmin()
        publisher = SoyuzTestPublisher()
        publisher.prepareBreezyAutotest()
        pub_src = publisher.getPubSource(
            archive=archive, distroseries=self.breezy,
            status=PackagePublishingStatus.PUBLISHED)
        alias_id = pub_src.sourcepackagerelease.files[0].libraryfile.id

        switch_dbuser('librariangc')
        content = getUtility(ILibraryFileAliasSet)[alias_id].content
        # Decrement the archive index cruft automatically added by
        # IArchive.estimated_size.
        removeSecurityProxy(content).filesize = size - 1024
        self.switchToUploader()

        # Re-initialize uploadprocessor since it depends on the new
        # transaction reset by switch_dbuser.
        self.uploadprocessor = self.getUploadProcessor(self.layer.txn)

    def testPPASizeQuotaSourceRejection(self):
        """Verify the size quota check for PPA uploads.

        New source uploads are submitted to the size quota check, where
        the size of the upload plus the current PPA size must be smaller
        than the PPA.authorized_size, otherwise the upload will be rejected.
        """
        # Stuff 2048 MiB in name16 PPA, so anything will be above the
        # default quota limit, 2048 MiB.
        self._fillArchive(self.name16.archive, 2048 * (2 ** 20))

        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        upload_results = self.processUpload(self.uploadprocessor, upload_dir)

        # Upload got rejected.
        self.assertEqual(upload_results, ['rejected'])

        # An email communicating the rejection and the reason why it was
        # rejected is sent to the uploaders.
        contents = [
            "Subject: [PPA name16] bar_1.0-1_source.changes rejected",
            "Rejected:",
            "PPA exceeded its size limit (2048.00 of 2048.00 MiB). "
            "Ask a question in https://answers.launchpad.net/soyuz/ "
            "if you need more space."]
        self.assertEmail(contents)

    def testPPASizeNoQuota(self):
        self.name16.archive.authorized_size = None
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        contents = [
            "Subject: [PPA name16] [ubuntu/breezy] bar 1.0-1 (Accepted)"]
        self.assertEmail(contents)
        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

    def testPPASizeQuotaSourceWarning(self):
        """Verify the size quota warning for PPA near size limit.

        The system start warning users for uploads exceeding 95 % of
        the current size limit.
        """
        # Stuff 1945 MiB into name16 PPA, approximately 95 % of
        # the default quota limit, 2048 MiB.
        self._fillArchive(self.name16.archive, 2000 * (2 ** 20))

        # Ensure the warning is sent in the acceptance notification.
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)
        contents = [
            "Subject: [PPA name16] [ubuntu/breezy] bar 1.0-1 (Accepted)",
            "Upload Warnings:",
            "PPA exceeded 95 % of its size limit (2000.00 of 2048.00 MiB). "
            "Ask a question in https://answers.launchpad.net/soyuz/ "
            "if you need more space."]
        self.assertEmail(contents)

        # User was warned about quota limits but the source was accepted
        # as informed in the upload notification.
        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

    def testPPADoNotCheckSizeQuotaForBinary(self):
        """Verify the size quota check for internal binary PPA uploads.

        Binary uploads are not submitted to the size quota check, since
        they are automatically generated, rejecting/warning them would
        just cause unnecessary hassle.
        """
        upload_dir = self.queueUpload("bar_1.0-1", "~name16/ubuntu")
        self.processUpload(self.uploadprocessor, upload_dir)

        self.assertEqual(
            self.uploadprocessor.last_processed_upload.queue_root.status,
            PackageUploadStatus.DONE)

        # Retrieve the build record for source bar in breezy-i386
        # distroarchseries, and setup a appropriate upload policy
        # in preparation to the corresponding binary upload.
        [build] = self.name16.archive.getBuildRecords(name=u'bar')
        self.options.context = 'buildd'

        # Stuff 2048 MiB in name16 PPA, so anything will be above the
        # default quota limit, 2048 MiB.
        self._fillArchive(self.name16.archive, 2048 * (2 ** 20))

        upload_dir = self.queueUpload("bar_1.0-1_binary", "~name16/ubuntu")
        self.processUpload(
            self.build_uploadprocessor, upload_dir, build=build)

        # The binary upload was accepted, and it's waiting in the queue.
        queue_items = self.breezy.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, name=u"bar",
            version=u"1.0-1", exact_match=True, archive=self.name16.archive)
        self.assertEqual(queue_items.count(), 1)

    def testArchiveBinarySize(self):
        """Test an archive's binaries_size reports correctly.

        The binary size for an archive should only take into account one
        occurrence of arch-independent files published in multiple locations.
        """
        self.switchToAdmin()

        # We need to publish an architecture-independent package
        # for a couple of distroseries in a PPA.
        publisher = SoyuzTestPublisher()
        publisher.prepareBreezyAutotest()

        # Publish To Breezy:
        publisher.getPubBinaries(
            archive=self.name16.archive, distroseries=self.breezy,
            status=PackagePublishingStatus.PUBLISHED)

        # Create chroot for warty/i386, allowing binaries to build and
        # thus be published in this architecture.
        warty = self.ubuntu['warty']
        fake_chroot = self.addMockFile('fake_chroot.tar.gz')
        warty['i386'].addOrUpdateChroot(fake_chroot)

        # Publish To Warty:
        publisher.getPubBinaries(
            archive=self.name16.archive, distroseries=warty,
            status=PackagePublishingStatus.PUBLISHED)

        self.switchToUploader()

        self.assertEqual(18, self.name16.archive.binaries_size)
