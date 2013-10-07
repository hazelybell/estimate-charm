# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'TeamJoinMixin',
    'userIsActiveTeamMember',
    ]

from zope.component import getUtility

from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchBag


def userIsActiveTeamMember(team):
    """Return True if the user is an active member of this team."""
    user = getUtility(ILaunchBag).user
    if user is None:
        return False
    if not check_permission('launchpad.View', team):
        return False
    return user in team.activemembers


class TeamJoinMixin:
    """Mixin class for views related to joining teams."""

    @property
    def user_can_subscribe_to_list(self):
        """Can the prospective member subscribe to this team's mailing list?

        A user can subscribe to the list if the team has an active
        mailing list, and if they do not already have a subscription.
        """
        if self.team_has_mailing_list:
            # If we are already subscribed, then we can not subscribe again.
            return not self.user_is_subscribed_to_list
        else:
            return False

    @property
    def user_is_subscribed_to_list(self):
        """Is the user subscribed to the team's mailing list?

        Subscriptions hang around even if the list is deactivated, etc.

        It is an error to ask if the user is subscribed to a mailing list
        that doesn't exist.
        """
        if self.user is None:
            return False

        mailing_list = self.context.mailing_list
        assert mailing_list is not None, "This team has no mailing list."
        has_subscription = bool(mailing_list.getSubscription(self.user))
        return has_subscription

    @property
    def team_has_mailing_list(self):
        """Is the team mailing list available for subscription?"""
        mailing_list = self.context.mailing_list
        return mailing_list is not None and mailing_list.is_usable

    @property
    def user_is_active_member(self):
        """Return True if the user is an active member of this team."""
        return userIsActiveTeamMember(self.context)

    @property
    def user_is_proposed_member(self):
        """Return True if the user is a proposed member of this team."""
        if self.user is None:
            return False
        return self.user in self.context.proposedmembers

    @property
    def user_can_request_to_leave(self):
        """Return true if the user can request to leave this team.

        A given user can leave a team only if he's an active member.
        """
        return self.user_is_active_member
