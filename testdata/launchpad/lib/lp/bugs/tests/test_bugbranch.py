# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bug-branch linking from the bugs side."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bugbranch import (
    IBugBranch,
    IBugBranchSet,
    )
from lp.bugs.model.bugbranch import (
    BugBranch,
    BugBranchSet,
    )
from lp.testing import (
    anonymous_logged_in,
    celebrity_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugBranchSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_bugbranchset_provides_IBugBranchSet(self):
        # BugBranchSet objects provide IBugBranchSet.
        self.assertProvides(BugBranchSet(), IBugBranchSet)

    def test_getBranchesWithVisibleBugs_no_branches(self):
        bug_branches = getUtility(IBugBranchSet)
        links = bug_branches.getBranchesWithVisibleBugs(
            [], self.factory.makePerson())
        self.assertEqual([], list(links))

    def test_getBranchesWithVisibleBugs_finds_branches_with_public_bugs(self):
        # IBugBranchSet.getBranchesWithVisibleBugs returns all of the
        # Branch ids associated with the given branches that have bugs
        # visible to the current user.  Those trivially include ones
        # for non-private bugs.
        branch_1 = self.factory.makeBranch()
        branch_2 = self.factory.makeBranch()
        bug_a = self.factory.makeBug()
        self.factory.makeBug()
        self.factory.loginAsAnyone()
        bug_a.linkBranch(branch_1, self.factory.makePerson())
        bug_a.linkBranch(branch_2, self.factory.makePerson())
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [branch_1.id, branch_2.id],
            utility.getBranchesWithVisibleBugs(
                [branch_1, branch_2], self.factory.makePerson()))

    def test_getBranchesWithVisibleBugs_shows_public_bugs_to_anon(self):
        # getBranchesWithVisibleBugs shows public bugs to anyone,
        # including anonymous users.
        branch = self.factory.makeBranch()
        bug = self.factory.makeBug()
        with celebrity_logged_in('admin'):
            bug.linkBranch(branch, self.factory.makePerson())
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [branch.id], utility.getBranchesWithVisibleBugs([branch], None))

    def test_getBranchesWithVisibleBugs_ignores_duplicate_bugbranches(self):
        # getBranchesWithVisibleBugs reports a branch only once even if
        # it's linked to the same bug multiple times.
        branch = self.factory.makeBranch()
        user = self.factory.makePerson()
        bug = self.factory.makeBug()
        self.factory.loginAsAnyone()
        bug.linkBranch(branch, user)
        bug.linkBranch(branch, user)
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [branch.id], utility.getBranchesWithVisibleBugs([branch], user))

    def test_getBranchesWithVisibleBugs_ignores_extra_bugs(self):
        # getBranchesWithVisibleBugs reports a branch only once even if
        # it's liked to multiple bugs.
        branch = self.factory.makeBranch()
        user = self.factory.makePerson()
        with celebrity_logged_in('admin'):
            self.factory.makeBug().linkBranch(branch, user)
            self.factory.makeBug().linkBranch(branch, user)
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [branch.id], utility.getBranchesWithVisibleBugs([branch], user))

    def test_getBranchesWithVisibleBugs_hides_private_bugs_from_anon(self):
        # getBranchesWithVisibleBugs does not show private bugs to users
        # who aren't logged in.
        branch = self.factory.makeBranch()
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        with celebrity_logged_in('admin'):
            bug.linkBranch(branch, self.factory.makePerson())
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [], utility.getBranchesWithVisibleBugs([branch], None))

    def test_getBranchesWithVisibleBugs_hides_private_bugs_from_joe(self):
        # getBranchesWithVisibleBugs does not show private bugs to
        # arbitrary logged-in users (such as Average Joe, or J. Random
        # Hacker).
        branch = self.factory.makeBranch()
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        with celebrity_logged_in('admin'):
            bug.linkBranch(branch, self.factory.makePerson())
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [],
            utility.getBranchesWithVisibleBugs(
                [branch], self.factory.makePerson()))

    def test_getBranchesWithVisibleBugs_shows_private_bugs_to_sub(self):
        # getBranchesWithVisibleBugs will show private bugs to their
        # subscribers.
        branch = self.factory.makeBranch()
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        user = self.factory.makePerson()
        with celebrity_logged_in('admin'):
            bug.subscribe(user, self.factory.makePerson())
            bug.linkBranch(branch, self.factory.makePerson())
        utility = getUtility(IBugBranchSet)
        self.assertContentEqual(
            [branch.id], utility.getBranchesWithVisibleBugs([branch], user))

    def test_getBranchesWithVisibleBugs_shows_private_bugs_to_admins(self):
        # getBranchesWithVisibleBugs will show private bugs to admins.
        branch = self.factory.makeBranch()
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        with celebrity_logged_in('admin'):
            bug.linkBranch(branch, self.factory.makePerson())
        utility = getUtility(IBugBranchSet)
        admin = getUtility(ILaunchpadCelebrities).admin
        self.assertContentEqual(
            [branch.id], utility.getBranchesWithVisibleBugs([branch], admin))

    def test_getBugBranchesForBugTasks(self):
        # IBugBranchSet.getBugBranchesForBugTasks returns all of the BugBranch
        # objects associated with the given bug tasks.
        bug_a = self.factory.makeBug()
        bug_b = self.factory.makeBug()
        bugtasks = bug_a.bugtasks + bug_b.bugtasks
        branch = self.factory.makeBranch()
        self.factory.loginAsAnyone()
        link_1 = bug_a.linkBranch(branch, self.factory.makePerson())
        link_2 = bug_b.linkBranch(branch, self.factory.makePerson())
        found_links = getUtility(IBugBranchSet).getBugBranchesForBugTasks(
            bugtasks)
        self.assertEqual(set([link_1, link_2]), set(found_links))


class TestBugBranch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugBranch, self).setUp()
        # Bug branch linking is generally available to any logged in user.
        self.factory.loginAsAnyone()

    def test_bugbranch_provides_IBugBranch(self):
        # BugBranch objects provide IBugBranch.
        bug_branch = BugBranch(
            branch=self.factory.makeBranch(), bug=self.factory.makeBug(),
            registrant=self.factory.makePerson())
        self.assertProvides(bug_branch, IBugBranch)

    def test_linkBranch_returns_IBugBranch(self):
        # Bug.linkBranch returns an IBugBranch linking the bug to the branch.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        registrant = self.factory.makePerson()
        bug_branch = bug.linkBranch(branch, registrant)
        self.assertEqual(branch, bug_branch.branch)
        self.assertEqual(bug, bug_branch.bug)
        self.assertEqual(registrant, bug_branch.registrant)

    def test_bug_start_with_no_linked_branches(self):
        # Bugs have a linked_branches attribute which is initially an empty
        # collection.
        bug = self.factory.makeBug()
        self.assertEqual([], list(bug.linked_branches))

    def test_linkBranch_adds_to_linked_branches(self):
        # Bug.linkBranch populates the Bug.linked_branches with the created
        # BugBranch object.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        bug_branch = bug.linkBranch(branch, self.factory.makePerson())
        self.assertEqual([bug_branch], list(bug.linked_branches))

    def test_linking_branch_twice_returns_same_IBugBranch(self):
        # Calling Bug.linkBranch twice with the same parameters returns the
        # same object.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        bug_branch = bug.linkBranch(branch, self.factory.makePerson())
        bug_branch_2 = bug.linkBranch(branch, self.factory.makePerson())
        self.assertEqual(bug_branch, bug_branch_2)

    def test_linking_branch_twice_different_registrants(self):
        # Calling Bug.linkBranch twice with the branch but different
        # registrants returns the existing bug branch object rather than
        # creating a new one.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        bug_branch = bug.linkBranch(branch, self.factory.makePerson())
        bug_branch_2 = bug.linkBranch(branch, self.factory.makePerson())
        self.assertEqual(bug_branch, bug_branch_2)

    def test_bug_has_no_branches(self):
        # Bug.hasBranch returns False for any branch that it is not linked to.
        bug = self.factory.makeBug()
        self.assertFalse(bug.hasBranch(self.factory.makeBranch()))

    def test_bug_has_branch(self):
        # Bug.hasBranch returns False for any branch that it is linked to.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        bug.linkBranch(branch, self.factory.makePerson())
        self.assertTrue(bug.hasBranch(branch))

    def test_unlink_branch(self):
        # Bug.unlinkBranch removes the bug<->branch link.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        bug.linkBranch(branch, self.factory.makePerson())
        bug.unlinkBranch(branch, self.factory.makePerson())
        self.assertEqual([], list(bug.linked_branches))
        self.assertFalse(bug.hasBranch(branch))

    def test_unlink_not_linked_branch(self):
        # When unlinkBranch is called with a branch that isn't already linked,
        # nothing discernable happens.
        bug = self.factory.makeBug()
        branch = self.factory.makeBranch()
        bug.unlinkBranch(branch, self.factory.makePerson())
        self.assertEqual([], list(bug.linked_branches))
        self.assertFalse(bug.hasBranch(branch))

    def test_the_unwashed_cannot_link_branch_to_private_bug(self):
        # Those who cannot see a bug are forbidden to link a branch to it.
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        self.assertRaises(Unauthorized, getattr, bug, 'linkBranch')

    def test_the_unwashed_cannot_unlink_branch_from_private_bug(self):
        # Those who cannot see a bug are forbidden to unlink branches from it.
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        self.assertRaises(Unauthorized, getattr, bug, 'unlinkBranch')

    def test_anonymous_users_cannot_link_branches(self):
        # Anonymous users cannot link branches to bugs, even public bugs.
        bug = self.factory.makeBug()
        with anonymous_logged_in():
            self.assertRaises(Unauthorized, getattr, bug, 'linkBranch')

    def test_anonymous_users_cannot_unlink_branches(self):
        # Anonymous users cannot unlink branches from bugs, even public bugs.
        bug = self.factory.makeBug()
        with anonymous_logged_in():
            self.assertRaises(Unauthorized, getattr, bug, 'unlinkBranch')

    def test_adding_branch_changes_date_last_updated(self):
        # Adding a branch to a bug changes IBug.date_last_updated.
        bug = self.factory.makeBug()
        last_updated = bug.date_last_updated
        branch = self.factory.makeBranch()
        self.factory.loginAsAnyone()
        bug.linkBranch(branch, self.factory.makePerson())
        self.assertTrue(bug.date_last_updated > last_updated)
