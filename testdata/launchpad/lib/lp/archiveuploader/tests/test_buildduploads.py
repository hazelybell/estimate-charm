# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test buildd uploads use-cases."""

__metaclass__ = type

import os

from zope.component import getUtility

from lp.archiveuploader.tests.test_uploadprocessor import (
    TestUploadProcessorBase,
    )
from lp.archiveuploader.uploadprocessor import UploadHandler
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.database.constants import UTC_NOW
from lp.soyuz.enums import (
    PackagePublishingStatus,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.interfaces.publishing import IPublishingSet
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.testing.gpgkeys import import_public_test_keys


class TestStagedBinaryUploadBase(TestUploadProcessorBase):
    name = 'baz'
    version = '1.0-1'
    distribution_name = None
    distroseries_name = None
    pocket = None
    policy = 'buildd'
    no_mails = True

    @property
    def distribution(self):
        return getUtility(IDistributionSet)[self.distribution_name]

    @property
    def distroseries(self):
        return self.distribution[self.distroseries_name]

    @property
    def package_name(self):
        return "%s_%s" % (self.name, self.version)

    @property
    def source_dir(self):
        return self.package_name

    @property
    def source_changesfile(self):
        return "%s_source.changes" % self.package_name

    @property
    def binary_dir(self):
        return "%s_binary" % self.package_name

    def getBinaryChangesfileFor(self, archtag):
        return "%s_%s.changes" % (self.package_name, archtag)

    def setUp(self):
        """Setup environment for staged binaries upload via security policy.

        1. Setup queue directory and other basic attributes
        2. Override policy options to get security policy and not send emails
        3. Setup a common UploadProcessor with the overridden options
        4. Store number of build present before issuing any upload
        5. Upload the source package via security policy
        6. Clean log messages.
        7. Commit transaction, so the upload source can be seen.
        """
        super(TestStagedBinaryUploadBase, self).setUp()
        self.options.context = self.policy
        self.options.nomails = self.no_mails
        # Set up the uploadprocessor with appropriate options and logger
        self.uploadprocessor = self.getUploadProcessor(self.layer.txn)
        self.build_uploadprocessor = self.getUploadProcessor(
            self.layer.txn, builds=True)
        self.builds_before_upload = BinaryPackageBuild.select().count()
        self.source_queue = None
        self._uploadSource()
        self.layer.txn.commit()

    def assertBuildsCreated(self, amount):
        """Assert that a given 'amount' of build records was created."""
        builds_count = BinaryPackageBuild.select().count()
        self.assertEqual(
            self.builds_before_upload + amount, builds_count)

    def _prepareUpload(self, upload_dir):
        """Place a copy of the upload directory into incoming queue."""
        os.system("cp -a %s %s" %
            (os.path.join(self.test_files_dir, upload_dir),
             os.path.join(self.queue_folder, "incoming")))

    def _uploadSource(self):
        """Upload and Accept (if necessary) the base source."""
        self._prepareUpload(self.source_dir)
        fsroot = os.path.join(self.queue_folder, "incoming")
        handler = UploadHandler.forProcessor(
            self.uploadprocessor, fsroot, self.source_dir)
        handler.processChangesFile(self.source_changesfile)
        queue_item = self.uploadprocessor.last_processed_upload.queue_root
        self.assertTrue(
            queue_item is not None,
            "Source Upload Failed\nGot: %s" % self.log.getLogBuffer())
        acceptable_statuses = [
            PackageUploadStatus.NEW,
            PackageUploadStatus.UNAPPROVED,
            ]
        if queue_item.status in acceptable_statuses:
            queue_item.setAccepted()
        # Store source queue item for future use.
        self.source_queue = queue_item

    def _uploadBinary(self, archtag, build):
        """Upload the base binary.

        Ensure it got processed and has a respective queue record.
        Return the IBuild attached to upload.
        """
        self._prepareUpload(self.binary_dir)
        fsroot = os.path.join(self.queue_folder, "incoming")
        handler = UploadHandler.forProcessor(
            self.build_uploadprocessor, fsroot, self.binary_dir, build=build)
        handler.processChangesFile(self.getBinaryChangesfileFor(archtag))
        last_processed = self.build_uploadprocessor.last_processed_upload
        queue_item = last_processed.queue_root
        self.assertTrue(
            queue_item is not None,
            "Binary Upload Failed\nGot: %s" % self.log.getLogBuffer())
        self.assertEqual(1, len(queue_item.builds))
        return queue_item.builds[0].build

    def _createBuild(self, archtag):
        """Create a build record attached to the base source."""
        spr = self.source_queue.sources[0].sourcepackagerelease
        build = spr.createBuild(
            distro_arch_series=self.distroseries[archtag],
            pocket=self.pocket, archive=self.distroseries.main_archive)
        self.layer.txn.commit()
        return build


class TestBuilddUploads(TestStagedBinaryUploadBase):
    """Test how buildd uploads behave inside Soyuz.

    Buildd uploads are exclusively binary uploads which use 'buildd' upload
    policy.

    An upload of a binaries does not necessary need to happen in the same
    batch, and Soyuz is prepared to cope with it.

    The only mandatory condition is to process the sources first.

    This class will start to tests all known/possible cases using a test
    (empty) upload and its binary.

     * 'lib/lp/archiveuploader/tests/data/suite/foo_1.0-1/'
     * 'lib/lp/archiveuploader/tests/data/suite/foo_1.0-1_binary/'

    This class allows uploads to ubuntu/breezy in i386 & powerpc
    architectures.
    """
    name = 'foo'
    version = '1.0-1'
    distribution_name = 'ubuntu'
    distroseries_name = 'breezy'
    pocket = PackagePublishingPocket.RELEASE
    policy = 'buildd'
    no_mails = True

    def setupBreezy(self):
        """Extend breezy setup to enable uploads to powerpc architecture."""
        TestStagedBinaryUploadBase.setupBreezy(self)
        self.switchToAdmin()
        ppc = getUtility(IProcessorSet).new(
            name='powerpc', title='PowerPC', description='not yet')
        self.breezy.newArch(
            'powerpc', ppc, True, self.breezy.owner)
        self.switchToUploader()

    def setUp(self):
        """Setup environment for binary uploads.

        1. import pub GPG keys
        2. setup ubuntu/breezy for i386 & powerpc
        3. override policy to upload the source in question via
           TestStagedBinaryUploadBase.setUp()
        4. restore 'buildd' policy.
        """
        import_public_test_keys()
        self.setupBreezy()
        self.layer.txn.commit()

        real_policy = self.policy
        self.policy = 'insecure'
        super(TestBuilddUploads, self).setUp()
        # Publish the source package release so it can be found by
        # NascentUploadFile.findSourcePackageRelease().
        spr = self.source_queue.sources[0].sourcepackagerelease
        getUtility(IPublishingSet).newSourcePublication(
            self.distroseries.main_archive, spr,
            self.distroseries, spr.component,
            spr.section, PackagePublishingPocket.RELEASE)
        self.policy = real_policy

    def _publishBuildQueueItem(self, queue_item):
        """Publish build part of the given queue item."""
        self.switchToAdmin()
        queue_item.setAccepted()
        pubrec = queue_item.builds[0].publish(self.log)[0]
        pubrec.status = PackagePublishingStatus.PUBLISHED
        pubrec.datepublished = UTC_NOW
        queue_item.setDone()
        self.switchToUploader()

    def _setupUploadProcessorForBuild(self):
        """Setup an UploadProcessor instance for a given buildd context."""
        self.options.context = self.policy
        self.uploadprocessor = self.getUploadProcessor(
            self.layer.txn)

    def testDelayedBinaryUpload(self):
        """Check if Soyuz copes with delayed binary uploads.

        The binaries are build asynchronously, which means we can't
        predict if the builds for all architectures of a given source
        will be delivered within the same publication cycle.

        Find more information on bug #89846.
        """
        # Upload i386 binary.
        build_candidate = self._createBuild('i386')
        self._setupUploadProcessorForBuild()
        build_used = self._uploadBinary('i386', build_candidate)

        self.assertEqual(build_used.id, build_candidate.id)
        self.assertBuildsCreated(1)
        self.assertEqual(
            u'i386 build of foo 1.0-1 in ubuntu breezy RELEASE',
            build_used.title)
        self.assertEqual('FULLYBUILT', build_used.status.name)

        # Force immediate publication.
        last_processed = self.build_uploadprocessor.last_processed_upload
        queue_item = last_processed.queue_root
        self._publishBuildQueueItem(queue_item)

        # Upload powerpc binary
        build_candidate = self._createBuild('powerpc')
        self._setupUploadProcessorForBuild()
        build_used = self._uploadBinary('powerpc', build_candidate)

        self.assertEqual(build_used.id, build_candidate.id)
        self.assertBuildsCreated(2)
        self.assertEqual(
            u'powerpc build of foo 1.0-1 in ubuntu breezy RELEASE',
            build_used.title)
        self.assertEqual('FULLYBUILT', build_used.status.name)
