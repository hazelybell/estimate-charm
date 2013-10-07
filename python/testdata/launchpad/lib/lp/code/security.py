# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Security adapters for the code module."""

__metaclass__ = type
__all__ = [
    'BranchSubscriptionEdit',
    'BranchSubscriptionView',
    ]

from lp.app.security import AuthorizationBase
from lp.code.interfaces.branchsubscription import IBranchSubscription


class BranchSubscriptionEdit(AuthorizationBase):
    permission = 'launchpad.Edit'
    usedfor = IBranchSubscription

    def checkAuthenticated(self, user):
        """Is the user able to edit a branch subscription?

        Any team member can edit a branch subscription for their team.
        Launchpad Admins can also edit any branch subscription.
        The owner of the subscribed branch can edit the subscription. If the
        branch owner is a team, then members of the team can edit the
        subscription.
        """
        return (user.inTeam(self.obj.branch.owner) or
                user.inTeam(self.obj.person) or
                user.inTeam(self.obj.subscribed_by) or
                user.in_admin)


class BranchSubscriptionView(BranchSubscriptionEdit):
    permission = 'launchpad.View'
