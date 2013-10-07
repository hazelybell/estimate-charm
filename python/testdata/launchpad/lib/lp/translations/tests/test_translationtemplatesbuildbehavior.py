# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for TranslationTemplatesBuildBehavior."""

import datetime
import logging
import os

import pytz
from testtools.deferredruntest import AsynchronousDeferredRunTest
from twisted.internet import defer
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interactor import BuilderInteractor
from lp.buildmaster.interfaces.builder import CannotBuild
from lp.buildmaster.interfaces.buildfarmjobbehavior import (
    IBuildFarmJobBehavior,
    )
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.buildmaster.tests.mock_slaves import (
    SlaveTestHelpers,
    WaitingSlave,
    )
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.utils import copy_and_close
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )


class FakeBuildQueue:
    """Pretend `BuildQueue`."""

    def __init__(self, behavior):
        """Pretend to be a BuildQueue item for the given build behavior.

        Copies its builder from the behavior object.
        """
        self.builder = behavior._builder
        self.specific_job = behavior.buildfarmjob
        self.date_started = datetime.datetime.now(pytz.UTC)
        self.destroySelf = FakeMethod()


class MakeBehaviorMixin(object):
    """Provide common test methods."""

    def makeBehavior(self, branch=None, use_fake_chroot=True):
        """Create a TranslationTemplatesBuildBehavior.

        Anything that might communicate with build slaves and such
        (which we can't really do here) is mocked up.
        """
        specific_job = self.factory.makeTranslationTemplatesBuildJob(
            branch=branch)
        behavior = IBuildFarmJobBehavior(specific_job)
        slave = WaitingSlave()
        behavior.setBuilder(self.factory.makeBuilder(), slave)
        if use_fake_chroot:
            lf = self.factory.makeLibraryFileAlias()
            self.layer.txn.commit()
            behavior._getChroot = lambda: lf
        return behavior

    def makeProductSeriesWithBranchForTranslation(self):
        productseries = self.factory.makeProductSeries()
        branch = self.factory.makeProductBranch(
            productseries.product)
        productseries.branch = branch
        productseries.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        return productseries


class TestTranslationTemplatesBuildBehavior(
    TestCaseWithFactory, MakeBehaviorMixin):
    """Test `TranslationTemplatesBuildBehavior`."""

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTest

    def setUp(self):
        super(TestTranslationTemplatesBuildBehavior, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())

    def _getBuildQueueItem(self, behavior):
        """Get `BuildQueue` for an `IBuildFarmJobBehavior`."""
        job = removeSecurityProxy(behavior.buildfarmjob.job)
        return IStore(BuildQueue).find(BuildQueue, job=job).one()

    def test_getLogFileName(self):
        # Each job has a unique log file name.
        b1 = self.makeBehavior()
        b2 = self.makeBehavior()
        self.assertNotEqual(b1.getLogFileName(), b2.getLogFileName())

    def test_dispatchBuildToSlave_no_chroot_fails(self):
        # dispatchBuildToSlave will fail if the chroot does not exist.
        behavior = self.makeBehavior(use_fake_chroot=False)
        buildqueue_item = self._getBuildQueueItem(behavior)

        switch_dbuser(config.builddmaster.dbuser)
        self.assertRaises(
            CannotBuild, behavior.dispatchBuildToSlave, buildqueue_item,
            logging)

    def test_dispatchBuildToSlave(self):
        # dispatchBuildToSlave ultimately causes the slave's build
        # method to be invoked.  The slave receives the URL of the
        # branch it should build from.
        behavior = self.makeBehavior()
        buildqueue_item = self._getBuildQueueItem(behavior)

        switch_dbuser(config.builddmaster.dbuser)
        d = behavior.dispatchBuildToSlave(buildqueue_item, logging)

        def got_dispatch((status, info)):
            # call_log lives on the mock WaitingSlave and tells us what
            # calls to the slave that the behaviour class made.
            call_log = behavior._slave.call_log
            build_params = call_log[-1]
            self.assertEqual('build', build_params[0])
            build_type = build_params[2]
            self.assertEqual('translation-templates', build_type)
            branch_url = build_params[-1]['branch_url']
            # The slave receives the public http URL for the branch.
            self.assertEqual(
                branch_url,
                behavior.buildfarmjob.branch.composePublicURL())
        return d.addCallback(got_dispatch)

    def test_getChroot(self):
        # _getChroot produces the current chroot for the current Ubuntu
        # release, on the nominated architecture for
        # architecture-independent builds.
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        current_ubuntu = ubuntu.currentseries
        distroarchseries = current_ubuntu.nominatedarchindep

        # Set an arbitrary chroot file.
        fake_chroot_file = getUtility(ILibraryFileAliasSet)[1]
        distroarchseries.addOrUpdateChroot(fake_chroot_file)

        behavior = self.makeBehavior(use_fake_chroot=False)
        chroot = behavior._getChroot()

        self.assertNotEqual(None, chroot)
        self.assertEqual(fake_chroot_file, chroot)

    def test_readTarball(self):
        behavior = self.makeBehavior()
        buildqueue = FakeBuildQueue(behavior)
        path = behavior.templates_tarball_path
        # Poke the file we're expecting into the mock slave.
        behavior._slave.valid_file_hashes.append(path)

        def got_tarball(filename):
            tarball = open(filename, 'r')
            try:
                self.assertEqual(
                    "This is a %s" % path, tarball.read())
            finally:
                tarball.close()
                os.remove(filename)

        d = behavior._readTarball(buildqueue, {path: path}, logging)
        return d.addCallback(got_tarball)

    def test_handleStatus_OK(self):
        # Hopefully, a build will succeed and produce a tarball.
        behavior = self.makeBehavior()
        behavior._uploadTarball = FakeMethod()
        queue_item = FakeBuildQueue(behavior)
        slave = behavior._slave

        d = behavior.dispatchBuildToSlave(queue_item, logging)

        def got_dispatch((status, info)):
            self.assertEqual(0, queue_item.destroySelf.call_count)
            slave_call_log = slave.call_log
            self.assertNotIn('clean', slave_call_log)
            self.assertEqual(0, behavior._uploadTarball.call_count)

            return slave.status()

        def got_status(status):
            slave_call_log = slave.call_log
            slave_status = {
                'builder_status': status[0],
                'build_status': status[1],
                'filemap': {'translation-templates.tar.gz': 'foo'},
                }
            return (
                behavior.handleStatus(
                    queue_item,
                    BuilderInteractor.extractBuildStatus(slave_status),
                    slave_status),
                slave_call_log)

        def build_updated(ignored):
            self.assertEqual(BuildStatus.FULLYBUILT, behavior.build.status)
            # Log file is stored.
            self.assertIsNotNone(behavior.build.log)
            slave_call_log = slave.call_log
            self.assertEqual(1, queue_item.destroySelf.call_count)
            self.assertIn('clean', slave_call_log)
            self.assertEqual(1, behavior._uploadTarball.call_count)

        d.addCallback(got_dispatch)
        d.addCallback(got_status)
        d.addCallback(build_updated)
        return d

    def test_handleStatus_failed(self):
        # Builds may also fail (and produce no tarball).
        behavior = self.makeBehavior()
        behavior._uploadTarball = FakeMethod()
        queue_item = FakeBuildQueue(behavior)
        slave = behavior._slave
        d = behavior.dispatchBuildToSlave(queue_item, logging)

        def got_dispatch((status, info)):
            # Now that we've dispatched, get the status.
            return slave.status()

        def got_status(status):
            raw_status = (
                'BuilderStatus.WAITING',
                'BuildStatus.FAILEDTOBUILD',
                status[2],
                )
            slave_status = {
                'builder_status': raw_status[0],
                'build_status': raw_status[1],
                }
            behavior.updateSlaveStatus(raw_status, slave_status)
            self.assertNotIn('filemap', slave_status)
            return behavior.handleStatus(
                queue_item,
                BuilderInteractor.extractBuildStatus(slave_status),
                slave_status),

        def build_updated(ignored):
            self.assertEqual(BuildStatus.FAILEDTOBUILD, behavior.build.status)
            # Log file is stored.
            self.assertIsNotNone(behavior.build.log)
            self.assertEqual(1, queue_item.destroySelf.call_count)
            self.assertIn('clean', slave.call_log)
            self.assertEqual(0, behavior._uploadTarball.call_count)

        d.addCallback(got_dispatch)
        d.addCallback(got_status)
        d.addCallback(build_updated)
        return d

    def test_handleStatus_notarball(self):
        # Even if the build status is "OK," absence of a tarball will
        # not faze the Behavior class.
        behavior = self.makeBehavior()
        behavior._uploadTarball = FakeMethod()
        queue_item = FakeBuildQueue(behavior)
        slave = behavior._slave
        d = behavior.dispatchBuildToSlave(queue_item, logging)

        def got_dispatch((status, info)):
            return slave.status()

        def got_status(status):
            raw_status = (
                'BuilderStatus.WAITING',
                'BuildStatus.OK',
                status[2],
                )
            slave_status = {
                'builder_status': raw_status[0],
                'build_status': raw_status[1],
                }
            behavior.updateSlaveStatus(raw_status, slave_status)
            self.assertFalse('filemap' in slave_status)
            return behavior.handleStatus(
                queue_item,
                BuilderInteractor.extractBuildStatus(slave_status),
                slave_status),

        def build_updated(ignored):
            self.assertEqual(BuildStatus.FULLYBUILT, behavior.build.status)
            self.assertEqual(1, queue_item.destroySelf.call_count)
            self.assertIn('clean', slave.call_log)
            self.assertEqual(0, behavior._uploadTarball.call_count)

        d.addCallback(got_dispatch)
        d.addCallback(got_status)
        d.addCallback(build_updated)
        return d

    def test_handleStatus_uploads(self):
        productseries = self.makeProductSeriesWithBranchForTranslation()
        branch = productseries.branch
        behavior = self.makeBehavior(branch=branch)
        queue_item = FakeBuildQueue(behavior)
        slave = behavior._slave

        d = behavior.dispatchBuildToSlave(queue_item, logging)

        def fake_getFile(sum, file):
            dummy_tar = os.path.join(
                os.path.dirname(__file__), 'dummy_templates.tar.gz')
            tar_file = open(dummy_tar)
            copy_and_close(tar_file, file)
            return defer.succeed(None)

        def got_dispatch((status, info)):
            slave.getFile = fake_getFile
            slave.filemap = {'translation-templates.tar.gz': 'foo'}
            return slave.status()

        def got_status(status):
            slave_status = {
                'builder_status': status[0],
                'build_status': status[1],
                'build_id': status[2],
                }
            behavior.updateSlaveStatus(status, slave_status)
            return behavior.handleStatus(
                queue_item,
                BuilderInteractor.extractBuildStatus(slave_status),
                slave_status),

        def build_updated(ignored):
            self.assertEqual(BuildStatus.FULLYBUILT, behavior.build.status)
            entries = getUtility(
                ITranslationImportQueue).getAllEntries(target=productseries)
            expected_templates = [
                'po/domain.pot',
                'po-other/other.pot',
                'po-thethird/templ3.pot',
                ]
            list1 = sorted(expected_templates)
            list2 = sorted([entry.path for entry in entries])
            self.assertEqual(list1, list2)

        d.addCallback(got_dispatch)
        d.addCallback(got_status)
        d.addCallback(build_updated)
        return d


class TestTTBuildBehaviorTranslationsQueue(
        TestCaseWithFactory, MakeBehaviorMixin):
    """Test uploads to the import queue."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTTBuildBehaviorTranslationsQueue, self).setUp()

        self.queue = getUtility(ITranslationImportQueue)
        self.dummy_tar = os.path.join(
            os.path.dirname(__file__), 'dummy_templates.tar.gz')
        self.productseries = self.makeProductSeriesWithBranchForTranslation()
        self.branch = self.productseries.branch

    def test_uploadTarball(self):
        # Files from the tarball end up in the import queue.
        behavior = self.makeBehavior()
        behavior._uploadTarball(
            self.branch, file(self.dummy_tar).read(), None)

        entries = self.queue.getAllEntries(target=self.productseries)
        expected_templates = [
            'po/domain.pot',
            'po-other/other.pot',
            'po-thethird/templ3.pot',
            ]

        paths = [entry.path for entry in entries]
        self.assertContentEqual(expected_templates, paths)

    def test_uploadTarball_approved(self):
        # Uploaded template files are automatically approved.
        behavior = self.makeBehavior()
        behavior._uploadTarball(
            self.branch, file(self.dummy_tar).read(), None)

        entries = self.queue.getAllEntries(target=self.productseries)
        statuses = [entry.status for entry in entries]
        self.assertEqual(
            [RosettaImportStatus.APPROVED] * 3, statuses)

    def test_uploadTarball_importer(self):
        # Files from the tarball are owned by the branch owner.
        behavior = self.makeBehavior()
        behavior._uploadTarball(
            self.branch, file(self.dummy_tar).read(), None)

        entries = self.queue.getAllEntries(target=self.productseries)
        self.assertEqual(self.branch.owner, entries[0].importer)
