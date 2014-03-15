# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for visibility of branches.

Most branches on Launchpad are considered public branches, and are
visible to everybody, even people not logged in.

Some branches are also considered "private".  These are branches that
are only visible to the owner of the branch, and the subscribers.
"""

__metaclass__ = type

from zope.component import (
    getAdapter,
    getUtility,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.interfaces.security import IAuthorization
from lp.code.enums import (
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.interfaces.branch import IBranchSet
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.registry.interfaces.role import IPersonRoles
from lp.security import AccessBranch
from lp.services.webapp.authorization import (
    check_permission,
    clear_cache,
    )
from lp.services.webapp.interaction import ANONYMOUS
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchVisibility(TestCaseWithFactory):
    """Tests for branch privacy."""

    layer = DatabaseFunctionalLayer

    def test_branch_permission(self):
        #Calling check_permission is used to show that the AccessBranch is in
        #fact configured correctly.
        branch = self.factory.makeBranch()
        login(ANONYMOUS)
        self.assertTrue(check_permission('launchpad.View', branch))
        login('test@canonical.com')
        self.assertTrue(check_permission('launchpad.View', branch))

    def test_branch_access(self):
        # Accessing any attributes of the Branch content class through the
        # IBranch interface is configured to require the launchpad.View
        # permission. The AccessBranch authorization class is used to
        # authorize users for the combination of the launchpad.View permission
        # and the IBranch interface.
        branch = self.factory.makeBranch()
        naked_branch = removeSecurityProxy(branch)
        self.assertTrue(
            isinstance(
                getAdapter(branch, IAuthorization, name='launchpad.View'),
                AccessBranch))
        access = AccessBranch(naked_branch)
        self.assertTrue(access.checkUnauthenticated())
        person = self.factory.makePerson()
        self.assertTrue(
            access.checkAuthenticated(IPersonRoles(person)))

    def test_visible_to_owner(self):
        # The owners of a branch always have visibility of their own branches.

        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            owner=owner, information_type=InformationType.USERDATA)
        naked_branch = removeSecurityProxy(branch)

        clear_cache()  # Clear authorization cache for check_permission.
        access = AccessBranch(naked_branch)
        self.assertFalse(access.checkUnauthenticated())
        self.assertTrue(
            access.checkAuthenticated(IPersonRoles(owner)))
        self.assertFalse(check_permission('launchpad.View', branch))

    def test_visible_to_administrator(self):
        # Launchpad administrators often have a need to see private
        # Launchpad things in order to fix up fubars by users.
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        naked_branch = removeSecurityProxy(branch)
        admin = getUtility(ILaunchpadCelebrities).admin.teamowner
        access = AccessBranch(naked_branch)
        self.assertTrue(access.checkAuthenticated(IPersonRoles(admin)))

    def test_visible_to_subscribers(self):
        # Branches that are not public are viewable by members of the
        # visibility_team and to subscribers.
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        naked_branch = removeSecurityProxy(branch)
        person = self.factory.makePerson()
        teamowner = self.factory.makePerson()
        team = self.factory.makeTeam(
            membership_policy=TeamMembershipPolicy.MODERATED,
            owner=teamowner, members=[person])

        # Not visible to an unsubscribed person.
        access = AccessBranch(naked_branch)
        self.assertFalse(access.checkAuthenticated(IPersonRoles(person)))

        # Subscribing the team to the branch will allow access to the branch.
        naked_branch.subscribe(
            team,
            BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.NOEMAIL, teamowner)
        self.assertTrue(access.checkAuthenticated(IPersonRoles(person)))

    def test_branchset_restricted_queries(self):
        # All of the BranchSet queries that are used to populate user viewable
        # branch listings have an optional parameter called `visible_by_user`.
        # This parameter is used to restrict the result set to those branches
        # that would be visible by that user. If the parameter is None, then
        # only the public branches are returned.
        #
        # Since we are printing out general private branch details, we log in
        # a member of the Launchpad admin team so there are no permission
        # errors.

        login('foo.bar@canonical.com')
        branch_set = getUtility(IBranchSet)

        # Make some test branches
        private_owner = self.factory.makePerson()
        test_branches = []
        for x in range(5):
            # We want the first 3 public and the last 3 private.
            information_type = InformationType.PUBLIC
            if x > 2:
                information_type = InformationType.USERDATA
            branch = self.factory.makeBranch(
                information_type=information_type)
            test_branches.append(branch)
        test_branches.append(
            self.factory.makeBranch(
                owner=private_owner,
                information_type=InformationType.USERDATA))

        # Anonymous users see just the public branches.
        branch_info = [(branch, branch.private)
                for branch in branch_set.getRecentlyRegisteredBranches(3)]
        self.assertEqual([
            (test_branches[2], False),
            (test_branches[1], False),
            (test_branches[0], False),
        ], branch_info)

        # An arbitrary person is not in eligible to see any of the private
        # branches.
        person = self.factory.makePerson()
        branch_info = [(branch, branch.private)
                for branch in branch_set.getRecentlyRegisteredBranches(
                    3, visible_by_user=person)]
        self.assertEqual([
            (test_branches[2], False),
            (test_branches[1], False),
            (test_branches[0], False),
        ], branch_info)

        # Private owner sees his new private branch and other public
        # branches, but not other's private branches.
        branch_info = [(branch, branch.private)
                for branch in branch_set.getRecentlyRegisteredBranches(
                    3, visible_by_user=private_owner)]
        self.assertEqual([
            (test_branches[5], True),
            (test_branches[2], False),
            (test_branches[1], False),
        ], branch_info)

        # Launchpad admins can see all the private branches.
        admin = getUtility(ILaunchpadCelebrities).admin.teamowner
        branch_info = [(branch, branch.private)
                for branch in branch_set.getRecentlyRegisteredBranches(
                    3, visible_by_user=admin)]
        self.assertEqual([
            (test_branches[5], True),
            (test_branches[4], True),
            (test_branches[3], True),
        ], branch_info)
