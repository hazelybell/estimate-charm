# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the QuestionSubscrption model object.."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.errors import UserCannotUnsubscribePerson
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestQuestionSubscription(TestCaseWithFactory):
    """Tests relating to question subscriptions in general."""

    layer = DatabaseFunctionalLayer

    def test_owner_subscribed(self):
        # The owner of a question is subscribed to the question.
        question = self.factory.makeQuestion()
        [subscription] = list(question.subscriptions)
        self.assertEqual(question.owner, subscription.person)

    def test_subscribed_by_set(self):
        """The user subscribing is recorded along the subscriber."""
        subscriber = self.factory.makePerson()
        question = self.factory.makeQuestion()
        with person_logged_in(subscriber):
            subscription = question.subscribe(subscriber)
        self.assertEqual(subscriber, subscription.person)

    def test_unsubscribe(self):
        """Test unsubscribing by the subscriber."""
        subscription = self.factory.makeQuestionSubscription()
        subscriber = subscription.person
        question = subscription.question
        with person_logged_in(subscriber):
            question.unsubscribe(subscriber, subscriber)
        self.assertFalse(question.isSubscribed(subscriber))

    def test_unsubscribe_by_unauthorized(self):
        """Test unsubscribing someone you shouldn't be able to."""
        subscription = self.factory.makeQuestionSubscription()
        question = subscription.question
        unsubscriber = self.factory.makePerson()
        with person_logged_in(unsubscriber):
            self.assertRaises(
                UserCannotUnsubscribePerson,
                question.unsubscribe,
                subscription.person,
                unsubscriber)


class TestQuestionSubscriptionCanBeUnsubscribedbyUser(TestCaseWithFactory):
    """Tests for QuestionSubscription.canBeUnsubscribedByUser."""

    layer = DatabaseFunctionalLayer

    def test_none(self):
        """None for a user always returns False."""
        subscription = self.factory.makeQuestionSubscription()
        self.assertFalse(subscription.canBeUnsubscribedByUser(None))

    def test_self_subscriber(self):
        """The subscriber has permission to unsubscribe."""
        subscription = self.factory.makeQuestionSubscription()
        self.assertTrue(
            subscription.canBeUnsubscribedByUser(subscription.person))

    def test_non_subscriber_fails(self):
        """An unrelated person can't unsubscribe a user."""
        subscription = self.factory.makeQuestionSubscription()
        editor = self.factory.makePerson()
        self.assertFalse(subscription.canBeUnsubscribedByUser(editor))

    def test_team_member_can_unsubscribe(self):
        """Any team member can unsubscribe the team from a question."""
        team = self.factory.makeTeam()
        member = self.factory.makePerson()
        with person_logged_in(team.teamowner):
            team.addMember(member, team.teamowner)
        subscription = self.factory.makeQuestionSubscription(person=team)
        self.assertTrue(subscription.canBeUnsubscribedByUser(member))

    def test_question_person_owner_can_unsubscribe(self):
        """Question owner can unsubscribe someone from a question."""
        question_owner = self.factory.makePerson()
        question = self.factory.makeQuestion(owner=question_owner)
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeQuestionSubscription(
            question=question, person=subscriber)
        self.assertTrue(subscription.canBeUnsubscribedByUser(question_owner))

    def test_question_team_owner_can_unsubscribe(self):
        """Question team owner can unsubscribe someone from a question.

        If the owner of a question is a team, then the team members can
        unsubscribe someone.
        """
        team_owner = self.factory.makePerson()
        team_member = self.factory.makePerson()
        question_owner = self.factory.makeTeam(
            owner=team_owner, members=[team_member])
        question = self.factory.makeQuestion(owner=question_owner)
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeQuestionSubscription(
            question=question, person=subscriber)
        self.assertTrue(subscription.canBeUnsubscribedByUser(team_owner))
        self.assertTrue(subscription.canBeUnsubscribedByUser(team_member))

    def test_question_target_owner_can_unsubscribe(self):
        """Question target owner can unsubscribe someone from a question."""
        target_owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=target_owner)
        question = self.factory.makeQuestion(target=product)
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeQuestionSubscription(
            question=question, person=subscriber)
        self.assertTrue(subscription.canBeUnsubscribedByUser(target_owner))

    def test_question_target_answer_contact_can_unsubscribe(self):
        """Question target answer contact can unsubscribe someone."""
        answer_contact = self.factory.makePerson()
        english = getUtility(ILanguageSet)['en']
        answer_contact.addLanguage(english)
        distro_owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=distro_owner)
        with person_logged_in(distro_owner):
            distro.addAnswerContact(answer_contact, answer_contact)
        question = self.factory.makeQuestion(target=distro)
        subscriber = self.factory.makePerson()
        subscription = self.factory.makeQuestionSubscription(
            question=question, person=subscriber)
        self.assertTrue(subscription.canBeUnsubscribedByUser(answer_contact))
