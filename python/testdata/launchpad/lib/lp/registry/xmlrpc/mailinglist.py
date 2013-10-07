# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XMLRPC APIs for mailing lists."""

__metaclass__ = type
__all__ = [
    'MailingListAPIView',
    ]

import re
import xmlrpclib

from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.mailinglist import (
    IMailingListAPIView,
    IMailingListSet,
    IMessageApprovalSet,
    MailingListStatus,
    PostedMessageStatus,
    )
from lp.registry.interfaces.person import (
    IPersonSet,
    PersonalStanding,
    )
from lp.services.config import config
from lp.services.encoding import escape_nonascii_uniquely
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp import LaunchpadXMLRPCView
from lp.xmlrpc import faults

# Not all developers will have built the Mailman instance (via
# 'make mailman_instance').  In that case, this import will fail, but in that
# case just use the constant value directly.
try:
    from Mailman.MemberAdaptor import ENABLED, BYUSER
    ENABLED, BYUSER
except ImportError:
    ENABLED = 0
    BYUSER = 2


class MailingListAPIView(LaunchpadXMLRPCView):
    """The XMLRPC API that Mailman polls for mailing list actions."""

    implements(IMailingListAPIView)

    def getPendingActions(self):
        """See `IMailingListAPIView`."""
        list_set = getUtility(IMailingListSet)
        # According to the interface, the return value is a dictionary where
        # the keys are one of the pending actions 'create', 'deactivate', or
        # 'modify'.  Do the 'create' action first, where the value is a
        # sequence of 2-tuples giving the team name and any initial values for
        # the mailing list.
        response = {}
        # Handle unsynchronized lists.
        unsynchronized = []
        for mailing_list in list_set.unsynchronized_lists:
            name = removeSecurityProxy(mailing_list.team).name
            if mailing_list.status == MailingListStatus.CONSTRUCTING:
                unsynchronized.append((name, 'constructing'))
            elif mailing_list.status == MailingListStatus.UPDATING:
                unsynchronized.append((name, 'updating'))
            else:
                raise AssertionError(
                    'Mailing list is neither CONSTRUCTING nor UPDATING: %s'
                    % name)
        if len(unsynchronized) > 0:
            response['unsynchronized'] = unsynchronized
        creates = []
        for mailing_list in list_set.approved_lists:
            initializer = {}
            # If the welcome message is not None, that means it is being
            # initialized when the list is created.  Currently, this is the
            # only value that can be initialized.
            if mailing_list.welcome_message is not None:
                initializer['welcome_message'] = mailing_list.welcome_message
            creates.append(
                (removeSecurityProxy(mailing_list.team).name, initializer))
            # In addition, all approved mailing lists that are being
            # constructed by Mailman need to have their status changed.
            mailing_list.startConstructing()
        if len(creates) > 0:
            response['create'] = creates
        # Next do mailing lists that are to be deactivated.
        deactivated = [removeSecurityProxy(mailing_list.team).name
                       for mailing_list in list_set.deactivated_lists]
        if len(deactivated) > 0:
            response['deactivate'] = deactivated
        # Do modified lists.  Currently, the only value that can be modified
        # is the welcome message.
        modified = []
        for mailing_list in list_set.modified_lists:
            changes = (removeSecurityProxy(mailing_list.team).name,
                       dict(welcome_message=mailing_list.welcome_message))
            modified.append(changes)
            mailing_list.startUpdating()
        if len(modified) > 0:
            response['modify'] = modified
        return response

    def reportStatus(self, statuses):
        """See `IMailingListAPIView`."""
        list_set = getUtility(IMailingListSet)
        for team_name, action_status in statuses.items():
            mailing_list = list_set.get(team_name)
            if mailing_list is None:
                return faults.NoSuchTeamMailingList(team_name)
            if action_status == 'failure':
                if mailing_list.status == MailingListStatus.CONSTRUCTING:
                    mailing_list.transitionToStatus(MailingListStatus.FAILED)
                elif mailing_list.status in (MailingListStatus.UPDATING,
                                             MailingListStatus.DEACTIVATING):
                    mailing_list.transitionToStatus(
                        MailingListStatus.MOD_FAILED)
                else:
                    return faults.UnexpectedStatusReport(
                        team_name, action_status)
            elif action_status == 'success':
                if mailing_list.status in (MailingListStatus.CONSTRUCTING,
                                           MailingListStatus.UPDATING):
                    mailing_list.transitionToStatus(MailingListStatus.ACTIVE)
                elif mailing_list.status == MailingListStatus.DEACTIVATING:
                    mailing_list.transitionToStatus(
                        MailingListStatus.INACTIVE)
                else:
                    return faults.UnexpectedStatusReport(
                        team_name, action_status)
            else:
                return faults.BadStatus(team_name, action_status)
        # Everything was fine.
        return True

    def getMembershipInformation(self, teams):
        """See `IMailingListAPIView`."""
        mailing_list_set = getUtility(IMailingListSet)
        response = {}
        # There are two sets of email addresses we need.  The first is the set
        # of all email addresses which can post to specific mailing lists.
        poster_addresses = mailing_list_set.getSenderAddresses(teams)
        # The second is the set of all email addresses which will receive
        # messages posted to the mailing lists.
        subscriber_addresses = mailing_list_set.getSubscribedAddresses(teams)
        # The above two results are dictionaries mapping team names to lists
        # of string addresses.  The expected response is a dictionary mapping
        # team names to lists of membership-tuples.  Each membership-tuple
        # contains the email address, fullname, flags (currently hardcoded to
        # 0 to mean regular delivery, no self-post acknowledgements, receive
        # own posts, and no moderation), and status (either ENABLED meaning
        # they can post to the mailing list or BYUSER meaning they can't).
        for team_name in teams:
            team_posters = poster_addresses.get(team_name, [])
            team_subscribers = subscriber_addresses.get(team_name, [])
            if not team_posters and not team_subscribers:
                # Mailman requested a bogus team.  Ignore it.
                response[team_name] = None
                continue
            # Map {address -> (full_name, flags, status)}
            members = {}
            # Hard code flags to 0 currently, meaning the member will get
            # regular (not digest) delivery, will not get post
            # acknowledgements, will receive their own posts, and will not
            # be moderated.  A future phase may change some of these
            # values.
            flags = 0
            # Turn the lists of 2-tuples into two sets and a dictionary.  The
            # dictionary maps email addresses to full names.
            posters = set()
            subscribers = set()
            full_names = dict()
            for full_name, address in team_posters:
                posters.add(address)
                full_names[address] = full_name
            for full_name, address in team_subscribers:
                subscribers.add(address)
                full_names[address] = full_name
            # The team members is the union of all posters and subscribers.
            # Iterate through these addresses, creating the 3-tuple entry
            # required for the members map for this team.
            for address in (posters | subscribers):
                if address in subscribers:
                    status = ENABLED
                else:
                    status = BYUSER
                members[address] = (full_names[address], flags, status)
            # Add the archive recipient if there is one, and if the team is
            # public.  This address should never be registered in Launchpad,
            # meaning specifically that the isRegisteredInLaunchpad() test
            # below should always fail for it.  That way, the address can
            # never be used to forge spam onto a list.
            mailing_list = mailing_list_set.get(team_name)
            if config.mailman.archive_address and mailing_list.is_public:
                members[config.mailman.archive_address] = ('', flags, ENABLED)
            # The response must be a dictionary mapping team names to lists of
            # 4-tuples: (address, full_name, flags, status)
            response[team_name] = [
                (address, members[address][0],
                 members[address][1], members[address][2])
                for address in sorted(members)]
        return response

    def isTeamPublic(self, team_name):
        """See `IMailingListAPIView.`."""
        team = getUtility(IPersonSet).getByName(team_name)
        if team is None:
            return faults.NoSuchPersonWithName(team_name)
        return team.visibility == PersonVisibility.PUBLIC

    def isRegisteredInLaunchpad(self, address):
        """See `IMailingListAPIView.`."""
        if (config.mailman.archive_address and
            address == config.mailman.archive_address):
            # Hard code that the archive address is never registered in
            # Launchpad, so forged messages from that sender will always be
            # discarded.
            return False
        email_address = getUtility(IEmailAddressSet).getByEmail(address)
        return (email_address is not None and
                not email_address.person.is_team and
                email_address.status in (EmailAddressStatus.VALIDATED,
                                         EmailAddressStatus.PREFERRED))

    def inGoodStanding(self, address):
        """See `IMailingListAPIView`."""
        person = getUtility(IPersonSet).getByEmail(address)
        if person is None or person.is_team:
            return False
        return person.personal_standing in (PersonalStanding.GOOD,
                                            PersonalStanding.EXCELLENT)

    def holdMessage(self, team_name, bytes):
        """See `IMailingListAPIView`."""
        # For testing purposes, accept both strings and Binary instances.  In
        # production, bytes will always be a Binary so that unencoded
        # non-ascii characters in the message can be safely passed across
        # XMLRPC. For most tests though it's much more convenient to just
        # pass 8-bit strings.
        if isinstance(bytes, xmlrpclib.Binary):
            bytes = bytes.data
        # Although it is illegal for an email header to have unencoded
        # non-ascii characters, it is better to let the list owner
        # process the message than to cause an oops.
        header_body_separator = re.compile('\r\n\r\n|\r\r|\n\n')
        match = header_body_separator.search(bytes)
        header = bytes[:match.start()]
        header = escape_nonascii_uniquely(header)
        bytes = header + bytes[match.start():]

        mailing_list = getUtility(IMailingListSet).get(team_name)
        message = getUtility(IMessageSet).fromEmail(bytes)
        mailing_list.holdMessage(message)
        return True

    def getMessageDispositions(self):
        """See `IMailingListAPIView`."""
        message_set = getUtility(IMessageApprovalSet)
        # A mapping from message ids to statuses.
        response = {}
        # Start by iterating over all held messages that are pending approval.
        # These are messages that the team owner has approved, but Mailman
        # hasn't yet acted upon.  For each of these, set their state to final
        # approval.
        status_dispositions = (
            (PostedMessageStatus.APPROVAL_PENDING, 'accept'),
            (PostedMessageStatus.REJECTION_PENDING, 'decline'),
            (PostedMessageStatus.DISCARD_PENDING, 'discard'),
            )
        for status, disposition in status_dispositions:
            held_messages = message_set.getHeldMessagesWithStatus(status)
            for message_id, team_name in held_messages:
                response[message_id] = (team_name, disposition)
            message_set.acknowledgeMessagesWithStatus(status)
        return response
