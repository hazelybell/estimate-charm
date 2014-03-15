# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from testtools.content import text_content
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.database.interfaces import IStore
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import (
    JobStatus,
    JobType,
    )
from lp.services.job.model.job import Job
from lp.services.job.tests import block_on_job
from lp.soyuz.enums import PackageDiffStatus
from lp.soyuz.interfaces.packagediffjob import (
    IPackageDiffJob,
    IPackageDiffJobSource,
    )
from lp.soyuz.model.packagediffjob import PackageDiffJob
from lp.soyuz.tests.test_packagediff import create_proper_job
from lp.testing import (
    run_script,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadZopelessLayer,
    )


class TestPackageDiffJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def makeJob(self):
        ppa = self.factory.makeArchive()
        from_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        to_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        diff = from_spr.requestDiffTo(ppa.owner, to_spr)
        job = IStore(Job).find(
            Job, Job.base_job_type == JobType.GENERATE_PACKAGE_DIFF).order_by(
                Job.id).last()
        return diff, PackageDiffJob(job)

    def test_job_implements_IPackageDiffJob(self):
        _, job = self.makeJob()
        self.assertTrue(verifyObject(IPackageDiffJob, job))

    def test_job_source_implements_IPackageDiffJobSource(self):
        job_source = getUtility(IPackageDiffJobSource)
        self.assertTrue(verifyObject(IPackageDiffJobSource, job_source))

    def test_iterReady(self):
        _, job1 = self.makeJob()
        removeSecurityProxy(job1).job._status = JobStatus.COMPLETED
        _, job2 = self.makeJob()
        jobs = list(PackageDiffJob.iterReady())
        self.assertEqual(1, len(jobs))

    def test_run(self):
        diff, job = self.makeJob()
        method = FakeMethod()
        removeSecurityProxy(diff).performDiff = method
        job.run()
        self.assertEqual(1, method.call_count)

    def test_smoke(self):
        diff = create_proper_job(self.factory)
        transaction.commit()
        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IPackageDiffJobSource.getName()))

        self.addDetail("stdout", text_content(out))
        self.addDetail("stderr", text_content(err))
        self.assertEqual(0, exit_code)
        self.assertEqual(PackageDiffStatus.COMPLETED, diff.status)
        self.assertIsNot(None, diff.diff_content)


class TestViaCelery(TestCaseWithFactory):
    """PackageDiffJob runs under Celery."""

    layer = CeleryJobLayer

    def test_run(self):
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'PackageDiffJob',
        }))

        diff = create_proper_job(self.factory)
        with block_on_job(self):
            transaction.commit()
        self.assertEqual(PackageDiffStatus.COMPLETED, diff.status)
        self.assertIsNot(None, diff.diff_content)
