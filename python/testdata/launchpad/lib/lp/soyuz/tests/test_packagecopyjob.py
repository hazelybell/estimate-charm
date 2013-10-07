# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for sync package jobs."""

import operator
from textwrap import dedent

from storm.store import Store
from testtools.content import text_content
from testtools.matchers import (
    MatchesRegex,
    MatchesStructure,
    )
import transaction
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.distroseriesdifferencecomment import (
    DistroSeriesDifferenceComment,
    )
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.runner import JobRunner
from lp.services.job.tests import (
    block_on_job,
    pop_remote_notifications,
    )
from lp.services.mail.sendmail import format_address_for_person
from lp.soyuz.adapters.overrides import SourceOverride
from lp.soyuz.enums import (
    ArchivePurpose,
    PackageCopyPolicy,
    PackageUploadCustomFormat,
    PackageUploadStatus,
    SourcePackageFormat,
    )
from lp.soyuz.interfaces.archive import CannotCopy
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packagecopyjob import (
    IPackageCopyJob,
    IPackageCopyJobSource,
    IPlainPackageCopyJob,
    IPlainPackageCopyJobSource,
    )
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.soyuz.interfaces.queue import IPackageUploadSet
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.packagecopyjob import PackageCopyJob
from lp.soyuz.model.queue import PackageUpload
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    admin_logged_in,
    person_logged_in,
    run_script,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.mail_helpers import pop_notifications
from lp.testing.matchers import Provides


def get_dsd_comments(dsd):
    """Retrieve `DistroSeriesDifferenceComment`s for `dsd`."""
    return IStore(dsd).find(
        DistroSeriesDifferenceComment,
        DistroSeriesDifferenceComment.distro_series_difference == dsd)


def create_proper_job(factory):
    """Create a job that will complete successfully."""
    publisher = SoyuzTestPublisher()
    with admin_logged_in():
        publisher.prepareBreezyAutotest()
    distroseries = publisher.breezy_autotest

    # Synchronise from breezy-autotest to a brand new distro derived
    # from breezy.
    breezy_archive = factory.makeArchive(
        distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
    dsp = factory.makeDistroSeriesParent(parent_series=distroseries)
    target_series = dsp.derived_series
    target_archive = factory.makeArchive(
        target_series.distribution, purpose=ArchivePurpose.PRIMARY)
    getUtility(ISourcePackageFormatSelectionSet).add(
        target_series, SourcePackageFormat.FORMAT_1_0)

    publisher.getPubSource(
        distroseries=distroseries, sourcename="libc",
        version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
        archive=breezy_archive)
    # The target archive needs ancestry so the package is
    # auto-accepted.
    publisher.getPubSource(
        distroseries=target_series, sourcename="libc",
        version="2.8-0", status=PackagePublishingStatus.PUBLISHED,
        archive=target_archive)

    source = getUtility(IPlainPackageCopyJobSource)
    requester = factory.makePerson()
    with person_logged_in(target_archive.owner):
        target_archive.newComponentUploader(requester, "main")
    return source.create(
        package_name="libc",
        source_archive=breezy_archive, target_archive=target_archive,
        target_distroseries=target_series,
        target_pocket=PackagePublishingPocket.RELEASE,
        package_version="2.8-1", include_binaries=False,
        requester=requester)


class LocalTestHelper:
    """Put test helpers that want to be in the test classes here."""

    dbuser = config.IPlainPackageCopyJobSource.dbuser

    def makeJob(self, dsd=None, **kwargs):
        """Create a `PlainPackageCopyJob` that would resolve `dsd`."""
        if dsd is None:
            dsd = self.factory.makeDistroSeriesDifference()
        source_archive = dsd.parent_series.main_archive
        target_archive = dsd.derived_series.main_archive
        target_distroseries = dsd.derived_series
        target_pocket = self.factory.getAnyPocket()
        requester = self.factory.makePerson()
        return getUtility(IPlainPackageCopyJobSource).create(
            dsd.source_package_name.name, source_archive, target_archive,
            target_distroseries, target_pocket, requester=requester,
            package_version=dsd.parent_source_version, **kwargs)

    def makePPAJob(self, source_archive=None, target_archive=None, **kwargs):
        if source_archive is None:
            source_archive = self.factory.makeArchive(
                purpose=ArchivePurpose.PPA)
        if target_archive is None:
            target_archive = self.factory.makeArchive(
                purpose=ArchivePurpose.PPA)
        source_name = self.factory.getUniqueString('src-name')
        target_series = self.factory.makeDistroSeries()
        target_pocket = self.factory.getAnyPocket()
        requester = self.factory.makePerson()
        return getUtility(IPlainPackageCopyJobSource).create(
            source_name, source_archive, target_archive,
            target_series, target_pocket, requester=requester,
            package_version="1.0", **kwargs)

    def runJob(self, job):
        """Helper to switch to the right DB user and run the job."""
        switch_dbuser(self.dbuser)
        JobRunner([job]).runAll()


class PlainPackageCopyJobTests(TestCaseWithFactory, LocalTestHelper):
    """Test case for PlainPackageCopyJob."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(PlainPackageCopyJobTests, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()
        self.distroseries = self.publisher.breezy_autotest

    def test_job_implements_IPlainPackageCopyJob(self):
        job = self.makeJob()
        self.assertTrue(verifyObject(IPlainPackageCopyJob, job))

    def test_job_source_implements_IPlainPackageCopyJobSource(self):
        job_source = getUtility(IPlainPackageCopyJobSource)
        self.assertTrue(verifyObject(IPlainPackageCopyJobSource, job_source))

    def test_getErrorRecipients_requester(self):
        # The job requester is the recipient.
        job = self.makeJob()
        email = format_address_for_person(job.requester)
        self.assertEqual([email], job.getErrorRecipients())

    def test_create(self):
        # A PackageCopyJob can be created and stores its arguments.
        distroseries = self.factory.makeDistroSeries()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        sponsored = self.factory.makePerson()
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name="foo", source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=False,
            copy_policy=PackageCopyPolicy.MASS_SYNC,
            requester=requester, sponsored=sponsored,
            phased_update_percentage=20)
        self.assertProvides(job, IPackageCopyJob)
        self.assertEqual(archive1.id, job.source_archive_id)
        self.assertEqual(archive1, job.source_archive)
        self.assertEqual(archive2.id, job.target_archive_id)
        self.assertEqual(archive2, job.target_archive)
        self.assertEqual(distroseries, job.target_distroseries)
        self.assertEqual(PackagePublishingPocket.RELEASE, job.target_pocket)
        self.assertEqual("foo", job.package_name)
        self.assertEqual("1.0-1", job.package_version)
        self.assertEqual(False, job.include_binaries)
        self.assertEqual(PackageCopyPolicy.MASS_SYNC, job.copy_policy)
        self.assertEqual(requester, job.requester)
        self.assertEqual(sponsored, job.sponsored)
        self.assertEqual(20, job.phased_update_percentage)

    def test_createMultiple_creates_one_job_per_copy(self):
        mother = self.factory.makeDistroSeriesParent()
        derived_series = mother.derived_series
        father = self.factory.makeDistroSeriesParent(
            derived_series=derived_series)
        mother_package = self.factory.makeSourcePackageName()
        father_package = self.factory.makeSourcePackageName()
        requester = self.factory.makePerson()
        job_source = getUtility(IPlainPackageCopyJobSource)
        copy_tasks = [
            (
                mother_package.name,
                "1.5mother1",
                mother.parent_series.main_archive,
                derived_series.main_archive,
                derived_series,
                PackagePublishingPocket.RELEASE,
                ),
            (
                father_package.name,
                "0.9father1",
                father.parent_series.main_archive,
                derived_series.main_archive,
                derived_series,
                PackagePublishingPocket.UPDATES,
                ),
            ]
        job_ids = list(job_source.createMultiple(copy_tasks, requester))
        jobs = list(job_source.getActiveJobs(derived_series.main_archive))
        self.assertContentEqual(job_ids, [job.id for job in jobs])
        self.assertEqual(len(copy_tasks), len(set([job.job for job in jobs])))
        # Get jobs into the same order as copy_tasks, for ease of
        # comparison.
        if jobs[0].package_name != mother_package.name:
            jobs = reversed(jobs)
        requested_copies = [
            (
                job.package_name,
                job.package_version,
                job.source_archive,
                job.target_archive,
                job.target_distroseries,
                job.target_pocket,
                )
            for job in jobs]
        self.assertEqual(copy_tasks, requested_copies)

        # The passed requester should be the same on all jobs.
        actual_requester = set(job.requester for job in jobs)
        self.assertEqual(1, len(actual_requester))
        self.assertEqual(requester, jobs[0].requester)

    def test_getActiveJobs(self):
        # getActiveJobs() can retrieve all active jobs for an archive.
        distroseries = self.factory.makeDistroSeries()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        source = getUtility(IPlainPackageCopyJobSource)
        requester = self.factory.makePerson()
        job = source.create(
            package_name="foo", source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=False,
            requester=requester)
        self.assertContentEqual([job], source.getActiveJobs(archive2))

    def test_getActiveJobs_gets_oldest_first(self):
        # getActiveJobs returns the oldest available job first.
        dsd = self.factory.makeDistroSeriesDifference()
        target_archive = dsd.derived_series.main_archive
        jobs = [self.makeJob(dsd) for counter in xrange(2)]
        source = getUtility(IPlainPackageCopyJobSource)
        self.assertEqual(jobs[0], source.getActiveJobs(target_archive)[0])

    def test_getActiveJobs_only_returns_waiting_jobs(self):
        # getActiveJobs ignores jobs that aren't in the WAITING state.
        job = self.makeJob()
        removeSecurityProxy(job).job._status = JobStatus.RUNNING
        source = getUtility(IPlainPackageCopyJobSource)
        self.assertContentEqual([], source.getActiveJobs(job.target_archive))

    def test_run_raises_errors(self):
        # A job reports unexpected errors as exceptions.
        class Boom(Exception):
            pass

        job = self.makeJob()
        removeSecurityProxy(job).attemptCopy = FakeMethod(failure=Boom())

        self.assertRaises(Boom, job.run)

    def test_run_posts_copy_failure_as_comment(self):
        # If the job fails with a CannotCopy exception, it swallows the
        # exception and posts a DistroSeriesDifferenceComment with the
        # failure message.
        dsd = self.factory.makeDistroSeriesDifference()
        self.factory.makeArchive(
            distribution=dsd.derived_series.distribution,
            purpose=ArchivePurpose.PRIMARY)
        job = self.makeJob(dsd)
        removeSecurityProxy(job).attemptCopy = FakeMethod(
            failure=CannotCopy("Server meltdown"))

        # The job's error handling will abort, so commit the objects we
        # created as would have happened in real life.
        transaction.commit()

        job.run()

        self.assertEqual(
            ["Server meltdown"],
            [comment.body_text for comment in get_dsd_comments(dsd)])

    def test_run_cannot_copy_unknown_package(self):
        # Attempting to copy an unknown package is reported as a
        # failure.
        distroseries = self.factory.makeDistroSeries()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        job_source = getUtility(IPlainPackageCopyJobSource)
        job = job_source.create(
            package_name="foo", source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=False,
            requester=requester)
        naked_job = removeSecurityProxy(job)
        naked_job.reportFailure = FakeMethod()

        self.assertRaises(CannotCopy, job.run)

        self.assertEqual(1, naked_job.reportFailure.call_count)

    def test_copy_with_packageupload(self):
        # When a PCJ with a PackageUpload gets processed, the resulting
        # publication is linked to the PackageUpload.
        spn = self.factory.getUniqueUnicode()
        pcj = self.createCopyJob(spn, 'universe', 'web', '1.0-1', True)
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [pcj.id]).one()
        pu.acceptFromQueue()
        owner = pcj.target_archive.owner
        switch_dbuser("launchpad_main")
        with person_logged_in(owner):
            pcj.target_archive.newComponentUploader(pcj.requester, 'universe')
        self.runJob(pcj)
        new_publication = pcj.target_archive.getPublishedSources(
            name=spn).one()
        self.assertEqual(new_publication.packageupload, pu)

    def test_target_ppa_non_release_pocket(self):
        # When copying to a PPA archive the target must be the release pocket.
        distroseries = self.factory.makeDistroSeries()
        package = self.factory.makeSourcePackageName()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name=package.name, source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.UPDATES,
            include_binaries=False, package_version='1.0',
            requester=requester)

        naked_job = removeSecurityProxy(job)
        naked_job.reportFailure = FakeMethod()

        self.assertRaises(CannotCopy, job.run)

        self.assertEqual(1, naked_job.reportFailure.call_count)

    def test_target_ppa_message(self):
        # When copying to a PPA archive the error message is stored in the
        # job's metadata and the job fails, but no OOPS is recorded.
        distroseries = self.factory.makeDistroSeries()
        package = self.factory.makeSourcePackageName()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        ppa = self.factory.makeArchive(distroseries.distribution)
        job = getUtility(IPlainPackageCopyJobSource).create(
            package_name=package.name, source_archive=archive1,
            target_archive=ppa, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.UPDATES,
            include_binaries=False, package_version='1.0',
            requester=self.factory.makePerson())
        transaction.commit()
        switch_dbuser(self.dbuser)
        runner = JobRunner([job])
        runner.runAll()
        self.assertEqual(JobStatus.FAILED, job.status)

        self.assertEqual(
            "PPA uploads must be for the RELEASE pocket.", job.error_message)
        self.assertEqual([], runner.oops_ids)

    def assertOopsRecorded(self, job):
        self.assertEqual(JobStatus.FAILED, job.status)
        self.assertThat(
            job.error_message, MatchesRegex(
                "Launchpad encountered an internal error while copying this"
                " package.  It was logged with id .*.  Sorry for the"
                " inconvenience."))

    def test_target_ppa_message_unexpected_error(self):
        # When copying to a PPA archive, unexpected errors are stored in the
        # job's metadata with an apologetic message.
        job = self.makePPAJob()
        removeSecurityProxy(job).attemptCopy = FakeMethod(failure=Exception())
        self.runJob(job)
        self.assertOopsRecorded(job)

    def test_target_ppa_message_integrity_error(self):
        # Even database integrity errors (which cause exceptions on commit)
        # reliably store an error message in the job's metadata.
        job = self.makePPAJob()
        spr = self.factory.makeSourcePackageRelease(archive=job.target_archive)

        def copy_integrity_error():
            """Force an integrity error."""
            spr.requestDiffTo(job.requester, spr)

        removeSecurityProxy(job).attemptCopy = copy_integrity_error
        self.runJob(job)
        # Abort the transaction to simulate the job runner script exiting.
        transaction.abort()
        self.assertOopsRecorded(job)

    def test_target_primary_redirects(self):
        # For primary archives with redirect_release_uploads set, ordinary
        # uploaders may not copy directly into the release pocket.
        job = create_proper_job(self.factory)
        job.target_archive.distribution.redirect_release_uploads = True
        # CannotCopy exceptions when copying into a primary archive are
        # swallowed, but reportFailure is still called.
        naked_job = removeSecurityProxy(job)
        naked_job.reportFailure = FakeMethod()
        transaction.commit()
        self.runJob(job)
        self.assertEqual(1, naked_job.reportFailure.call_count)

    def test_target_primary_queue_admin_bypasses_redirect(self):
        # For primary archives with redirect_release_uploads set, queue
        # admins may copy directly into the release pocket anyway.
        job = create_proper_job(self.factory)
        job.target_archive.distribution.redirect_release_uploads = True
        with person_logged_in(job.target_archive.owner):
            job.target_archive.newPocketQueueAdmin(
                job.requester, PackagePublishingPocket.RELEASE)
        # CannotCopy exceptions when copying into a primary archive are
        # swallowed, but reportFailure is still called.
        naked_job = removeSecurityProxy(job)
        naked_job.reportFailure = FakeMethod()
        transaction.commit()
        self.runJob(job)
        self.assertEqual(0, naked_job.reportFailure.call_count)

    def test_run(self):
        # A proper test run synchronizes packages.

        job = create_proper_job(self.factory)
        self.assertEqual("libc", job.package_name)
        self.assertEqual("2.8-1", job.package_version)

        switch_dbuser(self.dbuser)
        # Switch back to a db user that has permission to clean up
        # featureflag.
        self.addCleanup(switch_dbuser, 'launchpad_main')
        pop_notifications()
        job.run()

        published_sources = job.target_archive.getPublishedSources(
            name=u"libc", version="2.8-1")
        self.assertIsNot(None, published_sources.any())

        # The copy should have sent an email too. (see
        # soyuz/scripts/tests/test_copypackage.py for detailed
        # notification tests)
        emails = pop_notifications()
        self.assertEqual(len(emails), 1)

    def test_iterReady_orders_by_copy_policy(self):
        # iterReady prioritises mass-sync copies below anything else.
        self.makeJob(copy_policy=PackageCopyPolicy.MASS_SYNC)
        self.makeJob()
        self.makeJob(copy_policy=PackageCopyPolicy.MASS_SYNC)
        ready_jobs = list(getUtility(IPlainPackageCopyJobSource).iterReady())
        self.assertEqual([
            PackageCopyPolicy.INSECURE,
            PackageCopyPolicy.MASS_SYNC,
            PackageCopyPolicy.MASS_SYNC,
            ], [job.copy_policy for job in ready_jobs])

    def test_iterReady_preempt(self):
        # Ordinary ("insecure") copy jobs that arrive in the middle of a
        # long mass-sync run take precedence immediately.
        for i in range(2):
            self.makeJob(copy_policy=PackageCopyPolicy.MASS_SYNC)
        iterator = getUtility(IPlainPackageCopyJobSource).iterReady()
        self.assertEqual(
            PackageCopyPolicy.MASS_SYNC, next(iterator).copy_policy)
        self.makeJob()
        self.assertEqual(
            PackageCopyPolicy.INSECURE, next(iterator).copy_policy)
        self.assertEqual(
            PackageCopyPolicy.MASS_SYNC, next(iterator).copy_policy)
        self.assertRaises(StopIteration, next, iterator)

    def test_getOopsVars(self):
        distroseries = self.factory.makeDistroSeries()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name="foo", source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=False,
            requester=requester)
        oops_vars = job.getOopsVars()
        naked_job = removeSecurityProxy(job)
        self.assertIn(('source_archive_id', archive1.id), oops_vars)
        self.assertIn(('target_archive_id', archive2.id), oops_vars)
        self.assertIn(('target_distroseries_id', distroseries.id), oops_vars)
        self.assertIn(('package_copy_job_id', naked_job.context.id), oops_vars)
        self.assertIn(
            ('package_copy_job_type', naked_job.context.job_type.title),
            oops_vars)

    def test_smoke(self):
        archive1 = self.factory.makeArchive(self.distroseries.distribution)
        archive2 = self.factory.makeArchive(self.distroseries.distribution)
        requester = self.factory.makePerson()
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="libc",
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            archive=archive1)
        getUtility(IPlainPackageCopyJobSource).create(
            package_name="libc", source_archive=archive1,
            target_archive=archive2, target_distroseries=self.distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="2.8-1", include_binaries=False,
            requester=requester)
        with person_logged_in(archive2.owner):
            archive2.newComponentUploader(requester, "main")
        transaction.commit()

        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IPlainPackageCopyJobSource.getName()))

        self.addDetail("stdout", text_content(out))
        self.addDetail("stderr", text_content(err))

        self.assertEqual(0, exit_code)
        copied_source_package = archive2.getPublishedSources(
            name=u"libc", version="2.8-1", exact_match=True).first()
        self.assertIsNot(copied_source_package, None)

    def test___repr__(self):
        distroseries = self.factory.makeDistroSeries()
        archive1 = self.factory.makeArchive(distroseries.distribution)
        archive2 = self.factory.makeArchive(distroseries.distribution)
        requester = self.factory.makePerson()
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name="foo", source_archive=archive1,
            target_archive=archive2, target_distroseries=distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            package_version="1.0-1", include_binaries=True,
            requester=requester)
        self.assertEqual(
            ("<PlainPackageCopyJob to copy package foo from "
             "{distroseries.distribution.name}/{archive1.name} to "
             "{distroseries.distribution.name}/{archive2.name}, "
             "RELEASE pocket, in {distroseries.distribution.name} "
             "{distroseries.name}, including binaries>").format(
                distroseries=distroseries, archive1=archive1,
                archive2=archive2),
            repr(job))

    def test_getPendingJobsPerPackage_finds_jobs(self):
        # getPendingJobsPerPackage finds jobs, and the packages they
        # belong to.
        dsd = self.factory.makeDistroSeriesDifference()
        job = self.makeJob(dsd)
        job_source = getUtility(IPlainPackageCopyJobSource)
        self.assertEqual(
            {dsd.source_package_name.name: job},
            job_source.getPendingJobsPerPackage(dsd.derived_series))

    def test_getPendingJobsPerPackage_ignores_other_distroseries(self):
        # getPendingJobsPerPackage only looks for jobs on the indicated
        # distroseries.
        self.makeJob()
        other_series = self.factory.makeDistroSeries()
        job_source = getUtility(IPlainPackageCopyJobSource)
        self.assertEqual({}, job_source.getPendingJobsPerPackage(other_series))

    def test_getPendingJobsPerPackage_only_returns_pending_jobs(self):
        # getPendingJobsPerPackage ignores jobs that have already been
        # run.
        dsd = self.factory.makeDistroSeriesDifference()
        job = self.makeJob(dsd)
        job_source = getUtility(IPlainPackageCopyJobSource)
        found_by_state = {}
        for status in JobStatus.items:
            removeSecurityProxy(job).job._status = status
            result = job_source.getPendingJobsPerPackage(dsd.derived_series)
            if len(result) > 0:
                found_by_state[status] = result[dsd.source_package_name.name]
        expected = {
            JobStatus.WAITING: job,
            JobStatus.RUNNING: job,
            JobStatus.SUSPENDED: job,
        }
        self.assertEqual(expected, found_by_state)

    def test_getPendingJobsPerPackage_distinguishes_jobs(self):
        # getPendingJobsPerPackage associates the right job with the
        # right package.
        derived_series = self.factory.makeDistroSeries()
        dsds = [
            self.factory.makeDistroSeriesDifference(
                derived_series=derived_series)
            for counter in xrange(2)]
        jobs = map(self.makeJob, dsds)
        job_source = getUtility(IPlainPackageCopyJobSource)
        self.assertEqual(
            dict(zip([dsd.source_package_name.name for dsd in dsds], jobs)),
            job_source.getPendingJobsPerPackage(derived_series))

    def test_getPendingJobsPerPackage_picks_oldest_job_for_dsd(self):
        # If there are multiple jobs for one package,
        # getPendingJobsPerPackage picks the oldest.
        dsd = self.factory.makeDistroSeriesDifference()
        jobs = [self.makeJob(dsd) for counter in xrange(2)]
        job_source = getUtility(IPlainPackageCopyJobSource)
        self.assertEqual(
            {dsd.source_package_name.name: jobs[0]},
            job_source.getPendingJobsPerPackage(dsd.derived_series))

    def test_getPendingJobsPerPackage_ignores_dsds_without_jobs(self):
        # getPendingJobsPerPackage produces no dict entry for packages
        # that have no pending jobs, even if they do have DSDs.
        dsd = self.factory.makeDistroSeriesDifference()
        job_source = getUtility(IPlainPackageCopyJobSource)
        self.assertEqual(
            {}, job_source.getPendingJobsPerPackage(dsd.derived_series))

    def test_getIncompleteJobsForArchive_finds_jobs_in_right_archive(self):
        # getIncompleteJobsForArchive should return all the jobs in an
        # specified archive.
        target1 = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        target2 = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        job_source = getUtility(IPlainPackageCopyJobSource)
        target1_jobs = [
            self.makePPAJob(target_archive=target1)
            for counter in xrange(2)]
        self.makePPAJob(target2)

        pending_jobs = list(job_source.getIncompleteJobsForArchive(target1))
        self.assertContentEqual(pending_jobs, target1_jobs)

    def test_getIncompleteJobsForArchive_finds_failed_and_running_jobs(self):
        # getIncompleteJobsForArchive should return only waiting, failed
        # and running jobs.
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        for status in JobStatus.items:
            job = self.makePPAJob(target_archive=ppa)
            removeSecurityProxy(job).job._status = status

        job_source = getUtility(IPlainPackageCopyJobSource)
        found_jobs = job_source.getIncompleteJobsForArchive(ppa)
        found_statuses = [job.status for job in found_jobs]
        self.assertContentEqual(
            [JobStatus.WAITING, JobStatus.RUNNING, JobStatus.FAILED],
            found_statuses)

    def test_copying_to_main_archive_ancestry_overrides(self):
        # The job will complete right away for auto-approved copies to a
        # main archive and apply any ancestry overrides.
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive with some overridable
        # properties set to known values.
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="libc",
            component='universe', section='web',
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)

        # Now put the same named package in the target archive with
        # different override values.
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="libc",
            component='restricted', section='games',
            version="2.8-0", status=PackagePublishingStatus.PUBLISHED,
            archive=target_archive)

        # Now, run the copy job, which should auto-approve the copy and
        # override the package with the existing values in the
        # target_archive.

        source = getUtility(IPlainPackageCopyJobSource)
        requester = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.newComponentUploader(requester, "restricted")
        job = source.create(
            package_name="libc", package_version="2.8-1",
            source_archive=source_archive, target_archive=target_archive,
            target_distroseries=self.distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            include_binaries=False, requester=requester)

        self.runJob(job)

        new_publication = target_archive.getPublishedSources(
            name=u'libc', version='2.8-1').one()
        self.assertEqual('restricted', new_publication.component.name)
        self.assertEqual('games', new_publication.section.name)

        # There should also be a PackageDiff generated between the new
        # publication and the ancestry.
        [diff] = new_publication.sourcepackagerelease.package_diffs
        self.assertIsNot(None, diff)

    def test_copying_to_ppa_archive(self):
        # Packages can be copied into PPA archives.
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PPA)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive with some overridable
        # properties set to known values.
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="libc",
            component='universe', section='web',
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)

        # Now, run the copy job.
        source = getUtility(IPlainPackageCopyJobSource)
        requester = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.newComponentUploader(requester, "main")
        job = source.create(
            package_name="libc", package_version="2.8-1",
            source_archive=source_archive, target_archive=target_archive,
            target_distroseries=self.distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            include_binaries=False, requester=requester)

        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)

        new_publication = target_archive.getPublishedSources(
            name=u'libc', version='2.8-1').one()
        self.assertEqual('main', new_publication.component.name)
        self.assertEqual('web', new_publication.section.name)

    def test_copying_to_main_archive_manual_overrides(self):
        # Test processing a packagecopyjob that has manual overrides.
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive with some overridable
        # properties set to known values.
        source_package = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            component='universe', section='web',
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)

        # Now, run the copy job, which should raise an error because
        # there's no ancestry.
        source = getUtility(IPlainPackageCopyJobSource)
        requester = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.newComponentUploader(requester, "main")
        job = source.create(
            package_name="copyme", package_version="2.8-1",
            source_archive=source_archive, target_archive=target_archive,
            target_distroseries=self.distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            include_binaries=False, requester=requester)

        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        switch_dbuser("launchpad_main")

        # Add some overrides to the job.
        package = source_package.sourcepackagerelease.sourcepackagename
        restricted = getUtility(IComponentSet)['restricted']
        editors = getUtility(ISectionSet)['editors']
        override = SourceOverride(package, restricted, editors)
        job.addSourceOverride(override)

        # Accept the upload to release the job then run it.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        pu.acceptFromQueue()
        self.runJob(job)

        # The copied source should have the manual overrides, not the
        # original values.
        new_publication = target_archive.getPublishedSources(
            name=u'copyme', version='2.8-1').one()
        self.assertEqual('restricted', new_publication.component.name)
        self.assertEqual('editors', new_publication.section.name)

    def test_copying_to_main_archive_with_no_ancestry(self):
        # The job should suspend itself and create a packageupload with
        # a reference to the package_copy_job.
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive with some overridable
        # properties set to known values.
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            component='multiverse', section='web',
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)

        # There is no package of the same name already in the target
        # archive.
        existing_sources = target_archive.getPublishedSources(name=u'copyme')
        self.assertEqual(None, existing_sources.any())

        # Now, run the copy job.
        source = getUtility(IPlainPackageCopyJobSource)
        requester = self.factory.makePerson()
        job = source.create(
            package_name="copyme", package_version="2.8-1",
            source_archive=source_archive, target_archive=target_archive,
            target_distroseries=self.distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            include_binaries=False, requester=requester)

        # The job should be suspended and there's a PackageUpload with
        # its package_copy_job set.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        pu = Store.of(target_archive).find(
            PackageUpload,
            PackageUpload.package_copy_job_id == job.id).one()
        pcj = removeSecurityProxy(job).context
        self.assertEqual(pcj, pu.package_copy_job)

        # The job metadata should contain default overrides from the
        # UnknownOverridePolicy policy.
        self.assertEqual('universe', pcj.metadata['component_override'])

    def createCopyJobForSPPH(self, spph, source_archive, target_archive,
                             target_pocket=PackagePublishingPocket.RELEASE,
                             include_binaries=False, requester=None, **kwargs):
        # Helper method to create a package copy job from an SPPH.
        source = getUtility(IPlainPackageCopyJobSource)
        if requester is None:
            requester = self.factory.makePerson()
        return source.create(
            package_name=spph.sourcepackagerelease.name,
            package_version=spph.sourcepackagerelease.version,
            source_archive=source_archive, target_archive=target_archive,
            target_distroseries=spph.distroseries, target_pocket=target_pocket,
            include_binaries=include_binaries, requester=requester,
            **kwargs)

    def createCopyJob(self, sourcename, component, section, version,
                      return_job=False):
        # Helper method to create a package copy job for a package with
        # the given sourcename, component, section and version.
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive with some overridable
        # properties set to known values.
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename=sourcename,
            component=component, section=section,
            version=version, status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)

        job = self.createCopyJobForSPPH(spph, source_archive, target_archive)

        # Run the job so it gains a PackageUpload.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        if return_job:
            return job
        return removeSecurityProxy(job).context

    def test_copying_to_main_archive_debian_override_contrib(self):
        # The job uses the overrides to map debian components to
        # the right components.
        # 'contrib' gets mapped to 'multiverse'.

        # Create debian component.
        self.factory.makeComponent('contrib')
        # Create a copy job for a package in 'contrib'.
        pcj = self.createCopyJob('package', 'contrib', 'web', '2.8.1')

        self.assertEqual('multiverse', pcj.metadata['component_override'])

    def test_copying_to_main_archive_debian_override_nonfree(self):
        # The job uses the overrides to map debian components to
        # the right components.
        # 'nonfree' gets mapped to 'multiverse'.

        # Create debian component.
        self.factory.makeComponent('non-free')
        # Create a copy job for a package in 'non-free'.
        pcj = self.createCopyJob('package', 'non-free', 'web', '2.8.1')

        self.assertEqual('multiverse', pcj.metadata['component_override'])

    def test_double_copy(self):
        # Copying a package already in the target successfully does nothing.
        job = create_proper_job(self.factory)
        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)
        published_sources = job.target_archive.getPublishedSources(
            name=job.package_name)
        self.assertEqual(2, len(list(published_sources)))
        switch_dbuser("launchpad_main")
        second_job = getUtility(IPlainPackageCopyJobSource).create(
            job.package_name, job.source_archive, job.target_archive,
            job.target_distroseries, job.target_pocket,
            include_binaries=job.include_binaries,
            package_version=job.package_version, requester=job.requester)
        self.runJob(second_job)
        self.assertEqual(JobStatus.COMPLETED, second_job.status)
        published_sources = job.target_archive.getPublishedSources(
            name=job.package_name)
        self.assertEqual(2, len(list(published_sources)))

    def test_copying_resurrects_deleted_package(self):
        # A copy job can be used to resurrect previously-deleted packages.
        archive = self.factory.makeArchive(self.distroseries.distribution)
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            status=PackagePublishingStatus.DELETED, archive=archive)
        job = self.createCopyJobForSPPH(
            spph, archive, archive, requester=archive.owner)
        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)
        published_sources = archive.getPublishedSources(name=u"copyme")
        self.assertIsNotNone(published_sources.any())

    def test_copying_resurrects_deleted_package_primary_new(self):
        # Resurrecting a previously-deleted package in a PRIMARY archive
        # (which has an archive admin workflow) requires NEW queue approval.
        archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            status=PackagePublishingStatus.DELETED, archive=archive)
        job = self.createCopyJobForSPPH(
            spph, archive, archive, requester=archive.owner)
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        self.assertEqual(PackageUploadStatus.NEW, pu.status)

    def test_copying_to_main_archive_unapproved(self):
        # Uploading to a series that is in a state that precludes auto
        # approval will cause the job to suspend and a packageupload
        # created in the UNAPPROVED state.

        # The series is frozen so it won't auto-approve new packages.
        self.distroseries.status = SeriesStatus.FROZEN
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive.
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            component='multiverse', section='web',
            archive=source_archive)

        # Now put the same named package in the target archive so it has
        # ancestry.
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            version="2.8-0", status=PackagePublishingStatus.PUBLISHED,
            component='main', section='games',
            archive=target_archive)

        # Now, run the copy job.
        job = self.createCopyJobForSPPH(spph, source_archive, target_archive)

        # The job should be suspended and there's a PackageUpload with
        # its package_copy_job set in the UNAPPROVED queue.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)

        pu = Store.of(target_archive).find(
            PackageUpload,
            PackageUpload.package_copy_job_id == job.id).one()
        pcj = removeSecurityProxy(job).context
        self.assertEqual(pcj, pu.package_copy_job)
        self.assertEqual(PackageUploadStatus.UNAPPROVED, pu.status)

        # The job's metadata should contain the override ancestry from
        # the target archive.
        self.assertEqual('main', pcj.metadata['component_override'])

    def createAutoApproveEnvironment(self, create_ancestry, component_names,
                                     pocket_admin=False):
        """Create an environment for testing the auto_approve flag."""
        if create_ancestry:
            self.distroseries.status = SeriesStatus.FROZEN
        target = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source = self.factory.makeArchive()
        requester = self.factory.makePerson()
        with person_logged_in(target.owner):
            for component_name in component_names:
                target.newQueueAdmin(requester, component_name)
            if pocket_admin:
                target.newPocketQueueAdmin(
                    requester, PackagePublishingPocket.RELEASE)
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries,
            status=PackagePublishingStatus.PUBLISHED, archive=source)
        spr = spph.sourcepackagerelease
        if create_ancestry:
            self.publisher.getPubSource(
                distroseries=self.distroseries, sourcename=spr.name,
                version="%s~" % spr.version,
                status=PackagePublishingStatus.PUBLISHED, archive=target)
        return spph, source, target, requester

    def assertCanAutoApprove(self, create_ancestry, component_names,
                             pocket_admin=False):
        spph, source, target, requester = self.createAutoApproveEnvironment(
            create_ancestry, component_names, pocket_admin=pocket_admin)
        job = self.createCopyJobForSPPH(
            spph, source, target, requester=requester, auto_approve=True)
        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)
        spr = spph.sourcepackagerelease
        new_publication = target.getPublishedSources(
            name=spr.name, version=spr.version, exact_match=True).one()
        self.assertEqual(target, new_publication.archive)

    def assertCannotAutoApprove(self, create_ancestry, component_names,
                                pocket_admin=False):
        spph, source, target, requester = self.createAutoApproveEnvironment(
            create_ancestry, component_names, pocket_admin=pocket_admin)
        job = self.createCopyJobForSPPH(
            spph, source, target, requester=requester, auto_approve=True)
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)

    def test_auto_approve(self):
        # The auto_approve flag causes the job to be processed immediately,
        # even if it would normally have required manual approval.
        self.assertCanAutoApprove(True, ["main"])

    def test_auto_approve_non_queue_admin(self):
        # The auto_approve flag is ignored for people without queue admin
        # permissions.
        self.assertCannotAutoApprove(True, [])

    def test_auto_approve_pocket_queue_admin(self):
        # The auto_approve flag is honoured for people with pocket queue
        # admin permissions.
        self.assertCanAutoApprove(True, [], pocket_admin=True)

    def test_auto_approve_new(self):
        # The auto_approve flag causes copies to bypass the NEW queue.
        spph, source, target, requester = self.createAutoApproveEnvironment(
            False, ["universe"])

        # Without auto_approve, this job would be suspended and the upload
        # moved to the NEW queue.
        job = self.createCopyJobForSPPH(
            spph, source, target, requester=requester)
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        switch_dbuser("launchpad_main")
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        self.assertEqual(PackageUploadStatus.NEW, pu.status)

        # With auto_approve, the job completes immediately.
        job = self.createCopyJobForSPPH(
            spph, source, target, requester=requester, auto_approve=True)
        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)
        spr = spph.sourcepackagerelease
        new_publication = target.getPublishedSources(
            name=spr.name, version=spr.version, exact_match=True).one()
        self.assertEqual(target, new_publication.archive)

    def test_auto_approve_new_non_queue_admin(self):
        # For NEW packages, the auto_approve flag is ignored for people
        # without queue admin permissions.
        self.assertCannotAutoApprove(False, [])

    def test_auto_approve_new_pocket_queue_admin(self):
        # For NEW packages, the auto_approve flag is honoured for people
        # with pocket queue admin permissions.
        self.assertCanAutoApprove(False, [], pocket_admin=True)

    def test_copying_after_job_released(self):
        # The first pass of the job may have created a PackageUpload and
        # suspended the job.  Here we test the second run to make sure
        # that it actually copies the package.
        self.distroseries.changeslist = "changes@example.com"

        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()

        # Publish a package in the source archive.
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)

        requester = self.factory.makePerson(
            displayname="Nancy Requester", email="requester@example.com")
        with person_logged_in(target_archive.owner):
            target_archive.newComponentUploader(requester, "main")
        job = self.createCopyJobForSPPH(
            spph, source_archive, target_archive, requester=requester)

        # Run the job so it gains a PackageUpload.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        switch_dbuser("launchpad_main")

        # Accept the upload to release the job then run it.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        pu.acceptFromQueue()
        # Clear existing emails so we can see only the ones the job
        # generates later.
        pop_notifications()
        self.runJob(job)

        # The job should have set the PU status to DONE:
        self.assertEqual(PackageUploadStatus.DONE, pu.status)

        # Make sure packages were actually copied.
        existing_sources = target_archive.getPublishedSources(name=u'copyme')
        self.assertIsNot(None, existing_sources.any())

        # It would be nice to test emails in a separate test but it would
        # require all of the same setup as above again so we might as well
        # do it here.
        emails = pop_notifications(sort_key=operator.itemgetter('To'))

        # We expect an uploader email and an announcement to the changeslist.
        self.assertEqual(2, len(emails))
        self.assertIn("requester@example.com", emails[0]['To'])
        self.assertIn("changes@example.com", emails[1]['To'])
        self.assertEqual(
            "Nancy Requester <requester@example.com>", emails[1]['From'])

    def test_copying_closes_bugs(self):
        # Copying a package into a primary archive should close any bugs
        # mentioned in its changelog for versions added since the most
        # recently published version in the target.

        # Firstly, lots of boring set up.
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()
        bug280 = self.factory.makeBug()
        bug281 = self.factory.makeBug()
        bug282 = self.factory.makeBug()

        # Publish a package in the source archive and give it a changelog
        # entry that closes a bug.
        source_pub = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.distroseries, sourcepackagename="libc",
            version="2.8-2", status=PackagePublishingStatus.PUBLISHED,
            archive=source_archive)
        spr = removeSecurityProxy(source_pub).sourcepackagerelease
        changelog = dedent("""\
            libc (2.8-2) unstable; urgency=low

              * closes: %s

             -- Foo Bar <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000

            libc (2.8-1) unstable; urgency=low

              * closes: %s

             -- Foo Bar <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000

            libc (2.8-0) unstable; urgency=low

              * closes: %s

             -- Foo Bar <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000
            """ % (bug282.id, bug281.id, bug280.id))
        spr.changelog = self.factory.makeLibraryFileAlias(content=changelog)
        spr.changelog_entry = "dummy"
        self.layer.txn.commit()  # Librarian.

        # Now put the same named package in the target archive at the
        # oldest version in the changelog.
        self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="libc",
            version="2.8-0", status=PackagePublishingStatus.PUBLISHED,
            archive=target_archive)

        bugtask280 = self.factory.makeBugTask(
            target=spr.sourcepackage, bug=bug280, publish=False)
        bugtask281 = self.factory.makeBugTask(
            target=spr.sourcepackage, bug=bug281, publish=False)
        bugtask282 = self.factory.makeBugTask(
            target=spr.sourcepackage, bug=bug282, publish=False)

        # Run the copy job.
        requester = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.newComponentUploader(requester, "main")
        job = self.createCopyJobForSPPH(
            source_pub, source_archive, target_archive, requester=requester)
        self.runJob(job)

        # All the bugs apart from the one for 2.8-0 should be fixed.
        self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask282.status)
        self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask281.status)
        self.assertEqual(BugTaskStatus.NEW, bugtask280.status)

    def test_copying_unembargoes_files(self):
        # The unembargo flag causes the job to unrestrict files.
        self.distroseries.status = SeriesStatus.CURRENT
        target_archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive(private=True)

        # Publish a package in the source archive.
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            component='multiverse', section='web', archive=source_archive)
        self.publisher.getPubBinaries(
            binaryname="copyme", pub_source=spph,
            distroseries=self.distroseries,
            status=PackagePublishingStatus.PUBLISHED)
        spr = spph.sourcepackagerelease
        for source_file in spr.files:
            self.assertTrue(source_file.libraryfile.restricted)
        spr.changelog = self.factory.makeLibraryFileAlias(restricted=True)

        # Publish a package in the target archive and request a private diff
        # against it.
        old_spph = self.publisher.getPubSource(
            distroseries=self.distroseries, sourcename="copyme",
            version="2.8-0", status=PackagePublishingStatus.PUBLISHED,
            component='multiverse', section='web', archive=target_archive)
        old_spr = old_spph.sourcepackagerelease
        diff_file = self.publisher.addMockFile("diff_file", restricted=True)
        package_diff = old_spr.requestDiffTo(target_archive.owner, spr)
        package_diff.diff_content = diff_file

        # Now, run the copy job.
        requester = self.factory.makePerson()
        with person_logged_in(target_archive.owner):
            target_archive.newPocketUploader(
                requester, PackagePublishingPocket.SECURITY)
        job = self.createCopyJobForSPPH(
            spph, source_archive, target_archive,
            target_pocket=PackagePublishingPocket.SECURITY,
            include_binaries=True, requester=requester, unembargo=True)
        self.assertTrue(job.unembargo)

        # Run the job so it gains a PackageUpload.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        switch_dbuser("launchpad_main")

        # Accept the upload to release the job then run it.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        self.assertEqual(PackageUploadStatus.UNAPPROVED, pu.status)
        pu.acceptFromQueue()
        self.assertEqual(PackageUploadStatus.ACCEPTED, pu.status)
        self.runJob(job)

        # The job should have set the PU status to DONE:
        self.assertEqual(PackageUploadStatus.DONE, pu.status)

        # Make sure packages were actually copied.
        copied_sources = target_archive.getPublishedSources(
            name=u"copyme", version="2.8-1")
        self.assertNotEqual(0, copied_sources.count())
        copied_binaries = target_archive.getAllPublishedBinaries(name="copyme")
        self.assertNotEqual(0, copied_binaries.count())

        # Check that files were unembargoed.
        for copied_source in copied_sources:
            for source_file in copied_source.sourcepackagerelease.files:
                self.assertFalse(source_file.libraryfile.restricted)
            copied_spr = copied_source.sourcepackagerelease
            self.assertFalse(copied_spr.upload_changesfile.restricted)
            self.assertFalse(copied_spr.changelog.restricted)
            [diff] = copied_spr.package_diffs
            self.assertFalse(diff.diff_content.restricted)
        for copied_binary in copied_binaries:
            for binary_file in copied_binary.binarypackagerelease.files:
                self.assertFalse(binary_file.libraryfile.restricted)
            copied_build = copied_binary.binarypackagerelease.build
            self.assertFalse(copied_build.upload_changesfile.restricted)
            self.assertFalse(copied_build.log.restricted)

    def test_copy_custom_upload_files(self):
        # Copyable custom upload files are queued for republication when
        # they are copied.
        self.distroseries.status = SeriesStatus.CURRENT
        spph = self.publisher.getPubSource(
            pocket=PackagePublishingPocket.PROPOSED)
        self.publisher.getPubBinaries(
            pocket=PackagePublishingPocket.PROPOSED, pub_source=spph)
        [build] = spph.getBuilds()
        custom_file = self.factory.makeLibraryFileAlias()
        build.package_upload.addCustom(
            custom_file, PackageUploadCustomFormat.DIST_UPGRADER)
        build.package_upload.addCustom(
            self.factory.makeLibraryFileAlias(),
            PackageUploadCustomFormat.ROSETTA_TRANSLATIONS)
        # Make the new librarian file available.
        self.layer.txn.commit()

        # Create the copy job.
        requester = self.factory.makePerson()
        with person_logged_in(spph.archive.owner):
            spph.archive.newPocketUploader(
                requester, PackagePublishingPocket.UPDATES)
        job = self.createCopyJobForSPPH(
            spph, spph.archive, spph.archive, requester=requester,
            target_pocket=PackagePublishingPocket.UPDATES,
            include_binaries=True)

        # Start, accept, and run the job.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        switch_dbuser("launchpad_main")
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        self.assertEqual(PackageUploadStatus.UNAPPROVED, pu.status)
        pu.acceptFromQueue()
        self.assertEqual(PackageUploadStatus.ACCEPTED, pu.status)
        self.runJob(job)
        self.assertEqual(PackageUploadStatus.DONE, pu.status)

        uploads = list(self.distroseries.getPackageUploads(
            status=PackageUploadStatus.ACCEPTED, archive=spph.archive,
            pocket=PackagePublishingPocket.UPDATES))

        # ROSETTA_TRANSLATIONS is not a copyable type, so is not copied.
        self.assertEqual(1, len(uploads))
        upload = uploads[0]
        self.assertEqual(
            PackageUploadCustomFormat.DIST_UPGRADER,
            upload.customfiles[0].customformat)

        # The upload is targeted to the right publishing context.
        self.assertEqual(spph.archive, upload.archive)
        self.assertEqual(self.distroseries, upload.distroseries)
        self.assertEqual(PackagePublishingPocket.UPDATES, upload.pocket)

        # It contains only the custom files.
        self.assertEqual([], list(upload.sources))
        self.assertEqual([], list(upload.builds))
        self.assertEqual(
            [custom_file],
            [custom.libraryfilealias for custom in upload.customfiles])

    def test_copy_phased_update_percentage(self):
        # The copier applies any requested phased_update_percentage.
        self.distroseries.status = SeriesStatus.CURRENT
        archive = self.factory.makeArchive(
            self.distroseries.distribution, purpose=ArchivePurpose.PRIMARY)

        # Publish a test package.
        spph = self.publisher.getPubSource(
            distroseries=self.distroseries,
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.PROPOSED)
        self.publisher.getPubBinaries(
            binaryname="copyme", pub_source=spph,
            distroseries=self.distroseries,
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.PROPOSED)

        # Create and run the job.
        requester = self.factory.makePerson()
        with person_logged_in(archive.owner):
            archive.newPocketQueueAdmin(
                requester, PackagePublishingPocket.UPDATES)
        job = self.createCopyJobForSPPH(
            spph, archive, archive,
            target_pocket=PackagePublishingPocket.UPDATES,
            include_binaries=True, requester=requester,
            auto_approve=True, phased_update_percentage=0)
        self.assertEqual(0, job.phased_update_percentage)
        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)

        # Make sure packages were copied with the correct
        # phased_update_percentage.
        copied_binaries = archive.getAllPublishedBinaries(
            name=u"copyme", pocket=PackagePublishingPocket.UPDATES)
        self.assertNotEqual(0, copied_binaries.count())
        for binary in copied_binaries:
            self.assertEqual(0, binary.phased_update_percentage)

    def test_findMatchingDSDs_matches_all_DSDs_for_job(self):
        # findMatchingDSDs finds matching DSDs for any of the packages
        # in the job.
        dsd = self.factory.makeDistroSeriesDifference()
        naked_job = removeSecurityProxy(self.makeJob(dsd))
        self.assertContentEqual([dsd], naked_job.findMatchingDSDs())

    def test_findMatchingDSDs_ignores_other_source_series(self):
        # findMatchingDSDs tries to ignore DSDs that are for different
        # parent series than the job's source series.  (This can't be
        # done with perfect precision because the job doesn't keep track
        # of source distroseries, but in practice it should be good
        # enough).
        dsd = self.factory.makeDistroSeriesDifference()
        naked_job = removeSecurityProxy(self.makeJob(dsd))

        # If the dsd differs only in parent series, that's enough to
        # make it a non-match.
        removeSecurityProxy(dsd).parent_series = (
            self.factory.makeDistroSeries())

        self.assertContentEqual([], naked_job.findMatchingDSDs())

    def test_findMatchingDSDs_ignores_other_packages(self):
        # findMatchingDSDs does not return DSDs that are similar to the
        # information in the job, but are for different packages.
        dsd = self.factory.makeDistroSeriesDifference()
        self.factory.makeDistroSeriesDifference(
            derived_series=dsd.derived_series,
            parent_series=dsd.parent_series)
        naked_job = removeSecurityProxy(self.makeJob(dsd))
        self.assertContentEqual([dsd], naked_job.findMatchingDSDs())

    def test_addSourceOverride(self):
        # Test the addOverride method which adds an ISourceOverride to the
        # metadata.
        name = self.factory.makeSourcePackageName()
        component = self.factory.makeComponent()
        section = self.factory.makeSection()
        pcj = self.factory.makePlainPackageCopyJob()
        switch_dbuser('copy_packages')

        override = SourceOverride(
            source_package_name=name, component=component, section=section)
        pcj.addSourceOverride(override)

        metadata_component = getUtility(
            IComponentSet)[pcj.metadata["component_override"]]
        metadata_section = getUtility(
            ISectionSet)[pcj.metadata["section_override"]]
        matcher = MatchesStructure.byEquality(
            component=metadata_component,
            section=metadata_section)
        self.assertThat(override, matcher)

    def test_addSourceOverride_accepts_None_component_as_no_change(self):
        # When given an override with None as the component,
        # addSourceOverride will update the section but not the
        # component.
        pcj = self.factory.makePlainPackageCopyJob()
        old_component = self.factory.makeComponent()
        old_section = self.factory.makeSection()
        pcj.addSourceOverride(SourceOverride(
            source_package_name=pcj.package_name,
            component=old_component, section=old_section))
        new_section = self.factory.makeSection()
        pcj.addSourceOverride(SourceOverride(
            source_package_name=pcj.package_name,
            component=None, section=new_section))
        self.assertEqual(old_component.name, pcj.component_name)
        self.assertEqual(new_section.name, pcj.section_name)

    def test_addSourceOverride_accepts_None_section_as_no_change(self):
        # When given an override with None for the section,
        # addSourceOverride will update the component but not the
        # section.
        pcj = self.factory.makePlainPackageCopyJob()
        old_component = self.factory.makeComponent()
        old_section = self.factory.makeSection()
        pcj.addSourceOverride(SourceOverride(
            source_package_name=pcj.package_name,
            component=old_component, section=old_section))
        new_component = self.factory.makeComponent()
        pcj.addSourceOverride(SourceOverride(
            source_package_name=pcj.package_name,
            component=new_component, section=None))
        self.assertEqual(new_component.name, pcj.component_name)
        self.assertEqual(old_section.name, pcj.section_name)

    def test_getSourceOverride(self):
        # Test the getSourceOverride which gets an ISourceOverride from
        # the metadata.
        name = self.factory.makeSourcePackageName()
        component = self.factory.makeComponent()
        section = self.factory.makeSection()
        pcj = self.factory.makePlainPackageCopyJob(
            package_name=name.name, package_version="1.0")
        switch_dbuser('copy_packages')

        override = SourceOverride(
            source_package_name=name, component=component, section=section)
        pcj.addSourceOverride(override)

        self.assertEqual(override, pcj.getSourceOverride())

    def test_findSourcePublication_with_source_series_and_pocket(self):
        # The source_distroseries and source_pocket parameters cause
        # findSourcePublication to select a matching source publication.
        spph = self.publisher.getPubSource()
        other_series = self.factory.makeDistroSeries(
            distribution=spph.distroseries.distribution,
            status=SeriesStatus.DEVELOPMENT)
        spph.copyTo(
            other_series, PackagePublishingPocket.PROPOSED, spph.archive)
        spph.requestDeletion(spph.archive.owner)
        job = self.createCopyJobForSPPH(
            spph, spph.archive, spph.archive,
            target_pocket=PackagePublishingPocket.UPDATES,
            source_distroseries=spph.distroseries, source_pocket=spph.pocket)
        self.assertEqual(spph, job.findSourcePublication())

    def test_getPolicyImplementation_returns_policy(self):
        # getPolicyImplementation returns the ICopyPolicy that was
        # chosen for the job.
        dsd = self.factory.makeDistroSeriesDifference()
        for policy in PackageCopyPolicy.items:
            naked_job = removeSecurityProxy(
                self.makeJob(dsd, copy_policy=policy))
            self.assertEqual(
                policy, naked_job.getPolicyImplementation().enum_value)

    def test_rejects_PackageUpload_when_job_fails(self):
        # If a PCJ with a PU fails when running then we need to ensure the
        # PU gets rejected.
        target_archive = self.factory.makeArchive(
            purpose=ArchivePurpose.PRIMARY)
        source_archive = self.factory.makeArchive()
        source_pub = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename="copyme",
            version="1.0",
            archive=source_archive,
            status=PackagePublishingStatus.PUBLISHED)
        job = self.createCopyJobForSPPH(
            source_pub, source_archive, target_archive)

        # Run the job so it gains a PackageUpload.
        self.runJob(job)
        self.assertEqual(JobStatus.SUSPENDED, job.status)
        switch_dbuser("launchpad_main")

        # Patch the job's attemptCopy() method so it just raises an
        # exception.
        naked_job = removeSecurityProxy(job)
        self.patch(naked_job, "attemptCopy", FakeMethod(failure=Exception()))

        # Accept the upload to release the job then run it.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [removeSecurityProxy(job).context.id]).one()
        pu.acceptFromQueue()
        self.runJob(job)

        # The job should have set the PU status to REJECTED.
        self.assertEqual(PackageUploadStatus.REJECTED, pu.status)

    def test_diffs_are_not_created_when_only_copying_binaries(self):
        # The job will not fail because a packagediff from a source that wasn't
        # copied could not be created.
        archive = self.distroseries.distribution.main_archive
        source = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.distroseries, sourcepackagename="copyme",
            version="2.8-1", status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE, archive=archive,
            component='multiverse')
        spph = self.factory.makeSourcePackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.UPDATES, archive=archive,
            distroseries=self.distroseries,
            sourcepackagerelease=source.sourcepackagerelease)
        das = self.factory.makeDistroArchSeries(distroseries=self.distroseries)
        self.factory.makeBinaryPackagePublishingHistory(
            status=PackagePublishingStatus.PUBLISHED, distroarchseries=das,
            pocket=PackagePublishingPocket.UPDATES, archive=archive,
            source_package_release=spph.sourcepackagerelease,
            architecturespecific=True)
        requester = self.factory.makePerson()
        with person_logged_in(archive.owner):
            archive.newComponentUploader(requester, 'multiverse')
        source = getUtility(IPlainPackageCopyJobSource)
        job = source.create(
            package_name="copyme", package_version="2.8-1",
            source_archive=archive, target_archive=archive,
            target_distroseries=self.distroseries,
            target_pocket=PackagePublishingPocket.RELEASE,
            include_binaries=True, requester=requester)
        self.runJob(job)
        self.assertEqual(JobStatus.COMPLETED, job.status)
        self.assertContentEqual(
            [], archive.getPublishedSources(
                status=PackagePublishingStatus.PENDING))
        self.assertEqual(
            1, archive.getPublishedOnDiskBinaries(
                status=PackagePublishingStatus.PENDING).count())


class TestViaCelery(TestCaseWithFactory):
    """PackageCopyJob runs under Celery."""

    layer = CeleryJobLayer

    def test_run(self):
        # A proper test run synchronizes packages.
        # Turn on Celery handling of PCJs.
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'PlainPackageCopyJob',
        }))

        job = create_proper_job(self.factory)
        self.assertEqual("libc", job.package_name)
        self.assertEqual("2.8-1", job.package_version)

        with block_on_job(self):
            transaction.commit()

        published_sources = job.target_archive.getPublishedSources(
            name=u"libc", version="2.8-1")
        self.assertIsNot(None, published_sources.any())

        # The copy should have sent an email too. (see
        # soyuz/scripts/tests/test_copypackage.py for detailed
        # notification tests)
        emails = pop_remote_notifications()
        self.assertEqual(1, len(emails))

    def test_resume_from_queue(self):
        # Accepting a suspended copy from the queue sends it back
        # through celery.
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'PlainPackageCopyJob',
        }))

        source_pub = self.factory.makeSourcePackagePublishingHistory(
            component=u"main", status=PackagePublishingStatus.PUBLISHED)
        target_series = self.factory.makeDistroSeries()
        getUtility(ISourcePackageFormatSelectionSet).add(
            target_series, SourcePackageFormat.FORMAT_1_0)
        requester = self.factory.makePerson()
        with person_logged_in(target_series.main_archive.owner):
            target_series.main_archive.newComponentUploader(requester, u"main")
        job = getUtility(IPlainPackageCopyJobSource).create(
            package_name=source_pub.source_package_name,
            package_version=source_pub.source_package_version,
            source_archive=source_pub.archive,
            target_archive=target_series.main_archive,
            target_distroseries=target_series,
            target_pocket=PackagePublishingPocket.PROPOSED,
            include_binaries=False, requester=requester)

        # Run the job once. There's no ancestry so it will be suspended
        # and added to the queue.
        with block_on_job(self):
            transaction.commit()
        self.assertEqual(JobStatus.SUSPENDED, job.status)

        # Approve its queue entry and rerun to completion.
        pu = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
            [job.id]).one()
        with admin_logged_in():
            pu.acceptFromQueue()
        self.assertEqual(JobStatus.WAITING, job.status)

        with block_on_job(self):
            transaction.commit()
        self.assertEqual(JobStatus.COMPLETED, job.status)
        self.assertEqual(
            1,
            target_series.main_archive.getPublishedSources(
                name=source_pub.source_package_name).count())


class TestPlainPackageCopyJobPermissions(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_extendMetadata_edit_privilege_by_queue_admin(self):
        # A person who has any queue admin rights can edit the copy job.
        archive = self.factory.makeArchive(purpose=ArchivePurpose.PRIMARY)
        pcj = self.factory.makePlainPackageCopyJob(target_archive=archive)
        queue_admin = self.factory.makePerson()
        with person_logged_in(pcj.target_archive.owner):
            pcj.target_archive.newQueueAdmin(queue_admin, "main")
        with person_logged_in(queue_admin):
            # This won't blow up.
            pcj.extendMetadata({})

    def test_extendMetadata_edit_privilege_by_other(self):
        # Random people cannot edit the copy job.
        pcj = self.factory.makePlainPackageCopyJob()
        self.assertRaises(Unauthorized, getattr, pcj, "extendMetadata")

    def test_PPA_edit_privilege_by_owner(self):
        # A PCJ for a PPA allows the PPA owner to edit it.
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        pcj = self.factory.makePlainPackageCopyJob(target_archive=ppa)
        with person_logged_in(ppa.owner):
            # This will not throw an exception.
            pcj.extendMetadata({})

    def test_PPA_edit_privilege_by_other(self):
        # A PCJ for a PPA does not allow non-owners to edit it.
        ppa = self.factory.makeArchive(purpose=ArchivePurpose.PPA)
        pcj = self.factory.makePlainPackageCopyJob(target_archive=ppa)
        person = self.factory.makePerson()
        with person_logged_in(person):
            self.assertRaises(Unauthorized, getattr, pcj, "extendMetadata")


class TestPlainPackageCopyJobDbPrivileges(TestCaseWithFactory,
                                          LocalTestHelper):
    """Test that `PlainPackageCopyJob` has the database privileges it needs.

    This test looks for errors, not failures.  It's here only to see that
    these operations don't run into any privilege limitations.
    """

    layer = LaunchpadZopelessLayer

    def test_findMatchingDSDs(self):
        job = self.makeJob()
        switch_dbuser(self.dbuser)
        removeSecurityProxy(job).findMatchingDSDs()

    def test_reportFailure(self):
        job = self.makeJob()
        switch_dbuser(self.dbuser)
        removeSecurityProxy(job).reportFailure("Mommy it hurts")


class TestPackageCopyJobSource(TestCaseWithFactory):
    """Test the `IPackageCopyJob` utility."""

    layer = ZopelessDatabaseLayer

    def test_implements_interface(self):
        job_source = getUtility(IPackageCopyJobSource)
        self.assertThat(job_source, Provides(IPackageCopyJobSource))

    def test_wrap_accepts_None(self):
        job_source = getUtility(IPackageCopyJobSource)
        self.assertIs(None, job_source.wrap(None))

    def test_wrap_wraps_PlainPackageCopyJob(self):
        original_ppcj = self.factory.makePlainPackageCopyJob()
        IStore(PackageCopyJob).flush()
        pcj = IStore(PackageCopyJob).get(PackageCopyJob, original_ppcj.id)
        self.assertNotEqual(None, pcj)
        job_source = getUtility(IPackageCopyJobSource)
        self.assertEqual(original_ppcj, job_source.wrap(pcj))
