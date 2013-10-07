# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class SpecificationPortletSubscribersContentsTestCase(TestCaseWithFactory):
    """Tests for SpecificationPortletSubscribersContents view."""

    layer = DatabaseFunctionalLayer

    def test_sorted_subscriptions(self):
        # SpecificationPortletSubscribersContents.sorted_subscriptions
        spec = self.factory.makeSpecification()
        subscriber = self.factory.makePerson(displayname="Joe")
        subscriber1 = self.factory.makePerson(displayname="Mark")
        subscriber2 = self.factory.makePerson(displayname="Fred")
        with person_logged_in(subscriber):
            sub1 = spec.subscribe(subscriber, subscriber)
            sub2 = spec.subscribe(subscriber1, subscriber)
            sub3 = spec.subscribe(subscriber2, subscriber)
            view = create_initialized_view(
                spec, name="+blueprint-portlet-subscribers-content")
            self.assertEqual([sub1, sub3, sub2], view.sorted_subscriptions)


class TestSpecificationPortletSubcribersIds(TestCaseWithFactory):
    # Tests for SpecificationPortletSubcribersIds view.
    layer = DatabaseFunctionalLayer

    def test_subscriber_ids(self):
        spec = self.factory.makeSpecification()
        subscriber = self.factory.makePerson()
        person = self.factory.makePerson()
        with person_logged_in(person):
            spec.subscribe(subscriber, subscriber)
            view = create_initialized_view(
                spec, name="+blueprint-portlet-subscribers-ids")
            subscriber_ids = dict(
                    (subscriber.name, 'subscriber-%s' % subscriber.id)
                    for subscriber in [person, subscriber])
            self.assertEqual(subscriber_ids, view.subscriber_ids)
