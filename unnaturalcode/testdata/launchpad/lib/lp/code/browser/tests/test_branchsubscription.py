# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for BranchSubscriptions."""

__metaclass__ = type

from lp.app.enums import InformationType
from lp.services.webapp.interfaces import IPrimaryContext
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class TestBranchSubscriptionPrimaryContext(TestCaseWithFactory):
    # Tests the adaptation of a branch subscription into a primary context.

    layer = DatabaseFunctionalLayer

    def testPrimaryContext(self):
        # The primary context of a branch subscription is the same as the
        # primary context of the branch that the subscription is for.
        subscription = self.factory.makeBranchSubscription()
        self.assertEqual(
            IPrimaryContext(subscription).context,
            IPrimaryContext(subscription.branch).context)


class TestBranchSubscriptionAddOtherView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_cannot_subscribe_open_team_to_private_branch(self):
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA, owner=owner)
        team = self.factory.makeTeam()
        form = {
            'field.person': team.name,
            'field.notification_level': 'NOEMAIL',
            'field.max_diff_lines': 'NODIFF',
            'field.review_level': 'NOEMAIL',
            'field.actions.subscribe_action': 'Subscribe'}
        with person_logged_in(owner):
            view = create_initialized_view(
                branch, '+addsubscriber', pricipal=owner, form=form)
            self.assertContentEqual(
                ['Open and delegated teams cannot be subscribed to private '
                'branches.'], view.errors)

    def test_can_subscribe_open_team_to_public_branch(self):
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(owner=owner)
        team = self.factory.makeTeam()
        form = {
            'field.person': team.name,
            'field.notification_level': 'NOEMAIL',
            'field.max_diff_lines': 'NODIFF',
            'field.review_level': 'NOEMAIL',
            'field.actions.subscribe_action': 'Subscribe'}
        with person_logged_in(owner):
            view = create_initialized_view(
                branch, '+addsubscriber', pricipal=owner, form=form)
            self.assertContentEqual([], view.errors)
