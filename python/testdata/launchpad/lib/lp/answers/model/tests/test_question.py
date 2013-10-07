# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestQuestionDirectSubscribers(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_get_direct_subscribers(self):
        question = self.factory.makeQuestion()
        subscriber = self.factory.makePerson()
        subscribers = [question.owner, subscriber]
        with person_logged_in(subscriber):
            question.subscribe(subscriber, subscriber)

        direct_subscribers = question.getDirectSubscribers()
        self.assertEqual(
            set(subscribers), set(direct_subscribers),
            "Subscribers did not match expected value.")

    def test_get_direct_subscribers_with_details_other_subscriber(self):
        # getDirectSubscribersWithDetails() returns
        # Person and QuestionSubscription records in one go.
        question = self.factory.makeQuestion()
        with person_logged_in(question.owner):
            # Unsubscribe question owner so it doesn't taint the result.
            question.unsubscribe(question.owner, question.owner)
        subscriber = self.factory.makePerson()
        subscribee = self.factory.makePerson()
        with person_logged_in(subscriber):
            subscription = question.subscribe(subscribee, subscriber)
        self.assertContentEqual(
            [(subscribee, subscription)],
            question.getDirectSubscribersWithDetails())

    def test_get_direct_subscribers_with_details_self_subscribed(self):
        # getDirectSubscribersWithDetails() returns
        # Person and QuestionSubscription records in one go.
        question = self.factory.makeQuestion()
        with person_logged_in(question.owner):
            # Unsubscribe question owner so it doesn't taint the result.
            question.unsubscribe(question.owner, question.owner)
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            subscription = question.subscribe(subscriber, subscriber)
        self.assertContentEqual(
            [(subscriber, subscription)],
            question.getDirectSubscribersWithDetails())


class TestQuestionInDirectSubscribers(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_answerContactIsIndirectSubscriber(self):
        # Question answer contacts are indirect subscribers to questions.
        person = self.factory.makePerson()
        person.addLanguage(getUtility(ILanguageSet)['en'])
        question = self.factory.makeQuestion()
        with person_logged_in(question.owner):
            question.target.addAnswerContact(person, person)

        # Check the results.
        self.assertEqual([person], question.getIndirectSubscribers())

    def test_assigneeIsIndirectSubscriber(self):
        # Question assignees are indirect subscribers to questions.
        person = self.factory.makePerson()
        question = self.factory.makeQuestion()
        with person_logged_in(question.owner):
            question.assignee = person

        # Check the results.
        self.assertEqual([person], question.getIndirectSubscribers())

    def test_answerContactIsIndirectSubscriberCorrectLanguage(self):
        # Question answer contacts are indirect subscribers to questions and
        # are filtered according to the question's language.
        english_person = self.factory.makePerson()
        english_person.addLanguage(getUtility(ILanguageSet)['en'])
        spanish = getUtility(ILanguageSet)['es']
        spanish_person = self.factory.makePerson()
        spanish_person.addLanguage(spanish)
        question = self.factory.makeQuestion(language=spanish)
        with person_logged_in(question.owner):
            question.target.addAnswerContact(english_person, english_person)
            question.target.addAnswerContact(spanish_person, spanish_person)

        # Check the results.
        self.assertEqual([spanish_person], question.getIndirectSubscribers())
