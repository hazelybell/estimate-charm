# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for IFAQ"""

__metaclass__ = type

from zope.component import getUtility

from lp.services.webapp.authorization import check_permission
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestFAQPermissions(TestCaseWithFactory):
    """Test who can edit FAQs."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestFAQPermissions, self).setUp()
        target = self.factory.makeProduct()
        self.owner = target.owner
        with person_logged_in(self.owner):
            self.faq = self.factory.makeFAQ(target=target)

    def addAnswerContact(self, answer_contact):
        """Add the test person to the faq target's answer contacts."""
        language_set = getUtility(ILanguageSet)
        answer_contact.addLanguage(language_set['en'])
        self.faq.target.addAnswerContact(answer_contact, answer_contact)

    def assertCanEdit(self, user, faq):
        """Assert that the user can edit an FAQ."""
        can_edit = check_permission('launchpad.Edit', faq)
        self.assertTrue(can_edit, 'User cannot edit %s' % faq)

    def assertCannotEdit(self, user, faq):
        """Assert that the user cannot edit an FAQ."""
        can_edit = check_permission('launchpad.Edit', faq)
        self.assertFalse(can_edit, 'User can edit edit %s' % faq)

    def test_owner_can_edit(self):
        # The owner of an FAQ target can edit its FAQs.
        login_person(self.owner)
        self.assertCanEdit(self.owner, self.faq)

    def test_direct_answer_contact_can_edit(self):
        # A direct answer contact for an FAQ target can edit its FAQs.
        direct_answer_contact = self.factory.makePerson()
        login_person(direct_answer_contact)
        self.addAnswerContact(direct_answer_contact)
        self.assertCanEdit(direct_answer_contact, self.faq)

    def test_indirect_answer_contact_can_edit(self):
        # A indirect answer contact (a member of a team that is an answer
        # contact) for an FAQ target can edit its FAQs.
        indirect_answer_contact = self.factory.makePerson()
        direct_answer_contact = self.factory.makeTeam()
        with person_logged_in(direct_answer_contact.teamowner):
            direct_answer_contact.addMember(
                indirect_answer_contact, direct_answer_contact.teamowner)
            self.addAnswerContact(direct_answer_contact)
        login_person(indirect_answer_contact)
        self.assertCanEdit(indirect_answer_contact, self.faq)

    def test_nonparticipating_user_cannot_edit(self):
        # A user that is neither an owner of, or answer contact for, an
        # FAQ target's cannot edit a its FAQs.
        nonparticipant = self.factory.makePerson()
        login_person(nonparticipant)
        self.assertCannotEdit(nonparticipant, self.faq)
