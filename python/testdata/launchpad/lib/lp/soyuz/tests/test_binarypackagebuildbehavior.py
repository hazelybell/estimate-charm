# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BinaryPackageBuildBehavior."""

__metaclass__ = type

import gzip
import os
import shutil
import tempfile

from storm.store import Store
from testtools.deferredruntest import AsynchronousDeferredRunTest
import transaction
from twisted.trial.unittest import TestCase as TrialTestCase
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interactor import (
    BuilderInteractor,
    extract_vitals_from_db,
    )
from lp.buildmaster.interfaces.builder import CannotBuild
from lp.buildmaster.interfaces.buildfarmjobbehavior import (
    IBuildFarmJobBehavior,
    )
from lp.buildmaster.tests.mock_slaves import (
    AbortingSlave,
    BuildingSlave,
    OkSlave,
    WaitingSlave,
    )
from lp.buildmaster.tests.test_buildfarmjobbehavior import (
    TestGetUploadMethodsMixin,
    TestHandleStatusMixin,
    )
from lp.buildmaster.tests.test_manager import MockBuilderFactory
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.job.interfaces.job import JobStatus
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.log.logger import BufferLogger
from lp.soyuz.adapters.archivedependencies import (
    get_sources_list_for_building,
    )
from lp.soyuz.enums import ArchivePurpose
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class TestBinaryBuildPackageBehavior(TestCaseWithFactory):
    """Tests for the BinaryPackageBuildBehavior.

    In particular, these tests are about how the BinaryPackageBuildBehavior
    interacts with the build slave.  We test this by using a test double that
    implements the same interface as `BuilderSlave` but instead of actually
    making XML-RPC calls, just records any method invocations along with
    interesting parameters.
    """

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTest

    def setUp(self):
        super(TestBinaryBuildPackageBehavior, self).setUp()
        switch_dbuser('testadmin')

    def assertExpectedInteraction(self, ignored, call_log, builder, build,
                                  chroot, archive, archive_purpose,
                                  component=None, extra_urls=None,
                                  filemap_names=None):
        expected = self.makeExpectedInteraction(
            builder, build, chroot, archive, archive_purpose, component,
            extra_urls, filemap_names)
        self.assertEqual(call_log, expected)

    def makeExpectedInteraction(self, builder, build, chroot, archive,
                                archive_purpose, component=None,
                                extra_urls=None, filemap_names=None):
        """Build the log of calls that we expect to be made to the slave.

        :param builder: The builder we are using to build the binary package.
        :param build: The build being done on the builder.
        :param chroot: The `LibraryFileAlias` for the chroot in which we are
            building.
        :param archive: The `IArchive` into which we are building.
        :param archive_purpose: The ArchivePurpose we are sending to the
            builder. We specify this separately from the archive because
            sometimes the behavior object has to give a different purpose
            in order to trick the slave into building correctly.
        :return: A list of the calls we expect to be made.
        """
        cookie = IBuildFarmJobBehavior(
            build.buildqueue_record.specific_job).getBuildCookie()
        ds_name = build.distro_arch_series.distroseries.name
        suite = ds_name + pocketsuffix[build.pocket]
        archives = get_sources_list_for_building(
            build, build.distro_arch_series,
            build.source_package_release.name)
        arch_indep = build.distro_arch_series.isNominatedArchIndep
        if component is None:
            component = build.current_component.name
        if filemap_names is None:
            filemap_names = []
        if extra_urls is None:
            extra_urls = []

        upload_logs = [
            ('ensurepresent', url, '', '')
            for url in [chroot.http_url] + extra_urls]

        extra_args = {
            'arch_indep': arch_indep,
            'arch_tag': build.distro_arch_series.architecturetag,
            'archive_private': archive.private,
            'archive_purpose': archive_purpose.name,
            'archives': archives,
            'build_debug_symbols': archive.build_debug_symbols,
            'ogrecomponent': component,
            'suite': suite,
            }
        build_log = [
            ('build', cookie, 'binarypackage', chroot.content.sha1,
             filemap_names, extra_args)]
        if builder.virtualized:
            result = [('echo', 'ping')] + upload_logs + build_log
        else:
            result = upload_logs + build_log
        return result

    def test_non_virtual_ppa_dispatch(self):
        # When the BinaryPackageBuildBehavior dispatches PPA builds to
        # non-virtual builders, it stores the chroot on the server and
        # requests a binary package build, lying to say that the archive
        # purpose is "PRIMARY" because this ensures that the package mangling
        # tools will run over the built packages.
        archive = self.factory.makeArchive(virtualized=False)
        slave = OkSlave()
        builder = self.factory.makeBuilder(virtualized=False)
        vitals = extract_vitals_from_db(builder)
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        build.distro_arch_series.addOrUpdateChroot(lf)
        bq = build.queueBuild()
        bq.markAsBuilding(builder)
        interactor = BuilderInteractor()
        d = interactor._startBuild(
            bq, vitals, builder, slave,
            interactor.getBuildBehavior(bq, builder, slave), BufferLogger())
        d.addCallback(
            self.assertExpectedInteraction, slave.call_log, builder, build,
            lf, archive, ArchivePurpose.PRIMARY, 'universe')
        return d

    def test_virtual_ppa_dispatch(self):
        # Make sure the builder slave gets reset before a build is
        # dispatched to it.
        archive = self.factory.makeArchive(virtualized=True)
        slave = OkSlave()
        builder = self.factory.makeBuilder(
            virtualized=True, vm_host="foohost")
        vitals = extract_vitals_from_db(builder)
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        build.distro_arch_series.addOrUpdateChroot(lf)
        bq = build.queueBuild()
        bq.markAsBuilding(builder)
        interactor = BuilderInteractor()
        d = interactor._startBuild(
            bq, vitals, builder, slave,
            interactor.getBuildBehavior(bq, builder, slave), BufferLogger())

        def check_build(ignored):
            # We expect the first call to the slave to be a resume call,
            # followed by the rest of the usual calls we expect.
            expected_resume_call = slave.call_log.pop(0)
            self.assertEqual('resume', expected_resume_call)
            self.assertExpectedInteraction(
                ignored, slave.call_log, builder, build, lf, archive,
                ArchivePurpose.PPA)
        return d.addCallback(check_build)

    def test_partner_dispatch_no_publishing_history(self):
        archive = self.factory.makeArchive(
            virtualized=False, purpose=ArchivePurpose.PARTNER)
        slave = OkSlave()
        builder = self.factory.makeBuilder(virtualized=False)
        vitals = extract_vitals_from_db(builder)
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        build.distro_arch_series.addOrUpdateChroot(lf)
        bq = build.queueBuild()
        bq.markAsBuilding(builder)
        interactor = BuilderInteractor()
        d = interactor._startBuild(
            bq, vitals, builder, slave,
            interactor.getBuildBehavior(bq, builder, slave), BufferLogger())
        d.addCallback(
            self.assertExpectedInteraction, slave.call_log, builder, build,
            lf, archive, ArchivePurpose.PARTNER)
        return d

    def test_dont_dispatch_release_builds(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        builder = self.factory.makeBuilder()
        distroseries = self.factory.makeDistroSeries(
            status=SeriesStatus.CURRENT, distribution=archive.distribution)
        distro_arch_series = self.factory.makeDistroArchSeries(
            distroseries=distroseries)
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive,
            distroarchseries=distro_arch_series,
            pocket=PackagePublishingPocket.RELEASE)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        build.distro_arch_series.addOrUpdateChroot(lf)
        candidate = build.queueBuild()
        behavior = IBuildFarmJobBehavior(candidate.specific_job)
        behavior.setBuilder(builder, None)
        e = self.assertRaises(
            AssertionError, behavior.verifyBuildRequest, BufferLogger())
        expected_message = (
            "%s (%s) can not be built for pocket %s: invalid pocket due "
            "to the series status of %s." % (
                build.title, build.id, build.pocket.name,
                build.distro_series.name))
        self.assertEqual(expected_message, str(e))

    def test_dont_dispatch_security_builds(self):
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        builder = self.factory.makeBuilder()
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive,
            pocket=PackagePublishingPocket.SECURITY)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        build.distro_arch_series.addOrUpdateChroot(lf)
        candidate = build.queueBuild()
        behavior = IBuildFarmJobBehavior(candidate.specific_job)
        behavior.setBuilder(builder, None)
        e = self.assertRaises(
            AssertionError, behavior.verifyBuildRequest, BufferLogger())
        self.assertEqual(
            'Soyuz is not yet capable of building SECURITY uploads.',
            str(e))

    def test_verifyBuildRequest(self):
        # Don't allow a virtual build on a non-virtual builder.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        builder = self.factory.makeBuilder(virtualized=False)
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive,
            pocket=PackagePublishingPocket.RELEASE)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        build.distro_arch_series.addOrUpdateChroot(lf)
        candidate = build.queueBuild()
        behavior = IBuildFarmJobBehavior(candidate.specific_job)
        behavior.setBuilder(builder, None)
        e = self.assertRaises(
            AssertionError, behavior.verifyBuildRequest, BufferLogger())
        self.assertEqual(
            'Attempt to build virtual item on a non-virtual builder.',
            str(e))

    def test_verifyBuildRequest_no_chroot(self):
        # Don't dispatch a build when the DAS has no chroot.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        builder = self.factory.makeBuilder()
        build = self.factory.makeBinaryPackageBuild(
            builder=builder, archive=archive)
        candidate = build.queueBuild()
        behavior = IBuildFarmJobBehavior(candidate.specific_job)
        behavior.setBuilder(builder, None)
        e = self.assertRaises(
            CannotBuild, behavior.verifyBuildRequest, BufferLogger())
        self.assertIn("Missing CHROOT", str(e))

    def test_getBuildCookie(self):
        # A build cookie is made up of the job type and record id.
        # The uploadprocessor relies on this format.
        build = self.factory.makeBinaryPackageBuild()
        candidate = build.queueBuild()
        behavior = IBuildFarmJobBehavior(candidate.specific_job)
        cookie = removeSecurityProxy(behavior).getBuildCookie()
        expected_cookie = "PACKAGEBUILD-%d" % build.id
        self.assertEqual(expected_cookie, cookie)


class TestBinaryBuildPackageBehaviorBuildCollection(TestCaseWithFactory):
    """Tests for the BinaryPackageBuildBehavior.

    Using various mock slaves, we check how updateBuild() behaves in
    various scenarios.
    """

    # XXX: These tests replace part of the old buildd-slavescanner.txt
    # It was checking that each call to updateBuild was sending 3 (!)
    # emails but this behaviour is so ill-defined and dependent on the
    # sample data that I've not replicated that here.  We need to
    # examine that behaviour separately somehow, but the old tests gave
    # NO clue as to what, exactly, they were testing.

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTest

    def _cleanup(self):
        if os.path.exists(config.builddmaster.root):
            shutil.rmtree(config.builddmaster.root)

    def setUp(self):
        super(TestBinaryBuildPackageBehaviorBuildCollection, self).setUp()
        switch_dbuser('testadmin')

        self.builder = self.factory.makeBuilder()
        self.interactor = BuilderInteractor()
        self.build = self.factory.makeBinaryPackageBuild(
            builder=self.builder, pocket=PackagePublishingPocket.RELEASE)
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        self.build.distro_arch_series.addOrUpdateChroot(lf)
        self.candidate = self.build.queueBuild()
        self.candidate.markAsBuilding(self.builder)
        # This is required so that uploaded files from the buildd don't
        # hang around between test runs.
        self.addCleanup(self._cleanup)

    def updateBuild(self, candidate, slave):
        bf = MockBuilderFactory(self.builder, candidate)
        return self.interactor.updateBuild(
            bf.getVitals('foo'), slave, bf, self.interactor.getBuildBehavior)

    def assertBuildProperties(self, build):
        """Check that a build happened by making sure some of its properties
        are set."""
        self.assertIsNot(None, build.builder)
        self.assertIsNot(None, build.date_finished)
        self.assertIsNot(None, build.duration)
        self.assertIsNot(None, build.log)

    def test_packagefail_collection(self):
        # When a package fails to build, make sure the builder notes are
        # stored and the build status is set as failed.
        def got_update(ignored):
            self.assertBuildProperties(self.build)
            self.assertEqual(BuildStatus.FAILEDTOBUILD, self.build.status)

        d = self.updateBuild(
            self.candidate, WaitingSlave('BuildStatus.PACKAGEFAIL'))
        return d.addCallback(got_update)

    def test_depwait_collection(self):
        # Package build was left in dependency wait.
        DEPENDENCIES = 'baz (>= 1.0.1)'

        def got_update(ignored):
            self.assertBuildProperties(self.build)
            self.assertEqual(BuildStatus.MANUALDEPWAIT, self.build.status)
            self.assertEqual(DEPENDENCIES, self.build.dependencies)

        d = self.updateBuild(
            self.candidate, WaitingSlave('BuildStatus.DEPFAIL', DEPENDENCIES))
        return d.addCallback(got_update)

    def test_chrootfail_collection(self):
        # There was a chroot problem for this build.
        def got_update(ignored):
            self.assertBuildProperties(self.build)
            self.assertEqual(BuildStatus.CHROOTWAIT, self.build.status)

        d = self.updateBuild(
            self.candidate, WaitingSlave('BuildStatus.CHROOTFAIL'))
        return d.addCallback(got_update)

    def test_builderfail_collection(self):
        # The builder failed after we dispatched the build.
        def got_update(ignored):
            self.assertEqual(
                "Builder returned BUILDERFAIL when asked for its status",
                self.builder.failnotes)
            self.assertIs(None, self.candidate.builder)
            self.assertEqual(BuildStatus.NEEDSBUILD, self.build.status)
            job = self.candidate.specific_job.job
            self.assertEqual(JobStatus.WAITING, job.status)

        d = self.updateBuild(
            self.candidate, WaitingSlave('BuildStatus.BUILDERFAIL'))
        return d.addCallback(got_update)

    def test_building_collection(self):
        # The builder is still building the package.
        def got_update(ignored):
            # The fake log is returned from the BuildingSlave() mock.
            self.assertEqual("This is a build log", self.candidate.logtail)

        d = self.updateBuild(self.candidate, BuildingSlave())
        return d.addCallback(got_update)

    def test_aborting_collection(self):
        # The builder is in the process of aborting.
        def got_update(ignored):
            self.assertEqual(
                "Waiting for slave process to be terminated",
                self.candidate.logtail)

        d = self.updateBuild(self.candidate, AbortingSlave())
        return d.addCallback(got_update)

    def test_collection_for_deleted_source(self):
        # If we collected a build for a superseded/deleted source then
        # the build should get marked superseded as the build results
        # get discarded.
        spr = removeSecurityProxy(self.build.source_package_release)
        pub = self.build.current_source_publication
        pub.requestDeletion(spr.creator)

        def got_update(ignored):
            self.assertEqual(
                BuildStatus.SUPERSEDED, self.build.status)

        d = self.updateBuild(self.candidate, WaitingSlave('BuildStatus.OK'))
        return d.addCallback(got_update)

    def test_uploading_collection(self):
        # After a successful build, the status should be UPLOADING.
        def got_update(ignored):
            self.assertEqual(self.build.status, BuildStatus.UPLOADING)
            # We do not store any upload log information when the binary
            # upload processing succeeded.
            self.assertIs(None, self.build.upload_log)

        d = self.updateBuild(self.candidate, WaitingSlave('BuildStatus.OK'))
        return d.addCallback(got_update)

    def test_givenback_collection(self):
        score = self.candidate.lastscore

        def got_update(ignored):
            self.assertIs(None, self.candidate.builder)
            self.assertIs(None, self.candidate.date_started)
            self.assertEqual(score, self.candidate.lastscore)
            self.assertEqual(BuildStatus.NEEDSBUILD, self.build.status)
            job = self.candidate.specific_job.job
            self.assertEqual(JobStatus.WAITING, job.status)

        d = self.updateBuild(
            self.candidate, WaitingSlave('BuildStatus.GIVENBACK'))
        return d.addCallback(got_update)

    def test_log_file_collection(self):
        self.build.updateStatus(BuildStatus.FULLYBUILT)
        old_tmps = sorted(os.listdir('/tmp'))

        slave = WaitingSlave('BuildStatus.OK')

        def got_log(logfile_lfa_id):
            # Grabbing logs should not leave new files in /tmp (bug #172798)
            logfile_lfa = getUtility(ILibraryFileAliasSet)[logfile_lfa_id]
            new_tmps = sorted(os.listdir('/tmp'))
            self.assertEqual(old_tmps, new_tmps)

            # The new librarian file is stored compressed with a .gz
            # extension and text/plain file type for easy viewing in
            # browsers, as it decompresses and displays the file inline.
            self.assertTrue(
                logfile_lfa.filename.endswith('_FULLYBUILT.txt.gz'))
            self.assertEqual('text/plain', logfile_lfa.mimetype)
            self.layer.txn.commit()

            # LibrarianFileAlias does not implement tell() or seek(), which
            # are required by gzip.open(), so we need to read the file out
            # of the librarian first.
            fd, fname = tempfile.mkstemp()
            self.addCleanup(os.remove, fname)
            tmp = os.fdopen(fd, 'wb')
            tmp.write(logfile_lfa.read())
            tmp.close()
            uncompressed_file = gzip.open(fname).read()

            # Now make a temp filename that getFile() can write to.
            fd, tmp_orig_file_name = tempfile.mkstemp()
            self.addCleanup(os.remove, tmp_orig_file_name)

            # Check that the original file from the slave matches the
            # uncompressed file in the librarian.
            def got_orig_log(ignored):
                orig_file_content = open(tmp_orig_file_name).read()
                self.assertEqual(orig_file_content, uncompressed_file)

            d = removeSecurityProxy(slave).getFile(
                'buildlog', tmp_orig_file_name)
            return d.addCallback(got_orig_log)

        behavior = IBuildFarmJobBehavior(self.candidate.specific_job)
        behavior.setBuilder(self.builder, slave)
        d = behavior.getLogFromSlave(self.build.buildqueue_record)
        return d.addCallback(got_log)

    def test_private_build_log_storage(self):
        # Builds in private archives should have their log uploaded to
        # the restricted librarian.

        # Go behind Storm's back since the field validator on
        # Archive.private prevents us from setting it to True with
        # existing published sources.
        Store.of(self.build).execute("""
            UPDATE archive SET private=True,buildd_secret='foo'
            WHERE archive.id = %s""" % self.build.archive.id)
        Store.of(self.build).invalidate()

        def got_update(ignored):
            # Librarian needs a commit.  :(
            self.layer.txn.commit()
            self.assertTrue(self.build.log.restricted)

        d = self.updateBuild(self.candidate, WaitingSlave('BuildStatus.OK'))
        return d.addCallback(got_update)


class MakeBinaryPackageBuildMixin:
    """Provide the makeBuild method returning a queud build."""

    def makeBuild(self):
        build = self.factory.makeBinaryPackageBuild()
        build.updateStatus(BuildStatus.BUILDING)
        build.queueBuild()
        return build


class TestGetUploadMethodsForBinaryPackageBuild(
    MakeBinaryPackageBuildMixin, TestGetUploadMethodsMixin,
    TestCaseWithFactory):
    """IPackageBuild.getUpload-related methods work with binary builds."""


class TestHandleStatusForBinaryPackageBuild(
    MakeBinaryPackageBuildMixin, TestHandleStatusMixin, TrialTestCase):
    """IPackageBuild.handleStatus works with binary builds."""
