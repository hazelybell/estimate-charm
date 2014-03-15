# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.soyuz.adapters.copypolicy import (
    InsecureCopyPolicy,
    MassSyncCopyPolicy,
    )
from lp.soyuz.enums import (
    ArchivePurpose,
    PackageCopyPolicy,
    )
from lp.soyuz.interfaces.copypolicy import ICopyPolicy
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import ZopelessDatabaseLayer


class TestCopyPolicy(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def _getUploadCriteria(self, archive_purpose, status=None, pocket=None):
        archive = self.factory.makeArchive(purpose=archive_purpose)
        distroseries = self.factory.makeDistroSeries()
        if status is not None:
            distroseries.status = status
        if pocket is None:
            pocket = self.factory.getAnyPocket()
        return archive, distroseries, pocket

    def assertApproved(self, archive_purpose, method,
                       status=None, pocket=None):
        archive, distroseries, pocket = self._getUploadCriteria(
            archive_purpose, status=status, pocket=pocket)
        self.assertTrue(method(archive, distroseries, pocket))

    def assertUnapproved(self, archive_purpose, method,
                         status=None, pocket=None):
        archive, distroseries, pocket = self._getUploadCriteria(
            archive_purpose, status=status, pocket=pocket)
        self.assertFalse(method(archive, distroseries, pocket))

    def test_insecure_holds_new_distro_package(self):
        cp = InsecureCopyPolicy()
        self.assertUnapproved(ArchivePurpose.PRIMARY, cp.autoApproveNew)

    def test_insecure_approves_new_ppa_packages(self):
        cp = InsecureCopyPolicy()
        self.assertApproved(ArchivePurpose.PPA, cp.autoApproveNew)

    def test_insecure_approves_known_distro_package_to_unfrozen_release(self):
        cp = InsecureCopyPolicy()
        self.assertApproved(
            ArchivePurpose.PRIMARY, cp.autoApprove,
            pocket=PackagePublishingPocket.RELEASE)

    def test_insecure_holds_copy_to_updates_pocket_in_frozen_series(self):
        cp = InsecureCopyPolicy()
        self.assertUnapproved(
            ArchivePurpose.PRIMARY, cp.autoApprove, status=SeriesStatus.FROZEN,
            pocket=PackagePublishingPocket.UPDATES)

    def test_insecure_holds_copy_to_release_pocket_in_frozen_series(self):
        cp = InsecureCopyPolicy()
        self.assertUnapproved(
            ArchivePurpose.PRIMARY, cp.autoApprove, status=SeriesStatus.FROZEN,
            pocket=PackagePublishingPocket.RELEASE)

    def test_insecure_approves_copy_to_proposed_in_unfrozen_series(self):
        cp = InsecureCopyPolicy()
        self.assertApproved(
            ArchivePurpose.PRIMARY, cp.autoApprove,
            pocket=PackagePublishingPocket.PROPOSED)

    def test_insecure_holds_copy_to_proposed_in_frozen_series(self):
        cp = InsecureCopyPolicy()
        self.assertUnapproved(
            ArchivePurpose.PRIMARY, cp.autoApprove, status=SeriesStatus.FROZEN,
            pocket=PackagePublishingPocket.PROPOSED)

    def test_insecure_holds_copy_to_proposed_in_current_series(self):
        cp = InsecureCopyPolicy()
        self.assertUnapproved(
            ArchivePurpose.PRIMARY, cp.autoApprove,
            status=SeriesStatus.CURRENT,
            pocket=PackagePublishingPocket.PROPOSED)

    def test_insecure_approves_existing_ppa_package(self):
        cp = InsecureCopyPolicy()
        self.assertApproved(ArchivePurpose.PPA, cp.autoApprove)

    def test_insecure_sends_emails(self):
        cp = InsecureCopyPolicy()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        self.assertTrue(cp.send_email(archive))

    def test_insecure_doesnt_send_emails_for_ppa(self):
        cp = InsecureCopyPolicy()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertFalse(cp.send_email(archive))

    def test_sync_does_not_send_emails(self):
        cp = MassSyncCopyPolicy()
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        self.assertFalse(cp.send_email(archive))
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        self.assertFalse(cp.send_email(archive))

    def test_policies_implement_ICopyPolicy(self):
        for policy in PackageCopyPolicy.items:
            self.assertTrue(verifyObject(ICopyPolicy, ICopyPolicy(policy)))
