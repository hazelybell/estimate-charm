# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Import mailing list information."""

__metaclass__ = type
__all__ = [
    'Importer',
    ]


from email.Utils import parseaddr

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.mailinglist import (
    CannotSubscribe,
    IMailingListSet,
    MailingListStatus,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.log.logger import BufferLogger


class Importer:
    """Perform mailing list imports for command line scripts."""

    def __init__(self, team_name, log=None):
        self.team_name = team_name
        self.team = getUtility(IPersonSet).getByName(team_name)
        assert self.team is not None, (
            'No team with name: %s' % team_name)
        self.mailing_list = getUtility(IMailingListSet).get(team_name)
        assert self.mailing_list is not None, (
            'Team has no mailing list: %s' % team_name)
        assert self.mailing_list.status == MailingListStatus.ACTIVE, (
            'Team mailing list is not active: %s' % team_name)
        if log is None:
            self.log = BufferLogger()
        else:
            self.log = log

    def importAddresses(self, addresses):
        """Import all addresses.

        Every address that is preferred or validated and connected to a person
        is made a member of the team, and is subscribed to the mailing list
        (with the address given).  If the address is not valid, or if it is
        associated with a team, the address is ignored.

        :param addresses: The email addresses to join and subscribe.
        :type addresses: sequence of strings
        """
        email_set = getUtility(IEmailAddressSet)
        person_set = getUtility(IPersonSet)
        for entry in addresses:
            real_name, address = parseaddr(entry)
            # address could be empty or None.
            if not address:
                continue
            person = person_set.getByEmail(address, filter_status=False)
            if person is None or person.is_team:
                self.log.error('No person for address: %s', address)
                continue
            email = email_set.getByEmail(address)
            assert email is not None, (
                'Address has no IEmailAddress? %s' % address)
            if email.status not in (EmailAddressStatus.PREFERRED,
                                    EmailAddressStatus.VALIDATED):
                self.log.error('No valid email for address: %s', address)
                continue
            # Turn off may_subscribe_to_list because we want to explicitly
            # force subscription without relying on the person's
            # auto-subscribe policy.
            naked_team = removeSecurityProxy(self.team)
            naked_team.addMember(person, reviewer=person,
                                 status=TeamMembershipStatus.APPROVED,
                                 force_team_add=True,
                                 may_subscribe_to_list=False)
            try:
                self.mailing_list.subscribe(person, email)
            except CannotSubscribe as error:
                self.log.error('%s', error)
            # It's okay to str()-ify these because addresses and person names
            # are guaranteed to be in the ASCII range.
            self.log.info('%s (%s) joined and subscribed',
                          str(address), str(person.name))

    def importFromFile(self, filename):
        """Import all addresses given in the named file.

        The named file has email address to import, one per line.  The lines
        may be formatted using any format recognized by
        `email.Utils.parseaddr()`.

        :param filename: The name of the file containing email address.
        :type filename: string
        """
        in_file = open(filename)
        try:
            addresses = list(in_file)
        finally:
            in_file.close()
        self.importAddresses(addresses)
