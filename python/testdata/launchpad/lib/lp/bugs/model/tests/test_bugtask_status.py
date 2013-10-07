# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bug task status transitions."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    BugTaskStatusSearch,
    BugTaskStatusSearchDisplay,
    UserCannotEditBugTaskStatus,
    )
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugTaskStatusTransitionForUser(TestCaseWithFactory):
    """Test bugtask status transitions for a regular logged in user."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskStatusTransitionForUser, self).setUp()
        self.user = self.factory.makePerson()
        self.task = self.factory.makeBugTask()

    def test_user_transition_all_statuses(self):
        # A regular user should not be able to set statuses in
        # BUG_SUPERVISOR_BUGTASK_STATUSES, but can set any
        # other status.
        self.assertEqual(self.task.status, BugTaskStatus.NEW)
        with person_logged_in(self.user):
            self.assertRaises(
                UserCannotEditBugTaskStatus, self.task.transitionToStatus,
                BugTaskStatus.WONTFIX, self.user)
            self.assertRaises(
                UserCannotEditBugTaskStatus, self.task.transitionToStatus,
                BugTaskStatus.EXPIRED, self.user)
            self.assertRaises(
                UserCannotEditBugTaskStatus, self.task.transitionToStatus,
                BugTaskStatus.TRIAGED, self.user)
            self.task.transitionToStatus(BugTaskStatus.NEW, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.NEW)
            self.task.transitionToStatus(
                BugTaskStatus.INCOMPLETE, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.INCOMPLETE)
            self.task.transitionToStatus(BugTaskStatus.OPINION, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.OPINION)
            self.task.transitionToStatus(BugTaskStatus.INVALID, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.INVALID)
            self.task.transitionToStatus(BugTaskStatus.CONFIRMED, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.CONFIRMED)
            self.task.transitionToStatus(
                BugTaskStatus.INPROGRESS, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.INPROGRESS)
            self.task.transitionToStatus(
                BugTaskStatus.FIXCOMMITTED, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.FIXCOMMITTED)
            self.task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, self.user)
            self.assertEqual(self.task.status, BugTaskStatus.FIXRELEASED)

    def test_user_cannot_unset_wont_fix_status(self):
        # A regular user should not be able to transition a bug away
        # from Won't Fix.
        removeSecurityProxy(self.task)._status = BugTaskStatus.WONTFIX
        with person_logged_in(self.user):
            self.assertRaises(
                UserCannotEditBugTaskStatus, self.task.transitionToStatus,
                BugTaskStatus.CONFIRMED, self.user)

    def test_user_cannot_unset_fix_released_status(self):
        # A regular user should not be able to transition a bug away
        # from Fix Released.
        removeSecurityProxy(self.task)._status = BugTaskStatus.FIXRELEASED
        with person_logged_in(self.user):
            self.assertRaises(
                UserCannotEditBugTaskStatus, self.task.transitionToStatus,
                BugTaskStatus.FIXRELEASED, self.user)

    def test_user_canTransitionToStatus(self):
        # Regular user cannot transition to BUG_SUPERVISOR_BUGTASK_STATUSES,
        # but can transition to any other status.
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.WONTFIX, self.user),
            False)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.EXPIRED, self.user),
            False)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.TRIAGED, self.user),
            False)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.NEW, self.user),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.INCOMPLETE, self.user), True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.OPINION, self.user),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.INVALID, self.user),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.CONFIRMED, self.user),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.INPROGRESS, self.user),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.FIXCOMMITTED, self.user),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.FIXRELEASED, self.user),
            True)

    def test_user_canTransitionToStatus_from_wontfix(self):
        # A regular user cannot transition away from Won't Fix,
        # so canTransitionToStatus should return False.
        removeSecurityProxy(self.task)._status = BugTaskStatus.WONTFIX
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.NEW, self.user),
            False)

    def test_user_canTransitionToStatus_from_fixreleased(self):
        # A regular user cannot transition away from Fix Released,
        # so canTransitionToStatus should return False.
        removeSecurityProxy(self.task)._status = BugTaskStatus.FIXRELEASED
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.NEW, self.user),
            False)

    def test_transitionToStatus_normalization(self):
        # The new status is normalized using normalize_bugtask_status, so
        # members of BugTaskStatusSearch or BugTaskStatusSearchDisplay can
        # also be used.
        with person_logged_in(self.user):
            self.task.transitionToStatus(
                BugTaskStatusSearch.CONFIRMED, self.user)
            self.assertEqual(BugTaskStatus.CONFIRMED, self.task.status)
            self.task.transitionToStatus(
                BugTaskStatusSearchDisplay.CONFIRMED, self.user)
            self.assertEqual(BugTaskStatus.CONFIRMED, self.task.status)

    def test_canTransitionToStatus_normalization(self):
        # The new status is normalized using normalize_bugtask_status, so
        # members of BugTaskStatusSearch or BugTaskStatusSearchDisplay can
        # also be used.
        self.assertTrue(
            self.task.canTransitionToStatus(
                BugTaskStatusSearch.CONFIRMED, self.user))
        self.assertFalse(
            self.task.canTransitionToStatus(
                BugTaskStatusSearch.WONTFIX, self.user))
        self.assertTrue(
            self.task.canTransitionToStatus(
                BugTaskStatusSearchDisplay.CONFIRMED, self.user))
        self.assertFalse(
            self.task.canTransitionToStatus(
                BugTaskStatusSearchDisplay.WONTFIX, self.user))


class TestBugTaskStatusTransitionForReporter(TestCaseWithFactory):
    """Tests for bug reporter status transitions."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskStatusTransitionForReporter, self).setUp()
        self.task = self.factory.makeBugTask()
        self.reporter = self.task.bug.owner

    def test_reporter_can_unset_fix_released_status(self):
        # The bug reporter can transition away from Fix Released.
        removeSecurityProxy(self.task)._status = BugTaskStatus.FIXRELEASED
        with person_logged_in(self.reporter):
            self.task.transitionToStatus(
                BugTaskStatus.CONFIRMED, self.reporter)
            self.assertEqual(self.task.status, BugTaskStatus.CONFIRMED)

    def test_reporter_canTransitionToStatus(self):
        # The bug reporter can transition away from Fix Released, so
        # canTransitionToStatus should always return True.
        removeSecurityProxy(self.task)._status = BugTaskStatus.FIXRELEASED
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.CONFIRMED, self.reporter),
            True)

    def test_reporter_team_can_unset_fix_released_status(self):
        # The bug reporter can be a team in the case of bug imports
        # and needs to be able to transition away from Fix Released.
        team = self.factory.makeTeam(members=[self.reporter])
        team_bug = self.factory.makeBug(owner=team)
        naked_task = removeSecurityProxy(team_bug.default_bugtask)
        naked_task._status = BugTaskStatus.FIXRELEASED
        with person_logged_in(self.reporter):
            team_bug.default_bugtask.transitionToStatus(
                BugTaskStatus.CONFIRMED, self.reporter)
            self.assertEqual(
                team_bug.default_bugtask.status, BugTaskStatus.CONFIRMED)


class TestBugTaskStatusTransitionForPrivilegedUserBase:
    """Base class used to test privileged users and status transitions."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskStatusTransitionForPrivilegedUserBase, self).setUp()
        # Creation of task and target are deferred to subclasses.
        self.task = None
        self.person = None
        self.makePersonAndTask()

    def makePersonAndTask(self):
        """Create a bug task and privileged person for this task.

        This method is implemented by subclasses to correctly setup
        each test.
        """
        raise NotImplementedError(self.makePersonAndTask)

    def test_privileged_user_transition_any_status(self):
        # Privileged users (like owner or bug supervisor) should
        # be able to set any status.
        with person_logged_in(self.person):
            self.task.transitionToStatus(BugTaskStatus.WONTFIX, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.WONTFIX)
            self.task.transitionToStatus(BugTaskStatus.EXPIRED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.EXPIRED)
            self.task.transitionToStatus(BugTaskStatus.TRIAGED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.TRIAGED)
            self.task.transitionToStatus(BugTaskStatus.NEW, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.NEW)
            self.task.transitionToStatus(
                BugTaskStatus.INCOMPLETE, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.INCOMPLETE)
            self.task.transitionToStatus(BugTaskStatus.OPINION, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.OPINION)
            self.task.transitionToStatus(BugTaskStatus.INVALID, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.INVALID)
            self.task.transitionToStatus(BugTaskStatus.CONFIRMED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.CONFIRMED)
            self.task.transitionToStatus(
                BugTaskStatus.INPROGRESS, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.INPROGRESS)
            self.task.transitionToStatus(
                BugTaskStatus.FIXCOMMITTED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.FIXCOMMITTED)
            self.task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.FIXRELEASED)

    def test_privileged_user_can_unset_wont_fix_status(self):
        # Privileged users can transition away from Won't Fix.
        removeSecurityProxy(self.task)._status = BugTaskStatus.WONTFIX
        with person_logged_in(self.person):
            self.task.transitionToStatus(BugTaskStatus.CONFIRMED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.CONFIRMED)

    def test_privileged_user_can_unset_fix_released_status(self):
        # Privileged users can transition away from Fix Released.
        removeSecurityProxy(self.task)._status = BugTaskStatus.FIXRELEASED
        with person_logged_in(self.person):
            self.task.transitionToStatus(BugTaskStatus.CONFIRMED, self.person)
            self.assertEqual(self.task.status, BugTaskStatus.CONFIRMED)

    def test_privileged_user_canTransitionToStatus(self):
        # Privileged users (like owner or bug supervisor) should
        # be able to set any status, so canTransitionToStatus should
        # always return True.
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.WONTFIX, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.EXPIRED, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.TRIAGED, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.NEW, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.INCOMPLETE, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.OPINION, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.INVALID, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.CONFIRMED, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.INPROGRESS, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.FIXCOMMITTED, self.person),
            True)
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.FIXRELEASED, self.person),
            True)

    def test_privileged_user_canTransitionToStatus_from_wontfix(self):
        # A privileged user can transition away from Won't Fix, so
        # canTransitionToStatus should return True.
        removeSecurityProxy(self.task)._status = BugTaskStatus.WONTFIX
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.NEW, self.person),
            True)

    def test_privileged_user_canTransitionToStatus_from_fixreleased(self):
        # A privileged user can transition away from Fix Released, so
        # canTransitionToStatus should return True.
        removeSecurityProxy(self.task)._status = BugTaskStatus.FIXRELEASED
        self.assertEqual(
            self.task.canTransitionToStatus(
                BugTaskStatus.NEW, self.person),
            True)


class TestBugTaskStatusTransitionOwnerPerson(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure owner person can transition to any status.."""

    def makePersonAndTask(self):
        self.person = self.factory.makePerson()
        self.product = self.factory.makeProduct(owner=self.person)
        self.task = self.factory.makeBugTask(target=self.product)


class TestBugTaskStatusTransitionOwnerTeam(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure owner team can transition to any status.."""

    def makePersonAndTask(self):
        self.person = self.factory.makePerson()
        self.team = self.factory.makeTeam(
            members=[self.person],
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        self.product = self.factory.makeProduct(owner=self.team)
        self.task = self.factory.makeBugTask(target=self.product)


class TestBugTaskStatusTransitionBugSupervisorPerson(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure bug supervisor person can transition to any status."""

    def makePersonAndTask(self):
        self.owner = self.factory.makePerson()
        self.person = self.factory.makePerson()
        self.product = self.factory.makeProduct(
            owner=self.owner, bug_supervisor=self.person)
        self.task = self.factory.makeBugTask(target=self.product)


class TestBugTaskStatusTransitionBugSupervisorTeamMember(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure bug supervisor team can transition to any status."""

    def makePersonAndTask(self):
        self.owner = self.factory.makePerson()
        self.person = self.factory.makePerson()
        self.team = self.factory.makeTeam(members=[self.person])
        self.product = self.factory.makeProduct(
            owner=self.owner, bug_supervisor=self.team)
        self.task = self.factory.makeBugTask(target=self.product)


class TestBugTaskStatusTransitionBugWatchUpdater(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure bug_watch_updater can transition to any status."""

    def makePersonAndTask(self):
        self.person = getUtility(ILaunchpadCelebrities).bug_watch_updater
        self.task = self.factory.makeBugTask()


class TestBugTaskStatusTransitionBugImporter(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure bug_importer can transition to any status."""

    def makePersonAndTask(self):
        self.person = getUtility(ILaunchpadCelebrities).bug_importer
        self.task = self.factory.makeBugTask()


class TestBugTaskStatusTransitionJanitor(
    TestBugTaskStatusTransitionForPrivilegedUserBase, TestCaseWithFactory):
    """Tests to ensure lp janitor can transition to any status."""

    def makePersonAndTask(self):
        self.person = getUtility(ILaunchpadCelebrities).janitor
        self.task = self.factory.makeBugTask()
