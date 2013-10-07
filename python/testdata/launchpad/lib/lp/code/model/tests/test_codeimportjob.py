# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for CodeImportJob and CodeImportJobWorkflow."""

__metaclass__ = type

__all__ = [
    'NewEvents',
    ]

from datetime import datetime
import StringIO
import unittest

from pytz import UTC
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.enums import (
    CodeImportEventType,
    CodeImportJobState,
    CodeImportResultStatus,
    CodeImportReviewStatus,
    )
from lp.code.interfaces.codeimport import ICodeImportSet
from lp.code.interfaces.codeimportevent import ICodeImportEventSet
from lp.code.interfaces.codeimportjob import (
    ICodeImportJobSet,
    ICodeImportJobWorkflow,
    )
from lp.code.interfaces.codeimportresult import ICodeImportResult
from lp.code.model.codeimportjob import CodeImportJob
from lp.code.model.codeimportresult import CodeImportResult
from lp.code.tests.codeimporthelpers import (
    make_finished_import,
    make_running_import,
    )
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.interfaces.client import ILibrarianClient
from lp.services.webapp import canonical_url
from lp.testing import (
    ANONYMOUS,
    login,
    login_celebrity,
    logout,
    TestCaseWithFactory,
    with_anonymous_login,
    with_celebrity_logged_in,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.pages import get_feedback_messages


def login_for_code_imports():
    """Login as a member of the vcs-imports team.

    CodeImports are currently hidden from regular users currently. Members of
    the vcs-imports team and can access the objects freely.
    """
    return login_celebrity('vcs_imports')


class TestCodeImportJobSet(TestCaseWithFactory):
    """Unit tests for the CodeImportJobSet utility."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobSet, self).setUp()
        login_for_code_imports()

    def test_getByIdExisting(self):
        # CodeImportJobSet.getById retrieves a CodeImportJob by database id.
        made_job = self.factory.makeCodeImportJob()
        found_job = getUtility(ICodeImportJobSet).getById(made_job.id)
        self.assertEqual(made_job, found_job)

    def test_getByIdNotExisting(self):
        # CodeImportJobSet.getById returns None if there is not CodeImportJob
        # with the specified id.
        no_job = getUtility(ICodeImportJobSet).getById(-1)
        self.assertIs(None, no_job)


class TestCodeImportJobSetGetJobForMachine(TestCaseWithFactory):
    """Tests for the CodeImportJobSet.getJobForMachine method.

    For brevity, these test cases describe jobs using specs: a 2- or 3-tuple::

        (<job state>, <date_due time delta>, <requesting user, if present>).

    The time delta is measured in days relative to the present, so using a
    value of -1 creates a job with a date_due of 1 day ago.  The instance
    method makeJob() creates actual CodeImportJob objects from these specs.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Login so we can access the code import system, delete all jobs in
        # the sample data and set up some objects.
        super(TestCodeImportJobSetGetJobForMachine, self).setUp()
        login_for_code_imports()
        for job in CodeImportJob.select():
            job.destroySelf()
        self.machine = self.factory.makeCodeImportMachine(set_online=True)

    def makeJob(self, state, date_due_delta, requesting_user=None):
        """Create a CodeImportJob object from a spec."""
        code_import = self.factory.makeCodeImport(
            review_status=CodeImportReviewStatus.NEW)
        job = self.factory.makeCodeImportJob(code_import)
        if state == CodeImportJobState.RUNNING:
            getUtility(ICodeImportJobWorkflow).startJob(job, self.machine)
        naked_job = removeSecurityProxy(job)
        naked_job.date_due = UTC_NOW + u'%d days' % date_due_delta
        naked_job.requesting_user = requesting_user
        return job

    def assertJobIsSelected(self, desired_job):
        """Assert that the expected job is chosen by getJobForMachine."""
        observed_job = getUtility(ICodeImportJobSet).getJobForMachine(
            self.machine.hostname, worker_limit=10)
        self.assert_(observed_job is not None, "No job was selected.")
        self.assertEqual(desired_job, observed_job,
                         "Expected job not selected.")

    def assertNoJobSelected(self):
        """Assert that no job is selected."""
        observed_job = getUtility(ICodeImportJobSet).getJobForMachine(
            'machine', worker_limit=10)
        self.assert_(observed_job is None, "Job unexpectedly selected.")

    def test_nothingSelectedIfNothingCreated(self):
        # There are no due jobs pending if we don't create any (this
        # is mostly a test of setUp() above).
        self.assertNoJobSelected()

    def test_simple(self):
        # The simplest case: there is one job, which is due.
        self.assertJobIsSelected(
            self.makeJob(CodeImportJobState.PENDING, -1))

    def test_nothingDue(self):
        # When there is a PENDING job but it is due in the future, no
        # job should be returned.
        self.makeJob(CodeImportJobState.PENDING, +1)
        self.assertNoJobSelected()

    def test_ignoreNonPendingJobs(self):
        # Only PENDING jobs are returned -- it doesn't make sense to allocate
        # a job that is already RUNNING to a machine.
        self.makeJob(CodeImportJobState.RUNNING, -1)
        self.assertNoJobSelected()

    def test_mostOverdueJobsFirst(self):
        # The job that was due longest ago should be selected, then the next
        # longest, etc.
        five_days_ago = self.makeJob(CodeImportJobState.PENDING, -5)
        two_days_ago = self.makeJob(CodeImportJobState.PENDING, -2)
        ten_days_ago = self.makeJob(CodeImportJobState.PENDING, -10)
        self.assertJobIsSelected(ten_days_ago)
        self.assertJobIsSelected(five_days_ago)
        self.assertJobIsSelected(two_days_ago)

    def test_requestedJobWins(self):
        # A job that is requested by a user is selected over ones that
        # are not, even over jobs that are more overdue.
        person = self.factory.makePerson()
        self.makeJob(CodeImportJobState.PENDING, -5)
        self.makeJob(CodeImportJobState.PENDING, -2)
        self.assertJobIsSelected(
            self.makeJob(CodeImportJobState.PENDING, -1, person))

    def test_mostOverdueRequestedJob(self):
        # When multiple jobs are requested by users, we go back to the
        # "most overdue wins" behaviour.
        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        person_c = self.factory.makePerson()
        five_days_ago = self.makeJob(
            CodeImportJobState.PENDING, -5, person_b)
        two_days_ago = self.makeJob(
            CodeImportJobState.PENDING, -2, person_a)
        ten_days_ago = self.makeJob(
            CodeImportJobState.PENDING, -10, person_c)
        self.assertJobIsSelected(ten_days_ago)
        self.assertJobIsSelected(five_days_ago)
        self.assertJobIsSelected(two_days_ago)

    def test_independentOfCreationOrder(self):
        # The order the jobs are created doesn't affect the outcome (the way
        # the other tests are written, an implementation that returned the
        # most recently created due job would pass).
        ten_days_ago = self.makeJob(CodeImportJobState.PENDING, -10)
        five_days_ago = self.makeJob(CodeImportJobState.PENDING, -5)
        two_days_ago = self.makeJob(CodeImportJobState.PENDING, -2)
        self.assertJobIsSelected(ten_days_ago)
        self.assertJobIsSelected(five_days_ago)
        self.assertJobIsSelected(two_days_ago)

    def test_notReturnedTwice(self):
        # Once a job has been selected by getJobForMachine, it should not be
        # selected again.
        self.assertJobIsSelected(
            self.makeJob(CodeImportJobState.PENDING, -1))
        self.assertNoJobSelected()


class ReclaimableJobTests(TestCaseWithFactory):
    """Helpers for tests that need to create reclaimable jobs."""

    LIMIT = config.codeimportworker.maximum_heartbeat_interval

    def setUp(self):
        super(ReclaimableJobTests, self).setUp()
        login_for_code_imports()
        for job in CodeImportJob.select():
            job.destroySelf()

    def makeJobWithHeartbeatInPast(self, seconds_in_past):
        code_import = make_running_import(factory=self.factory)
        naked_job = removeSecurityProxy(code_import.import_job)
        naked_job.heartbeat = UTC_NOW + u'%d seconds' % -seconds_in_past
        return code_import.import_job

    def assertReclaimableJobs(self, jobs):
        """Assert that the set of reclaimable jobs equals `jobs`."""
        self.assertEqual(
            set(jobs),
            set(getUtility(ICodeImportJobSet).getReclaimableJobs()))


class TestCodeImportJobSetGetReclaimableJobs(ReclaimableJobTests):
    """Tests for the CodeImportJobSet.getReclaimableJobs method."""

    layer = DatabaseFunctionalLayer

    def test_upToDateJob(self):
        # A job that was updated recently is not considered reclaimable.
        self.makeJobWithHeartbeatInPast(self.LIMIT/2)
        self.assertReclaimableJobs([])

    def test_staleJob(self):
        # A job that hasn't been updated for a long time is considered
        # reclaimable.
        stale_job = self.makeJobWithHeartbeatInPast(self.LIMIT * 2)
        self.assertReclaimableJobs([stale_job])

    def test_pendingJob(self):
        # A pending job (which cannot have a non-NULL heartbeat) is
        # not returned.
        pending_job = self.factory.makeCodeImportJob()
        self.assertEqual(
            pending_job.state, CodeImportJobState.PENDING,
            "makeCodeImportJob() made non-pending job!")
        self.assertReclaimableJobs([])

    def test_staleAndFreshJobs(self):
        # If there are both fresh and stake jobs in the DB, only the
        # stale ones are returned by getReclaimableJobs().
        self.makeJobWithHeartbeatInPast(self.LIMIT/2)
        stale_job = self.makeJobWithHeartbeatInPast(self.LIMIT*2)
        self.assertReclaimableJobs([stale_job])


class TestCodeImportJobSetGetJobForMachineGardening(ReclaimableJobTests):
    """Test that getJobForMachine gardens stale code import jobs."""

    layer = DatabaseFunctionalLayer

    def test_getJobForMachineGardens(self):
        # getJobForMachine reclaims all reclaimable jobs each time it is
        # called.
        stale_job = self.makeJobWithHeartbeatInPast(self.LIMIT*2)
        # We assume that this is the only reclaimable job.
        self.assertReclaimableJobs([stale_job])
        machine = self.factory.makeCodeImportMachine(set_online=True)
        login(ANONYMOUS)
        getUtility(ICodeImportJobSet).getJobForMachine(
            machine.hostname, worker_limit=10)
        login_for_code_imports()
        # Now there are no reclaimable jobs.
        self.assertReclaimableJobs([])


class AssertFailureMixin:
    """Helper to test assert statements."""

    def assertFailure(self, message, callable_obj, *args, **kwargs):
        """Fail unless an AssertionError with the specified message is raised
        by callable_obj when invoked with arguments args and keyword
        arguments kwargs.

        If a different type of exception is thrown, it will not be caught, and
        the test case will be deemed to have suffered an error, exactly as for
        an unexpected exception.
        """
        try:
            callable_obj(*args, **kwargs)
        except AssertionError as exception:
            self.assertEqual(str(exception), message)
        else:
            self.fail("AssertionError was not raised")


class NewEvents(object):
    """Help in testing the creation of CodeImportEvent objects.

    To test that an operation creates CodeImportEvent objects, create an
    NewEvent object, perform the operation, then test the value of the
    NewEvents instance.

    Doctests should print the NewEvent object, and unittests should iterate
    over it.
    """

    def __init__(self):
        event_set = getUtility(ICodeImportEventSet)
        self.initial = set(event.id for event in event_set.getAll())

    def summary(self):
        """Render a summary of the newly created CodeImportEvent objects."""
        lines = []
        for event in self:
            words = []
            words.append(event.event_type.name)
            if event.code_import is not None:
                words.append(event.code_import.branch.unique_name)
            if event.machine is not None:
                words.append(event.machine.hostname)
            if event.person is not None:
                words.append(event.person.name)
            lines.append(' '.join(words))
        return '\n'.join(lines)

    def __iter__(self):
        """Iterate over the newly created CodeImportEvent objects."""
        event_set = getUtility(ICodeImportEventSet)
        for event in event_set.getAll():
            if event.id in self.initial:
                continue
            yield event


class AssertEventMixin:
    """Helper to test that a CodeImportEvent has the expected values."""

    def assertEventLike(
            self, import_event, event_type, code_import,
            machine=None, person=None):
        """Fail unless `import_event` has the expected attribute values.

        :param import_event: The `CodeImportEvent` to test.
        :param event_type: expected value of import_event.event_type.
        :param code_import: expected value of import_event.code_import.
        :param machine: expected value of import_event.machine.
        :param person: expected value of import_event.person.
        """
        self.assertEqual(import_event.event_type, event_type)
        self.assertEqual(import_event.code_import, code_import)
        self.assertEqual(import_event.machine, machine)
        self.assertEqual(import_event.person, person)


class TestCodeImportJobWorkflowNewJob(TestCaseWithFactory,
    AssertFailureMixin):
    """Unit tests for the CodeImportJobWorkflow.newJob method."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowNewJob, self).setUp()
        login_for_code_imports()

    def test_wrongReviewStatus(self):
        # CodeImportJobWorkflow.newJob fails if the CodeImport review_status
        # is different from REVIEWED.
        new_import = self.factory.makeCodeImport(
            review_status=CodeImportReviewStatus.SUSPENDED)
        branch_name = new_import.branch.unique_name
        # Testing newJob failure.
        self.assertFailure(
            "Review status of %s is not REVIEWED: SUSPENDED" % (branch_name,),
            getUtility(ICodeImportJobWorkflow).newJob, new_import)

    def test_existingJob(self):
        # CodeImportJobWorkflow.newJob fails if the CodeImport is already
        # associated to a CodeImportJob.
        job = self.factory.makeCodeImportJob()
        reviewed_import = job.code_import
        branch_name = reviewed_import.branch.unique_name
        self.assertFailure(
            "Already associated to a CodeImportJob: %s" % (branch_name,),
            getUtility(ICodeImportJobWorkflow).newJob, reviewed_import)

    def getCodeImportForDateDueTest(self):
        """Return a `CodeImport` object for testing how date_due is set.

        It is not associated to any `CodeImportJob` or `CodeImportResult`, and
        its review_status is REVIEWED.
        """
        return self.factory.makeCodeImport(
            review_status=CodeImportReviewStatus.REVIEWED)

    def test_dateDueNoPreviousResult(self):
        # If there is no CodeImportResult for the CodeImport, then the new
        # CodeImportJob has date_due set to UTC_NOW.
        code_import = self.getCodeImportForDateDueTest()
        self.assertSqlAttributeEqualsDate(code_import.import_job, 'date_due',
            UTC_NOW)

    def test_dateDueRecentPreviousResult(self):
        # If there is a CodeImportResult for the CodeImport that is more
        # recent than the effective_update_interval, then the new
        # CodeImportJob has date_due set in the future.
        code_import = self.getCodeImportForDateDueTest()
        # A code import job is automatically started when a reviewed code import
        # is created. Remove it, so a "clean" one can be created later.
        removeSecurityProxy(code_import).import_job.destroySelf()
        # Create a CodeImportResult that started a long time ago. This one
        # must be superseded by the more recent one created below.
        machine = self.factory.makeCodeImportMachine()
        FAILURE = CodeImportResultStatus.FAILURE
        CodeImportResult(
            code_import=code_import, machine=machine, status=FAILURE,
            date_job_started=datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC),
            date_created=datetime(2000, 1, 1, 12, 5, 0, tzinfo=UTC))
        # Create a CodeImportResult that started a shorter time ago than the
        # effective update interval of the code import. This is the most
        # recent one and must supersede the older one.

        # XXX 2008-06-09 jamesh:
        # psycopg2 isn't correctly substituting intervals into the
        # expression (it doesn't include the "INTERVAL" keyword).
        # This causes problems for the "UTC_NOW - interval / 2"
        # expression below.
        interval = code_import.effective_update_interval
        from lp.services.database.sqlbase import get_transaction_timestamp
        recent_result = CodeImportResult(
            code_import=code_import, machine=machine, status=FAILURE,
            date_job_started=get_transaction_timestamp() - interval / 2)
        # When we create the job, its date_due should be set to the date_due
        # of the job that was deleted when the CodeImport review status
        # changed from REVIEWED. That is the date_job_started of the most
        # recent CodeImportResult plus the effective update interval.
        getUtility(ICodeImportJobWorkflow).newJob(code_import)
        self.assertSqlAttributeEqualsDate(
            code_import.import_job, 'date_due',
            recent_result.date_job_started + interval)

    def test_dateDueOldPreviousResult(self):
        # If the most recent CodeImportResult for the CodeImport is older than
        # the effective_update_interval, then new CodeImportJob has date_due
        # set to UTC_NOW.
        code_import = self.getCodeImportForDateDueTest()
        # Create a CodeImportResult that started a long time ago.
        machine = self.factory.makeCodeImportMachine()
        FAILURE = CodeImportResultStatus.FAILURE
        CodeImportResult(
            code_import=code_import, machine=machine, status=FAILURE,
            date_job_started=datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC),
            date_created=datetime(2000, 1, 1, 12, 5, 0, tzinfo=UTC))
        # When we create the job, its date due must be set to UTC_NOW.
        self.assertSqlAttributeEqualsDate(code_import.import_job, 'date_due',
            UTC_NOW)


class TestCodeImportJobWorkflowDeletePendingJob(TestCaseWithFactory,
        AssertFailureMixin):
    """Unit tests for CodeImportJobWorkflow.deletePendingJob."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowDeletePendingJob, self).setUp()
        self.import_admin = login_for_code_imports()

    def test_wrongReviewStatus(self):
        # CodeImportJobWorkflow.deletePendingJob fails if the
        # CodeImport review_status is equal to REVIEWED.
        reviewed_import = self.factory.makeCodeImport()
        reviewed_import.updateFromData(
            {'review_status': CodeImportReviewStatus.REVIEWED},
            self.import_admin)
        branch_name = reviewed_import.branch.unique_name
        # Testing deletePendingJob failure.
        self.assertFailure(
            "The review status of %s is REVIEWED." % (branch_name,),
            getUtility(ICodeImportJobWorkflow).deletePendingJob,
            reviewed_import)

    def test_noJob(self):
        # CodeImportJobWorkflow.deletePendingJob fails if the
        # CodeImport is not associated to a CodeImportJob.
        new_import = self.factory.makeCodeImport(
            review_status=CodeImportReviewStatus.NEW)
        branch_name = new_import.branch.unique_name
        # Testing deletePendingJob failure.
        self.assertFailure(
            "Not associated to a CodeImportJob: %s" % (branch_name,),
            getUtility(ICodeImportJobWorkflow).deletePendingJob,
            new_import)

    def test_wrongJobState(self):
        # CodeImportJobWorkflow.deletePendingJob fails if the state of
        # the CodeImportJob is different from PENDING.
        job = self.factory.makeCodeImportJob()
        code_import = job.code_import
        branch_name = job.code_import.branch.unique_name
        # ICodeImport does not allow setting 'review_status', so we must use
        # removeSecurityProxy.
        INVALID = CodeImportReviewStatus.INVALID
        removeSecurityProxy(code_import).review_status = INVALID
        # ICodeImportJob does not allow setting 'state', so we must
        # use removeSecurityProxy.
        RUNNING = CodeImportJobState.RUNNING
        removeSecurityProxy(code_import.import_job).state = RUNNING
        # Testing deletePendingJob failure.
        self.assertFailure(
            "The CodeImportJob associated to %s is RUNNING." % (branch_name,),
            getUtility(ICodeImportJobWorkflow).deletePendingJob, code_import)


class TestCodeImportJobWorkflowRequestJob(TestCaseWithFactory,
        AssertFailureMixin, AssertEventMixin):
    """Unit tests for CodeImportJobWorkflow.requestJob."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowRequestJob, self).setUp()
        login_for_code_imports()

    def test_wrongJobState(self):
        # CodeImportJobWorkflow.requestJob fails if the state of the
        # CodeImportJob is different from PENDING.
        person = self.factory.makePerson()
        code_import = self.factory.makeCodeImport()
        import_job = self.factory.makeCodeImportJob(code_import)
        # ICodeImportJob does not allow setting 'state', so we must
        # use removeSecurityProxy.
        # XXX: StuartBishop 20090302 - This test is creating invalid
        # CodeImportJob instances here - the object cannot be flushed
        # to the database as database constraints are violated.
        # This is a problem, as flushing can happen implicitly by Storm,
        # so minor changes to this test can make it explode.
        removeSecurityProxy(import_job).state = CodeImportJobState.RUNNING
        self.assertFailure(
            "The CodeImportJob associated with %s is "
            "RUNNING." % code_import.branch.unique_name,
            getUtility(ICodeImportJobWorkflow).requestJob,
            import_job, person)

    def test_alreadyRequested(self):
        # CodeImportJobWorkflow.requestJob fails if the job was requested
        # already, that is, if its requesting_user attribute is set.
        code_import = self.factory.makeCodeImport()
        import_job = self.factory.makeCodeImportJob(code_import)
        person = self.factory.makePerson()
        other_person = self.factory.makePerson()
        # ICodeImportJob does not allow setting requesting_user, so we must
        # use removeSecurityProxy.
        removeSecurityProxy(import_job).requesting_user = person
        self.assertFailure(
            "The CodeImportJob associated with %s was already requested by "
            "%s." % (code_import.branch.unique_name, person.name),
            getUtility(ICodeImportJobWorkflow).requestJob,
            import_job, other_person)

    def test_requestFutureJob(self):
        # CodeImportJobWorkflow.requestJob sets requesting_user and
        # date_due if the current date_due is in the future.
        code_import = self.factory.makeCodeImport()
        pending_job = code_import.import_job
        person = self.factory.makePerson()
        # Set date_due in the future. ICodeImportJob does not allow setting
        # date_due, so we must use removeSecurityProxy.
        removeSecurityProxy(pending_job).date_due = (
            datetime(2100, 1, 1, tzinfo=UTC))
        # requestJob sets both requesting_user and date_due.
        new_events = NewEvents()
        getUtility(ICodeImportJobWorkflow).requestJob(
            pending_job, person)
        self.assertEqual(pending_job.requesting_user, person)
        self.assertSqlAttributeEqualsDate(pending_job, 'date_due', UTC_NOW)
        # When requestJob is successful, it creates a REQUEST event.
        [request_event] = list(new_events)
        self.assertEventLike(
            request_event, CodeImportEventType.REQUEST,
            pending_job.code_import, person=person)

    def test_requestOverdueJob(self):
        # CodeImportJobWorkflow.requestJob only sets requesting_user if the
        # date_due is already past.
        code_import = self.factory.makeCodeImport()
        pending_job = self.factory.makeCodeImportJob(code_import)
        person = self.factory.makePerson()
        # Set date_due in the past. ICodeImportJob does not allow setting
        # date_due, so we must use removeSecurityProxy.
        past_date = datetime(1900, 1, 1, tzinfo=UTC)
        removeSecurityProxy(pending_job).date_due = past_date
        # requestJob only sets requesting_user.
        new_events = NewEvents()
        getUtility(ICodeImportJobWorkflow).requestJob(
            pending_job, person)
        self.assertEqual(pending_job.requesting_user, person)
        self.assertSqlAttributeEqualsDate(
            pending_job, 'date_due', past_date)
        # When requestJob is successful, it creates a REQUEST event.
        [request_event] = list(new_events)
        self.assertEventLike(
            request_event, CodeImportEventType.REQUEST,
            pending_job.code_import, person=person)


class TestCodeImportJobWorkflowStartJob(TestCaseWithFactory,
        AssertFailureMixin, AssertEventMixin):
    """Unit tests for CodeImportJobWorkflow.startJob."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowStartJob, self).setUp()
        login_for_code_imports()

    def test_wrongJobState(self):
        # Calling startJob with a job whose state is not PENDING is an error.
        code_import = self.factory.makeCodeImport()
        machine = self.factory.makeCodeImportMachine(set_online=True)
        job = self.factory.makeCodeImportJob(code_import)
        # ICodeImportJob does not allow setting 'state', so we must
        # use removeSecurityProxy.
        RUNNING = CodeImportJobState.RUNNING
        removeSecurityProxy(job).state = RUNNING
        # Testing startJob failure.
        self.assertFailure(
            "The CodeImportJob associated with %s is "
            "RUNNING." % code_import.branch.unique_name,
            getUtility(ICodeImportJobWorkflow).requestJob,
            job, machine)

    def test_startJob(self):
        # After startJob, the date_started and heartbeat fields are both
        # updated to the current time, the logtail is the empty string,
        # machine is set to the supplied import machine and the state is
        # RUNNING.
        code_import = self.factory.makeCodeImport()
        machine = self.factory.makeCodeImportMachine(set_online=True)
        job = self.factory.makeCodeImportJob(code_import)
        getUtility(ICodeImportJobWorkflow).startJob(job, machine)
        self.assertSqlAttributeEqualsDate(job, 'date_started', UTC_NOW)
        self.assertSqlAttributeEqualsDate(job, 'heartbeat', UTC_NOW)
        self.assertEqual('', job.logtail)
        self.assertEqual(machine, job.machine)
        self.assertEqual(CodeImportJobState.RUNNING, job.state)

    def test_offlineMachine(self):
        # Calling startJob with a machine which is not ONLINE is an error.
        machine = self.factory.makeCodeImportMachine()
        code_import = self.factory.makeCodeImport()
        job = self.factory.makeCodeImportJob(code_import)
        # Testing startJob failure.
        self.assertFailure(
            "The machine %s is OFFLINE." % machine.hostname,
            getUtility(ICodeImportJobWorkflow).startJob,
            job, machine)


class TestCodeImportJobWorkflowUpdateHeartbeat(TestCaseWithFactory,
        AssertFailureMixin, AssertEventMixin):
    """Unit tests for CodeImportJobWorkflow.updateHeartbeat."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowUpdateHeartbeat, self).setUp()
        login_for_code_imports()

    def test_wrongJobState(self):
        # Calling updateHeartbeat with a job whose state is not RUNNING is an
        # error.
        code_import = self.factory.makeCodeImport()
        job = self.factory.makeCodeImportJob(code_import)
        self.assertFailure(
            "The CodeImportJob associated with %s is "
            "PENDING." % code_import.branch.unique_name,
            getUtility(ICodeImportJobWorkflow).updateHeartbeat,
            job, u'')

    def test_updateHeartboat(self):
        code_import = self.factory.makeCodeImport()
        machine = self.factory.makeCodeImportMachine(set_online=True)
        job = self.factory.makeCodeImportJob(code_import)
        workflow = getUtility(ICodeImportJobWorkflow)
        workflow.startJob(job, machine)
        # Set heartbeat to something wrong so that we can prove that it was
        # changed.
        removeSecurityProxy(job).heartbeat = None
        workflow.updateHeartbeat(job, u'some interesting log output')
        self.assertSqlAttributeEqualsDate(job, 'heartbeat', UTC_NOW)
        self.assertEqual(u'some interesting log output', job.logtail)


class TestCodeImportJobWorkflowFinishJob(TestCaseWithFactory,
        AssertFailureMixin, AssertEventMixin):
    """Unit tests for CodeImportJobWorkflow.finishJob."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowFinishJob, self).setUp()
        self.vcs_imports = login_for_code_imports()
        self.machine = self.factory.makeCodeImportMachine(set_online=True)

    def makeRunningJob(self, code_import=None):
        """Make and return a CodeImportJob object with state==RUNNING.

        This is suitable for passing into finishJob().
        """
        if code_import is None:
            code_import = self.factory.makeCodeImport()
        job = code_import.import_job
        if job is None:
            job = self.factory.makeCodeImportJob(code_import)
        getUtility(ICodeImportJobWorkflow).startJob(job, self.machine)
        return job

    # Precondition tests. Only one of these.

    def test_wrongJobState(self):
        # Calling finishJob with a job whose state is not RUNNING is an error.
        code_import = self.factory.makeCodeImport()
        job = self.factory.makeCodeImportJob(code_import)
        self.assertFailure(
            "The CodeImportJob associated with %s is "
            "PENDING." % code_import.branch.unique_name,
            getUtility(ICodeImportJobWorkflow).finishJob,
            job, CodeImportResultStatus.SUCCESS, None)

    # Postcondition tests. Several of these -- finishJob is quite a complex
    # function!

    def test_deletesPassedJob(self):
        # finishJob() deletes the job it is passed.
        running_job = self.makeRunningJob()
        running_job_id = running_job.id
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.SUCCESS, None)
        self.assertEqual(
            None, getUtility(ICodeImportJobSet).getById(running_job_id))

    def test_createsNewJob(self):
        # finishJob() creates a new CodeImportJob for the given CodeImport,
        # scheduled appropriately far in the future.
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.SUCCESS, None)
        new_job = code_import.import_job
        self.assert_(new_job is not None)
        self.assertEqual(new_job.state, CodeImportJobState.PENDING)
        self.assertEqual(new_job.machine, None)
        self.assertEqual(
            new_job.date_due - running_job.date_due,
            code_import.effective_update_interval)

    def test_partialSuccessCreatesNewJobDueNow(self):
        # If called with a status of SUCCESS_PARTIAL, finishJob() creates a
        # new CodeImportJob for the given CodeImport that is due to run right
        # now.
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.SUCCESS_PARTIAL, None)
        new_job = code_import.import_job
        self.assert_(new_job is not None)
        self.assertEqual(new_job.state, CodeImportJobState.PENDING)
        self.assertEqual(new_job.machine, None)
        self.assertSqlAttributeEqualsDate(new_job, 'date_due', UTC_NOW)

    def test_failures_back_off(self):
        # We wait for longer and longer between retrying failing imports, to
        # make it less likely that an import is marked failing just because
        # someone's DNS went down for a day.
        running_job = self.makeRunningJob()
        intervals = []
        interval = running_job.code_import.effective_update_interval
        expected_intervals = []
        for i in range(config.codeimport.consecutive_failure_limit - 1):
            expected_intervals.append(interval)
            interval *= 2
        # Fail an import a bunch of times and record how far in the future the
        # next job was scheduled.
        for i in range(config.codeimport.consecutive_failure_limit - 1):
            code_import = running_job.code_import
            getUtility(ICodeImportJobWorkflow).finishJob(
                running_job, CodeImportResultStatus.FAILURE, None)
            intervals.append(
                code_import.import_job.date_due -
                code_import.results[-1].date_job_started)
            running_job = code_import.import_job
            getUtility(ICodeImportJobWorkflow).startJob(
                running_job, self.machine)
        self.assertEqual(expected_intervals, intervals)

    def test_doesntCreateNewJobIfCodeImportNotReviewed(self):
        # finishJob() creates a new CodeImportJob for the given CodeImport,
        # unless the CodeImport has been suspended or marked invalid.
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.SUSPENDED},
            self.vcs_imports)
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.SUCCESS, None)
        self.assertTrue(code_import.import_job is None)

    def test_createsResultObject(self):
        # finishJob() creates a CodeImportResult object for the given import.
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        # Before calling finishJob() there are no CodeImportResults for the
        # given import...
        self.assertEqual(len(list(code_import.results)), 0)
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.SUCCESS, None)
        # ... and after, there is exactly one.
        self.assertEqual(len(list(code_import.results)), 1)

    def getResultForJob(self, job, status=CodeImportResultStatus.SUCCESS,
                        log_alias=None):
        """Call finishJob() on job and return the created result."""
        code_import = job.code_import
        getUtility(ICodeImportJobWorkflow).finishJob(
            job, status, log_alias)
        [result] = list(code_import.results)
        return result

    def assertFinishJobPassesThroughJobField(self, from_field, to_field,
                                             value):
        """Assert that an attribute is carried from the job to the result.

        This helper creates a job, sets the `from_field` attribute on
        it to value, and then checks that this gets copied to the
        `to_field` attribute on the result that gets created when
        finishJob() is called on the job.
        """
        job = self.makeRunningJob()
        # There are ways of setting all the fields through other workflow
        # methods -- e.g. calling requestJob to set requesting_user -- but
        # using removeSecurityProxy and forcing here is expedient.
        setattr(removeSecurityProxy(job), from_field, value)
        result = self.getResultForJob(job)
        self.assertEqual(
            value, getattr(result, to_field),
            "Value %r in job field %r was not passed through to result field"
            " %r." % (value, from_field, to_field))

    def test_resultObjectFields(self):
        # The CodeImportResult object that finishJob creates contains all the
        # relevant details from the job object.

        unchecked_result_fields = set(ICodeImportResult)

        # We don't care about 'id', and 'job_duration' only matters
        # when we have a valid date_created (as opposed to UTC_NOW).
        unchecked_result_fields.remove('id')
        unchecked_result_fields.remove('job_duration')
        # Some result fields are tested in other tests:
        unchecked_result_fields.difference_update(['log_file', 'status'])

        code_import = self.factory.makeCodeImport()
        removeSecurityProxy(code_import).import_job.destroySelf()
        self.assertFinishJobPassesThroughJobField(
            'code_import', 'code_import', code_import)
        unchecked_result_fields.remove('code_import')
        self.assertFinishJobPassesThroughJobField(
            'machine', 'machine', self.factory.makeCodeImportMachine())
        unchecked_result_fields.remove('machine')
        self.assertFinishJobPassesThroughJobField(
            'requesting_user', 'requesting_user', self.factory.makePerson())
        unchecked_result_fields.remove('requesting_user')
        self.assertFinishJobPassesThroughJobField(
            'logtail', 'log_excerpt', "some pretend log output")
        unchecked_result_fields.remove('log_excerpt')
        self.assertFinishJobPassesThroughJobField(
            'date_started', 'date_job_started',
            datetime(2008, 1, 1, tzinfo=UTC))
        unchecked_result_fields.remove('date_job_started')

        result = self.getResultForJob(self.makeRunningJob())
        self.assertSqlAttributeEqualsDate(result, 'date_created', UTC_NOW)
        # date_job_finished is punned with date_created
        unchecked_result_fields.difference_update(
            ['date_created', 'date_job_finished'])

        # By now we should have checked all the result fields.
        self.assertEqual(
            set(), unchecked_result_fields,
            "These result field not checked %r!" % unchecked_result_fields)

    def test_resultStatus(self):
        # finishJob() sets the status appropriately on the result object.
        status_jobs = []
        for status in CodeImportResultStatus.items:
            status_jobs.append((status, self.makeRunningJob()))
        for status, job in status_jobs:
            result = self.getResultForJob(job, status)
            self.assertEqual(result.status, status)

    def test_resultLogFile(self):
        # If you pass a link to a file in the librarian to finishJob(), it
        # gets set on the result object.

        job = self.makeRunningJob()

        log_data = 'several\nlines\nof\nlog data'
        log_alias_id = getUtility(ILibrarianClient).addFile(
           'import_log.txt', len(log_data),
           StringIO.StringIO(log_data), 'text/plain')
        transaction.commit()
        log_alias = getUtility(ILibraryFileAliasSet)[log_alias_id]
        result = self.getResultForJob(job, log_alias=log_alias)

        self.assertEqual(result.log_file.read(), log_data)

    def test_createsFinishCodeImportEvent(self):
        # finishJob() creates a FINISH CodeImportEvent.
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        machine = running_job.machine
        new_events = NewEvents()
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.SUCCESS, None)
        [finish_event] = list(new_events)
        self.assertEventLike(
            finish_event, CodeImportEventType.FINISH,
            code_import, machine)

    def test_successfulResultUpdatesCodeImportLastSuccessful(self):
        # finishJob() updates CodeImport.date_last_successful if and only if
        # the status was success.
        status_jobs = []
        for status in CodeImportResultStatus.items:
            status_jobs.append((status, self.makeRunningJob()))
        for status, job in status_jobs:
            code_import = job.code_import
            self.assertTrue(code_import.date_last_successful is None)
            getUtility(ICodeImportJobWorkflow).finishJob(job, status, None)
            if status in [CodeImportResultStatus.SUCCESS,
                          CodeImportResultStatus.SUCCESS_NOCHANGE]:
                self.assertTrue(code_import.date_last_successful is not None)
            else:
                self.assertTrue(code_import.date_last_successful is None)

    def test_successfulResultCallsRequestMirror(self):
        # finishJob() calls requestMirror() on the import branch if and only
        # if the status was success.
        status_jobs = []
        for status in CodeImportResultStatus.items:
            status_jobs.append((status, self.makeRunningJob()))
        for status, job in status_jobs:
            code_import = job.code_import
            self.assertTrue(code_import.date_last_successful is None)
            getUtility(ICodeImportJobWorkflow).finishJob(job, status, None)
            if status == CodeImportResultStatus.SUCCESS:
                self.assertTrue(
                    code_import.branch.next_mirror_time is not None)
            else:
                self.assertTrue(
                    code_import.branch.next_mirror_time is None)

    def test_enoughFailuresMarksAsFailing(self):
        # If a code import fails config.codeimport.consecutive_failure_limit
        # times in a row, the import is marked as FAILING.
        code_import = self.factory.makeCodeImport()
        failure_limit = config.codeimport.consecutive_failure_limit
        for i in range(failure_limit - 1):
            running_job = self.makeRunningJob(code_import)
            getUtility(ICodeImportJobWorkflow).finishJob(
                running_job, CodeImportResultStatus.FAILURE, None)
        self.assertEqual(
            failure_limit - 1, code_import.consecutive_failure_count)
        self.assertEqual(
            CodeImportReviewStatus.REVIEWED, code_import.review_status)
        running_job = self.makeRunningJob(code_import)
        getUtility(ICodeImportJobWorkflow).finishJob(
            running_job, CodeImportResultStatus.FAILURE, None)
        self.assertEqual(
            CodeImportReviewStatus.FAILING, code_import.review_status)


class TestCodeImportJobWorkflowReclaimJob(TestCaseWithFactory,
        AssertFailureMixin, AssertEventMixin):
    """Tests for reclaimJob.

    The code import worker is meant to update the heartbeat field of the row
    of CodeImportJob frequently.  The code import watchdog periodically checks
    the heartbeats of the running jobs and if it finds that a heartbeat was
    not updated recently enough, it assumes it has become stuck somehow and
    'reclaims' the job -- removes the job from the database and creates a
    pending job for the same import that is due immediately.  This reclaiming
    is done by the 'reclaimJob' code import job workflow method.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCodeImportJobWorkflowReclaimJob, self).setUp()
        login_for_code_imports()
        self.machine = self.factory.makeCodeImportMachine(set_online=True)

    def makeRunningJob(self, code_import=None):
        """Make and return a CodeImportJob object with state==RUNNING.

        This is suitable for passing into finishJob().
        """
        if code_import is None:
            code_import = self.factory.makeCodeImport()
        job = code_import.import_job
        if job is None:
            job = self.factory.makeCodeImportJob(code_import)
        getUtility(ICodeImportJobWorkflow).startJob(job, self.machine)
        return job

    def test_deletes_job(self):
        running_job = self.makeRunningJob()
        job_id = running_job.id
        getUtility(ICodeImportJobWorkflow).reclaimJob(running_job)
        matching_job = getUtility(ICodeImportJobSet).getById(job_id)
        self.assertIs(None, matching_job)

    def test_makes_reclaim_result(self):
        running_job = self.makeRunningJob()
        getUtility(ICodeImportJobWorkflow).reclaimJob(running_job)
        [result] = list(running_job.code_import.results)
        self.assertEqual(CodeImportResultStatus.RECLAIMED, result.status)

    def test_creates_new_job(self):
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        getUtility(ICodeImportJobWorkflow).reclaimJob(running_job)
        self.assertSqlAttributeEqualsDate(
            code_import.import_job, 'date_due', UTC_NOW)

    def test_logs_reclaim_event(self):
        running_job = self.makeRunningJob()
        code_import = running_job.code_import
        machine = running_job.machine
        new_events = NewEvents()
        getUtility(ICodeImportJobWorkflow).reclaimJob(running_job)
        [reclaim_event] = list(new_events)
        self.assertEventLike(
            reclaim_event, CodeImportEventType.RECLAIM,
            code_import, machine)


logged_in_for_code_imports = with_celebrity_logged_in('vcs_imports')


class TestRequestJobUIRaces(TestCaseWithFactory):
    """What does the 'Import Now' button do when things have changed?

    All these tests load up a view of a code import that shows the 'Import
    Now' button, make a change so the button no longer makes sense then press
    the button and check that appropriate notifications are displayed.
    """

    layer = DatabaseFunctionalLayer

    @logged_in_for_code_imports
    def getNewCodeImportIDAndBranchURL(self):
        """Create a code import and return its ID and the URL of its branch.
        """
        code_import = make_finished_import(factory=self.factory)
        branch_url = canonical_url(code_import.branch)
        code_import_id = code_import.id
        return code_import_id, branch_url

    def requestJobByUserWithDisplayName(self, code_import_id, displayname):
        """Record a request for the job by a user with the given name."""
        self.factory.loginAsAnyone()
        try:
            getUtility(ICodeImportJobWorkflow).requestJob(
                getUtility(ICodeImportSet).get(code_import_id).import_job,
                self.factory.makePerson(displayname=displayname))
        finally:
            logout()

    @logged_in_for_code_imports
    def deleteJob(self, code_import_id):
        """Cause the code import job associated to the import to be deleted.
        """
        user = self.factory.makePerson()
        getUtility(ICodeImportSet).get(code_import_id).updateFromData(
            {'review_status': CodeImportReviewStatus.SUSPENDED}, user)

    @with_anonymous_login
    def startJob(self, code_import_id):
        """Mark the job as started on an arbitrary machine."""
        getUtility(ICodeImportJobWorkflow).startJob(
            getUtility(ICodeImportSet).get(code_import_id).import_job,
            self.factory.makeCodeImportMachine(set_online=True))

    def test_pressButtonImportAlreadyRequested(self):
        # If the import has been requested by another user, we display a
        # notification saying who it was.
        code_import_id, branch_url = self.getNewCodeImportIDAndBranchURL()
        user_browser = self.getUserBrowser(branch_url)
        self.requestJobByUserWithDisplayName(code_import_id, "New User")
        user_browser.getControl('Import Now').click()
        self.assertEqual(
            [u'The import has already been requested by New User.'],
            get_feedback_messages(user_browser.contents))

    def test_pressButtonJobDeleted(self):
        # If the import job has been deleled, for example because the code
        # import has been suspended, we display a notification saying this.
        code_import_id, branch_url = self.getNewCodeImportIDAndBranchURL()
        user_browser = self.getUserBrowser(branch_url)
        self.deleteJob(code_import_id)
        user_browser.getControl('Import Now').click()
        self.assertEqual(
            [u'This import is no longer being updated automatically.'],
            get_feedback_messages(user_browser.contents))

    def test_pressButtonJobStarted(self):
        # If the job has started, we display a notification saying so.
        code_import_id, branch_url = self.getNewCodeImportIDAndBranchURL()
        user_browser = self.getUserBrowser(branch_url)
        self.startJob(code_import_id)
        user_browser.getControl('Import Now').click()
        self.assertEqual(
            [u'The import is already running.'],
            get_feedback_messages(user_browser.contents))


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
