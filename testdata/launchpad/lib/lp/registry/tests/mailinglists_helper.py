# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions for testing XML-RPC services."""

__metaclass__ = type
__all__ = [
    'fault_catcher',
    'get_alternative_email',
    'mailman',
    'new_list_for_team',
    'new_team',
    ]


import xmlrpclib

from zope.component import getUtility

from lp.registry.enums import TeamMembershipPolicy
from lp.registry.interfaces.mailinglist import (
    IMailingListSet,
    IMessageApprovalSet,
    MailingListStatus,
    PostedMessageStatus,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.xmlrpc.mailinglist import MailingListAPIView
from lp.services.database.sqlbase import flush_database_updates


COMMASPACE = ', '


def fault_catcher(func):
    """Decorator for displaying Faults in a cross-compatible way.

    When running the same doctest with the ServerProxy, faults are turned into
    exceptions by the XMLRPC machinery, but with the direct view the faults
    are just returned.  This causes an impedance mismatch with exception
    display in the doctest that cannot be papered over by using ellipses.  So
    to make this work in a consistent way, a subclass of the view class is
    used which prints faults to match the output of ServerProxy (proper
    exceptions aren't really necessary).
    """

    def caller(self, *args, **kws):
        result = func(self, *args, **kws)
        if isinstance(result, xmlrpclib.Fault):
            # Fake this to look like exception output.  The second line is
            # necessary to match ellipses in the doctest, but its contents are
            # completely ignored; /something/ just has to be there.
            print 'Traceback (most recent call last):'
            print 'ignore'
            print 'Fault:', result
        else:
            return result
    return caller


def new_team(team_name, with_list=False):
    """A helper function for the mailinglist doctests.

    This just provides a convenience function for creating the kinds of teams
    we need to use in the doctest.
    """
    displayname = ' '.join(word.capitalize() for word in team_name.split('-'))
    # XXX BarryWarsaw 2007-09-27 bug 125505: Set the team's subscription
    # policy to OPEN.
    policy = TeamMembershipPolicy.OPEN
    personset = getUtility(IPersonSet)
    team_creator = personset.getByName('no-priv')
    team = personset.newTeam(team_creator, team_name, displayname,
                             membership_policy=policy)
    if not with_list:
        return team
    else:
        return team, new_list_for_team(team)


def new_list_for_team(team):
    """A helper that creates a new, active mailing list for a team.

    Used in doctests.
    """
    list_set = getUtility(IMailingListSet)
    team_list = list_set.new(team)
    team_list.startConstructing()
    team_list.transitionToStatus(MailingListStatus.ACTIVE)
    flush_database_updates()
    return team_list


def get_alternative_email(person):
    """Return a non-preferred IEmailAddress for a person.

    This assumes and asserts that there is exactly one non-preferred email
    address for the person.
    """
    alternatives = list(person.validatedemails)
    assert len(alternatives) == 1, (
        'Unexpected email count: %d' % len(alternatives))
    return alternatives[0]


class MailmanStub:
    """A stand-in for Mailman's XMLRPC client for page tests."""

    def act(self):
        """Perform the effects of the Mailman XMLRPC client.

        This doesn't have to be complete, it just has to do whatever the
        appropriate tests require.
        """
        # Simulate constructing and activating new mailing lists.
        mailing_list_set = getUtility(IMailingListSet)
        for mailing_list in mailing_list_set.approved_lists:
            mailing_list.startConstructing()
            mailing_list.transitionToStatus(MailingListStatus.ACTIVE)
        for mailing_list in mailing_list_set.deactivated_lists:
            mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        for mailing_list in mailing_list_set.modified_lists:
            mailing_list.startUpdating()
            mailing_list.transitionToStatus(MailingListStatus.ACTIVE)
        # Simulate acknowledging held messages.
        message_set = getUtility(IMessageApprovalSet)
        for status in (PostedMessageStatus.APPROVAL_PENDING,
                       PostedMessageStatus.REJECTION_PENDING,
                       PostedMessageStatus.DISCARD_PENDING):
            message_set.acknowledgeMessagesWithStatus(status)


mailman = MailmanStub()


class MailingListXMLRPCTestProxy(MailingListAPIView):
    """A low impedance test proxy for code that uses MailingListAPIView."""

    @fault_catcher
    def getPendingActions(self):
        return super(MailingListXMLRPCTestProxy, self).getPendingActions()

    @fault_catcher
    def reportStatus(self, statuses):
        return super(MailingListXMLRPCTestProxy, self).reportStatus(statuses)

    @fault_catcher
    def getMembershipInformation(self, teams):
        return super(
            MailingListXMLRPCTestProxy, self).getMembershipInformation(teams)

    @fault_catcher
    def isLaunchpadMember(self, address):
        return super(MailingListXMLRPCTestProxy, self).isLaunchpadMember(
            address)

    @fault_catcher
    def isTeamPublic(self, team_name):
        return super(MailingListXMLRPCTestProxy, self).isTeamPublic(team_name)
