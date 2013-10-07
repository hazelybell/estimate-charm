# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite
import time
import unittest

from zope.interface import (
    directlyProvidedBy,
    directlyProvides,
    )

from lp.registry.interfaces.person import PersonVisibility
from lp.services.mail.helpers import (
    ensure_not_weakly_authenticated,
    ensure_sane_signature_timestamp,
    get_contact_email_addresses,
    get_person_or_team,
    IncomingEmailError,
    parse_commands,
    )
from lp.services.mail.interfaces import (
    EmailProcessingError,
    IWeaklyAuthenticatedPrincipal,
    )
from lp.services.webapp.interaction import get_current_principal
from lp.testing import (
    login_person,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestParseCommands(TestCase):
    """Test the ParseCommands function."""

    def test_parse_commandsEmpty(self):
        """Empty messages have no commands."""
        self.assertEqual([], parse_commands('', {'command': True}))

    def test_parse_commandsNoIndent(self):
        """Commands with no indent are not commands."""
        self.assertEqual([], parse_commands('command',  {'command': True}))

    def test_parse_commandsSpaceIndent(self):
        """Commands indented with spaces are recognized."""
        self.assertEqual(
            [('command', [])], parse_commands(' command', {'command': True}))

    def test_parse_commands_args(self):
        """Commands indented with spaces are recognized."""
        self.assertEqual(
            [('command', ['arg1', 'arg2'])],
            parse_commands(' command arg1 arg2', {'command': True}))

    def test_parse_commands_args_uppercase_unchanged(self):
        """Commands and args containing uppercase letters are not
        converted to lowercase if the flag is False."""
        self.assertEqual(
            [('command', ['Arg1', 'aRg2'])],
            parse_commands(' comMand Arg1 aRg2', {'command': False}))

    def test_parse_commands_args_uppercase_to_lowercase(self):
        """Commands and args containing uppercase letters are converted to
        lowercase."""
        self.assertEqual(
            [('command', ['arg1', 'arg2'])],
            parse_commands(' comMand Arg1 aRg2', {'command': True}))

    def test_parse_commands_args_quoted(self):
        """Commands indented with spaces are recognized."""
        self.assertEqual(
            [('command', ['"arg1', 'arg2"'])],
            parse_commands(' command "arg1 arg2"', {'command': True}))

    def test_parse_commandsTabIndent(self):
        """Commands indented with tabs are recognized.

        (Tabs?  What are we, make?)
        """
        self.assertEqual(
            [('command', [])], parse_commands('\tcommand', {'command': True}))

    def test_parse_commandsDone(self):
        """The 'done' pseudo-command halts processing."""
        self.assertEqual(
            [('command', []), ('command', [])],
            parse_commands(' command\n command', {'command': True}))
        self.assertEqual(
            [('command', [])],
            parse_commands(' command\n done\n command', {'command': True}))
        # done takes no arguments.
        self.assertEqual(
            [('command', []), ('command', [])],
            parse_commands(
                ' command\n done commands\n command', {'command': True}))

    def test_parse_commands_optional_colons(self):
        """Colons at the end of commands are accepted and stripped."""
        self.assertEqual(
            [('command', ['arg1', 'arg2'])],
            parse_commands(' command: arg1 arg2', {'command': True}))
        self.assertEqual(
            [('command', [])],
            parse_commands(' command:', {'command': True}))


class TestEnsureSaneSignatureTimestamp(unittest.TestCase):
    """Tests for ensure_sane_signature_timestamp"""

    def test_too_old_timestamp(self):
        # signature timestamps shouldn't be too old
        now = time.time()
        one_week = 60 * 60 * 24 * 7
        self.assertRaises(
            IncomingEmailError, ensure_sane_signature_timestamp,
            now - one_week, 'bug report')

    def test_future_timestamp(self):
        # signature timestamps shouldn't be (far) in the future
        now = time.time()
        one_week = 60 * 60 * 24 * 7
        self.assertRaises(
            IncomingEmailError, ensure_sane_signature_timestamp,
            now + one_week, 'bug report')

    def test_near_future_timestamp(self):
        # signature timestamps in the near future are OK
        now = time.time()
        one_minute = 60
        # this should not raise an exception
        ensure_sane_signature_timestamp(now + one_minute, 'bug report')

    def test_recent_timestamp(self):
        # signature timestamps in the recent past are OK
        now = time.time()
        one_hour = 60 * 60
        # this should not raise an exception
        ensure_sane_signature_timestamp(now - one_hour, 'bug report')


class TestEnsureNotWeaklyAuthenticated(TestCaseWithFactory):
    """Test the ensure_not_weakly_authenticated function."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, 'test@canonical.com')
        self.eric = self.factory.makePerson(name='eric')
        login_person(self.eric)

    def test_normal_user(self):
        # If the current principal doesn't provide
        # IWeaklyAuthenticatedPrincipal, then we are good.
        signed_msg = self.factory.makeSignedMessage()
        ensure_not_weakly_authenticated(signed_msg, 'test case')

    def _setWeakPrincipal(self):
        # Get the current principal to provide IWeaklyAuthenticatedPrincipal
        # this is set when the message is unsigned or the signature doesn't
        # match a key that the person has.
        cur_principal = get_current_principal()
        directlyProvides(
            cur_principal, directlyProvidedBy(cur_principal),
            IWeaklyAuthenticatedPrincipal)

    def test_weakly_authenticated_no_sig(self):
        signed_msg = self.factory.makeSignedMessage()
        self.assertIs(None, signed_msg.signature)
        self._setWeakPrincipal()
        error = self.assertRaises(
            IncomingEmailError,
            ensure_not_weakly_authenticated,
            signed_msg, 'test')
        self.assertEqual(
            "The message you sent included commands to modify the test,\n"
            "but you didn't sign the message with an OpenPGP key that is\n"
            "registered in Launchpad.\n",
            error.message)

    def test_weakly_authenticated_with_sig(self):
        signed_msg = self.factory.makeSignedMessage()
        signed_msg.signature = 'fakesig'
        self._setWeakPrincipal()
        error = self.assertRaises(
            IncomingEmailError,
            ensure_not_weakly_authenticated,
            signed_msg, 'test')
        self.assertEqual(
            "The message you sent included commands to modify the test,\n"
            "but your OpenPGP key isn't imported into Launchpad. "
            "Please go to\n"
            "http://launchpad.dev/~eric/+editpgpkeys to import your key.\n",
            error.message)


class TestGetPersonOrTeam(TestCaseWithFactory):
    """Test the get_person_or_team function."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, 'test@canonical.com')

    def test_by_name(self):
        # The user's launchpad name can be used to get them.
        eric = self.factory.makePerson(name="eric")
        self.assertEqual(eric, get_person_or_team('eric'))

    def test_by_email(self):
        # The user's launchpad name can be used to get them.
        eric = self.factory.makePerson(email="eric@example.com")
        self.assertEqual(eric, get_person_or_team('eric@example.com'))

    def test_not_found(self):
        # An unknown user raises an EmailProcessingError.
        error = self.assertRaises(
            EmailProcessingError,
            get_person_or_team,
            'unknown-user')
        self.assertEqual(
            "There's no such person with the specified name or email: "
            "unknown-user\n", str(error))

    def test_team_by_name(self):
        # A team can also be gotten by name.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(owner=owner, name='fooix-devs')
        self.assertEqual(team, get_person_or_team('fooix-devs'))

    def test_team_by_email(self):
        # The team's contact email address can also be used to get the team.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=owner, email='fooix-devs@lists.example.com')
        self.assertEqual(
            team, get_person_or_team('fooix-devs@lists.example.com'))


class Testget_contact_email_addresses(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_person_with_hidden_email(self):
        user = self.factory.makePerson(
            email='user@canonical.com',
            hide_email_addresses=True,
            name='user')
        result = get_contact_email_addresses(user)
        self.assertEqual(set(['user@canonical.com']), result)

    def test_user_with_preferredemail(self):
        user = self.factory.makePerson(
            email='user@canonical.com', name='user',)
        result = get_contact_email_addresses(user)
        self.assertEqual(set(['user@canonical.com']), result)

    def test_private_team(self):
        email = 'team@canonical.com'
        team = self.factory.makeTeam(
            name='breaks-things',
            email=email,
            visibility=PersonVisibility.PRIVATE)
        result = get_contact_email_addresses(team)
        self.assertEqual(set(['team@canonical.com']), result)


def test_suite():
    suite = DocTestSuite('lp.services.mail.helpers')
    suite.addTests(unittest.TestLoader().loadTestsFromName(__name__))
    return suite
