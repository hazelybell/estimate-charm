# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for nickname generation"""

__metaclass__ = type

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.registry.model.person import (
    generate_nick,
    NicknameGenerationError,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestNicknameGeneration(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_rejects_invalid_emails(self):
        # generate_nick rejects invalid email addresses.
        self.assertRaises(
            NicknameGenerationError, generate_nick, 'foo@example@com')

    def test_uses_email_address(self):
        # generate_nick uses the first part of the email address to create
        # the nick.
        nick = generate_nick('bar@example.com')
        self.assertEqual('bar', nick)

    def test_handles_symbols(self):
        # If an email starts with symbols, generate_nick still creates a
        # valid nick that doesn't start with symbols.
        parts = ['---bar', 'foo.bar', 'foo-bar', 'foo+bar']
        nicks = [generate_nick("%s@example.com" % part) for part in parts]
        self.assertEqual(['bar', 'foo-bar', 'foo-bar', 'foo+bar'], nicks)

    def test_enforces_minimum_length(self):
        # Nicks must be a minimum length. generate_nick enforces this by 
        # adding random suffixes to the required length.
        self.assertIs(None, getUtility(IPersonSet).getByName('i'))
        nick = generate_nick('i@example.com')
        self.assertEqual('i-b', nick)

    def test_can_create_noncolliding_nicknames(self):
        # Given the same email address, generate_nick doesn't recreate the
        # same nick once that nick is used.
        self.factory.makePerson(name='bar')
        nick = generate_nick('bar@example.com')
        self.assertEqual('bar-3', nick)

        # If we used the previously created nick and get another bar@ email
        # address, another new nick is generated.
        self.factory.makePerson(name=nick)
        nick = generate_nick('bar@example.com')
        self.assertEqual('5-bar', nick)
