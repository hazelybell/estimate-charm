# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test upload and queue manipulation of DDTP tarballs.

DDTP (Debian Description Translation Project) uploads consist of a tarball
containing translations of package descriptions for a component.  These
translations should be published in the Ubuntu archive under the
dists/SUITE/COMPONENT/i18n/ directory.

  https://wiki.ubuntu.com/TranslatedPackageDescriptionsSpec

See also lp.archivepublisher.tests.test_ddtp_tarball for detailed tests of
ddtp-tarball extraction.
"""

import os

import transaction

from lp.archiveuploader.nascentupload import (
    EarlyReturnUploadError,
    NascentUpload,
    )
from lp.archiveuploader.tests import (
    datadir,
    getPolicy,
    )
from lp.services.log.logger import DevNullLogger
from lp.soyuz.tests.test_publishing import TestNativePublishingBase
from lp.testing.gpgkeys import import_public_test_keys


class TestDistroSeriesQueueDdtpTarball(TestNativePublishingBase):

    def setUp(self):
        super(TestDistroSeriesQueueDdtpTarball, self).setUp()
        import_public_test_keys()
        # CustomUpload.installFiles requires a umask of 022.
        old_umask = os.umask(022)
        self.addCleanup(os.umask, old_umask)
        self.anything_policy = getPolicy(
            name="anything", distro="ubuntutest", distroseries=None)
        self.absolutely_anything_policy = getPolicy(
            name="absolutely-anything", distro="ubuntutest", distroseries=None)
        self.logger = DevNullLogger()

    def test_rejects_misspelled_changesfile_name(self):
        upload = NascentUpload.from_changesfile_path(
            datadir("ddtp-tarball/translations-main_20060728.changes"),
            self.absolutely_anything_policy, self.logger)
        self.assertRaises(EarlyReturnUploadError, upload.process)

    def uploadTestData(self, version):
        upload = NascentUpload.from_changesfile_path(
            datadir("ddtp-tarball/translations-main_%s_all.changes" % version),
            self.anything_policy, self.logger)
        upload.process()
        self.assertFalse(upload.is_rejected)
        self.assertTrue(upload.do_accept())
        self.assertFalse(upload.rejection_message)
        return upload

    def test_accepts_correct_upload(self):
        self.uploadTestData("20060728")

    def test_publish(self):
        upload = self.uploadTestData("20060728")
        transaction.commit()
        upload.queue_root.realiseUpload(self.logger)
        target_dir = os.path.join(
            self.config.distroroot, "ubuntutest", "dists", "breezy-autotest",
            "main", "i18n")
        # In this high-level test, we only care that something was unpacked.
        self.assertTrue([name for name in os.listdir(target_dir)
                         if name.startswith("Translation-")])
