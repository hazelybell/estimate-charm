# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for jobs to close bugs for accepted package uploads."""

from itertools import product

from testtools.content import text_content
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.runner import JobRunner
from lp.services.job.tests import block_on_job
from lp.soyuz.interfaces.processacceptedbugsjob import (
    IProcessAcceptedBugsJob,
    IProcessAcceptedBugsJobSource,
    )
from lp.soyuz.model.processacceptedbugsjob import (
    close_bug_ids_for_sourcepackagerelease,
    )
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
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


class TestCloseBugIDsForSourcePackageRelease(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer
    dbuser = config.IProcessAcceptedBugsJobSource.dbuser

    def setUp(self):
        super(TestCloseBugIDsForSourcePackageRelease, self).setUp()
        # Create a distribution with two series, two source package names,
        # and an SPR and a bug task for all combinations of those.
        self.distro = self.factory.makeDistribution()
        self.series = [
            self.factory.makeDistroSeries(
                distribution=self.distro, status=status)
            for status in (SeriesStatus.CURRENT, SeriesStatus.DEVELOPMENT)]
        self.spns = [self.factory.makeSourcePackageName() for _ in range(2)]
        self.bug = self.factory.makeBug()
        self.sprs = [
            self.factory.makeSourcePackageRelease(
                sourcepackagename=spn, distroseries=series,
                changelog_entry="changelog")
            for spn, series in product(self.spns, self.series)]
        self.bugtasks = [
            self.factory.makeBugTask(
                target=spr.upload_distroseries.getSourcePackage(
                    spr.sourcepackagename),
                bug=self.bug)
            for spr in self.sprs]

    def test_correct_tasks_with_distroseries(self):
        # Close the task for the correct source package name and the given
        # series.
        close_bug_ids_for_sourcepackagerelease(
            self.series[0], self.sprs[0], [self.bug.id])
        self.assertEqual(BugTaskStatus.FIXRELEASED, self.bugtasks[0].status)
        for i in (1, 2, 3):
            self.assertEqual(BugTaskStatus.NEW, self.bugtasks[i].status)

    def test_correct_message(self):
        # When closing a bug, a reasonable message is added.
        close_bug_ids_for_sourcepackagerelease(
            self.series[0], self.sprs[0], [self.bug.id])
        self.assertEqual(2, self.bug.messages.count())
        self.assertEqual(
            "This bug was fixed in the package %s"
            "\n\n---------------\nchangelog" % self.sprs[0].title,
            self.bug.messages[1].text_contents)

    def test_ignore_unknown_bug_ids(self):
        # Unknown bug IDs are ignored, and no message is added.
        close_bug_ids_for_sourcepackagerelease(
            self.series[0], self.sprs[0], [self.bug.id + 1])
        for bugtask in self.bugtasks:
            self.assertEqual(BugTaskStatus.NEW, bugtask.status)
        self.assertEqual(1, self.bug.messages.count())

    def test_private_bug(self):
        # Closing private bugs is not a problem.
        self.bug.transitionToInformationType(
            InformationType.USERDATA, self.distro.owner)
        close_bug_ids_for_sourcepackagerelease(
            self.series[0], self.sprs[0], [self.bug.id])
        self.assertEqual(BugTaskStatus.FIXRELEASED, self.bugtasks[0].status)


class TestProcessAcceptedBugsJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer
    dbuser = config.IProcessAcceptedBugsJobSource.dbuser

    def setUp(self):
        super(TestProcessAcceptedBugsJob, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()
        self.distroseries = self.publisher.breezy_autotest

    def makeJob(self, distroseries=None, spr=None, bug_ids=[1]):
        """Create a `ProcessAcceptedBugsJob`."""
        if distroseries is None:
            distroseries = self.distroseries
        if spr is None:
            spr = self.factory.makeSourcePackageRelease(
                distroseries=distroseries, changelog_entry="changelog")
        return getUtility(IProcessAcceptedBugsJobSource).create(
            distroseries, spr, bug_ids)

    def test_job_implements_IProcessAcceptedBugsJob(self):
        job = self.makeJob()
        self.assertTrue(verifyObject(IProcessAcceptedBugsJob, job))

    def test_job_source_implements_IProcessAcceptedBugsJobSource(self):
        job_source = getUtility(IProcessAcceptedBugsJobSource)
        self.assertTrue(
            verifyObject(IProcessAcceptedBugsJobSource, job_source))

    def test_create(self):
        # A ProcessAcceptedBugsJob can be created and stores its arguments.
        spr = self.factory.makeSourcePackageRelease(
            distroseries=self.distroseries, changelog_entry="changelog")
        bug_ids = [1, 2]
        job = self.makeJob(spr=spr, bug_ids=bug_ids)
        self.assertProvides(job, IProcessAcceptedBugsJob)
        self.assertEqual(self.distroseries, job.distroseries)
        self.assertEqual(spr, job.sourcepackagerelease)
        self.assertEqual(bug_ids, job.bug_ids)

    def test_run_raises_errors(self):
        # A job reports unexpected errors as exceptions.
        class Boom(Exception):
            pass

        distroseries = self.factory.makeDistroSeries()
        removeSecurityProxy(distroseries).getSourcePackage = FakeMethod(
            failure=Boom())
        job = self.makeJob(distroseries=distroseries)
        self.assertRaises(Boom, job.run)

    def test___repr__(self):
        spr = self.factory.makeSourcePackageRelease(
            distroseries=self.distroseries, changelog_entry="changelog")
        bug_ids = [1, 2]
        job = self.makeJob(spr=spr, bug_ids=bug_ids)
        self.assertEqual(
            ("<ProcessAcceptedBugsJob to close bugs [1, 2] for "
             "{spr.name}/{spr.version} ({distroseries.distribution.name} "
             "{distroseries.name})>").format(
                distroseries=self.distroseries, spr=spr),
            repr(job))

    def test_run(self):
        # A proper test run closes bugs.
        spr = self.factory.makeSourcePackageRelease(
            distroseries=self.distroseries, changelog_entry="changelog")
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(target=spr.sourcepackage, bug=bug)
        self.assertEqual(BugTaskStatus.NEW, bugtask.status)
        job = self.makeJob(spr=spr, bug_ids=[bug.id])
        JobRunner([job]).runAll()
        self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask.status)

    def test_smoke(self):
        spr = self.factory.makeSourcePackageRelease(
            distroseries=self.distroseries, changelog_entry="changelog")
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(target=spr.sourcepackage, bug=bug)
        self.assertEqual(BugTaskStatus.NEW, bugtask.status)
        self.makeJob(spr=spr, bug_ids=[bug.id])
        transaction.commit()

        out, err, exit_code = run_script(
            "LP_DEBUG_SQL=1 cronscripts/process-job-source.py -vv %s" % (
                IProcessAcceptedBugsJobSource.getName()))

        self.addDetail("stdout", text_content(out))
        self.addDetail("stderr", text_content(err))

        self.assertEqual(0, exit_code)
        self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask.status)


class TestViaCelery(TestCaseWithFactory):
    """ProcessAcceptedBugsJob runs under Celery."""

    layer = CeleryJobLayer

    def test_run(self):
        # A proper test run closes bugs.
        self.useFixture(FeatureFixture({
            "jobs.celery.enabled_classes": "ProcessAcceptedBugsJob",
        }))

        distroseries = self.factory.makeDistroSeries()
        spr = self.factory.makeSourcePackageRelease(
            distroseries=distroseries, changelog_entry="changelog")
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(target=spr.sourcepackage, bug=bug)
        self.assertEqual(BugTaskStatus.NEW, bugtask.status)
        job = getUtility(IProcessAcceptedBugsJobSource).create(
            distroseries, spr, [bug.id])
        self.assertEqual(distroseries, job.distroseries)
        self.assertEqual(spr, job.sourcepackagerelease)
        self.assertEqual([bug.id], job.bug_ids)

        with block_on_job(self):
            transaction.commit()

        self.assertEqual(JobStatus.COMPLETED, job.status)
        self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask.status)
