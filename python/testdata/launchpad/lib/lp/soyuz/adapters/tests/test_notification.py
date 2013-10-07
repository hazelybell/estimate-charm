# -*- coding: utf-8 -*-
# NOTE: The first line above must stay first; do not move the copyright
# notice to the top.  See http://www.python.org/dev/peps/pep-0263/.
#
# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from email.utils import formataddr
from textwrap import dedent

from storm.store import Store
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.archivepublisher.utils import get_ppa_reference
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.log.logger import BufferLogger
from lp.services.mail.sendmail import format_address_for_person
from lp.services.propertycache import get_property_cache
from lp.services.webapp.publisher import canonical_url
from lp.soyuz.adapters.notification import (
    assemble_body,
    calculate_subject,
    fetch_information,
    get_upload_notification_recipients,
    is_auto_sync_upload,
    notify,
    person_to_email,
    reject_changes_file,
    )
from lp.soyuz.enums import (
    ArchivePurpose,
    PackageUploadCustomFormat,
    )
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.model.component import ComponentSelection
from lp.soyuz.model.distroseriessourcepackagerelease import (
    DistroSeriesSourcePackageRelease,
    )
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class TestNotificationRequiringLibrarian(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_notify_from_unicode_names(self):
        # People with unicode in their names should appear correctly in the
        # email and not get smashed to ASCII or otherwise transliterated.
        RANDOM_UNICODE = u"Loïc"
        creator = self.factory.makePerson(displayname=RANDOM_UNICODE)
        spr = self.factory.makeSourcePackageRelease(creator=creator)
        self.factory.makeSourcePackageReleaseFile(sourcepackagerelease=spr)
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        pocket = PackagePublishingPocket.RELEASE
        distroseries = self.factory.makeDistroSeries()
        distroseries.changeslist = "blah@example.com"
        blamer = self.factory.makePerson()
        notify(
            blamer, spr, [], [], archive, distroseries, pocket,
            action='accepted')
        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        msg = notifications[1].get_payload(0)
        body = msg.get_payload(decode=True)
        self.assertIn("Loïc", body)

    def test_calculate_subject_customfile(self):
        lfa = self.factory.makeLibraryFileAlias()
        package_upload = self.factory.makePackageUpload()
        customfile = package_upload.addCustom(
            lfa, PackageUploadCustomFormat.DEBIAN_INSTALLER)
        archive = self.factory.makeArchive()
        pocket = self.factory.getAnyPocket()
        distroseries = self.factory.makeDistroSeries()
        expected_subject = '[PPA %s] [%s/%s] %s - (Accepted)' % (
            get_ppa_reference(archive), distroseries.distribution.name,
            distroseries.getSuite(pocket), lfa.filename)
        subject = calculate_subject(
            None, [], [customfile], archive, distroseries, pocket,
            'accepted')
        self.assertEqual(expected_subject, subject)

    def _setup_notification(self, from_person=None, distroseries=None,
                            spr=None):
        if spr is None:
            spr = self.factory.makeSourcePackageRelease()
        self.factory.makeSourcePackageReleaseFile(sourcepackagerelease=spr)
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        pocket = PackagePublishingPocket.RELEASE
        if distroseries is None:
            distroseries = self.factory.makeDistroSeries()
        distroseries.changeslist = "blah@example.com"
        blamer = self.factory.makePerson()
        if from_person is None:
            from_person = self.factory.makePerson()
        notify(
            blamer, spr, [], [], archive, distroseries, pocket,
            action='accepted', announce_from_person=from_person)

    def test_notify_from_person_override(self):
        # notify() takes an optional from_person to override the calculated
        # From: address in announcement emails.
        spr = self.factory.makeSourcePackageRelease()
        self.factory.makeSourcePackageReleaseFile(sourcepackagerelease=spr)
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        pocket = PackagePublishingPocket.RELEASE
        distroseries = self.factory.makeDistroSeries()
        distroseries.changeslist = "blah@example.com"
        blamer = self.factory.makePerson()
        from_person = self.factory.makePerson(
            email="lemmy@example.com", displayname="Lemmy Kilmister")
        notify(
            blamer, spr, [], [], archive, distroseries, pocket,
            action='accepted', announce_from_person=from_person)
        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        # The first notification is to the blamer, the second notification is
        # to the announce list, which is the one that gets the overridden
        # From:
        self.assertEqual(
            "Lemmy Kilmister <lemmy@example.com>", notifications[1]["From"])

    def test_notify_from_person_override_with_unicode_names(self):
        # notify() takes an optional from_person to override the calculated
        # From: address in announcement emails. Non-ASCII real names should be
        # correctly encoded in the From heade.
        spr = self.factory.makeSourcePackageRelease()
        self.factory.makeSourcePackageReleaseFile(sourcepackagerelease=spr)
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        pocket = PackagePublishingPocket.RELEASE
        distroseries = self.factory.makeDistroSeries()
        distroseries.changeslist = "blah@example.com"
        blamer = self.factory.makePerson()
        from_person = self.factory.makePerson(
            email="loic@example.com", displayname=u"Loïc Motörhead")
        notify(
            blamer, spr, [], [], archive, distroseries, pocket,
            action='accepted', announce_from_person=from_person)
        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        # The first notification is to the blamer, the second notification is
        # to the announce list, which is the one that gets the overridden
        # From:
        self.assertEqual(
            "=?utf-8?q?Lo=C3=AFc_Mot=C3=B6rhead?= <loic@example.com>",
            notifications[1]["From"])

    def test_notify_bcc_to_derivatives_list(self):
        # notify() will BCC the announcement email to the address defined in
        # Distribution.package_derivatives_email if it's defined.
        email = "{package_name}_thing@foo.com"
        distroseries = self.factory.makeDistroSeries()
        with person_logged_in(distroseries.distribution.owner):
            distroseries.distribution.package_derivatives_email = email
        spr = self.factory.makeSourcePackageRelease()
        self._setup_notification(distroseries=distroseries, spr=spr)

        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        bcc_address = notifications[1]["Bcc"]
        expected_email = email.format(package_name=spr.sourcepackagename.name)
        self.assertIn(expected_email, bcc_address)

    def test_fetch_information_spr_multiple_changelogs(self):
        # If previous_version is passed the "changelog" entry in the
        # returned dict should contain the changelogs for all SPRs *since*
        # that version and up to and including the passed SPR.
        changelog = self.factory.makeChangelog(
            spn="foo", versions=["1.2",  "1.1",  "1.0"])
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename="foo", version="1.3", changelog=changelog)
        self.layer.txn.commit()  # Yay, librarian.

        spr = spph.sourcepackagerelease
        info = fetch_information(spr, None, None, previous_version="1.0")

        self.assertIn("foo (1.1)", info['changelog'])
        self.assertIn("foo (1.2)", info['changelog'])

    def test_notify_bpr_rejected(self):
        # If we notify about a rejected bpr with no source, a notification is
        # sent.
        bpr = self.factory.makeBinaryPackageRelease()
        changelog = self.factory.makeChangelog(spn="foo", versions=["1.1"])
        removeSecurityProxy(
            bpr.build.source_package_release).changelog = changelog
        self.layer.txn.commit()
        person = self.factory.makePerson(name='archiver')
        archive = self.factory.makeArchive(owner=person, name='ppa')
        pocket = self.factory.getAnyPocket()
        distroseries = self.factory.makeDistroSeries()
        person = self.factory.makePerson()
        notify(
            person, None, [bpr], [], archive, distroseries, pocket,
            summary_text="Rejected by archive administrator.",
            action='rejected')
        [notification] = pop_notifications()
        body = notification.get_payload()[0].get_payload()
        self.assertEqual(person_to_email(person), notification['To'])
        expected_body = dedent("""\
            Rejected:
            Rejected by archive administrator.

            foo (1.1) unstable; urgency=3Dlow

              * 1.1.

            =3D=3D=3D

            If you don't understand why your files were rejected please send an email
            to launchpad-users@lists.launchpad.net for help (requires membership).

            --
            http://launchpad.dev/~archiver/+archive/ppa
            You are receiving this email because you are the uploader of the above
            PPA package.
            """)
        self.assertEqual(expected_body, body)


class TestNotification(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_fetch_information_changes(self):
        changes = {
            'Date': '2001-01-01',
            'Changed-By': 'Foo Bar <foo.bar@example.com>',
            'Maintainer': 'Foo Bar <foo.bar@example.com>',
            'Changes': ' * Foo!',
            }
        info = fetch_information(None, None, changes)
        self.assertEqual('2001-01-01', info['date'])
        self.assertEqual(' * Foo!', info['changelog'])
        fields = [
            info['changedby'],
            info['maintainer'],
            info['changedby_displayname'],
            info['maintainer_displayname'],
            ]
        for field in fields:
            self.assertEqual('Foo Bar <foo.bar@example.com>', field)

    def test_fetch_information_spr(self):
        creator = self.factory.makePerson(displayname=u"foø")
        maintainer = self.factory.makePerson(displayname=u"bær")
        spr = self.factory.makeSourcePackageRelease(
            creator=creator, maintainer=maintainer)
        info = fetch_information(spr, None, None)
        self.assertEqual(info['date'], spr.dateuploaded)
        self.assertEqual(info['changelog'], spr.changelog_entry)
        self.assertEqual(
            info['changedby'], format_address_for_person(spr.creator))
        self.assertEqual(
            info['maintainer'], format_address_for_person(spr.maintainer))
        self.assertEqual(
            u"foø <%s>" % spr.creator.preferredemail.email,
            info['changedby_displayname'])
        self.assertEqual(
            u"bær <%s>" % spr.maintainer.preferredemail.email,
            info['maintainer_displayname'])

    def test_fetch_information_bprs(self):
        bpr = self.factory.makeBinaryPackageRelease()
        info = fetch_information(None, [bpr], None)
        spr = bpr.build.source_package_release
        self.assertEqual(info['date'], spr.dateuploaded)
        self.assertEqual(info['changelog'], spr.changelog_entry)
        self.assertEqual(
            info['changedby'], format_address_for_person(spr.creator))
        self.assertEqual(
            info['maintainer'], format_address_for_person(spr.maintainer))
        self.assertEqual(
            info['changedby_displayname'],
            formataddr((spr.creator.displayname,
                        spr.creator.preferredemail.email)))
        self.assertEqual(
            info['maintainer_displayname'],
            formataddr((spr.maintainer.displayname,
                        spr.maintainer.preferredemail.email)))

    def test_calculate_subject_spr(self):
        spr = self.factory.makeSourcePackageRelease()
        archive = self.factory.makeArchive()
        pocket = self.factory.getAnyPocket()
        distroseries = self.factory.makeDistroSeries()
        expected_subject = '[PPA %s] [%s/%s] %s %s (Accepted)' % (
            get_ppa_reference(archive), distroseries.distribution.name,
            distroseries.getSuite(pocket), spr.name, spr.version)
        subject = calculate_subject(
            spr, [], [], archive, distroseries, pocket, 'accepted')
        self.assertEqual(expected_subject, subject)

    def test_calculate_subject_bprs(self):
        bpr = self.factory.makeBinaryPackageRelease()
        archive = self.factory.makeArchive()
        pocket = self.factory.getAnyPocket()
        distroseries = self.factory.makeDistroSeries()
        expected_subject = '[PPA %s] [%s/%s] %s %s (Accepted)' % (
            get_ppa_reference(archive), distroseries.distribution.name,
            distroseries.getSuite(pocket),
            bpr.build.source_package_release.name, bpr.version)
        subject = calculate_subject(
            None, [bpr], [], archive, distroseries, pocket, 'accepted')
        self.assertEqual(expected_subject, subject)

    def test_notify_bpr(self):
        # If we notify about an accepted bpr with no source, it is from a
        # build, and no notification is sent.
        bpr = self.factory.makeBinaryPackageRelease()
        archive = self.factory.makeArchive()
        pocket = self.factory.getAnyPocket()
        distroseries = self.factory.makeDistroSeries()
        person = self.factory.makePerson()
        notify(
            person, None, [bpr], [], archive, distroseries, pocket,
            action='accepted')
        notifications = pop_notifications()
        self.assertEqual(0, len(notifications))

    def test_reject_changes_file_no_email(self):
        # If we are rejecting a mail, and the person to notify has no
        # preferred email, we should return early.
        archive = self.factory.makeArchive()
        distroseries = self.factory.makeDistroSeries()
        uploader = self.factory.makePerson()
        get_property_cache(uploader).preferredemail = None
        email = '%s <foo@example.com>' % uploader.displayname
        changes = {'Changed-By': email, 'Maintainer': email}
        logger = BufferLogger()
        reject_changes_file(
            uploader, '/tmp/changes', changes, archive, distroseries, '',
            logger=logger)
        self.assertIn(
            'No recipients have a preferred email.', logger.getLogBuffer())

    def test_reject_with_no_changes(self):
        # If we don't have any files and no changes content, nothing happens.
        archive = self.factory.makeArchive()
        distroseries = self.factory.makeDistroSeries()
        pocket = self.factory.getAnyPocket()
        notify(None, None, (), (), archive, distroseries, pocket)
        notifications = pop_notifications()
        self.assertEqual(0, len(notifications))

    def _setup_recipients(self):
        blamer = self.factory.makePerson()
        maintainer = self.factory.makePerson(
            'maintainer@example.com', displayname='Maintainer')
        changer = self.factory.makePerson(
            'changer@example.com', displayname='Changer')
        return blamer, maintainer, changer

    def assertRecipientsEqual(self, expected, changes, blamer, maintainer,
                              changer, purpose=ArchivePurpose.PRIMARY):
        distribution = self.factory.makeDistribution()
        archive = self.factory.makeArchive(
            distribution=distribution, purpose=purpose)
        distroseries = self.factory.makeDistroSeries(distribution=distribution)
        # Now set the uploaders.
        component = getUtility(IComponentSet).ensure('main')
        if component not in distroseries.components:
            store = Store.of(distroseries)
            store.add(
                ComponentSelection(
                    distroseries=distroseries, component=component))
        distribution.main_archive.newComponentUploader(maintainer, component)
        distribution.main_archive.newComponentUploader(changer, component)
        observed = get_upload_notification_recipients(
            blamer, archive, distroseries, logger=None, changes=changes)
        self.assertContentEqual(
            [format_address_for_person(person) for person in expected],
            observed)

    def test_get_upload_notification_recipients_good_emails(self):
        # Test get_upload_notification_recipients with good email addresses..
        blamer, maintainer, changer = self._setup_recipients()
        changes = {
            'Date': '2001-01-01',
            'Changed-By': 'Changer <changer@example.com>',
            'Maintainer': 'Maintainer <maintainer@example.com>',
            'Changes': ' * Foo!',
            }
        self.assertRecipientsEqual(
            [blamer, maintainer, changer],
            changes, blamer, maintainer, changer)

    def test_get_upload_notification_recipients_bad_maintainer_email(self):
        blamer, maintainer, changer = self._setup_recipients()
        changes = {
            'Date': '2001-01-01',
            'Changed-By': 'Changer <changer@example.com>',
            'Maintainer': 'Maintainer <maintainer at example.com>',
            'Changes': ' * Foo!',
            }
        self.assertRecipientsEqual(
            [blamer, changer], changes, blamer, maintainer, changer)

    def test_get_upload_notification_recipients_bad_changedby_email(self):
        # Test get_upload_notification_recipients with invalid changedby
        # email address.
        blamer, maintainer, changer = self._setup_recipients()
        changes = {
            'Date': '2001-01-01',
            'Changed-By': 'Changer <changer at example.com>',
            'Maintainer': 'Maintainer <maintainer@example.com>',
            'Changes': ' * Foo!',
            }
        self.assertRecipientsEqual(
            [blamer, maintainer], changes, blamer, maintainer, changer)

    def test_get_upload_notification_recipients_unsigned_copy_archive(self):
        # Notifications for unsigned build uploads to copy archives only go
        # to the archive owner.
        _, maintainer, changer = self._setup_recipients()
        changes = {
            'Date': '2001-01-01',
            'Changed-By': 'Changer <changer@example.com>',
            'Maintainer': 'Maintainer <maintainer@example.com>',
            'Changes': ' * Foo!',
            }
        self.assertRecipientsEqual(
            [], changes, None, maintainer, changer,
            purpose=ArchivePurpose.COPY)

    def test_assemble_body_handles_no_preferred_email_for_changer(self):
        # If changer has no preferred email address,
        # assemble_body should still work.
        spr = self.factory.makeSourcePackageRelease()
        blamer = self.factory.makePerson()
        archive = self.factory.makeArchive()
        series = self.factory.makeDistroSeries()

        spr.creator.setPreferredEmail(None)

        body = assemble_body(blamer, spr, [], archive, series, "",
                             None, "unapproved")
        self.assertIn("Waiting for approval", body)

    def test_assemble_body_inserts_package_url_for_distro_upload(self):
        # The email body should contain the canonical url to the package
        # page in the target distroseries.
        spr = self.factory.makeSourcePackageRelease()
        blamer = self.factory.makePerson()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        series = self.factory.makeDistroSeries()

        body = assemble_body(blamer, spr, [], archive, series, "",
                             None, "unapproved")
        dsspr = DistroSeriesSourcePackageRelease(series, spr)
        url = canonical_url(dsspr)
        self.assertIn(url, body)

    def test__is_auto_sync_upload__no_preferred_email_for_changer(self):
        # If changer has no preferred email address,
        # is_auto_sync_upload should still work.
        result = is_auto_sync_upload(
            spr=None, bprs=None, pocket=None, changed_by_email=None)
        self.assertFalse(result)
