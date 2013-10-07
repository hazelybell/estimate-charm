# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the BranchSubscrptions model object.."""

__metaclass__ = type


from zope.component import getUtility

from lp.app.enums import InformationType
from lp.app.errors import (
    SubscriptionPrivacyViolation,
    UserCannotUnsubscribePerson,
    )
from lp.app.interfaces.services import IService
from lp.code.enums import (
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBranchSubscriptions(TestCaseWithFactory):
    """Tests relating to branch subscriptions in general."""

    layer = DatabaseFunctionalLayer

    def test_owner_subscribed(self):
        # The owner of a branch is subscribed to the branch.
        branch = self.factory.makeBranch()
        [subscription] = list(branch.subscriptions)
        self.assertEqual(branch.owner, subscription.person)

    def test_subscribed_by_set(self):
        """The user subscribing is recorded along the subscriber."""
        subscriber = self.factory.makePerson()
        subscribed_by = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        subscription = branch.subscribe(
            subscriber, BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.NOEMAIL, subscribed_by)
        self.assertEqual(subscriber, subscription.person)
        self.assertEqual(subscribed_by, subscription.subscribed_by)

    def test_unsubscribe(self):
        """Test unsubscribing by the subscriber."""
        subscription = self.factory.makeBranchSubscription()
        subscriber = subscription.person
        branch = subscription.branch
        branch.unsubscribe(subscriber, subscriber)
        self.assertFalse(branch.hasSubscription(subscriber))

    def test_unsubscribe_by_subscriber(self):
        """Test unsubscribing by the person who subscribed the user."""
        subscribed_by = self.factory.makePerson()
        subscription = self.factory.makeBranchSubscription(
            subscribed_by=subscribed_by)
        subscriber = subscription.person
        branch = subscription.branch
        branch.unsubscribe(subscriber, subscribed_by)
        self.assertFalse(branch.hasSubscription(subscriber))

    def test_unsubscribe_by_unauthorized(self):
        """Test unsubscribing someone you shouldn't be able to."""
        subscription = self.factory.makeBranchSubscription()
        branch = subscription.branch
        self.assertRaises(
            UserCannotUnsubscribePerson,
            branch.unsubscribe,
            subscription.person,
            self.factory.makePerson())

    def test_cannot_subscribe_open_team_to_private_branch(self):
        """It is forbidden to subscribe a open team to a private branch."""
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner)
        team = self.factory.makeTeam()
        with person_logged_in(owner):
            self.assertRaises(
                SubscriptionPrivacyViolation, branch.subscribe, team, None,
                None, None, owner)

    def test_subscribe_gives_access(self):
        """Subscribing a user to a branch gives them access."""
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner)
        subscribee = self.factory.makePerson()
        with person_logged_in(owner):
            self.assertFalse(branch.visibleByUser(subscribee))
            branch.subscribe(
                subscribee, BranchSubscriptionNotificationLevel.NOEMAIL,
                None, CodeReviewNotificationLevel.NOEMAIL, owner)
            self.assertTrue(branch.visibleByUser(subscribee))

    def test_unsubscribe_removes_access(self):
        """Unsubscibing a user to a branch removes their access."""
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner)
        subscribee = self.factory.makePerson()
        with person_logged_in(owner):
            branch.subscribe(
                subscribee, BranchSubscriptionNotificationLevel.NOEMAIL,
                None, CodeReviewNotificationLevel.NOEMAIL, owner)
            self.assertTrue(branch.visibleByUser(subscribee))
            branch.unsubscribe(subscribee, owner)
            self.assertFalse(branch.visibleByUser(subscribee))

    def test_subscribe_with_editable_stacked_branch(self):
        # Subscribing to a branch also subscribes access to any private
        # stacked on branches which the subscribed_by person can edit.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        private_stacked_on_branch = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.PRIVATESECURITY)
        branch = self.factory.makeBranch(
            product=product, owner=owner, stacked_on=private_stacked_on_branch,
            information_type=InformationType.USERDATA)

        with person_logged_in(owner):
            # Subscribe to the top level branch.
            grantee = self.factory.makePerson()
            branch.subscribe(
                grantee, BranchSubscriptionNotificationLevel.NOEMAIL,
                None, CodeReviewNotificationLevel.NOEMAIL, owner)
            # The stacked on branch should be visible.
            service = getUtility(IService, 'sharing')
            ignored, visible_branches, ignored = service.getVisibleArtifacts(
                grantee, branches=[private_stacked_on_branch])
            self.assertContentEqual(
                [private_stacked_on_branch], visible_branches)
            self.assertIn(
                grantee, private_stacked_on_branch.subscribers)

    def test_subscribe_with_non_editable_stacked_branch(self):
        # Subscribing to a branch ignores any stacked on private branches
        # which the subscribed_by person can not edit.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        private_stacked_on_branch = self.factory.makeBranch(
            product=product,
            information_type=InformationType.PRIVATESECURITY)
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            stacked_on=private_stacked_on_branch,
            information_type=InformationType.USERDATA)

        service = getUtility(IService, 'sharing')
        with person_logged_in(owner):
            # Subscribe to the top level branch.
            grantee = self.factory.makePerson()
            branch.subscribe(
                grantee, BranchSubscriptionNotificationLevel.NOEMAIL,
                None, CodeReviewNotificationLevel.NOEMAIL, owner)
            # The stacked on branch should not be visible.
            ignored, visible_branches, ignored = service.getVisibleArtifacts(
                grantee, branches=[private_stacked_on_branch])
            self.assertContentEqual([], visible_branches)
            self.assertIn(
                grantee, branch.subscribers)
            self.assertNotIn(
                grantee, private_stacked_on_branch.subscribers)

    def test_subscribe_with_public_stacked_branch(self):
        # Subscribing to branches does not create subscriptions for
        # public stacked on branches.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        public_stacked_on_branch = self.factory.makeBranch(product=product)
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            stacked_on=public_stacked_on_branch,
            information_type=InformationType.USERDATA)

        with person_logged_in(owner):
            # Subscribe to the top level branch.
            grantee = self.factory.makePerson()
            branch.subscribe(
                grantee, BranchSubscriptionNotificationLevel.NOEMAIL,
                None, CodeReviewNotificationLevel.NOEMAIL, owner)
            self.assertIn(
                grantee, branch.subscribers)
            self.assertNotIn(
                grantee, public_stacked_on_branch.subscribers)


class TestBranchSubscriptionCanBeUnsubscribedbyUser(TestCaseWithFactory):
    """Tests for BranchSubscription.canBeUnsubscribedByUser."""

    layer = DatabaseFunctionalLayer

    def test_none(self):
        """None for a user always returns False."""
        subscription = self.factory.makeBranchSubscription()
        self.assertFalse(subscription.canBeUnsubscribedByUser(None))

    def test_self_subscriber(self):
        """The subscriber has permission to unsubscribe."""
        subscription = self.factory.makeBranchSubscription()
        self.assertTrue(
            subscription.canBeUnsubscribedByUser(subscription.person))

    def test_non_subscriber_fails(self):
        """An unrelated person can't unsubscribe a user."""
        subscription = self.factory.makeBranchSubscription()
        editor = self.factory.makePerson()
        self.assertFalse(subscription.canBeUnsubscribedByUser(editor))

    def test_subscribed_by(self):
        """If a user subscribes someone else, the user can unsubscribe."""
        subscribed_by = self.factory.makePerson()
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeBranchSubscription(
            person=subscriber, subscribed_by=subscribed_by)
        self.assertTrue(subscription.canBeUnsubscribedByUser(subscribed_by))

    def test_team_member_can_unsubscribe(self):
        """Any team member can unsubscribe the team from a branch."""
        team = self.factory.makeTeam()
        member = self.factory.makePerson()
        with person_logged_in(team.teamowner):
            team.addMember(member, team.teamowner)
        subscription = self.factory.makeBranchSubscription(
            person=team, subscribed_by=team.teamowner)
        self.assertTrue(subscription.canBeUnsubscribedByUser(member))

    def test_team_subscriber_can_unsubscribe(self):
        """A team can be unsubscribed by the subscriber even if they are not a
        member."""
        team = self.factory.makeTeam()
        subscribed_by = self.factory.makePerson()
        subscription = self.factory.makeBranchSubscription(
            person=team, subscribed_by=subscribed_by)
        self.assertTrue(subscription.canBeUnsubscribedByUser(subscribed_by))

    def test_branch_person_owner_can_unsubscribe(self):
        """Branch owner can unsubscribe someone from a branch."""
        branch_owner = self.factory.makePerson()
        branch = self.factory.makeBranch(owner=branch_owner)
        subscribed_by = self.factory.makePerson()
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeBranchSubscription(
            branch=branch, person=subscriber, subscribed_by=subscribed_by)
        self.assertTrue(subscription.canBeUnsubscribedByUser(branch_owner))

    def test_branch_team_owner_can_unsubscribe(self):
        """Branch team owner can unsubscribe someone from a branch.

        If the owner of a branch is a team, then the team members can
        unsubscribe someone.
        """
        team_owner = self.factory.makePerson()
        team_member = self.factory.makePerson()
        branch_owner = self.factory.makeTeam(
            owner=team_owner, members=[team_member])
        branch = self.factory.makeBranch(owner=branch_owner)
        subscribed_by = self.factory.makePerson()
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeBranchSubscription(
            branch=branch, person=subscriber, subscribed_by=subscribed_by)
        self.assertTrue(subscription.canBeUnsubscribedByUser(team_owner))
        self.assertTrue(subscription.canBeUnsubscribedByUser(team_member))
