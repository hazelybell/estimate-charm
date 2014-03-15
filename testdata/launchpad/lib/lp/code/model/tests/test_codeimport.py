# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for methods of CodeImport and CodeImportSet."""

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from sqlobject import SQLObjectNotFound
from storm.store import Store
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.enums import (
    CodeImportResultStatus,
    CodeImportReviewStatus,
    RevisionControlSystems,
    )
from lp.code.errors import (
    BranchCreatorNotMemberOfOwnerTeam,
    CodeImportAlreadyRequested,
    CodeImportAlreadyRunning,
    CodeImportNotInReviewedState,
    )
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codeimportjob import ICodeImportJobWorkflow
from lp.code.model.codeimport import CodeImportSet
from lp.code.model.codeimportevent import CodeImportEvent
from lp.code.model.codeimportjob import (
    CodeImportJob,
    CodeImportJobSet,
    )
from lp.code.model.codeimportresult import CodeImportResult
from lp.code.tests.codeimporthelpers import make_running_import
from lp.registry.interfaces.person import IPersonSet
from lp.testing import (
    login,
    login_person,
    logout,
    TestCaseWithFactory,
    time_counter,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestCodeImportCreation(TestCaseWithFactory):
    """Test the creation of CodeImports."""

    layer = DatabaseFunctionalLayer

    def test_new_svn_import_svn_scheme(self):
        """A subversion import can use the svn:// scheme."""
        code_import = CodeImportSet().new(
            registrant=self.factory.makePerson(),
            target=IBranchTarget(self.factory.makeProduct()),
            branch_name='imported',
            rcs_type=RevisionControlSystems.SVN,
            url=self.factory.getUniqueURL(scheme="svn"))
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)
        # No job is created for the import.
        self.assertIsNot(None, code_import.import_job)

    def test_reviewed_svn_import(self):
        """A specific review status can be set for a new import."""
        code_import = CodeImportSet().new(
            registrant=self.factory.makePerson(),
            target=IBranchTarget(self.factory.makeProduct()),
            branch_name='imported',
            rcs_type=RevisionControlSystems.SVN,
            url=self.factory.getUniqueURL(),
            review_status=None)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)
        # A job is created for the import.
        self.assertIsNot(None, code_import.import_job)

    def test_cvs_import_reviewed(self):
        """A new CVS code import should have REVIEWED status."""
        code_import = CodeImportSet().new(
            registrant=self.factory.makePerson(),
            target=IBranchTarget(self.factory.makeProduct()),
            branch_name='imported',
            rcs_type=RevisionControlSystems.CVS,
            cvs_root=self.factory.getUniqueURL(),
            cvs_module='module',
            review_status=None)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)
        # A job is created for the import.
        self.assertIsNot(None, code_import.import_job)

    def test_git_import_git_scheme(self):
        """A git import can have a git:// style URL."""
        code_import = CodeImportSet().new(
            registrant=self.factory.makePerson(),
            target=IBranchTarget(self.factory.makeProduct()),
            branch_name='imported',
            rcs_type=RevisionControlSystems.GIT,
            url=self.factory.getUniqueURL(scheme="git"),
            review_status=None)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)
        # A job is created for the import.
        self.assertIsNot(None, code_import.import_job)

    def test_git_import_reviewed(self):
        """A new git import is always reviewed by default."""
        code_import = CodeImportSet().new(
            registrant=self.factory.makePerson(),
            target=IBranchTarget(self.factory.makeProduct()),
            branch_name='imported',
            rcs_type=RevisionControlSystems.GIT,
            url=self.factory.getUniqueURL(),
            review_status=None)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)
        # A job is created for the import.
        self.assertIsNot(None, code_import.import_job)

    def test_bzr_import_reviewed(self):
        """A new bzr import is always reviewed by default."""
        code_import = CodeImportSet().new(
            registrant=self.factory.makePerson(),
            target=IBranchTarget(self.factory.makeProduct()),
            branch_name='mirrored',
            rcs_type=RevisionControlSystems.BZR,
            url=self.factory.getUniqueURL(),
            review_status=None)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)
        # A job is created for the import.
        self.assertIsNot(None, code_import.import_job)

    def test_junk_code_import_rejected(self):
        """You are not allowed to create code imports targetting +junk."""
        registrant = self.factory.makePerson()
        self.assertRaises(AssertionError, CodeImportSet().new,
            registrant=registrant,
            target=IBranchTarget(registrant),
            branch_name='imported',
            rcs_type=RevisionControlSystems.GIT,
            url=self.factory.getUniqueURL(),
            review_status=None)

    def test_create_source_package_import(self):
        """Test that we can create an import targetting a source package."""
        registrant = self.factory.makePerson()
        source_package = self.factory.makeSourcePackage()
        target = IBranchTarget(source_package)
        code_import = CodeImportSet().new(
            registrant=registrant,
            target=target,
            branch_name='imported',
            rcs_type=RevisionControlSystems.GIT,
            url=self.factory.getUniqueURL(),
            review_status=None)
        code_import = removeSecurityProxy(code_import)
        self.assertEqual(registrant, code_import.registrant)
        self.assertEqual(registrant, code_import.branch.owner)
        self.assertEqual(target, code_import.branch.target)
        self.assertEqual(source_package, code_import.branch.sourcepackage)
        # And a job is still created
        self.assertIsNot(None, code_import.import_job)

    def test_set_owner(self):
        """Test that we can create an import owned by someone else."""
        registrant = self.factory.makePerson()
        owner = self.factory.makeTeam()
        removeSecurityProxy(registrant).join(owner)
        source_package = self.factory.makeSourcePackage()
        target = IBranchTarget(source_package)
        code_import = CodeImportSet().new(
            registrant=registrant,
            target=target,
            branch_name='imported',
            rcs_type=RevisionControlSystems.GIT,
            url=self.factory.getUniqueURL(),
            review_status=None, owner=owner)
        code_import = removeSecurityProxy(code_import)
        self.assertEqual(registrant, code_import.registrant)
        self.assertEqual(owner, code_import.branch.owner)
        self.assertEqual(registrant, code_import.branch.registrant)
        self.assertEqual(target, code_import.branch.target)
        self.assertEqual(source_package, code_import.branch.sourcepackage)
        # And a job is still created
        self.assertIsNot(None, code_import.import_job)

    def test_registrant_must_be_in_owner(self):
        """Test that we can't create an import for an arbitrary team."""
        registrant = self.factory.makePerson()
        owner = self.factory.makeTeam()
        source_package = self.factory.makeSourcePackage()
        target = IBranchTarget(source_package)
        self.assertRaises(
            BranchCreatorNotMemberOfOwnerTeam,
            CodeImportSet().new,
            registrant=registrant,
            target=target,
            branch_name='imported',
            rcs_type=RevisionControlSystems.GIT,
            url=self.factory.getUniqueURL(),
            review_status=None, owner=owner)


class TestCodeImportDeletion(TestCaseWithFactory):
    """Test the deletion of CodeImports."""

    layer = LaunchpadFunctionalLayer

    def test_delete(self):
        """Ensure CodeImport objects can be deleted via CodeImportSet."""
        code_import = self.factory.makeCodeImport()
        CodeImportSet().delete(code_import)

    def test_deleteIncludesJob(self):
        """Ensure deleting CodeImport objects deletes associated jobs."""
        code_import = self.factory.makeCodeImport()
        login_person(getUtility(ILaunchpadCelebrities).vcs_imports.teamowner)
        job_id = code_import.import_job.id
        CodeImportJobSet().getById(job_id)
        job = CodeImportJobSet().getById(job_id)
        assert job is not None
        CodeImportSet().delete(code_import)
        job = CodeImportJobSet().getById(job_id)
        assert job is None

    def test_deleteIncludesEvent(self):
        """Ensure deleting CodeImport objects deletes associated events."""
        code_import_event = self.factory.makeCodeImportEvent()
        code_import_event_id = code_import_event.id
        CodeImportSet().delete(code_import_event.code_import)
        # CodeImportEvent.get should not raise anything.
        # But since it populates the object cache, we must invalidate it.
        Store.of(code_import_event).invalidate(code_import_event)
        self.assertRaises(
            SQLObjectNotFound, CodeImportEvent.get, code_import_event_id)

    def test_deleteIncludesResult(self):
        """Ensure deleting CodeImport objects deletes associated results."""
        code_import_result = self.factory.makeCodeImportResult()
        code_import_result_id = code_import_result.id
        CodeImportSet().delete(code_import_result.code_import)
        # CodeImportResult.get should not raise anything.
        # But since it populates the object cache, we must invalidate it.
        Store.of(code_import_result).invalidate(code_import_result)
        self.assertRaises(
            SQLObjectNotFound, CodeImportResult.get, code_import_result_id)


class TestCodeImportStatusUpdate(TestCaseWithFactory):
    """Test the status updates of CodeImports."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Log in a VCS Imports member.
        TestCaseWithFactory.setUp(self, 'david.allouche@canonical.com')
        self.import_operator = getUtility(IPersonSet).getByEmail(
            'david.allouche@canonical.com')
        # Remove existing jobs.
        for job in CodeImportJob.select():
            job.destroySelf()

    def makeApprovedImportWithPendingJob(self):
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.REVIEWED},
            self.import_operator)
        return code_import

    def makeApprovedImportWithRunningJob(self):
        code_import = self.makeApprovedImportWithPendingJob()
        job = CodeImportJobSet().getJobForMachine('machine', 10)
        self.assertEqual(code_import.import_job, job)
        return code_import

    def test_approve(self):
        # Approving a code import will create a job for it.
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.REVIEWED},
            self.import_operator)
        self.assertIsNot(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED, code_import.review_status)

    def test_suspend_no_job(self):
        # Suspending a new import has no impact on jobs.
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.SUSPENDED},
            self.import_operator)
        self.assertIs(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.SUSPENDED, code_import.review_status)

    def test_suspend_pending_job(self):
        # Suspending an approved import with a pending job, removes job.
        code_import = self.makeApprovedImportWithPendingJob()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.SUSPENDED},
            self.import_operator)
        self.assertIs(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.SUSPENDED, code_import.review_status)

    def test_suspend_running_job(self):
        # Suspending an approved import with a running job leaves job.
        code_import = self.makeApprovedImportWithRunningJob()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.SUSPENDED},
            self.import_operator)
        self.assertIsNot(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.SUSPENDED, code_import.review_status)

    def test_invalidate_no_job(self):
        # Invalidating a new import has no impact on jobs.
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.INVALID},
            self.import_operator)
        self.assertIs(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.INVALID, code_import.review_status)

    def test_invalidate_pending_job(self):
        # Invalidating an approved import with a pending job, removes job.
        code_import = self.makeApprovedImportWithPendingJob()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.INVALID},
            self.import_operator)
        self.assertIs(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.INVALID, code_import.review_status)

    def test_invalidate_running_job(self):
        # Invalidating an approved import with a running job leaves job.
        code_import = self.makeApprovedImportWithRunningJob()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.INVALID},
            self.import_operator)
        self.assertIsNot(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.INVALID, code_import.review_status)

    def test_markFailing_no_job(self):
        # Marking a new import as failing has no impact on jobs.
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.FAILING},
            self.import_operator)
        self.assertIs(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.FAILING, code_import.review_status)

    def test_markFailing_pending_job(self):
        # Marking an import with a pending job as failing, removes job.
        code_import = self.makeApprovedImportWithPendingJob()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.FAILING},
            self.import_operator)
        self.assertIs(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.FAILING, code_import.review_status)

    def test_markFailing_running_job(self):
        # Marking an import with a running job as failing leaves job.
        code_import = self.makeApprovedImportWithRunningJob()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.FAILING},
            self.import_operator)
        self.assertIsNot(None, code_import.import_job)
        self.assertEqual(
            CodeImportReviewStatus.FAILING, code_import.review_status)


class TestCodeImportResultsAttribute(TestCaseWithFactory):
    """Test the results attribute of a CodeImport."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.code_import = self.factory.makeCodeImport()

    def tearDown(self):
        super(TestCodeImportResultsAttribute, self).tearDown()
        logout()

    def test_no_results(self):
        # Initially a new code import will have no results.
        self.assertEqual([], list(self.code_import.results))

    def test_single_result(self):
        # A result associated with the code import can be accessed directly
        # from the code import object.
        import_result = self.factory.makeCodeImportResult(self.code_import)
        results = list(self.code_import.results)
        self.assertEqual(1, len(results))
        self.assertEqual(import_result, results[0])

    def test_result_ordering(self):
        # The results query will order the results by job started time, with
        # the most recent import first.
        when = time_counter(
            origin=datetime(2007, 9, 9, 12, tzinfo=pytz.UTC),
            delta=timedelta(days=1))
        first = self.factory.makeCodeImportResult(
            self.code_import, date_started=when.next())
        second = self.factory.makeCodeImportResult(
            self.code_import, date_started=when.next())
        third = self.factory.makeCodeImportResult(
            self.code_import, date_started=when.next())
        self.assertTrue(first.date_job_started < second.date_job_started)
        self.assertTrue(second.date_job_started < third.date_job_started)
        results = list(self.code_import.results)
        self.assertEqual(third, results[0])
        self.assertEqual(second, results[1])
        self.assertEqual(first, results[2])

    def test_result_ordering_paranoia(self):
        # Similar to test_result_ordering, but with results created in reverse
        # order (this wouldn't really happen) but it shows that the id of the
        # import result isn't used to sort by.
        when = time_counter(
            origin=datetime(2007, 9, 11, 12, tzinfo=pytz.UTC),
            delta=timedelta(days=-1))
        first = self.factory.makeCodeImportResult(
            self.code_import, date_started=when.next())
        second = self.factory.makeCodeImportResult(
            self.code_import, date_started=when.next())
        third = self.factory.makeCodeImportResult(
            self.code_import, date_started=when.next())
        self.assertTrue(first.date_job_started > second.date_job_started)
        self.assertTrue(second.date_job_started > third.date_job_started)
        results = list(self.code_import.results)
        self.assertEqual(first, results[0])
        self.assertEqual(second, results[1])
        self.assertEqual(third, results[2])


class TestConsecutiveFailureCount(TestCaseWithFactory):
    """Tests for `ICodeImport.consecutive_failure_count`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        login('no-priv@canonical.com')
        self.machine = self.factory.makeCodeImportMachine()
        self.machine.setOnline()

    def makeRunningJob(self, code_import):
        """Make and return a CodeImportJob object with state==RUNNING.

        This is suitable for passing into finishJob().
        """
        if code_import.import_job is None:
            job = self.factory.makeCodeImportJob(code_import)
        else:
            job = code_import.import_job
        getUtility(ICodeImportJobWorkflow).startJob(job, self.machine)
        return job

    def failImport(self, code_import):
        """Create if necessary a job for `code_import` and have it fail."""
        running_job = self.makeRunningJob(code_import)
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.FAILURE, None)

    def succeedImport(self, code_import,
                      status=CodeImportResultStatus.SUCCESS):
        """Create if necessary a job for `code_import` and have it succeed."""
        if status not in CodeImportResultStatus.successes:
            raise AssertionError(
                "succeedImport() should be called with a successful status!")
        running_job = self.makeRunningJob(code_import)
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, status, None)

    def test_consecutive_failure_count_zero_initially(self):
        # A new code import has a consecutive_failure_count of 0.
        code_import = self.factory.makeCodeImport()
        self.assertEqual(0, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_succeed(self):
        # A code import that has succeeded once has a
        # consecutive_failure_count of 0.
        code_import = self.factory.makeCodeImport()
        self.succeedImport(code_import)
        self.assertEqual(0, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_fail(self):
        # A code import that has failed once has a consecutive_failure_count
        # of 1.
        code_import = self.factory.makeCodeImport()
        self.failImport(code_import)
        self.assertEqual(1, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_succeed_succeed_no_changes(self):
        # A code import that has succeeded then succeeded with no changes has
        # a consecutive_failure_count of 0.
        code_import = self.factory.makeCodeImport()
        self.succeedImport(code_import)
        self.succeedImport(
            code_import, CodeImportResultStatus.SUCCESS_NOCHANGE)
        self.assertEqual(0, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_succeed_succeed_partial(self):
        # A code import that has succeeded then succeeded with no changes has
        # a consecutive_failure_count of 0.
        code_import = self.factory.makeCodeImport()
        self.succeedImport(code_import)
        self.succeedImport(
            code_import, CodeImportResultStatus.SUCCESS_NOCHANGE)
        self.assertEqual(0, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_fail_fail(self):
        # A code import that has failed twice has a consecutive_failure_count
        # of 2.
        code_import = self.factory.makeCodeImport()
        self.failImport(code_import)
        self.failImport(code_import)
        self.assertEqual(2, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_fail_fail_succeed(self):
        # A code import that has failed twice then succeeded has a
        # consecutive_failure_count of 0.
        code_import = self.factory.makeCodeImport()
        self.failImport(code_import)
        self.failImport(code_import)
        self.succeedImport(code_import)
        self.assertEqual(0, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_fail_succeed_fail(self):
        # A code import that has failed then succeeded then failed again has a
        # consecutive_failure_count of 1.
        code_import = self.factory.makeCodeImport()
        self.failImport(code_import)
        self.succeedImport(code_import)
        self.failImport(code_import)
        self.assertEqual(1, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_succeed_fail_succeed(self):
        # A code import that has succeeded then failed then succeeded again
        # has a consecutive_failure_count of 0.
        code_import = self.factory.makeCodeImport()
        self.succeedImport(code_import)
        self.failImport(code_import)
        self.succeedImport(code_import)
        self.assertEqual(0, code_import.consecutive_failure_count)

    def test_consecutive_failure_count_other_import_non_interference(self):
        # The failure or success of other code imports does not affect
        # consecutive_failure_count.
        code_import = self.factory.makeCodeImport()
        other_import = self.factory.makeCodeImport()
        self.failImport(code_import)
        self.assertEqual(1, code_import.consecutive_failure_count)
        self.failImport(other_import)
        self.assertEqual(1, code_import.consecutive_failure_count)
        self.succeedImport(code_import)
        self.assertEqual(0, code_import.consecutive_failure_count)
        self.succeedImport(other_import)
        self.assertEqual(0, code_import.consecutive_failure_count)
        self.failImport(code_import)
        self.assertEqual(1, code_import.consecutive_failure_count)
        self.failImport(other_import)
        self.assertEqual(1, code_import.consecutive_failure_count)


class TestTryFailingImportAgain(TestCaseWithFactory):
    """Tests for `ICodeImport.tryFailingImportAgain`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Log in a VCS Imports member.
        TestCaseWithFactory.setUp(self)
        login_person(getUtility(ILaunchpadCelebrities).vcs_imports.teamowner)

    def test_mustBeFailing(self):
        # tryFailingImportAgain only succeeds for imports that are FAILING.
        outcomes = {}
        for status in CodeImportReviewStatus.items:
            code_import = self.factory.makeCodeImport(
                review_status=CodeImportReviewStatus.NEW)
            code_import.updateFromData(
                {'review_status': status}, self.factory.makePerson())
            try:
                code_import.tryFailingImportAgain(self.factory.makePerson())
            except AssertionError:
                outcomes[status] = 'failed'
            else:
                outcomes[status] = 'succeeded'
        self.assertEqual(
            {CodeImportReviewStatus.NEW: 'failed',
             CodeImportReviewStatus.REVIEWED: 'failed',
             CodeImportReviewStatus.SUSPENDED: 'failed',
             CodeImportReviewStatus.INVALID: 'failed',
             CodeImportReviewStatus.FAILING: 'succeeded'},
            outcomes)

    def test_resetsStatus(self):
        # tryFailingImportAgain sets the review_status of the import back to
        # REVIEWED.
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.FAILING},
            self.factory.makePerson())
        code_import.tryFailingImportAgain(self.factory.makePerson())
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED,
            code_import.review_status)

    def test_requestsImport(self):
        # tryFailingImportAgain requests an import.
        code_import = self.factory.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.FAILING},
            self.factory.makePerson())
        requester = self.factory.makePerson()
        code_import.tryFailingImportAgain(requester)
        self.assertEqual(
            requester, code_import.import_job.requesting_user)


class TestRequestImport(TestCaseWithFactory):
    """Tests for `ICodeImport.requestImport`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # We have to be logged in to request imports
        TestCaseWithFactory.setUp(self, user='no-priv@canonical.com')

    def test_requestsJob(self):
        code_import = self.factory.makeCodeImport(
            git_repo_url=self.factory.getUniqueURL())
        requester = self.factory.makePerson()
        old_date = code_import.import_job.date_due
        code_import.requestImport(requester)
        self.assertEqual(requester, code_import.import_job.requesting_user)
        self.assertTrue(code_import.import_job.date_due <= old_date)

    def test_noop_if_already_requested(self):
        code_import = self.factory.makeCodeImport(
            git_repo_url=self.factory.getUniqueURL())
        requester = self.factory.makePerson()
        code_import.requestImport(requester)
        old_date = code_import.import_job.date_due
        code_import.requestImport(requester)
        # The checks don't matter so much, it's more that we don't get
        # an exception.
        self.assertEqual(requester, code_import.import_job.requesting_user)
        self.assertEqual(old_date, code_import.import_job.date_due)

    def test_optional_error_if_already_requested(self):
        code_import = self.factory.makeCodeImport(
            git_repo_url=self.factory.getUniqueURL())
        requester = self.factory.makePerson()
        code_import.requestImport(requester)
        e = self.assertRaises(
            CodeImportAlreadyRequested, code_import.requestImport, requester,
            error_if_already_requested=True)
        self.assertEqual(requester, e.requesting_user)

    def test_exception_on_disabled(self):
        # get an SVN request which is suspended
        code_import = self.factory.makeCodeImport(
            svn_branch_url=self.factory.getUniqueURL(),
            review_status=CodeImportReviewStatus.SUSPENDED)
        requester = self.factory.makePerson()
        # which leads to an exception if we try and ask for an import
        self.assertRaises(
            CodeImportNotInReviewedState, code_import.requestImport,
            requester)

    def test_exception_if_already_running(self):
        code_import = self.factory.makeCodeImport(
            git_repo_url=self.factory.getUniqueURL())
        code_import = make_running_import(factory=self.factory,
            code_import=code_import)
        requester = self.factory.makePerson()
        self.assertRaises(
            CodeImportAlreadyRunning, code_import.requestImport,
            requester)
