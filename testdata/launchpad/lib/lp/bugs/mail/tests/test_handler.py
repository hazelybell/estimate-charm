# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test MaloneHandler."""

__metaclass__ = type

import email
import time

import transaction
from zope.component import getUtility
from zope.security.management import (
    getSecurityPolicy,
    setSecurityPolicy,
    )
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.mail.commands import (
    BugEmailCommand,
    BugEmailCommands,
    )
from lp.bugs.mail.handler import (
    BugCommandGroup,
    BugCommandGroups,
    BugTaskCommandGroup,
    MaloneHandler,
    )
from lp.bugs.model.bugnotification import BugNotification
from lp.registry.enums import BugSharingPolicy
from lp.services.config import config
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.services.mail import stub
from lp.services.webapp.authorization import LaunchpadSecurityPolicy
from lp.testing import (
    celebrity_logged_in,
    login,
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.factory import GPGSigningContext
from lp.testing.gpgkeys import import_secret_test_key
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class TestMaloneHandler(TestCaseWithFactory):
    """Test that the Malone/bugs handler works."""

    # LaunchpadFunctionalLayer has the LaunchpadSecurityPolicy that we
    # need, but we need to be able to switch DB users. So we have to use
    # LaunchpadZopelessLayer and set security up manually.
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestMaloneHandler, self).setUp()
        self._old_policy = getSecurityPolicy()
        setSecurityPolicy(LaunchpadSecurityPolicy)

    def tearDown(self):
        super(TestMaloneHandler, self).tearDown()
        setSecurityPolicy(self._old_policy)

    def test_getCommandsEmpty(self):
        """getCommands returns an empty list for messages with no command."""
        message = self.factory.makeSignedMessage()
        handler = MaloneHandler()
        self.assertEqual([], handler.getCommands(message))

    def test_getCommandsBug(self):
        """getCommands returns a reasonable list if commands are specified."""
        message = self.factory.makeSignedMessage(body=' bug foo')
        handler = MaloneHandler()
        commands = handler.getCommands(message)
        self.assertEqual(1, len(commands))
        self.assertTrue(isinstance(commands[0], BugEmailCommand))
        self.assertEqual('bug', commands[0].name)
        self.assertEqual(['foo'], commands[0].string_args)

    def test_NonGPGAuthenticatedNewBug(self):
        """Mail authenticated other than by gpg can create bugs.

        The incoming mail layer is responsible for authenticating the mail,
        and setting the current principal to the sender of the mail, either
        weakly or non-weakly authenticated.  At the layer of the handler,
        which this class is testing, we shouldn't care by what mechanism we
        decided to act on behalf of the mail sender, only that we did.

        In bug 643219, Launchpad had a problem where the MaloneHandler code
        was puncturing that abstraction and directly looking at the GPG
        signature; this test checks it's fixed.
        """
        # NB SignedMessage by default isn't actually signed, it just has the
        # capability of knowing about signing.
        message = self.factory.makeSignedMessage(body='  affects malone\nhi!')
        self.assertEquals(message.signature, None)

        # Pretend that the mail auth has given us a logged-in user.
        handler = MaloneHandler()
        with person_logged_in(self.factory.makePerson()):
            mail_handled, add_comment_to_bug, commands = \
                handler.extractAndAuthenticateCommands(message,
                    'new@bugs.launchpad.net')
        self.assertEquals(mail_handled, None)
        self.assertEquals(map(str, commands), [
            'bug new',
            'affects malone',
            ])

    def test_mailToHelpFromNonActiveUser(self):
        """Mail from people without a preferred email get a help message."""
        self.factory.makePerson(
            email='non@eg.dom',
            email_address_status=EmailAddressStatus.NEW)
        message = self.factory.makeSignedMessage(email_address='non@eg.dom')
        handler = MaloneHandler()
        response = handler.extractAndAuthenticateCommands(
            message, 'help@bugs.launchpad.net')
        mail_handled, add_comment_to_bug, commands = response
        self.assertEquals(mail_handled, True)
        emails = self.getSentMail()
        self.assertEquals(1, len(emails))
        self.assertEquals(['non@eg.dom'], emails[0][1])
        self.assertTrue(
            'Subject: Launchpad Bug Tracker Email Interface' in emails[0][2])

    def test_mailToHelpFromUnknownUser(self):
        """Mail from people of no account to help@ is simply dropped.
        """
        message = self.factory.makeSignedMessage(
            email_address='unregistered@eg.dom')
        handler = MaloneHandler()
        mail_handled, add_comment_to_bug, commands = \
            handler.extractAndAuthenticateCommands(message,
                'help@bugs.launchpad.net')
        self.assertEquals(mail_handled, True)
        self.assertEquals(self.getSentMail(), [])

    def test_mailToHelp(self):
        """Mail to help@ generates a help command."""
        user = self.factory.makePerson(email='user@dom.eg')
        message = self.factory.makeSignedMessage(email_address='user@dom.eg')
        handler = MaloneHandler()
        with person_logged_in(user):
            mail_handled, add_comment_to_bug, commands = \
                handler.extractAndAuthenticateCommands(message,
                    'help@bugs.launchpad.net')
        self.assertEquals(mail_handled, True)
        emails = self.getSentMail()
        self.assertEquals(1, len(emails))
        self.assertEquals([message['From']], emails[0][1])
        self.assertTrue(
            'Subject: Launchpad Bug Tracker Email Interface' in emails[0][2])

    def getSentMail(self):
        # Sending mail is (unfortunately) a side effect of parsing the
        # commands, and unfortunately you must commit the transaction to get
        # them sent.
        transaction.commit()
        return stub.test_emails[:]

    def getFailureForMessage(self, to_address, from_address=None, body=None):
        mail = self.factory.makeSignedMessage(
            body=body, email_address=from_address)
        switch_dbuser(config.processmail.dbuser)
        # Rejection email goes to the preferred email of the current user.
        # The current user is extracted from the current interaction, which is
        # set up using the authenticateEmail method.  However that expects
        # real GPG signed emails, which we are faking here.
        login(mail['from'])
        handler = MaloneHandler()
        self.assertTrue(handler.process(mail, to_address, None))
        notifications = pop_notifications()
        if not notifications:
            return None
        notification = notifications[0]
        self.assertEqual('Submit Request Failure', notification['subject'])
        # The returned message is a multipart message, the first part is
        # the message, and the second is the original message.
        message, original = notification.get_payload()
        return message.get_payload(decode=True)

    def test_new_bug_big_body(self):
        # If a bug email is sent with an excessively large body, we email the
        # user back and ask that they use attachments instead.
        big_body_text = 'This is really big.' * 10000
        message = self.getFailureForMessage(
            'new@bugs.launchpad.dev', body=big_body_text)
        self.assertIn("The description is too long.", message)

    def test_bug_not_found(self):
        # Non-existent bug numbers result in an informative error.
        message = self.getFailureForMessage('1234@bugs.launchpad.dev')
        self.assertIn(
            "There is no such bug in Launchpad: 1234", message)

    def test_accessible_private_bug(self):
        # Private bugs are accessible by their subscribers.
        person = self.factory.makePerson()
        with celebrity_logged_in('admin'):
            bug = getUtility(IBugSet).get(4)
            bug.setPrivate(True, person)
            bug.subscribe(person, person)
        # Drop the notifications from celebrity_logged_in.
        pop_notifications()
        message = self.getFailureForMessage(
            '4@bugs.launchpad.dev',
            from_address=removeSecurityProxy(person.preferredemail).email)
        self.assertIs(None, message)

    def test_inaccessible_private_bug_not_found(self):
        # Private bugs don't acknowledge their existence to non-subscribers.
        with celebrity_logged_in('admin'):
            getUtility(IBugSet).get(4).setPrivate(
                True, self.factory.makePerson())
        message = self.getFailureForMessage('4@bugs.launchpad.dev')
        self.assertIn(
            "There is no such bug in Launchpad: 4", message)


class MaloneHandlerProcessTestCase(TestCaseWithFactory):
    """Test the bug mail processing loop."""
    layer = LaunchpadFunctionalLayer

    @staticmethod
    def getLatestBugNotification():
        return BugNotification.selectFirst(orderBy='-id')

    def test_new_bug(self):
        project = self.factory.makeProduct(name='fnord')
        transaction.commit()
        handler = MaloneHandler()
        with person_logged_in(project.owner):
            msg = self.factory.makeSignedMessage(
                body='borked\n affects fnord',
                subject='subject borked',
                to_address='new@bugs.launchpad.dev')
            handler.process(msg, msg['To'])
        notification = self.getLatestBugNotification()
        bug = notification.bug
        self.assertEqual(
            [project.owner], list(bug.getDirectSubscribers()))
        self.assertEqual(project.owner, bug.owner)
        self.assertEqual('subject borked', bug.title)
        self.assertEqual(1, bug.messages.count())
        self.assertEqual('borked\n affects fnord', bug.description)
        self.assertEqual(1, len(bug.bugtasks))
        self.assertEqual(project, bug.bugtasks[0].target)

    def test_new_bug_with_sharing_policy_proprietary(self):
        project = self.factory.makeProduct(name='fnord')
        self.factory.makeCommercialSubscription(product=project)
        with person_logged_in(project.owner):
            project.setBugSharingPolicy(BugSharingPolicy.PROPRIETARY)
        transaction.commit()
        handler = MaloneHandler()
        with person_logged_in(project.owner):
            msg = self.factory.makeSignedMessage(
                body='borked\n affects fnord',
                subject='subject borked',
                to_address='new@bugs.launchpad.dev')
            handler.process(msg, msg['To'])
        notification = self.getLatestBugNotification()
        bug = notification.bug
        self.assertEqual([project.owner], list(bug.getDirectSubscribers()))
        self.assertEqual(InformationType.PROPRIETARY, bug.information_type)

    def test_new_bug_with_one_misplaced_affects_line(self):
        # Affects commands in the wrong position are processed as the user
        # intended when the bug is new and there is only one affects.
        project = self.factory.makeProduct(name='fnord')
        assignee = self.factory.makePerson(name='pting')
        transaction.commit()
        handler = MaloneHandler()
        with person_logged_in(project.owner):
            msg = self.factory.makeSignedMessage(
                body='borked\n assignee pting\n affects fnord',
                subject='affects after assignee',
                to_address='new@bugs.launchpad.dev')
            handler.process(msg, msg['To'])
        notification = self.getLatestBugNotification()
        bug = notification.bug
        self.assertEqual('affects after assignee', bug.title)
        self.assertEqual(1, len(bug.bugtasks))
        self.assertEqual(project, bug.bugtasks[0].target)
        self.assertEqual(assignee, bug.bugtasks[0].assignee)

    def test_new_affect_command_interleaved_with_bug_commands(self):
        # The bug commands can appear before and after the affects command.
        project = self.factory.makeProduct(name='fnord')
        transaction.commit()
        handler = MaloneHandler()
        with person_logged_in(project.owner):
            msg = self.factory.makeSignedMessage(
                body='unsecure\n security yes\n affects fnord\n tag ajax',
                subject='unsecure code',
                to_address='new@bugs.launchpad.dev')
            handler.process(msg, msg['To'])
        notification = self.getLatestBugNotification()
        bug = notification.bug
        self.assertEqual('unsecure code', bug.title)
        self.assertTrue(bug.security_related)
        self.assertEqual(['ajax'], bug.tags)
        self.assertEqual(1, len(bug.bugtasks))
        self.assertEqual(project, bug.bugtasks[0].target)

    def test_new_security_bug(self):
        # Structural subscribers are not notified of security bugs.
        maintainer = self.factory.makePerson(name='maintainer')
        project = self.factory.makeProduct(name='fnord', owner=maintainer)
        subscriber = self.factory.makePerson(name='subscriber')
        with person_logged_in(subscriber):
            project.addBugSubscription(subscriber, subscriber)
        transaction.commit()
        handler = MaloneHandler()
        with person_logged_in(project.owner):
            msg = self.factory.makeSignedMessage(
                body='bad thing\n security yes\n affects fnord',
                subject='security issue',
                to_address='new@bugs.launchpad.dev')
            handler.process(msg, msg['To'])
        notification = self.getLatestBugNotification()
        bug = notification.bug
        self.assertEqual('security issue', bug.title)
        self.assertTrue(bug.security_related)
        self.assertEqual(1, len(bug.bugtasks))
        self.assertEqual(project, bug.bugtasks[0].target)
        recipients = set()
        for notification in BugNotification.select():
            for recipient in notification.recipients:
                recipients.add(recipient.person)
        self.assertContentEqual([maintainer], recipients)

    def test_information_type(self):
        project = self.factory.makeProduct(name='fnord')
        transaction.commit()
        handler = MaloneHandler()
        with person_logged_in(project.owner):
            msg = self.factory.makeSignedMessage(
                body='unsecure\n informationtype userdata\n affects fnord',
                subject='unsecure code',
                to_address='new@bugs.launchpad.dev')
            handler.process(msg, msg['To'])
        notification = self.getLatestBugNotification()
        bug = notification.bug
        self.assertEqual('unsecure code', bug.title)
        self.assertEqual(InformationType.USERDATA, bug.information_type)
        self.assertEqual(1, len(bug.bugtasks))
        self.assertEqual(project, bug.bugtasks[0].target)


class BugTaskCommandGroupTestCase(TestCase):

    def test_BugTaskCommandGroup_init_with_command(self):
        # BugTaskCommandGroup can be inited with a BugEmailCommands.
        command = BugEmailCommands.get('status', ['triaged'])
        group = BugTaskCommandGroup(command)
        self.assertEqual([command], group._commands)

    def test_BugTaskCommandGroup_add(self):
        # BugEmailCommands can be added to the group.
        command_1 = BugEmailCommands.get('affects', ['fnord'])
        command_2 = BugEmailCommands.get('status', ['triaged'])
        group = BugTaskCommandGroup()
        group.add(command_1)
        group.add(command_2)
        self.assertEqual([command_1, command_2], group._commands)

    def test_BugTaskCommandGroup_sorted_commands(self):
        # Commands are sorted by the Command's Rank.
        command_3 = BugEmailCommands.get('importance', ['low'])
        command_2 = BugEmailCommands.get('status', ['triaged'])
        command_1 = BugEmailCommands.get('affects', ['fnord'])
        group = BugTaskCommandGroup()
        group.add(command_3)
        group.add(command_2)
        group.add(command_1)
        self.assertEqual(0, command_1.RANK)
        self.assertEqual(4, command_2.RANK)
        self.assertEqual(5, command_3.RANK)
        self.assertEqual(
            [command_1, command_2, command_3], group.commands)

    def test_BugTaskCommandGroup__nonzero__false(self):
        # A BugTaskCommandGroup is zero is it has no commands.
        group = BugTaskCommandGroup()
        self.assertEqual(0, len(group._commands))
        self.assertFalse(bool(group))

    def test_BugTaskCommandGroup__nonzero__true(self):
        # A BugTaskCommandGroup is non-zero is it has commands.
        group = BugTaskCommandGroup(
            BugEmailCommands.get('affects', ['fnord']))
        self.assertEqual(1, len(group._commands))
        self.assertTrue(bool(group))

    def test_BugTaskCommandGroup__str__(self):
        # The str of a BugTaskCommandGroup is the ideal order of the
        # text commands in the email.
        command_1 = BugEmailCommands.get('affects', ['fnord'])
        command_2 = BugEmailCommands.get('status', ['triaged'])
        group = BugTaskCommandGroup()
        group.add(command_1)
        group.add(command_2)
        self.assertEqual(
            'affects fnord\nstatus triaged', str(group))


class BugCommandGroupTestCase(TestCase):

    def test_BugCommandGroup_init_with_command(self):
        # A BugCommandGroup can be inited with a BugEmailCommand.
        command = BugEmailCommands.get('private', ['true'])
        group = BugCommandGroup(command)
        self.assertEqual([command], group._commands)
        self.assertEqual([], group._groups)

    def test_BugCommandGroup_add_command(self):
        # A BugEmailCommand can be added to a BugCommandGroup.
        command = BugEmailCommands.get('private', ['true'])
        group = BugCommandGroup()
        group.add(command)
        self.assertEqual([], group._groups)
        self.assertEqual([command], group._commands)

    def test_BugCommandGroup_add_bugtask_empty_group(self):
        # Empty BugTaskCommandGroups are ignored.
        bugtask_group = BugTaskCommandGroup()
        group = BugCommandGroup()
        group.add(bugtask_group)
        self.assertEqual([], group._commands)
        self.assertEqual([], group._groups)

    def test_BugCommandGroup_add_bugtask_non_empty_group(self):
        # Non-empty BugTaskCommandGroups are added.
        bugtask_group = BugTaskCommandGroup(
            BugEmailCommands.get('affects', ['fnord']))
        group = BugCommandGroup()
        group.add(bugtask_group)
        self.assertEqual([], group._commands)
        self.assertEqual([bugtask_group], group._groups)

    def test_BugCommandGroup_groups(self):
        # The groups property returns a copy _groups list in the order that
        # that they were added.
        bugtask_group_1 = BugTaskCommandGroup(
            BugEmailCommands.get('affects', ['fnord']))
        group = BugCommandGroup()
        group.add(bugtask_group_1)
        bugtask_group_2 = BugTaskCommandGroup(
            BugEmailCommands.get('affects', ['pting']))
        group.add(bugtask_group_2)
        self.assertEqual(group._groups, group.groups)
        self.assertFalse(group._groups is group.groups)
        self.assertEqual([bugtask_group_1, bugtask_group_2], group.groups)

    def test_BugCommandGroup_groups_new_bug_with_fixable_affects(self):
        # A new bug that affects only one target does not require the
        # affects command to be first.
        group = BugCommandGroup(
            BugEmailCommands.get('bug', ['new']))
        status_command = BugEmailCommands.get('status', ['triaged'])
        bugtask_group_1 = BugTaskCommandGroup(status_command)
        group.add(bugtask_group_1)
        affects_command = BugEmailCommands.get('affects', ['fnord'])
        bugtask_group_2 = BugTaskCommandGroup(affects_command)
        group.add(bugtask_group_2)
        self.assertEqual(1, len(group.groups))
        self.assertIsNot(
            group._groups, group.groups,
            "List reference returned instead of copy.")
        self.assertEqual(
            [affects_command, status_command], group.groups[0].commands)

    def test_BugCommandGroup__nonzero__false(self):
        # A BugCommandGroup is zero is it has no commands or groups.
        group = BugCommandGroup()
        self.assertEqual(0, len(group._commands))
        self.assertEqual(0, len(group._groups))
        self.assertFalse(bool(group))

    def test_BugCommandGroup__nonzero__true_commands(self):
        # A BugCommandGroup is not zero is it has a command.
        group = BugCommandGroup(
            BugEmailCommands.get('private', ['true']))
        self.assertEqual(1, len(group._commands))
        self.assertEqual(0, len(group._groups))
        self.assertTrue(bool(group))

    def test_BugCommandGroup__nonzero__true_groups(self):
        # A BugCommandGroup is not zero is it has a group.
        group = BugCommandGroup()
        group.add(BugTaskCommandGroup(
            BugEmailCommands.get('affects', ['fnord'])))
        self.assertEqual(0, len(group._commands))
        self.assertEqual(1, len(group._groups))
        self.assertTrue(bool(group))

    def test_BugCommandGroup__str__(self):
        # The str of a BugCommandGroup is the ideal order of the
        # text commands in the email.
        bug_group = BugCommandGroup(
            BugEmailCommands.get('private', ['true']))
        bug_group.add(
            BugEmailCommands.get('security', ['false']))
        bugtask_group = BugTaskCommandGroup(
            BugEmailCommands.get('affects', ['fnord']))
        bug_group.add(bugtask_group)
        self.assertEqual(
            'security false\nprivate true\naffects fnord', str(bug_group))


class BugCommandGroupsTestCase(TestCase):

    def test_BugCommandGroups_add_bug_email_command(self):
        # BugEmailCommands are ignored.
        group = BugCommandGroups([])
        group.add(
            BugEmailCommands.get('private', ['true']))
        self.assertEqual([], group._commands)
        self.assertEqual([], group._groups)

    def test_BugCommandGroups_add_bug_empty_group(self):
        # Empty BugCommandGroups are ignored.
        group = BugCommandGroups([])
        group.add(
            BugCommandGroup())
        self.assertEqual([], group._commands)
        self.assertEqual([], group._groups)

    def test_BugCommandGroup_add_bug_non_empty_group(self):
        # Non-empty BugCommandGroups are added.
        group = BugCommandGroups([])
        bug_group = BugCommandGroup(
            BugEmailCommands.get('private', ['true']))
        group.add(bug_group)
        self.assertEqual([], group._commands)
        self.assertEqual([bug_group], group._groups)

    def test_BugCommandGroups__init__no_commands(self):
        # Emails may not contain any commands to group.
        ordered_commands = BugCommandGroups([])
        self.assertEqual(0, len(ordered_commands.groups))
        self.assertEqual('', str(ordered_commands))

    def test_BugCommandGroups__init__one_bug_no_bugtasks(self):
        # Commands can operate on one bug.
        email_commands = [
            ('bug', '1234'),
            ('private', 'true'),
            ]
        commands = [
            BugEmailCommands.get(name=name, string_args=[args])
            for name, args in email_commands]
        ordered_commands = BugCommandGroups(commands)
        expected = '\n'.join([
            'bug 1234',
            'private true',
            ])
        self.assertEqual(1, len(ordered_commands.groups))
        self.assertEqual(2, len(ordered_commands.groups[0].commands))
        self.assertEqual(0, len(ordered_commands.groups[0].groups))
        self.assertEqual(expected, str(ordered_commands))

    def test_BugCommandGroups__init__one_bug_one_bugtask(self):
        # Commands can operate on one bug and one bugtask.
        email_commands = [
            ('bug', 'new'),
            ('affects', 'fnord'),
            ('importance', 'high'),
            ('private', 'true'),
            ]
        commands = [
            BugEmailCommands.get(name=name, string_args=[args])
            for name, args in email_commands]
        ordered_commands = BugCommandGroups(commands)
        expected = '\n'.join([
            'bug new',
            'private true',
            'affects fnord',
            'importance high',
            ])
        self.assertEqual(1, len(ordered_commands.groups))
        self.assertEqual(2, len(ordered_commands.groups[0].commands))
        self.assertEqual(1, len(ordered_commands.groups[0].groups))
        self.assertEqual(
            2, len(ordered_commands.groups[0].groups[0].commands))
        self.assertEqual(expected, str(ordered_commands))

    def test_BugCommandGroups__init__one_bug_many_bugtask(self):
        # Commands can operate on one bug and one bugtask.
        email_commands = [
            ('bug', 'new'),
            ('affects', 'fnord'),
            ('importance', 'high'),
            ('private', 'true'),
            ('affects', 'pting'),
            ('importance', 'low'),
            ]
        commands = [
            BugEmailCommands.get(name=name, string_args=[args])
            for name, args in email_commands]
        ordered_commands = BugCommandGroups(commands)
        expected = '\n'.join([
            'bug new',
            'private true',
            'affects fnord',
            'importance high',
            'affects pting',
            'importance low',
            ])
        self.assertEqual(1, len(ordered_commands.groups))
        self.assertEqual(2, len(ordered_commands.groups[0].commands))
        self.assertEqual(2, len(ordered_commands.groups[0].groups))
        self.assertEqual(
            2, len(ordered_commands.groups[0].groups[0].commands))
        self.assertEqual(
            2, len(ordered_commands.groups[0].groups[1].commands))
        self.assertEqual(expected, str(ordered_commands))

    def test_BugCommandGroups_init_many_bugs(self):
        # Commands can operate on many bugs.
        email_commands = [
            ('bug', '1234'),
            ('importance', 'high'),
            ('bug', '5678'),
            ('importance', 'low'),
            ('bug', '4321'),
            ('importance', 'medium'),
            ]
        commands = [
            BugEmailCommands.get(name=name, string_args=[args])
            for name, args in email_commands]
        ordered_commands = BugCommandGroups(commands)
        expected = '\n'.join([
            'bug 1234',
            'importance high',
            'bug 5678',
            'importance low',
            'bug 4321',
            'importance medium',
            ])
        self.assertEqual(3, len(ordered_commands.groups))
        self.assertEqual(expected, str(ordered_commands))

    def test_BugCommandGroups__iter_(self):
        email_commands = [
            ('bug', '1234'),
            ('importance', 'high'),
            ('private', 'yes'),
            ('bug', 'new'),
            ('security', 'yes'),
            ('status', 'triaged'),
            ('affects', 'fnord'),
            ]
        commands = [
            BugEmailCommands.get(name=name, string_args=[args])
            for name, args in email_commands]
        ordered_commands = list(BugCommandGroups(commands))
        expected = [
            'bug 1234',
            'private yes',
            'importance high',
            'bug new',
            'security yes',
            'affects fnord',
            'status triaged',
            ]
        self.assertEqual(
            expected, [str(command) for command in ordered_commands])


class FakeSignature:

    def __init__(self, timestamp):
        self.timestamp = timestamp


def get_last_email():
    from_addr, to_addrs, raw_message = stub.test_emails[-1]
    sent_msg = email.message_from_string(raw_message)
    error_mail, original_mail = sent_msg.get_payload()
    # clear the emails so we don't accidentally get one from a previous test
    return dict(
        subject=sent_msg['Subject'],
        body=error_mail.get_payload(decode=True))


BAD_SIGNATURE_TIMESTAMP_MESSAGE = (
    'The message you sent included commands to modify the bug '
    'report, but the\nsignature was (apparently) generated too far '
    'in the past or future.')


class TestSignatureTimestampValidation(TestCaseWithFactory):
    """GPG signature timestamps are checked for emails containing commands."""

    layer = LaunchpadFunctionalLayer

    def test_good_signature_timestamp(self):
        # An email message's GPG signature's timestamp checked to be sure it
        # isn't too far in the future or past.  This test shows that a
        # signature with a timestamp of appxoimately now will be accepted.
        signing_context = GPGSigningContext(
            import_secret_test_key().fingerprint, password='test')
        msg = self.factory.makeSignedMessage(
            body=' security no', signing_context=signing_context)
        handler = MaloneHandler()
        with person_logged_in(self.factory.makePerson()):
            handler.process(msg, msg['To'])
        transaction.commit()
        # Since there were no commands in the poorly-timestamped message, no
        # error emails were generated.
        self.assertEqual(stub.test_emails, [])

    def test_bad_timestamp_but_no_commands(self):
        # If an email message's GPG signature's timestamp is too far in the
        # future or past but it doesn't contain any commands, the email is
        # processed anyway.

        msg = self.factory.makeSignedMessage(
            body='I really hope this bug gets fixed.')
        now = time.time()
        one_week = 60 * 60 * 24 * 7
        msg.signature = FakeSignature(timestamp=now + one_week)
        handler = MaloneHandler()
        # Clear old emails before potentially generating more.
        del stub.test_emails[:]
        with person_logged_in(self.factory.makePerson()):
            handler.process(msg, msg['To'])
        transaction.commit()
        # Since there were no commands in the poorly-timestamped message, no
        # error emails were generated.
        self.assertEqual(stub.test_emails, [])
