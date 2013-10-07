# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for the private MailingList API."""

__metaclass__ = type
__all__ = []

from email import message_from_string
from textwrap import dedent
import xmlrpclib

import transaction
from zope.component import getUtility

from lp.registry.enums import TeamMembershipPolicy
from lp.registry.interfaces.mailinglist import (
    IMailingListSet,
    IMessageApprovalSet,
    MailingListStatus,
    PostedMessageStatus,
    )
from lp.registry.interfaces.person import (
    PersonalStanding,
    PersonVisibility,
    )
from lp.registry.tests.mailinglists_helper import new_team
from lp.registry.xmlrpc.mailinglist import (
    BYUSER,
    ENABLED,
    MailingListAPIView,
    )
from lp.services.config import config
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.messages.interfaces.message import IMessageSet
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.mail_helpers import pop_notifications
from lp.xmlrpc import faults


class MailingListAPITestCase(TestCaseWithFactory):
    """Tests for MailingListAPIView."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create a team with a list and subscribe self.member to it."""
        super(MailingListAPITestCase, self).setUp()
        self.team, self.mailing_list = new_team('team-a', with_list=True)
        self.member = self.factory.makePersonByName('Bob')
        with person_logged_in(self.member):
            self.member.join(self.team)
        self.mailing_list.subscribe(self.member)
        self.api = MailingListAPIView(None, None)
        self.team_expected = sorted([
            (config.mailman.archive_address, '', 0, ENABLED),
            ('bob.person@example.com', 'Bob Person', 0, ENABLED),
            ('bperson@example.org', u'Bob Person', 0, BYUSER),
            ('no-priv@canonical.com', u'No Privileges Person', 0, BYUSER),
            ])

    def test_getMembershipInformation(self):
        # Requesting a sequence of team names returns a dict:
        # team-name: (address, display name, 0, <ENABLED|BYUSER>)
        # where ENABLED are subscribers, and BYUSER are posters.
        team_b, member_b = self.factory.makeTeamWithMailingListSubscribers(
            'team-b', auto_subscribe=False)
        all_info = self.api.getMembershipInformation(
            [self.team.name, team_b.name])
        self.assertEqual(['team-a', 'team-b'], sorted(all_info.keys()))
        self.assertEqual(self.team_expected, sorted(all_info[self.team.name]))

    def test_getMembershipInformation_with_hidden_email(self):
        """Verify that hidden email addresses are still reported correctly."""
        with person_logged_in(self.member):
            self.member.hide_email_addresses = True
        all_info = self.api.getMembershipInformation([self.team.name])
        self.assertEqual(['team-a'], all_info.keys())
        self.assertEqual(self.team_expected, sorted(all_info[self.team.name]))

    def test_getMembershipInformation_remote_public_archive(self):
        # Private teams do not have config.mailman.archive_address,
        # 'archive@mail-archive.dev', in the list of membership information,
        # but public do.
        subscriber = self.factory.makePerson(email='me@eg.dom')
        team_b = self.factory.makeTeam(
            name='team-b', owner=subscriber,
            visibility=PersonVisibility.PRIVATE)
        with person_logged_in(subscriber):
            mailing_list = self.factory.makeMailingList(team_b, subscriber)
            mailing_list.subscribe(subscriber)
        private_expected = [('me@eg.dom', subscriber.displayname, 0, ENABLED)]
        all_info = self.api.getMembershipInformation(['team-a', 'team-b'])
        self.assertEqual(['team-a', 'team-b'], sorted(all_info.keys()))
        self.assertEqual(self.team_expected, sorted(all_info[self.team.name]))
        self.assertEqual(private_expected, sorted(all_info['team-b']))

    def test_getMembershipInformation_no_team(self):
        # Requesting a non-existant team will have None for the subcribers
        all_info = self.api.getMembershipInformation(['not-team'])
        self.assertEqual(['not-team'], sorted(all_info.keys()))
        self.assertIs(None, all_info['not-team'])

    def test_isRegisteredInLaunchpad_person_with_preferred_email(self):
        self.factory.makePerson(email='me@fndor.dom')
        self.assertTrue(self.api.isRegisteredInLaunchpad('me@fndor.dom'))

    def test_isRegisteredInLaunchpad_email_without_preferred_email(self):
        self.factory.makePerson(
            email='me@fndor.dom', email_address_status=EmailAddressStatus.NEW)
        self.assertFalse(self.api.isRegisteredInLaunchpad('me@fndor.dom'))

    def test_isRegisteredInLaunchpad_email_no_email_address(self):
        self.assertFalse(self.api.isRegisteredInLaunchpad('me@fndor.dom'))

    def test_isRegisteredInLaunchpad_archive_address_is_false(self):
        # The Mailman archive address can never be owned by an Lp user
        # because such a user would have acces to all lists.
        email = config.mailman.archive_address
        self.factory.makePerson(email=email)
        self.assertFalse(self.api.isRegisteredInLaunchpad(email))

    def test_isRegisteredInLaunchpad_team(self):
        self.factory.makeTeam(email='me@fndor.dom')
        self.assertFalse(self.api.isRegisteredInLaunchpad('me@fndor.dom'))

    def test_isTeamPublic(self):
        self.factory.makeTeam(
            name='team-b', visibility=PersonVisibility.PRIVATE)
        self.assertIs(True, self.api.isTeamPublic('team-a'))
        self.assertIs(False, self.api.isTeamPublic('team-b'))

    def test_isTeamPublic_fault(self):
        self.assertIsInstance(
            self.api.isTeamPublic('not-team'), faults.NoSuchPersonWithName)

    def test_inGoodStanding(self):
        self.factory.makePerson(email='no@eg.dom')
        yes_person = self.factory.makePerson(email='yes@eg.dom')
        with celebrity_logged_in('admin'):
            yes_person.personal_standing = PersonalStanding.GOOD
        self.assertIs(True, self.api.inGoodStanding('yes@eg.dom'))
        self.assertIs(False, self.api.inGoodStanding('no@eg.dom'))


class MailingListAPIWorkflowTestCase(TestCaseWithFactory):
    """Tests for MailingListAPIView workflows.

    getPendingActions and reportStatus combinations.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MailingListAPIWorkflowTestCase, self).setUp()
        self.mailinglist_api = MailingListAPIView(None, None)
        self.mailinglist_set = getUtility(IMailingListSet)

    def test_getPendingActions_nothing(self):
        # An empty dict is returned if there are no pending actions.
        self.assertEqual({}, self.mailinglist_api.getPendingActions())

    def test_getPendingActions_dict_format(self):
        # The dict has actions for keys. The values of each action is
        # a list of things that define what the action is to perform
        # on. The list can be tuples of teams and data dict to change.
        team_a = self.factory.makeTeam(name='team-a')
        team_b = self.factory.makeTeam(name='team-b')
        self.mailinglist_set.new(team_a, team_a.teamowner)
        self.mailinglist_set.new(team_b, team_b.teamowner)
        self.assertEqual(
            {'create': [
                (u'team-a', {}),
                (u'team-b', {})]},
            self.mailinglist_api.getPendingActions())

    def test_getPendingActions_constructing(self):
        # APPROVED lists have "create" actions that transition to CONSTRUCTING.
        team = self.factory.makeTeam(name='team')
        team_list = self.mailinglist_set.new(team, team.teamowner)
        self.assertEqual(MailingListStatus.APPROVED, team_list.status)
        actions = self.mailinglist_api.getPendingActions()
        self.assertEqual({'create': [(u'team', {})]}, actions)
        self.assertEqual(MailingListStatus.CONSTRUCTING, team_list.status)

    def test_reportStatus_constructing_success(self):
        # Successful constructions lead to ACTIVE lists.
        team = self.factory.makeTeam(name='team')
        team_list = self.mailinglist_set.new(team, team.teamowner)
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'success'})
        self.assertEqual(MailingListStatus.ACTIVE, team_list.status)

    def test_reportStatus_constructing_failure(self):
        # Failure constructions lead to FAILED lists.
        team = self.factory.makeTeam(name='team')
        team_list = self.mailinglist_set.new(team, team.teamowner)
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'failure'})
        self.assertEqual(MailingListStatus.FAILED, team_list.status)

    def test_getPendingActions_unsynchronized_constructing(self):
        # Once a list enters CONSTRUCTING, it enters the unsynchronize
        # action.
        team = self.factory.makeTeam(name='team')
        team_list = self.mailinglist_set.new(team, team.teamowner)
        actions = self.mailinglist_api.getPendingActions()
        actions = self.mailinglist_api.getPendingActions()
        self.assertEqual(
            {'unsynchronized': [(u'team', 'constructing')]}, actions)
        self.assertEqual(MailingListStatus.CONSTRUCTING, team_list.status)

    def test_getPendingActions_deactivating(self):
        # DEACTIVATING lists have "deactivate" actions.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.deactivate()
        self.assertEqual(MailingListStatus.DEACTIVATING, team_list.status)
        actions = self.mailinglist_api.getPendingActions()
        self.assertEqual({'deactivate': [u'team']}, actions)
        self.assertEqual(MailingListStatus.DEACTIVATING, team_list.status)

    def test_reportStatus_deactivating_success(self):
        # Successful deactivations lead to INACTIVE lists.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.deactivate()
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'success'})
        self.assertEqual(MailingListStatus.INACTIVE, team_list.status)

    def test_reportStatus_deactivating_failure(self):
        # Failure deactivations lead to MOD_FAILED lists.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.deactivate()
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'failure'})
        self.assertEqual(MailingListStatus.MOD_FAILED, team_list.status)

    def test_getPendingActions_modifying(self):
        # MODIFIED lists have "modify" actions.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.welcome_message = 'hi'
        self.assertEqual(MailingListStatus.MODIFIED, team_list.status)
        actions = self.mailinglist_api.getPendingActions()
        self.assertEqual(
            {'modify': [(u'team', {'welcome_message': u'hi'})]}, actions)
        self.assertEqual(MailingListStatus.UPDATING, team_list.status)

    def test_reportStatus_modifying_success(self):
        # Successfule modifications lead to ACTIVE lists.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.welcome_message = 'hi'
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'success'})
        self.assertEqual(MailingListStatus.ACTIVE, team_list.status)

    def test_reportStatus_modifying_failure(self):
        # Successfule modifications lead to ACTIVE lists.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.welcome_message = 'hi'
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'failure'})
        self.assertEqual(MailingListStatus.MOD_FAILED, team_list.status)

    def test_reportStatus_UnexpectedStatusReport_ACTIVE_fault(self):
        # A fault is raised if any status is sent about an ACTIVE list.
        team = self.factory.makeTeam(name='team')
        self.factory.makeMailingList(team, team.teamowner)
        info = self.mailinglist_api.reportStatus({'team': 'success'})
        self.assertIsInstance(info, faults.UnexpectedStatusReport)

    def test_reportStatus_UnexpectedStatusReport_FAILED_fault(self):
        # A fault is raised if any status is sent about an FAILED list.
        team = self.factory.makeTeam(name='team')
        self.mailinglist_set.new(team, team.teamowner)
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'failure'})
        info = self.mailinglist_api.reportStatus({'team': 'success'})
        self.assertIsInstance(info, faults.UnexpectedStatusReport)

    def test_reportStatus_UnexpectedStatusReport_MOD_FAILED_fault(self):
        # A fault is raised if any status is sent about an MOD_FAILED list.
        team = self.factory.makeTeam(name='team')
        team_list = self.factory.makeMailingList(team, team.teamowner)
        with person_logged_in(team.teamowner):
            team_list.welcome_message = 'hi'
        self.mailinglist_api.getPendingActions()
        self.mailinglist_api.reportStatus({'team': 'failure'})
        info = self.mailinglist_api.reportStatus({'team': 'success'})
        self.assertIsInstance(info, faults.UnexpectedStatusReport)

    def test_reportStatus_NoSuchTeamMailingList_fault(self):
        # A fault is raised if the team name does not exist.
        team = self.factory.makeTeam(name='team')
        self.factory.makeMailingList(team, team.teamowner)
        info = self.mailinglist_api.reportStatus({'not-team': 'success'})
        self.assertIsInstance(info, faults.NoSuchTeamMailingList)

    def test_reportStatus_BadStatus_fault(self):
        # A fault is raised if the stautus is not 'success' or 'failure'.
        team = self.factory.makeTeam(name='team')
        self.factory.makeMailingList(team, team.teamowner)
        info = self.mailinglist_api.reportStatus({'team': 'SUCCESS'})
        self.assertIsInstance(info, faults.BadStatus)
        info = self.mailinglist_api.reportStatus({'team': 'bogus'})
        self.assertIsInstance(info, faults.BadStatus)


class MailingListAPIMessageTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(MailingListAPIMessageTestCase, self).setUp()
        self.mailinglist_api = MailingListAPIView(None, None)
        self.mailinglist_set = getUtility(IMailingListSet)
        self.message_set = getUtility(IMessageSet)
        self.message_approval_set = getUtility(IMessageApprovalSet)

    def makeMailingListAndHeldMessage(self, private=False):
        if private:
            visibility = PersonVisibility.PRIVATE
        else:
            visibility = PersonVisibility.PUBLIC
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            name='team', owner=owner, visibility=visibility,
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        with person_logged_in(owner):
            self.factory.makeMailingList(team, owner)
        sender = self.factory.makePerson(email='me@eg.dom')
        with person_logged_in(sender):
            message = message_from_string(dedent("""\
                From: me@eg.dom
                To: team@lists.launchpad.dev
                Subject: A question
                Message-ID: <first-post>
                Date: Fri, 01 Aug 2000 01:08:59 -0000\n
                I have a question about this team.
                """))
        return team, sender, message

    def test_holdMessage(self):
        # Calling holdMessages send a copy of the message text to Lp
        # and notifies a team admins to moderate it.
        team, sender, message = self.makeMailingListAndHeldMessage()
        pop_notifications()
        info = self.mailinglist_api.holdMessage('team', message.as_string())
        notifications = pop_notifications()
        found = self.message_approval_set.getMessageByMessageID('<first-post>')
        self.assertIs(True, info)
        self.assertIsNot(None, found)
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            'New mailing list message requiring approval for Team',
            notifications[0]['subject'])
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*http://launchpad.dev/~team/\+mailinglist-moderate.*',
            notifications[0].get_payload())
        self.assertEqual({}, self.mailinglist_api.getMessageDispositions())

    def test_holdMessage_private_team(self):
        # Users can send messages to private teams (did they guess the name)?
        team, sender, message = self.makeMailingListAndHeldMessage(
            private=True)
        info = self.mailinglist_api.holdMessage('team', message.as_string())
        found = self.message_approval_set.getMessageByMessageID('<first-post>')
        self.assertIs(True, info)
        self.assertIsNot(None, found)

    def test_holdMessage_non_ascii_message_headers(self):
        # Non-ascii messages headers are re-encoded for moderators.
        team, sender, message = self.makeMailingListAndHeldMessage()
        with person_logged_in(sender):
            message = message_from_string(dedent("""\
                From: \xa9 me <me@eg.dom>
                To: team@lists.launchpad.dev
                Subject: \xa9 gremlins
                Message-ID: <\xa9-me>
                Date: Fri, 01 Aug 2000 01:08:59 -0000\n
                I put \xa9 in the body.
                """))
        info = self.mailinglist_api.holdMessage(
            'team', xmlrpclib.Binary(message.as_string()))
        transaction.commit()
        found = self.message_approval_set.getMessageByMessageID('<\\xa9-me>')
        self.assertIs(True, info)
        self.assertIsNot(None, found)
        try:
            found.posted_message.open()
            text = found.posted_message.read()
        finally:
            found.posted_message.close()
        self.assertEqual([
            'From: \\xa9 me <me@eg.dom>',
            'To: team@lists.launchpad.dev',
            'Subject: \\xa9 gremlins',
            'Message-ID: <\\xa9-me>',
            'Date: Fri, 01 Aug 2000 01:08:59 -0000',
            '',
            'I put \xa9 in the body.'], text.splitlines())

    def test_getMessageDispositions_accept(self):
        # List moderators can approve messages.
        team, sender, message = self.makeMailingListAndHeldMessage()
        pop_notifications()
        self.mailinglist_api.holdMessage('team', message.as_string())
        found = self.message_approval_set.getMessageByMessageID('<first-post>')
        found.approve(team.teamowner)
        self.assertEqual(PostedMessageStatus.APPROVAL_PENDING, found.status)
        self.assertEqual(
            {u'<first-post>': (u'team', 'accept')},
            self.mailinglist_api.getMessageDispositions())
        self.assertEqual(PostedMessageStatus.APPROVED, found.status)

    def test_getMessageDispositions_reject(self):
        # List moderators can reject messages.
        team, sender, message = self.makeMailingListAndHeldMessage()
        pop_notifications()
        self.mailinglist_api.holdMessage('team', message.as_string())
        found = self.message_approval_set.getMessageByMessageID('<first-post>')
        found.reject(team.teamowner)
        self.assertEqual(PostedMessageStatus.REJECTION_PENDING, found.status)
        self.assertEqual(
            {u'<first-post>': (u'team', 'decline')},
            self.mailinglist_api.getMessageDispositions())
        self.assertEqual(PostedMessageStatus.REJECTED, found.status)

    def test_getMessageDispositions_discard(self):
        # List moderators can discard messages.
        team, sender, message = self.makeMailingListAndHeldMessage()
        pop_notifications()
        self.mailinglist_api.holdMessage('team', message.as_string())
        found = self.message_approval_set.getMessageByMessageID('<first-post>')
        found.discard(team.teamowner)
        self.assertEqual(PostedMessageStatus.DISCARD_PENDING, found.status)
        self.assertEqual(
            {u'<first-post>': (u'team', 'discard')},
            self.mailinglist_api.getMessageDispositions())
        self.assertEqual(PostedMessageStatus.DISCARDED, found.status)
