# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from storm.store import Store
from zope.component import getUtility
from zope.event import notify
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJobOld
from lp.buildmaster.interfaces.buildqueue import IBuildQueueSet
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.code.interfaces.branch import IBranchSet
from lp.code.interfaces.branchjob import IBranchJob
from lp.code.model.branchjob import BranchJob
from lp.code.model.directbranchcommit import DirectBranchCommit
from lp.codehosting.scanner import events
from lp.services.database.interfaces import IStore
from lp.services.job.model.job import Job
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )
from lp.translations.interfaces.translationtemplatesbuildjob import (
    ITranslationTemplatesBuildJobSource,
    )
from lp.translations.model.translationtemplatesbuildjob import (
    TranslationTemplatesBuildJob,
    )


def get_job_id(job):
    """Peek inside a `Job` and retrieve its id."""
    return removeSecurityProxy(job).id


class TestTranslationTemplatesBuildJob(TestCaseWithFactory):
    """Test `TranslationTemplatesBuildJob`."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTranslationTemplatesBuildJob, self).setUp()
        self.jobset = getUtility(ITranslationTemplatesBuildJobSource)
        self.branch = self.factory.makeBranch()
        self.specific_job = self.jobset.create(self.branch)

    def test_new_TranslationTemplatesBuildJob(self):
        # TranslationTemplateBuildJob implements IBuildFarmJobOld,
        # and IBranchJob.
        verifyObject(IBranchJob, self.specific_job)
        verifyObject(IBuildFarmJobOld, self.specific_job)

        # Each of these jobs knows the branch it will operate on.
        self.assertEqual(self.branch, self.specific_job.branch)

    def test_has_Job(self):
        # Associated with each TranslationTemplateBuildJob is a Job.
        base_job = self.specific_job.job
        self.assertIsInstance(base_job, Job)

        # From a Job, the TranslationTemplatesBuildJobSource can find the
        # TranslationTemplatesBuildJob back for us.
        specific_job_for_base_job = removeSecurityProxy(
            TranslationTemplatesBuildJob.getByJob(base_job))
        self.assertEqual(self.specific_job, specific_job_for_base_job)

    def test_has_BuildQueue(self):
        # There's also a BuildQueue item associated with the job.
        queueset = getUtility(IBuildQueueSet)
        job_id = get_job_id(self.specific_job.job)
        buildqueue = queueset.get(job_id)

        self.assertIsInstance(buildqueue, BuildQueue)
        self.assertEqual(job_id, get_job_id(buildqueue.job))

    def test_BuildQueue_for_arch(self):
        # BuildQueue entry is for i386 (default Ubuntu) architecture.
        queueset = getUtility(IBuildQueueSet)
        job_id = get_job_id(self.specific_job.job)
        buildqueue = queueset.get(job_id)

        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.assertEquals(
            ubuntu.currentseries.nominatedarchindep.processor,
            buildqueue.processor)

    def test_score(self):
        # For now, these jobs always score themselves at 2510.  In the
        # future however the scoring system is to be revisited.
        self.assertEqual(2510, self.specific_job.score())

    def test_cleanUp(self):
        # TranslationTemplatesBuildJob has its own customized cleanup
        # behaviour, since it's actually a BranchJob.
        job = removeSecurityProxy(self.specific_job.job)
        buildqueue = IStore(BuildQueue).find(BuildQueue, job=job).one()

        job_id = job.id
        store = Store.of(job)
        branch_name = self.branch.unique_name

        buildqueue.destroySelf()

        # BuildQueue is gone.
        self.assertIs(
            None, store.find(BuildQueue, BuildQueue.job == job_id).one())
        # Job is gone.
        self.assertIs(None, store.find(Job, Job.id == job_id).one())
        # TranslationTemplatesBuildJob is gone.
        self.assertIs(None, TranslationTemplatesBuildJob.getByJob(job_id))
        # Branch is still here.
        branch_set = getUtility(IBranchSet)
        self.assertEqual(self.branch, branch_set.getByUniqueName(branch_name))


class FakeTranslationTemplatesJobSource(TranslationTemplatesBuildJob):
    """Fake utility class.

    Allows overriding of _hasPotteryCompatibleSetup.

    How do you fake a utility that is implemented as a class, not a
    factory?  By inheriting from `TranslationTemplatesJob`, this class
    "copies" the utility.  But you can make it fake the utility's
    behavior by setting an attribute of the class (not an object!) at
    the beginning of every test.
    """
    # Fake _hasPotteryCompatibleSetup, and if so, make it give what
    # answer?
    fake_pottery_compatibility = None

    @classmethod
    def _hasPotteryCompatibleSetup(cls, branch):
        if cls.fake_pottery_compatibility is None:
            # No fake compatibility setting call the real method.
            return TranslationTemplatesBuildJob._hasPotteryCompatibleSetup(
                branch)
        else:
            # Fake pottery compatibility.
            return cls.fake_pottery_compatibility


class TestTranslationTemplatesBuildJobSource(TestCaseWithFactory):
    """Test `TranslationTemplatesBuildJobSource`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationTemplatesBuildJobSource, self).setUp()
        self.jobsource = FakeTranslationTemplatesJobSource
        self.jobsource.fake_pottery_compabitility = None

    def tearDown(self):
        self._fakePotteryCompatibleSetup(compatible=None)
        super(TestTranslationTemplatesBuildJobSource, self).tearDown()

    def _makeTranslationBranch(self, fake_pottery_compatible=None):
        """Create a branch that provides translations for a productseries."""
        if fake_pottery_compatible is None:
            self.useBzrBranches(direct_database=True)
            branch, tree = self.create_branch_and_tree()
        else:
            branch = self.factory.makeAnyBranch()
        product = removeSecurityProxy(branch.product)
        trunk = product.getSeries('trunk')
        trunk.branch = branch
        trunk.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TEMPLATES)

        self._fakePotteryCompatibleSetup(fake_pottery_compatible)

        return branch

    def _fakePotteryCompatibleSetup(self, compatible=True):
        """Mock up branch compatibility check.

        :param compatible: Whether the mock check should say that
            branches have a pottery-compatible setup, or that they
            don't.
        """
        self.jobsource.fake_pottery_compatibility = compatible

    def test_baseline(self):
        utility = getUtility(ITranslationTemplatesBuildJobSource)
        verifyObject(ITranslationTemplatesBuildJobSource, utility)

    def test_generatesTemplates(self):
        # A branch "generates templates" if it is a translation branch
        # for a productseries that imports templates from it; is not
        # private; and has a pottery compatible setup.
        # For convenience we fake the pottery compatibility here.
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)
        self.assertTrue(self.jobsource.generatesTemplates(branch))

    def test_not_pottery_compatible(self):
        # If pottery does not see any files it can work with in the
        # branch, generatesTemplates returns False.
        branch = self._makeTranslationBranch()
        self.assertFalse(self.jobsource.generatesTemplates(branch))

    def test_branch_not_used(self):
        # We don't generate templates branches not attached to series.
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)

        trunk = branch.product.getSeries('trunk')
        removeSecurityProxy(trunk).branch = None

        self.assertFalse(self.jobsource.generatesTemplates(branch))

    def test_not_importing_templates(self):
        # We don't generate templates when imports are disabled.
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)

        trunk = branch.product.getSeries('trunk')
        removeSecurityProxy(trunk).translations_autoimport_mode = (
            TranslationsBranchImportMode.NO_IMPORT)

        self.assertFalse(self.jobsource.generatesTemplates(branch))

    def test_private_branch(self):
        # We don't generate templates for private branches.
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)
        removeSecurityProxy(branch).information_type = (
            InformationType.USERDATA)
        self.assertFalse(self.jobsource.generatesTemplates(branch))

    def test_scheduleTranslationTemplatesBuild_subscribed(self):
        # If the feature is enabled, a TipChanged event for a branch that
        # generates templates will schedule a templates build.
        branch = self._makeTranslationBranch()
        removeSecurityProxy(branch).last_scanned_id = 'null:'
        commit = DirectBranchCommit(branch)
        commit.writeFile('POTFILES.in', 'foo')
        commit.commit('message')
        notify(events.TipChanged(branch, None, False))
        branchjobs = list(TranslationTemplatesBuildJob.iterReady())
        self.assertEqual(1, len(branchjobs))
        self.assertEqual(branch, branchjobs[0].branch)

    def test_scheduleTranslationTemplatesBuild(self):
        # If the feature is enabled, scheduleTranslationTemplatesBuild
        # will schedule a templates build whenever a change is pushed to
        # a branch that generates templates.
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)

        self.jobsource.scheduleTranslationTemplatesBuild(branch)

        store = IStore(BranchJob)
        branchjobs = list(store.find(BranchJob, BranchJob.branch == branch))
        self.assertEqual(1, len(branchjobs))
        self.assertEqual(branch, branchjobs[0].branch)

    def test_create(self):
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)

        specific_job = self.jobsource.create(branch)

        # A job is created with the branch URL in its metadata.
        metadata = specific_job.metadata
        self.assertIn('branch_url', metadata)
        url = metadata['branch_url']
        head = 'http://'
        self.assertEqual(head, url[:len(head)])
        tail = branch.name
        self.assertEqual(tail, url[-len(tail):])

    def test_create_with_build(self):
        branch = self._makeTranslationBranch(fake_pottery_compatible=True)
        specific_job = self.jobsource.create(branch, testing=True)
        naked_job = removeSecurityProxy(specific_job)
        self.assertEquals(naked_job._constructed_build, specific_job.build)
