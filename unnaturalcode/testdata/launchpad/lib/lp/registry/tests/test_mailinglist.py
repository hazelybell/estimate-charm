# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = []

from textwrap import dedent

from testtools.matchers import Equals
import transaction
from zope.component import getUtility

from lp.registry.interfaces.mailinglist import (
    CannotChangeSubscription,
    CannotSubscribe,
    IHeldMessageDetails,
    IMailingList,
    IMailingListSet,
    IMessageApproval,
    IMessageApprovalSet,
    MailingListStatus,
    PostedMessageStatus,
    UnsafeToPurge,
    )
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.messages.interfaces.message import IMessageSet
from lp.testing import (
    login_celebrity,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.mail_helpers import pop_notifications
from lp.testing.matchers import HasQueryCount


class PersonMailingListTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_autoSubscribeToMailingList_ON_REGISTRATION_someone_else(self):
        # Users with autoSubscribeToMailingList set to ON_REGISTRATION
        # are not subscribed when someone else adds them.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        subscribed = member.autoSubscribeToMailingList(
            team.mailing_list, team.teamowner)
        self.assertEqual(
            MailingListAutoSubscribePolicy.ON_REGISTRATION,
            member.mailing_list_auto_subscribe_policy)
        self.assertIs(False, subscribed)
        self.assertEqual(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_ON_REGISTRATION_user(self):
        # Users with autoSubscribeToMailingList set to ON_REGISTRATION
        # are subscribed when when they add them selves.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertEqual(
            MailingListAutoSubscribePolicy.ON_REGISTRATION,
            member.mailing_list_auto_subscribe_policy)
        self.assertIs(True, subscribed)
        self.assertIsNot(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_ALWAYS(self):
        # When autoSubscribeToMailingList set to ALWAYS
        # users subscribed when when added by anyone.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            member.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.ALWAYS)
        subscribed = member.autoSubscribeToMailingList(
            team.mailing_list, team.teamowner)
        self.assertIs(True, subscribed)
        self.assertIsNot(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_NEVER(self):
        # When autoSubscribeToMailingList set to NEVER
        # users are never subscribed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            member.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.NEVER)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_without_preferredemail(self):
        # Users without preferred email addresses cannot subscribe.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            member.setPreferredEmail(None)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_with_inactive_list(self):
        # Users cannot subscribe to inactive lists.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_twice(self):
        # Users cannot subscribe twice.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(True, subscribed)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIsNot(None, team.mailing_list.getSubscription(member))


class MailingListTestCase(TestCaseWithFactory):
    """Tests for MailingList data and behaviour."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'test-mailinglist', 'team-owner')

    def test_attributes(self):
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        self.assertIs(None, team.mailing_list)
        mailing_list = mailing_list_set.new(team, team.teamowner)
        self.assertIs(True, verifyObject(IMailingList, mailing_list))
        self.assertEqual(mailing_list, team.mailing_list)
        self.assertEqual(team, mailing_list.team)
        self.assertEqual(team.teamowner, mailing_list.registrant)
        self.assertEqual('team@lists.launchpad.dev', mailing_list.address)
        self.assertEqual(MailingListStatus.APPROVED, mailing_list.status)
        self.assertIs(None, mailing_list.date_activated)
        self.assertIs(None, mailing_list.welcome_message)
        # archive_url is None until the archive is constructed.
        self.assertIs(None, mailing_list.archive_url)

    def test_new_list_notification(self):
        team = self.factory.makeTeam(name='team')
        member = self.factory.makePerson()
        with person_logged_in(team.teamowner):
            team.addMember(member, reviewer=team.teamowner)
            pop_notifications()
            self.factory.makeMailingList(team, team.teamowner)
        notifications = pop_notifications()
        self.assertEqual(2, len(notifications))
        self.assertEqual(
            'New Mailing List for Team', notifications[0]['subject'])
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*To subscribe:.*http://launchpad.dev/~.*/\+editemails.*',
            notifications[0].get_payload())

    def test_startConstructing_from_APPROVED(self):
        # Only approved mailing lists can be constructed.
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list = mailing_list_set.new(team, team.teamowner)
        mailing_list.startConstructing()
        self.assertEqual(MailingListStatus.CONSTRUCTING, mailing_list.status)
        self.assertIs(None, mailing_list.archive_url)

    def test_startConstructing_error(self):
        # Once constructed, a mailing list cannot be constructed again.
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list = mailing_list_set.new(team, team.teamowner)
        mailing_list.startConstructing()
        self.assertRaises(AssertionError, mailing_list.startConstructing)

    def test_startConstructing_to_FAIL(self):
        # Construction can faiil, and the archive_url remains None.
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list = mailing_list_set.new(team, team.teamowner)
        mailing_list.startConstructing()
        mailing_list.transitionToStatus(MailingListStatus.FAILED)
        self.assertEqual(MailingListStatus.FAILED, mailing_list.status)
        self.assertIs(None, mailing_list.archive_url)

    def test_startConstructing_to_ACTIVE(self):
        # When construction succeeds, the archive_url is set.
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list = mailing_list_set.new(team, team.teamowner)
        mailing_list.startConstructing()
        mailing_list.transitionToStatus(MailingListStatus.ACTIVE)
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)
        self.assertEqual(
            'http://lists.launchpad.dev/team', mailing_list.archive_url)
        email = getUtility(IEmailAddressSet).getByEmail(
            team.mailing_list.address)
        self.assertEqual(
            EmailAddressStatus.VALIDATED, email.status)

    def test_deactivate(self):
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        self.assertEqual(
            MailingListStatus.DEACTIVATING, team.mailing_list.status)

    def test_deactivate_to_DEACTIVATED(self):
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        team.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        self.assertEqual(MailingListStatus.INACTIVE, team.mailing_list.status)
        email = getUtility(IEmailAddressSet).getByEmail(
            team.mailing_list.address)
        self.assertEqual(EmailAddressStatus.NEW, email.status)

    def test_reactivate(self):
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        team.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        with person_logged_in(team.teamowner):
            team.mailing_list.reactivate()
        self.assertEqual(MailingListStatus.APPROVED, team.mailing_list.status)

    def test_purge(self):
        # Mailing lists can be purged after they are successfully deactivated.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
            team.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
            team.mailing_list.purge()
        self.assertEqual(
            MailingListStatus.PURGED, team.mailing_list.status)

    def test_purge_construction_fails(self):
        # Mailing lists can be purged if they failed to construct.
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list_set.new(team, team.teamowner)
        team.mailing_list.startConstructing()
        team.mailing_list.transitionToStatus(MailingListStatus.FAILED)
        with person_logged_in(team.teamowner):
            team.mailing_list.purge()
        self.assertEqual(
            MailingListStatus.PURGED, team.mailing_list.status)

    def test_purge_error(self):
        # Mailing lists can not be purged before it is inactive.
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        self.assertIs(None, team.mailing_list)
        mailing_list_set.new(team, team.teamowner)
        with person_logged_in(team.teamowner):
            self.assertRaises(UnsafeToPurge, team.mailing_list.purge)

    def test_welcome_message(self):
        # Setting the welcome message changes the list status.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.welcome_message = "hi"
        self.assertEqual('hi', team.mailing_list.welcome_message)
        self.assertEqual(MailingListStatus.MODIFIED, team.mailing_list.status)

    def test_welcome_message_error(self):
        # The welcome message cannot be changed when the list is not ACTIVE.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)

        def test_call():
            team.mailing_list.welcome_message = "goodbye"

        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
            self.assertIs(False, team.mailing_list.is_usable)
            self.assertRaises(AssertionError, test_call)

    def test_subscribe_without_address(self):
        # An error is raised if subscribe() if a team is passed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        team.mailing_list.subscribe(member)
        subscription = team.mailing_list.getSubscription(member)
        self.assertEqual(member, subscription.person)
        self.assertIs(None, subscription.email_address)

    def test_subscribe_with_address(self):
        # An error is raised if subscribe() if a team is passed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        email = self.factory.makeEmail('him@eg.dom', member)
        team.mailing_list.subscribe(member, email)
        subscription = team.mailing_list.getSubscription(member)
        self.assertEqual(member, subscription.person)
        self.assertEqual(email, subscription.email_address)

    def test_subscribe_team_error(self):
        # An error is raised if subscribe() if a team is passed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        other_team = self.factory.makeTeam()
        self.assertRaises(
            CannotSubscribe, team.mailing_list.subscribe, other_team)

    def test_subscribe_wrong_address_error(self):
        # An error is raised if subscribe() is called with an address that
        # does not belong to the user.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        email = self.factory.makeEmail('him@eg.dom', self.factory.makePerson())
        with person_logged_in(member):
            self.assertRaises(
                CannotSubscribe, team.mailing_list.subscribe, member, email)

    def test_subscribe_twice_error(self):
        # An error is raised if subscribe() is called with a user already
        # subscribed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        team.mailing_list.subscribe(member)
        self.assertRaises(CannotSubscribe, team.mailing_list.subscribe, member)

    def test_subscribe_inactive_list_error(self):
        # An error is raised if subscribe() is called on an inactive list.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        self.assertRaises(CannotSubscribe, team.mailing_list.subscribe, member)

    def test_changeAddress_with_address(self):
        # User can change the subscription email address
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=True)
        other_email = self.factory.makeEmail('me@eg.dom', member)
        team.mailing_list.changeAddress(member, other_email)
        subscription = team.mailing_list.getSubscription(member)
        self.assertEqual(other_email, subscription.email_address)

    def test_changeAddress_without_address(self):
        # Users can clear the subacription email address to use the preferred.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=True)
        other_email = self.factory.makeEmail('me@eg.dom', member)
        team.mailing_list.changeAddress(member, other_email)
        team.mailing_list.changeAddress(member, None)
        subscription = team.mailing_list.getSubscription(member)
        self.assertIs(None, subscription.email_address)

    def test_changeAddress_wrong_address_error(self):
        # Users can change to another user's email address.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=True)
        other_user = self.factory.makePerson()
        other_email = self.factory.makeEmail('me@eg.dom', other_user)
        with person_logged_in(member):
            self.assertRaises(
                CannotChangeSubscription, team.mailing_list.changeAddress,
                member, other_email)

    def test_changeAddress_non_subscriber_error(self):
        # Users cannot change the address if they are not subacribed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            self.assertRaises(
                CannotChangeSubscription, team.mailing_list.changeAddress,
                member, None)

    def test_unsubscribe(self):
        # A user can unsubscribe.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=True)
        team.mailing_list.unsubscribe(member)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_unsubscribe_deleted_email_address(self):
        # When a user delete an email address that use used by a
        # subscription, the user is implicitly unsubsscibed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        email = self.factory.makeEmail('him@eg.dom', member)
        team.mailing_list.subscribe(member, email)
        with person_logged_in(member):
            email.destroySelf()
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_getSubscribers_only_active_members_are_subscribers(self):
        former_member = self.factory.makePerson()
        pending_member = self.factory.makePerson()
        active_member = self.active_member = self.factory.makePerson()
        # Each of our members want to be subscribed to a team's mailing list
        # whenever they join the team.
        login_celebrity('admin')
        former_member.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        active_member.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        pending_member.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        self.team.membership_policy = TeamMembershipPolicy.MODERATED
        pending_member.join(self.team)
        self.team.addMember(former_member, reviewer=self.team.teamowner)
        former_member.leave(self.team)
        self.team.addMember(active_member, reviewer=self.team.teamowner)
        # Even though our 3 members want to subscribe to the team's mailing
        # list, only the active member is considered a subscriber.
        self.assertEqual(
            [active_member], list(self.mailing_list.getSubscribers()))

    def test_getSubscribers_order(self):
        person_1 = self.factory.makePerson(name="pb1", displayname="Me")
        with person_logged_in(person_1):
            person_1.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.ALWAYS)
            person_1.join(self.team)
        person_2 = self.factory.makePerson(name="pa2", displayname="Me")
        with person_logged_in(person_2):
            person_2.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.ALWAYS)
            person_2.join(self.team)
        subscribers = self.mailing_list.getSubscribers()
        self.assertEqual(2, subscribers.count())
        self.assertEqual(
            ['pa2', 'pb1'], [person.name for person in subscribers])


class MailingListSetTestCase(TestCaseWithFactory):
    """Test the mailing list set class."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MailingListSetTestCase, self).setUp()
        self.mailing_list_set = getUtility(IMailingListSet)
        login_celebrity('admin')

    def test_IMailingListSet(self):
        self.assertIs(
            True, verifyObject(IMailingListSet, self.mailing_list_set))

    def test_new(self):
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list = mailing_list_set.new(team, team.teamowner)
        self.assertIs(True, verifyObject(IMailingList, mailing_list))
        self.assertEqual(mailing_list, team.mailing_list)

    def test_new_twice_error(self):
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list_set.new(team, team.teamowner)
        self.assertRaises(
            ValueError, mailing_list_set.new, team, team.teamowner)

    def test_new_user_error(self):
        mailing_list_set = getUtility(IMailingListSet)
        user = self.factory.makePerson()
        self.assertRaises(ValueError, mailing_list_set.new, user, user)

    def test_new_wrong_owner_error(self):
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        user = self.factory.makePerson()
        self.assertRaises(ValueError, mailing_list_set.new, team, user)

    def test_get(self):
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        mailing_list_set.new(team, team.teamowner)
        self.assertEqual(team.mailing_list, mailing_list_set.get(team.name))

    def test_get_non_list(self):
        # None is returned when there is no list
        mailing_list_set = getUtility(IMailingListSet)
        team = self.factory.makeTeam(name='team')
        self.assertIs(None, mailing_list_set.get(team.name))
        self.assertIs(None, mailing_list_set.get('fnord'))

    def test_getSenderAddresses_dict_keys(self):
        # getSenderAddresses() returns a dict of teams names
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', auto_subscribe=False)
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSenderAddresses(team_names)
        self.assertContentEqual(team_names, result.keys())

    def test_getSenderAddresses_dict_values(self):
        # getSenderAddresses() returns a dict of team namess with a list of
        # all membera display names and email addresses.
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        result = self.mailing_list_set.getSenderAddresses([team1.name])
        list_senders = [
            (m.displayname, m.preferredemail.email) for m in team1.allmembers]
        self.assertContentEqual(list_senders, result[team1.name])

    def test_getSenderAddresses_multiple_and_lowercase_email(self):
        # getSenderAddresses() contains multiple email addresses for
        # users and they are lowercased for mailman.
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        email = self.factory.makeEmail('me@EG.dom', member1)
        result = self.mailing_list_set.getSenderAddresses([team1.name])
        list_senders = [
            (m.displayname, m.preferredemail.email) for m in team1.allmembers]
        list_senders.append((member1.displayname, email.email.lower()))
        self.assertContentEqual(list_senders, result[team1.name])

    def test_getSenderAddresses_participation_dict_values(self):
        # getSenderAddresses() dict values includes indirect participants.
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        result = self.mailing_list_set.getSenderAddresses([team1.name])
        list_senders = [
            (m.displayname, m.preferredemail.email)
            for m in team1.allmembers if m.preferredemail]
        self.assertContentEqual(list_senders, result[team1.name])

    def test_getSenderAddresses_non_members(self):
        # getSenderAddresses() only contains active and admin members.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team')
        with person_logged_in(team.teamowner):
            team.membership_policy = TeamMembershipPolicy.MODERATED
        non_member = self.factory.makePerson()
        with person_logged_in(non_member):
            non_member.join(team)
        result = self.mailing_list_set.getSenderAddresses([team.name])
        list_senders = [
            (team.teamowner.displayname, team.teamowner.preferredemail.email),
            (member.displayname, member.preferredemail.email)]
        self.assertContentEqual(list_senders, result[team.name])

    def test_getSenderAddresses_inactive_list(self):
        # Inactive lists are not include
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=True)
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', auto_subscribe=True)
        with person_logged_in(team2.teamowner):
            team2.mailing_list.deactivate()
            team2.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSenderAddresses(team_names)
        self.assertEqual([team1.name], result.keys())

    def test_getSubscribedAddresses_dict_keys(self):
        # getSubscribedAddresses() returns a dict of team names.
        # {team_name: [(subscriber_displayname, subscriber_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2')
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSubscribedAddresses(team_names)
        self.assertContentEqual(team_names, result.keys())

    def test_getSubscribedAddresses_dict_values(self):
        # getSubscribedAddresses() returns a dict of teams names with a list
        # of subscriber tuples.
        # {team_name: [(subscriber_displayname, subscriber_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, member1.preferredemail.email)]
        self.assertEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_multiple_lowercase_email(self):
        # getSubscribedAddresses() contains email addresses for
        # users and they are lowercased for mailman. The email maybe
        # explicitly set instead of the preferred email.
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        with person_logged_in(member1):
            email1 = self.factory.makeEmail('me@EG.dom', member1)
            member1.setPreferredEmail(email1)
        with person_logged_in(team1.teamowner):
            email2 = self.factory.makeEmail('you@EG.dom', team1.teamowner)
            team1.mailing_list.subscribe(team1.teamowner, email2)
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, email1.email.lower()),
            (team1.teamowner.displayname, email2.email.lower())]
        self.assertContentEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_participation_dict_values(self):
        # getSubscribedAddresses() dict values includes indirect participants.
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', super_team=team1)
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, member1.preferredemail.email),
            (member2.displayname, member2.preferredemail.email)]
        self.assertContentEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_non_members(self):
        # getSubscribedAddresses() only contains active and admin members..
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        with person_logged_in(team.teamowner):
            team.membership_policy = TeamMembershipPolicy.MODERATED
        non_member = self.factory.makePerson()
        with person_logged_in(non_member):
            non_member.join(team)
        result = self.mailing_list_set.getSubscribedAddresses([team.name])
        list_subscribers = [(member.displayname, member.preferredemail.email)]
        self.assertEqual(list_subscribers, result[team.name])

    def test_getSubscribedAddresses_excludes_former_participants(self):
        # getSubscribedAddresses() only includes present participants of
        # the team, even if they still participate in another team in
        # the batch (bug #1098170).
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2')
        team1.addMember(member2, reviewer=team1.teamowner)
        team1.mailing_list.subscribe(member2, address=member2.preferredemail)

        result = self.mailing_list_set.getSubscribedAddresses(
            ['team1', 'team2'])
        self.assertContentEqual(
            [(member1.displayname, member1.preferredemail.email),
             (member2.displayname, member2.preferredemail.email)],
            result['team1'])
        self.assertContentEqual(
            [(member2.displayname, member2.preferredemail.email)],
            result['team2'])

        member2.retractTeamMembership(team1, member2)
        result = self.mailing_list_set.getSubscribedAddresses(
            ['team1', 'team2'])
        self.assertContentEqual(
            [(member1.displayname, member1.preferredemail.email)],
            result['team1'])
        self.assertContentEqual(
            [(member2.displayname, member2.preferredemail.email)],
            result['team2'])

    def test_getSubscribedAddresses_preferredemail_dict_values(self):
        # getSubscribedAddresses() dict values include users who want email to
        # go to their preferred address.
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        team1.mailing_list.subscribe(member1)
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, member1.preferredemail.email)]
        self.assertEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_inactive_list(self):
        # Inactive lists are not include
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=True)
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', auto_subscribe=True)
        with person_logged_in(team2.teamowner):
            team2.mailing_list.deactivate()
            team2.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSubscribedAddresses(team_names)
        self.assertEqual([team1.name], result.keys())

    def test_getSubscribedAddresses_after_rejoin(self):
        # A users subscription is preserved when a user leaved a team, then
        # rejoins
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        team.mailing_list.subscribe(member)
        list_subscribers = [(member.displayname, member.preferredemail.email)]
        result = self.mailing_list_set.getSubscribedAddresses([team.name])
        self.assertEqual(list_subscribers, result[team.name])
        with person_logged_in(member):
            member.leave(team)
        result = self.mailing_list_set.getSubscribedAddresses([team.name])
        self.assertEqual({}, result)
        with person_logged_in(member):
            member.join(team)
        result = self.mailing_list_set.getSubscribedAddresses([team.name])
        self.assertEqual(list_subscribers, result[team.name])


class MailingListMessageTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(MailingListMessageTestCase, self).setUp()
        self.mailing_list_set = getUtility(IMailingListSet)
        login_celebrity('admin')

    def makeMailingListAndHeldMessage(self):
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=True)
        sender = self.factory.makePerson()
        email = dedent(str("""\
            From: %s
            To: %s
            Subject: A question
            Message-ID: <first-post>
            Date: Fri, 01 Aug 2000 01:08:59 -0000\n
            I have a question about this team.
            """ % (sender.preferredemail.email, team.mailing_list.address)))
        message = getUtility(IMessageSet).fromEmail(email)
        held_message = team.mailing_list.holdMessage(message)
        transaction.commit()
        return team, member, sender, held_message


class MailingListHeldMessageTestCase(MailingListMessageTestCase):
    """Test the MailingList held message behaviour."""

    def test_holdMessage(self):
        # calling holdMessage() will create a held message and a notification.
        # The messages content is re-encoded
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        sender = self.factory.makePerson()
        email = dedent(str("""\
            From: %s
            To: %s
            Subject:  =?iso-8859-1?q?Adi=C3=B3s?=
            Message-ID: <first-post>
            Date: Fri, 01 Aug 2000 01:08:59 -0000\n
            hi.
            """ % (sender.preferredemail.email, team.mailing_list.address)))
        message = getUtility(IMessageSet).fromEmail(email)
        pop_notifications()
        held_message = team.mailing_list.holdMessage(message)
        self.assertEqual(PostedMessageStatus.NEW, held_message.status)
        self.assertEqual(message.rfc822msgid, held_message.message_id)
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            'New mailing list message requiring approval for Team',
            notifications[0]['subject'])
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*Subject: Adi=C3=83=C2=B3s.*', notifications[0].get_payload())

    def test_getReviewableMessages(self):
        # All the messages that need review can be retrieved.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_messages = team.mailing_list.getReviewableMessages()
        self.assertEqual(1, held_messages.count())
        self.assertEqual(held_message.message_id, held_messages[0].message_id)

    def test_getReviewableMessages_queries(self):
        # The Message and user that posted it are retrieved with the query
        # that get the MessageApproval.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_messages = team.mailing_list.getReviewableMessages()
        with StormStatementRecorder() as recorder:
            held_message = held_messages[0]
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        with StormStatementRecorder() as recorder:
            held_message.message
            held_message.posted_by
        self.assertThat(recorder, HasQueryCount(Equals(0)))


class MessageApprovalTestCase(MailingListMessageTestCase):
    """Test the MessageApproval data behaviour."""

    def test_mailinglistset_getSenderAddresses_approved_dict_values(self):
        # getSenderAddresses() dict values includes senders where were
        # approved in the list moderation queue.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.approve(team.teamowner)
        result = self.mailing_list_set.getSenderAddresses([team.name])
        list_senders = [
            (team.teamowner.displayname, team.teamowner.preferredemail.email),
            (member.displayname, member.preferredemail.email),
            (sender.displayname, sender.preferredemail.email)]
        self.assertContentEqual(list_senders, result[team.name])

    def test_new_state(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        self.assertIs(True, verifyObject(IMessageApproval, held_message))
        self.assertEqual(PostedMessageStatus.NEW, held_message.status)
        self.assertIs(None, held_message.disposed_by)
        self.assertIs(None, held_message.disposal_date)
        self.assertEqual(sender, held_message.posted_by)
        self.assertEqual(team.mailing_list, held_message.mailing_list)
        self.assertEqual('<first-post>', held_message.message.rfc822msgid)
        self.assertEqual(
            held_message.message.datecreated, held_message.posted_date)
        try:
            held_message.posted_message.open()
            text = held_message.posted_message.read()
        finally:
            held_message.posted_message.close()
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*Message-ID: <first-post>.*', text)

    def test_approve(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.approve(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.APPROVAL_PENDING, held_message.status)
        self.assertEqual(team.teamowner, held_message.disposed_by)
        self.assertIsNot(None, held_message.disposal_date)

    def test_reject(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.reject(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.REJECTION_PENDING, held_message.status)
        self.assertEqual(team.teamowner, held_message.disposed_by)
        self.assertIsNot(None, held_message.disposal_date)

    def test_discad(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.discard(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.DISCARD_PENDING, held_message.status)
        self.assertEqual(team.teamowner, held_message.disposed_by)
        self.assertIsNot(None, held_message.disposal_date)

    def test_acknowledge(self):
        # The acknowledge method changes the pending status to the
        # final status.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.discard(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.DISCARD_PENDING, held_message.status)
        held_message.acknowledge()
        self.assertEqual(
            PostedMessageStatus.DISCARDED, held_message.status)


class MessageApprovalSetTestCase(MailingListMessageTestCase):
    """Test the MessageApprovalSet behaviour."""

    def test_IMessageApprovalSet(self):
        message_approval_set = getUtility(IMessageApprovalSet)
        self.assertIs(
            True, verifyObject(IMessageApprovalSet, message_approval_set))

    def test_getMessageByMessageID(self):
        # held Messages can be looked up by rfc822 messsge id.
        held_message = self.makeMailingListAndHeldMessage()[-1]
        message_approval_set = getUtility(IMessageApprovalSet)
        found_message = message_approval_set.getMessageByMessageID(
            held_message.message_id)
        self.assertEqual(held_message.message_id, found_message.message_id)

    def test_getHeldMessagesWithStatus(self):
        # Messages can be retrieved by status.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        message_approval_set = getUtility(IMessageApprovalSet)
        found_messages = message_approval_set.getHeldMessagesWithStatus(
            PostedMessageStatus.NEW)
        self.assertEqual(1, found_messages.count())
        self.assertEqual(
            (held_message.message_id, team.name), found_messages[0])

    def test_acknowledgeMessagesWithStatus(self):
        # Message statuses can be updated from pending states to final states.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.approve(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.APPROVAL_PENDING, held_message.status)
        message_approval_set = getUtility(IMessageApprovalSet)
        message_approval_set.acknowledgeMessagesWithStatus(
            PostedMessageStatus.APPROVAL_PENDING)
        self.assertEqual(PostedMessageStatus.APPROVED, held_message.status)


class HeldMessageDetailsTestCase(MailingListMessageTestCase):
    """Test the HeldMessageDetails data."""

    def test_attributes(self):
        held_message = self.makeMailingListAndHeldMessage()[-1]
        details = IHeldMessageDetails(held_message)
        self.assertIs(True, verifyObject(IHeldMessageDetails, details))
        self.assertEqual(held_message, details.message_approval)
        self.assertEqual(held_message.message, details.message)
        self.assertEqual(held_message.message_id, details.message_id)
        self.assertEqual(held_message.message.subject, details.subject)
        self.assertEqual(held_message.message.datecreated, details.date)
        self.assertEqual(held_message.message.owner, details.author)

    def test_body(self):
        held_message = self.makeMailingListAndHeldMessage()[-1]
        details = IHeldMessageDetails(held_message)
        self.assertEqual(
            'I have a question about this team.', details.body.strip())
