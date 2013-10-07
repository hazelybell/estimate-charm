# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test uploads of SourcePackageRecipeBuilds."""

__metaclass__ = type

import os

from storm.store import Store
from zope.component import getUtility

from lp.archiveuploader.tests.test_uploadprocessor import (
    TestUploadProcessorBase,
    )
from lp.archiveuploader.uploadprocessor import (
    UploadHandler,
    UploadStatusEnum,
    )
from lp.buildmaster.enums import BuildStatus
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuildSource,
    )


class TestSourcePackageRecipeBuildUploads(TestUploadProcessorBase):

    def setUp(self):
        super(TestSourcePackageRecipeBuildUploads, self).setUp()

        self.setupBreezy()

        # We need at least one architecture for the PPA upload to be
        # accepted.
        self.breezy['i386'].supports_virtualized = True

        self.switchToAdmin()
        self.recipe = self.factory.makeSourcePackageRecipe()
        self.build = getUtility(ISourcePackageRecipeBuildSource).new(
            distroseries=self.breezy,
            recipe=self.recipe,
            archive=self.factory.makeArchive(
                distribution=self.ubuntu, owner=self.recipe.owner),
            requester=self.recipe.owner)
        Store.of(self.build).flush()
        self.switchToUploader()
        self.options.context = 'buildd'

        self.uploadprocessor = self.getUploadProcessor(
            self.layer.txn, builds=True)

    def testSetsBuildAndState(self):
        # Ensure that the upload processor correctly links the SPR to
        # the SPRB, and that the status is set properly.
        # This test depends on write access being granted to anybody
        # (it does not matter who) on SPRB.{status,upload_log}.
        self.assertIs(None, self.build.source_package_release)
        self.assertEqual(False, self.build.verifySuccessfulUpload())
        self.queueUpload('bar_1.0-1', '%d/ubuntu' % self.build.archive.id)
        fsroot = os.path.join(self.queue_folder, "incoming")
        handler = UploadHandler.forProcessor(
            self.uploadprocessor, fsroot, 'bar_1.0-1', self.build)
        result = handler.processChangesFile(
            '%d/ubuntu/bar_1.0-1_source.changes' % self.build.archive.id)
        self.layer.txn.commit()

        self.assertEquals(UploadStatusEnum.ACCEPTED, result,
            "Source upload failed\nGot: %s" % self.log.getLogBuffer())

        self.assertEqual(BuildStatus.FULLYBUILT, self.build.status)
        self.assertEqual(True, self.build.verifySuccessfulUpload())
