# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for IFAQTarget"""

__metaclass__ = type

from zope.component import getUtility

from lp.answers.interfaces.faqtarget import IFAQTarget
from lp.services.webapp.authorization import check_permission
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class BaseIFAQTargetTests:
    """Common tests for all IFAQTargets."""

    layer = DatabaseFunctionalLayer

    def addAnswerContact(self, answer_contact):
        """Add the test person to the faq target's answer contacts."""
        language_set = getUtility(ILanguageSet)
        answer_contact.addLanguage(language_set['en'])
        self.target.addAnswerContact(answer_contact, answer_contact)

    def assertCanAppend(self, user, target):
        """Assert that the user can add an FAQ to an FAQ target."""
        can_append = check_permission('launchpad.Append', IFAQTarget(target))
        self.assertTrue(can_append, 'User cannot append to %s' % target)

    def assertCannotAppend(self, user, target):
        """Assert that the user cannot add an FAQ to an FAQ target."""
        can_append = check_permission('launchpad.Append', IFAQTarget(target))
        self.assertFalse(can_append, 'User can append append to %s' % target)

    def test_owner_can_append(self):
        # An owner of an FAQ target can add an FAQ.
        login_person(self.owner)
        self.assertCanAppend(self.owner, self.target)

    def test_direct_answer_contact_can_append(self):
        # An direct answer contact for an FAQ target can add an FAQ.
        direct_answer_contact = self.factory.makePerson()
        login_person(direct_answer_contact)
        self.addAnswerContact(direct_answer_contact)
        self.assertCanAppend(direct_answer_contact, self.target)

    def test_indirect_answer_contact_can_append(self):
        # An indirect answer contact (a member of a team that is an answer
        # contact) for an FAQ target can add an FAQ.
        indirect_answer_contact = self.factory.makePerson()
        direct_answer_contact = self.factory.makeTeam()
        with person_logged_in(direct_answer_contact.teamowner):
            direct_answer_contact.addMember(
                indirect_answer_contact, direct_answer_contact.teamowner)
            self.addAnswerContact(direct_answer_contact)
        login_person(indirect_answer_contact)
        self.assertCanAppend(indirect_answer_contact, self.target)

    def test_nonparticipating_user_cannot_append(self):
        # A user that is neither an owner of, or answer contact for, an
        # FAQ target cannot add an FAQ.
        nonparticipant = self.factory.makePerson()
        login_person(nonparticipant)
        self.assertCannotAppend(nonparticipant, self.target)


class TestDistributionPermissions(BaseIFAQTargetTests, TestCaseWithFactory):
    """Test who can add FAQs to a distribution."""

    def setUp(self):
        super(TestDistributionPermissions, self).setUp()
        self.target = self.factory.makeDistribution()
        self.owner = self.target.owner


class TestProductPermissions(BaseIFAQTargetTests, TestCaseWithFactory):
    """Test who can add FAQs to a product."""

    def setUp(self):
        super(TestProductPermissions, self).setUp()
        self.target = self.factory.makeProduct()
        self.owner = self.target.owner


class TestDSPPermissions(BaseIFAQTargetTests, TestCaseWithFactory):
    """Test who can add FAQs for a distribution source package."""

    def setUp(self):
        super(TestDSPPermissions, self).setUp()
        distribution = self.factory.makeDistribution()
        self.owner = distribution.owner
        self.target = self.factory.makeDistributionSourcePackage(
            sourcepackagename='fnord', distribution=distribution)
