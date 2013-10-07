# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test views and helpers related to the contact person feature."""

__metaclass__ = type

from testtools.matchers import LessThan

from lp.app.browser.tales import DateTimeFormatterAPI
from lp.registry.browser.person import (
    ContactViaWebLinksMixin,
    ContactViaWebNotificationRecipientSet,
    )
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.messages.interfaces.message import IDirectEmailAuthorization
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.views import create_initialized_view


class ContactViaWebNotificationRecipientSetTestCase(TestCaseWithFactory):
    """Tests the behaviour of ContactViaWebNotificationRecipientSet."""

    layer = DatabaseFunctionalLayer

    def test_len_to_user(self):
        # The recipient set length is based on the user activity.
        sender = self.factory.makePerson()
        user = self.factory.makePerson(email='him@eg.dom')
        self.assertEqual(
            1, len(ContactViaWebNotificationRecipientSet(sender, user)))
        inactive_user = self.factory.makePerson(
            email_address_status=EmailAddressStatus.NEW)
        self.assertEqual(
            0, len(
                ContactViaWebNotificationRecipientSet(sender, inactive_user)))

    def test_len_to_admins(self):
        # The recipient set length is based on the number of admins.
        sender = self.factory.makePerson()
        team = self.factory.makeTeam()
        self.assertEqual(
            1, len(ContactViaWebNotificationRecipientSet(sender, team)))
        with person_logged_in(team.teamowner):
            team.teamowner.leave(team)
        self.assertEqual(
            0, len(ContactViaWebNotificationRecipientSet(sender, team)))

    def test_len_to_members(self):
        # The recipient set length is based on the number members.
        member = self.factory.makePerson()
        sender_team = self.factory.makeTeam(members=[member])
        owner = sender_team.teamowner
        with StormStatementRecorder() as recorder:
            total = len(
                ContactViaWebNotificationRecipientSet(owner, sender_team))
            self.assertThat(recorder, HasQueryCount(LessThan(3)))
        self.assertEqual(2, total)
        with person_logged_in(owner):
            owner.leave(sender_team)
        self.assertEqual(
            1, len(ContactViaWebNotificationRecipientSet(owner, sender_team)))

    def test_nonzero(self):
        # The recipient set can be used in boolean conditions.
        sender = self.factory.makePerson()
        user = self.factory.makePerson(email='him@eg.dom')
        self.assertTrue(
            bool(ContactViaWebNotificationRecipientSet(sender, user)))
        inactive_user = self.factory.makePerson(
            email_address_status=EmailAddressStatus.NEW)
        self.assertFalse(
            bool(ContactViaWebNotificationRecipientSet(sender, inactive_user)))

    def test_getRecipientPersons_to_user(self):
        # The recipient set only contains the user.
        sender = self.factory.makePerson()
        user = self.factory.makePerson(email='him@eg.dom')
        recipient_set = ContactViaWebNotificationRecipientSet(sender, user)
        self.assertContentEqual(
            [('him@eg.dom', user)],
            list(recipient_set.getRecipientPersons()))

    def test_getRecipientPersons_to_admins(self):
        # The recipient set only contains the team admins when the user
        # is not an admin of the team the user is contacting
        admin = self.factory.makePerson(email='admin@eg.dom')
        member = self.factory.makePerson(email='member@eg.dom')
        team = self.factory.makeTeam(owner=admin, members=[member])
        recipient_set = ContactViaWebNotificationRecipientSet(member, team)
        self.assertContentEqual(
            [('admin@eg.dom', admin)],
            list(recipient_set.getRecipientPersons()))

    def test_getRecipientPersons_to_members(self):
        # The recipient set contains all the team members when the admin
        # is contacting the team.
        admin = self.factory.makePerson(email='admin@eg.dom')
        member = self.factory.makePerson(email='member@eg.dom')
        team = self.factory.makeTeam(owner=admin, members=[member])
        recipient_set = ContactViaWebNotificationRecipientSet(admin, team)
        self.assertContentEqual(
            [('admin@eg.dom', admin), ('member@eg.dom', member)],
            list(recipient_set.getRecipientPersons()))

    def test_description_to_user(self):
        sender = self.factory.makePerson()
        user = self.factory.makePerson(name='pting')
        recipient_set = ContactViaWebNotificationRecipientSet(sender, user)
        self.assertEqual(
            'You are contacting Pting (pting).',
            recipient_set.description)

    def test_description_to_admin(self):
        member = self.factory.makePerson()
        team = self.factory.makeTeam(name='pting', members=[member])
        recipient_set = ContactViaWebNotificationRecipientSet(member, team)
        self.assertEqual(
            'You are contacting the Pting (pting) team admins.',
            recipient_set.description)

    def test_description_to_members(self):
        member = self.factory.makePerson()
        team = self.factory.makeTeam(name='pting', members=[member])
        admin = team.teamowner
        recipient_set = ContactViaWebNotificationRecipientSet(admin, team)
        self.assertEqual(
            'You are contacting 2 members of the Pting (pting) team directly.',
            recipient_set.description)

    def test_rationale_and_reason_user(self):
        sender = self.factory.makePerson()
        user = self.factory.makePerson(name='pting')
        recipient_set = ContactViaWebNotificationRecipientSet(sender, user)
        for email, recipient in recipient_set.getRecipientPersons():
            reason, rationale = recipient_set.getReason(email)
        self.assertEqual(
            'using the "Contact this user" link on your profile page\n'
            '(http://launchpad.dev/~pting)',
            reason)
        self.assertEqual('ContactViaWeb user', rationale)

    def test_rationale_and_reason_admin(self):
        sender = self.factory.makePerson()
        team = self.factory.makeTeam(name='pting')
        recipient_set = ContactViaWebNotificationRecipientSet(sender, team)
        for email, recipient in recipient_set.getRecipientPersons():
            reason, rationale = recipient_set.getReason(email)
        self.assertEqual(
            'using the "Contact this team\'s admins" link '
            'on the Pting team page\n'
            '(http://launchpad.dev/~pting)',
            reason)
        self.assertEqual('ContactViaWeb owner (pting team)', rationale)

    def test_rationale_and_reason_members(self):
        team = self.factory.makeTeam(name='pting')
        sender = team.teamowner
        recipient_set = ContactViaWebNotificationRecipientSet(sender, team)
        for email, recipient in recipient_set.getRecipientPersons():
            reason, rationale = recipient_set.getReason(email)
        self.assertEqual(
            'to each member of the Pting team using the '
            '"Contact this team" link on the Pting team page\n'
            '(http://launchpad.dev/~pting)',
            reason)
        self.assertEqual('ContactViaWeb member (pting team)', rationale)


class ContactViaWebLinksMixinTestCase(TestCaseWithFactory):
    """Tests the behaviour of ContactViaWebLinksMixin."""

    layer = DatabaseFunctionalLayer

    def test_PersonView_composition(self):
        # PersonView uses the mixin.
        sender = self.factory.makePerson()
        user = self.factory.makePerson(name='pting')
        with person_logged_in(sender):
            view = create_initialized_view(user, '+index')
        self.assertTrue(issubclass(view.__class__, ContactViaWebLinksMixin))

    def test_contact_self(self):
        sender = self.factory.makePerson()
        with person_logged_in(sender):
            view = create_initialized_view(sender, '+index')
            self.assertEqual(
                'Send an email to yourself through Launchpad',
                view.contact_link_title)
        self.assertIs(
            ContactViaWebNotificationRecipientSet.TO_USER,
            view.group_to_contact)
        self.assertEqual('Contact this user', view.specific_contact_text)

    def test_contact_user(self):
        sender = self.factory.makePerson()
        user = self.factory.makePerson()
        with person_logged_in(sender):
            view = create_initialized_view(user, '+index')
        self.assertIs(
            ContactViaWebNotificationRecipientSet.TO_USER,
            view.group_to_contact)
        self.assertEqual('Contact this user', view.specific_contact_text)
        self.assertEqual(
            'Send an email to this user through Launchpad',
            view.contact_link_title)

    def test_contact_admins(self):
        sender = self.factory.makePerson()
        team = self.factory.makeTeam()
        with person_logged_in(sender):
            view = create_initialized_view(team, '+index')
            self.assertIs(
                ContactViaWebNotificationRecipientSet.TO_ADMINS,
                view.group_to_contact)
            self.assertEqual(
                "Contact this team's admins", view.specific_contact_text)
            self.assertEqual(
                "Send an email to this team's admins through Launchpad",
                view.contact_link_title)

    def test_contact_members(self):
        team = self.factory.makeTeam()
        admin = team.teamowner
        with person_logged_in(admin):
            view = create_initialized_view(team, '+index')
            self.assertIs(
                ContactViaWebNotificationRecipientSet.TO_MEMBERS,
                view.group_to_contact)
            self.assertEqual(
                "Contact this team's members", view.specific_contact_text)
            self.assertEqual(
                "Send an email to your team's members through Launchpad",
                view.contact_link_title)


class EmailToPersonViewTestCase(TestCaseWithFactory):
    """Tests the behaviour of EmailToPersonView."""

    layer = DatabaseFunctionalLayer

    def makeForm(self, email, subject='subject', message='body'):
        return {
                'field.field.from_': email,
                'field.subject': subject,
                'field.message': message,
                'field.actions.send': 'Send',
                }

    def makeThrottledSender(self):
        sender = self.factory.makePerson(email='me@eg.dom')
        old_message = self.factory.makeSignedMessage(email_address='me@eg.dom')
        authorization = IDirectEmailAuthorization(sender)
        for action in xrange(authorization.message_quota):
            authorization.record(old_message)
        return sender

    def test_anonymous_redirected(self):
        # Anonymous users cannot use the form.
        user = self.factory.makePerson(name='him')
        view = create_initialized_view(user, '+contactuser')
        response = view.request.response
        self.assertEqual(302, response.getStatus())
        self.assertEqual(
            'http://launchpad.dev/~him', response.getHeader('Location'))

    def test_inactive_user_redirects(self):
        # The view explains that the user is inactive.
        sender = self.factory.makePerson()
        inactive_user = self.factory.makePerson(
            name='him', email_address_status=EmailAddressStatus.NEW)
        with person_logged_in(sender):
            view = create_initialized_view(inactive_user, '+contactuser')
        response = view.request.response
        self.assertEqual(302, response.getStatus())
        self.assertEqual(
            'http://launchpad.dev/~him', response.getHeader('Location'))

    def test_contact_not_possible_reason_to_user(self):
        # The view explains that the user is inactive.
        inactive_user = self.factory.makePerson(
            email_address_status=EmailAddressStatus.NEW)
        user = self.factory.makePerson()
        with person_logged_in(user):
            view = create_initialized_view(inactive_user, '+contactuser')
        self.assertEqual(
            "The user is not active.", view.contact_not_possible_reason)

    def test_contact_not_possible_reason_to_admins(self):
        # The view explains that the team has no admins.
        team = self.factory.makeTeam()
        with person_logged_in(team.teamowner):
            team.teamowner.leave(team)
        user = self.factory.makePerson()
        with person_logged_in(user):
            view = create_initialized_view(team, '+contactuser')
        self.assertEqual(
            "The team has no admins. Contact the team owner instead.",
            view.contact_not_possible_reason)

    def test_contact_not_possible_reason_to_members(self):
        # The view explains the team has no members.
        team = self.factory.makeTeam()
        with person_logged_in(team.teamowner):
            team.teamowner.leave(team)
        with person_logged_in(team.teamowner):
            view = create_initialized_view(team, '+contactuser')
        self.assertEqual(
            "The team has no members.", view.contact_not_possible_reason)

    def test_has_valid_email_address(self):
        # The has_valid_email_address property checks the len of the
        # recipient set.
        team = self.factory.makeTeam()
        sender = self.factory.makePerson()
        with person_logged_in(sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertTrue(view.has_valid_email_address)
        with person_logged_in(team.teamowner):
            team.teamowner.leave(team)
        with person_logged_in(sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertFalse(view.has_valid_email_address)

    def test_contact_is_allowed(self):
        # The contact_is_allowed property checks if the user has not exceeded
        # the quota..
        team = self.factory.makeTeam()
        sender = self.factory.makePerson()
        with person_logged_in(sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertTrue(view.contact_is_allowed)

        other_sender = self.makeThrottledSender()
        with person_logged_in(other_sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertFalse(view.contact_is_allowed)

    def test_contact_is_possible(self):
        # The contact_is_possible property checks has_valid_email_address
        # and contact_is_allowed.
        team = self.factory.makeTeam()
        sender = self.factory.makePerson()
        with person_logged_in(sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertTrue(view.has_valid_email_address)
        self.assertTrue(view.contact_is_allowed)
        self.assertTrue(view.contact_is_possible)

        other_sender = self.makeThrottledSender()
        with person_logged_in(other_sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertTrue(view.has_valid_email_address)
        self.assertFalse(view.contact_is_allowed)
        self.assertFalse(view.contact_is_possible)

        with person_logged_in(team.teamowner):
            team.teamowner.leave(team)
        with person_logged_in(sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertTrue(view.contact_is_allowed)
        self.assertFalse(view.has_valid_email_address)
        self.assertFalse(view.contact_is_possible)

    def test_user_contacting_user(self):
        sender = self.factory.makePerson()
        user = self.factory.makePerson(name='pting')
        with person_logged_in(sender):
            view = create_initialized_view(user, '+contactuser')
        self.assertEqual('Contact user', view.label)
        self.assertEqual('Contact this user', view.page_title)

    def test_user_contacting_self(self):
        sender = self.factory.makePerson()
        with person_logged_in(sender):
            view = create_initialized_view(sender, '+contactuser')
        self.assertEqual('Contact user', view.label)
        self.assertEqual('Contact yourself', view.page_title)

    def test_user_contacting_team(self):
        sender = self.factory.makePerson()
        team = self.factory.makeTeam(name='pting')
        with person_logged_in(sender):
            view = create_initialized_view(team, '+contactuser')
        self.assertEqual('Contact user', view.label)
        self.assertEqual('Contact this team', view.page_title)

    def test_member_contacting_team(self):
        member = self.factory.makePerson()
        team = self.factory.makeTeam(name='pting', members=[member])
        with person_logged_in(member):
            view = create_initialized_view(team, '+contactuser')
        self.assertEqual('Contact user', view.label)
        self.assertEqual('Contact your team', view.page_title)

    def test_admin_contacting_team(self):
        member = self.factory.makePerson()
        team = self.factory.makeTeam(name='pting', members=[member])
        admin = team.teamowner
        with person_logged_in(admin):
            view = create_initialized_view(team, '+contactuser')
        self.assertEqual('Contact user', view.label)
        self.assertEqual('Contact your team', view.page_title)

    def test_submit(self):
        # The subject and message fields are required.
        sender = self.factory.makePerson(email='me@eg.dom')
        user = self.factory.makePerson(name='pting')
        form = self.makeForm('me@eg.dom', 'subject', 'body')
        with person_logged_in(sender):
            view = create_initialized_view(user, '+contactuser', form=form)
        self.assertEqual([], view.errors)
        notes = [n.message for n in view.request.response.notifications]
        self.assertEqual(['Message sent to Pting'], notes)

    def test_missing_subject_and_message(self):
        # The subject and message fields are required.
        sender = self.factory.makePerson(email='me@eg.dom')
        user = self.factory.makePerson()
        form = self.makeForm('me@eg.dom', ' ', ' ')
        with person_logged_in(sender):
            view = create_initialized_view(user, '+contactuser', form=form)
        self.assertEqual(
            [u'You must provide a subject and a message.'], view.errors)

    def test_submitted_after_quota(self):
        # The view explains when a message was not sent because the quota
        # was exceeded.
        user = self.factory.makePerson()
        sender = self.makeThrottledSender()
        form = self.makeForm('me@eg.dom')
        with person_logged_in(sender):
            view = create_initialized_view(user, '+contactuser', form=form)
        notification = [
            'Your message was not sent because you have exceeded your daily '
            'quota of 3 messages to contact users. Try again %s.' %
            DateTimeFormatterAPI(view.next_try).approximatedate()
            ]
        notes = [n.message for n in view.request.response.notifications]
        self.assertContentEqual(notification, notes)
