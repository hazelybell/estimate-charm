# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test notification behaviour for cross-distro package syncs."""

__metaclass__ = type

import os.path

from zope.component import getUtility

from lp.archiveuploader.nascentupload import (
    NascentUpload,
    UploadError,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.log.logger import DevNullLogger
from lp.soyuz.enums import (
    ArchivePermissionType,
    SourcePackageFormat,
    )
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.archivepermission import ArchivePermission
from lp.soyuz.scripts.packagecopier import do_copy
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.mail_helpers import pop_notifications


class FakeUploadPolicy:
    def __init__(self, spph):
        self.distroseries = spph.distroseries
        self.archive = spph.distroseries.main_archive
        self.pocket = spph.pocket
        self.redirect_warning = None

    setDistroSeriesAndPocket = FakeMethod()
    validateUploadType = FakeMethod()
    checkUpload = FakeMethod()


class FakeChangesFile:
    def __init__(self, spph, file_path):
        self.files = []
        self.filepath = file_path
        self.filename = os.path.basename(file_path)
        self.architectures = ['i386']
        self.suite_name = '-'.join([spph.distroseries.name, spph.pocket.name])
        self.raw_content = open(file_path).read()
        self.signingkey = None

    checkFileName = FakeMethod([])
    processAddresses = FakeMethod([])
    processFiles = FakeMethod([])
    verify = FakeMethod([UploadError("Deliberately broken")])


class TestSyncNotification(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def makePersonWithEmail(self):
        """Create a person; return (person, email)."""
        address = "%s@example.com" % self.factory.getUniqueString()
        person = self.factory.makePerson(email=address)
        return person, address

    def makeSPPH(self, distroseries, maintainer_address):
        """Create a `SourcePackagePublishingHistory`."""
        return self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, pocket=PackagePublishingPocket.RELEASE,
            dsc_maintainer_rfc822=maintainer_address)

    def makeUploader(self, person, archive, component):
        """Grant a person upload privileges for archive/component."""
        ArchivePermission(
            person=person, archive=archive, component=component,
            permission=ArchivePermissionType.UPLOAD)

    def syncSource(self, spph, target_distroseries, requester):
        """Sync `spph` into `target_distroseries`."""
        getUtility(ISourcePackageFormatSelectionSet).add(
            target_distroseries, SourcePackageFormat.FORMAT_1_0)
        target_archive = target_distroseries.main_archive
        self.makeUploader(requester, target_archive, spph.component)
        [synced_spph] = do_copy(
            [spph], target_archive, target_distroseries,
            pocket=spph.pocket, person=requester, close_bugs=False)
        return synced_spph

    def makeChangesFile(self, spph, maintainer, maintainer_address,
                        changer, changer_address):
        temp_dir = self.makeTemporaryDirectory()
        changes_file = os.path.join(
            temp_dir, "%s.changes" % spph.source_package_name)
        with open(changes_file, 'w') as changes:
            changes.write(
                "Maintainer: %s <%s>\n"
                "Changed-By: %s <%s>\n"
                % (
                    maintainer.name,
                    maintainer_address,
                    changer.name,
                    changer_address,
                    ))
        return FakeChangesFile(spph, changes_file)

    def makeNascentUpload(self, spph, maintainer, maintainer_address,
                          changer, changer_address):
        """Create a `NascentUpload` for `spph`."""
        changes = self.makeChangesFile(
            spph, maintainer, maintainer_address, changer, changer_address)
        upload = NascentUpload(
            changes, FakeUploadPolicy(spph), DevNullLogger())
        upload.queue_root = upload._createQueueEntry()
        das = self.factory.makeDistroArchSeries(
            distroseries=spph.distroseries)
        bpb = self.factory.makeBinaryPackageBuild(
            source_package_release=spph.sourcepackagerelease,
            archive=spph.archive, distroarchseries=das, pocket=spph.pocket,
            sourcepackagename=spph.sourcepackagename)
        upload.queue_root.addBuild(bpb)
        return upload

    def processAndRejectUpload(self, nascent_upload):
        nascent_upload.process()
        # Obtain the required privileges for do_reject.
        login('foo.bar@canonical.com')
        nascent_upload.do_reject(notify=True)

    def getNotifiedAddresses(self):
        """Get email addresses that were notified."""
        return [message['to'] for message in pop_notifications()]

    def test_failed_copy_builds_do_not_spam_upstream(self):
        """Failed builds do not spam people who are not responsible for them.

        We import Debian source packages, then sync them into Ubuntu (and
        from there, into Ubuntu-derived distros).  Those syncs then trigger
        builds that the original Debian maintainers and last-change authors
        are not responsible for.

        In a situation like that, we should not bother those people with the
        failure.  We notify the person who requested the sync instead.

        (The logic in lp.soyuz.adapters.notification may still notify the
        author of the last change, if that person is also an uploader for the
        archive that the failure happened in.  For this particular situation
        we consider that not so much an intended behaviour, as an emergent one
        that does not seem inappropriate.  It'd be hard to change if we wanted
        to.)

        This test guards against bug 876594.
        """
        maintainer, maintainer_address = self.makePersonWithEmail()
        changer, changer_address = self.makePersonWithEmail()
        dsp = self.factory.makeDistroSeriesParent()
        original_spph = self.makeSPPH(dsp.parent_series, maintainer_address)
        sync_requester, syncer_address = self.makePersonWithEmail()
        synced_spph = self.syncSource(
            original_spph, dsp.derived_series, sync_requester)
        nascent_upload = self.makeNascentUpload(
            synced_spph, maintainer, maintainer_address,
            changer, changer_address)
        pop_notifications()
        self.processAndRejectUpload(nascent_upload)

        notified_addresses = '\n'.join(self.getNotifiedAddresses())

        self.assertNotIn(maintainer_address, notified_addresses)
        self.assertNotIn(changer_address, notified_addresses)
        self.assertIn(syncer_address, notified_addresses)
