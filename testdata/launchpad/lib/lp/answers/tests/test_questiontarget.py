# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests related to IQuestionTarget."""

__metaclass__ = type

__all__ = []

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    login_celebrity,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class QuestionTargetAnswerContactTestCase(TestCaseWithFactory):
    """Tests for changing an answer contact."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(QuestionTargetAnswerContactTestCase, self).setUp()
        self.project = self.factory.makeProduct()
        self.user = self.factory.makePerson()

    def test_canUserAlterAnswerContact_self(self):
        login_person(self.user)
        self.assertTrue(
            self.project.canUserAlterAnswerContact(self.user, self.user))

    def test_canUserAlterAnswerContact_owner(self):
        login_person(self.user)
        self.assertTrue(
            self.project.canUserAlterAnswerContact(
                self.user, self.project.owner))

    def test_canUserAlterAnswerContact_DistributionSourcePackage_owner(self):
        login_person(self.user)
        distro = self.factory.makeDistribution()
        dsp = self.factory.makeDistributionSourcePackage(distribution=distro)
        self.assertTrue(
            dsp.canUserAlterAnswerContact(self.user, distro.owner))

    def test_canUserAlterAnswerContact_other_user(self):
        login_person(self.user)
        other_user = self.factory.makePerson()
        self.assertFalse(
            self.project.canUserAlterAnswerContact(other_user, self.user))

    def test_canUserAlterAnswerContact_administered_team(self):
        login_person(self.user)
        team = self.factory.makeTeam(owner=self.user)
        self.assertTrue(
            self.project.canUserAlterAnswerContact(team, self.user))

    def test_canUserAlterAnswerContact_other_team(self):
        login_person(self.user)
        other_team = self.factory.makeTeam()
        self.assertFalse(
            self.project.canUserAlterAnswerContact(other_team, self.user))

    def test_canUserAlterAnswerContact_admin(self):
        admin = login_celebrity('admin')
        other_user = self.factory.makePerson()
        self.assertTrue(
            self.project.canUserAlterAnswerContact(other_user, admin))


class TestQuestionTarget_answer_contacts_with_languages(TestCaseWithFactory):
    """Tests for the 'answer_contacts_with_languages' property of question
    targets.
    """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestQuestionTarget_answer_contacts_with_languages, self).setUp()
        self.answer_contact = self.factory.makePerson()
        login_person(self.answer_contact)
        lang_set = getUtility(ILanguageSet)
        self.answer_contact.addLanguage(lang_set['pt_BR'])
        self.answer_contact.addLanguage(lang_set['en'])

    def test_Product_implementation_should_prefill_cache(self):
        # Remove the answer contact's security proxy because we need to call
        # some non public methods to change its language cache.
        answer_contact = removeSecurityProxy(self.answer_contact)
        product = self.factory.makeProduct()
        product.addAnswerContact(answer_contact, answer_contact)

        # Must delete the cache because it's been filled in addAnswerContact.
        answer_contact.deleteLanguagesCache()
        self.assertRaises(AttributeError, answer_contact.getLanguagesCache)

        # Need to remove the product's security proxy because
        # answer_contacts_with_languages is not part of its public API.
        answer_contacts = removeSecurityProxy(
            product).answer_contacts_with_languages
        self.failUnlessEqual(answer_contacts, [answer_contact])
        langs = [
            lang.englishname for lang in answer_contact.getLanguagesCache()]
        # The languages cache has been filled in the correct order.
        self.failUnlessEqual(langs, [u'English', u'Portuguese (Brazil)'])

    def test_SourcePackage_implementation_should_prefill_cache(self):
        # Remove the answer contact's security proxy because we need to call
        # some non public methods to change its language cache.
        answer_contact = removeSecurityProxy(self.answer_contact)
        ubuntu = getUtility(IDistributionSet)['ubuntu']
        self.factory.makeSourcePackageName(name='test-pkg')
        source_package = ubuntu.getSourcePackage('test-pkg')
        source_package.addAnswerContact(answer_contact, answer_contact)

        # Must delete the cache because it's been filled in addAnswerContact.
        answer_contact.deleteLanguagesCache()
        self.assertRaises(AttributeError, answer_contact.getLanguagesCache)

        # Need to remove the sourcepackage's security proxy because
        # answer_contacts_with_languages is not part of its public API.
        answer_contacts = removeSecurityProxy(
            source_package).answer_contacts_with_languages
        self.failUnlessEqual(answer_contacts, [answer_contact])
        langs = [
            lang.englishname for lang in answer_contact.getLanguagesCache()]
        # The languages cache has been filled in the correct order.
        self.failUnlessEqual(langs, [u'English', u'Portuguese (Brazil)'])


class TestQuestionTargetCreateQuestionFromBug(TestCaseWithFactory):
    """Test the createQuestionFromBug from bug behavior."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestQuestionTargetCreateQuestionFromBug, self).setUp()
        self.bug = self.factory.makeBug(description="first comment")
        self.target = self.bug.bugtasks[0].target
        self.contributor = self.target.owner
        self.reporter = self.bug.owner

    def test_first_and_last_messages_copied_to_question(self):
        # The question is created with the bug's description and the last
        # message which presumably is about why the bug was converted.
        with person_logged_in(self.reporter):
            self.bug.newMessage(owner=self.reporter, content='second comment')
        with person_logged_in(self.contributor):
            last_message = self.bug.newMessage(
                owner=self.contributor, content='third comment')
            question = self.target.createQuestionFromBug(self.bug)
        question_messages = list(question.messages)
        self.assertEqual(1, len(question_messages))
        self.assertEqual(last_message.content, question_messages[0].content)
        self.assertEqual(self.bug.description, question.description)

    def test_bug_subscribers_copied_to_question(self):
        # Users who subscribe to the bug are also interested in the answer.
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            self.bug.subscribe(subscriber, subscriber)
        with person_logged_in(self.contributor):
            self.bug.newMessage(owner=self.contributor, content='comment')
            question = self.target.createQuestionFromBug(self.bug)
        self.assertTrue(question.isSubscribed(subscriber))
        self.assertTrue(question.isSubscribed(question.owner))
