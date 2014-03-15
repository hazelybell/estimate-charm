# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Bug subscription-related email tests."""

import transaction

from lp.services.mail import stub
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSubscribedBySomeoneElseNotification(TestCaseWithFactory):
    """Test emails sent when subscribed by someone else."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        # Run the tests as a logged-in user.
        super(TestSubscribedBySomeoneElseNotification, self).setUp(
            user='test@canonical.com')

    def test_suppress_notify_false_does_notify(self):
        """Test notifications are sent when suppress_notify is False."""
        bug = self.factory.makeBug()
        person_subscribing = self.factory.makePerson(
            name='foosuber', displayname='Foo Suber')
        person_subscribed = self.factory.makePerson(
            name='foosubed', displayname='Foo Subed')
        self.assertEqual(len(stub.test_emails), 0)
        bug_subscription = bug.subscribe(
            person_subscribed, person_subscribing, suppress_notify=False)
        transaction.commit()
        self.assertEqual(len(stub.test_emails), 1)
        rationale = 'You have been subscribed to a public bug by Foo Suber'
        msg = stub.test_emails[-1][2]
        self.assertTrue(rationale in msg)

    def test_suppress_notify_true_does_not_notify(self):
        """Test notifications are not sent when suppress_notify is True."""
        bug = self.factory.makeBug()
        person_subscribing = self.factory.makePerson(
            name='foosuber', displayname='Foo Suber')
        person_subscribed = self.factory.makePerson(
            name='foosubed', displayname='Foo Subed')
        self.assertEqual(len(stub.test_emails), 0)
        bug_subscription = bug.subscribe(
            person_subscribed, person_subscribing, suppress_notify=True)
        transaction.commit()
        self.assertEqual(len(stub.test_emails), 0)

    def test_suppress_notify_default_does_not_notify(self):
        """Test notifications are not sent when suppress_notify is undefined."""
        bug = self.factory.makeBug()
        person_subscribing = self.factory.makePerson(
            name='foosuber', displayname='Foo Suber')
        person_subscribed = self.factory.makePerson(
            name='foosubed', displayname='Foo Subed')
        self.assertEqual(len(stub.test_emails), 0)
        bug_subscription = bug.subscribe(
            person_subscribed, person_subscribing)
        transaction.commit()
        self.assertEqual(len(stub.test_emails), 0)
