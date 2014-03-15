# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `BugSubscriptionInfo`."""

__metaclass__ = type

from contextlib import contextmanager

from storm.store import Store
from testtools.matchers import Equals
from zope.component import queryAdapter
from zope.security.checker import getChecker

from lp.app.interfaces.security import IAuthorization
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.model.bug import (
    BugSubscriberSet,
    BugSubscriptionInfo,
    BugSubscriptionSet,
    load_people,
    StructuralSubscriptionSet,
    )
from lp.bugs.security import (
    PublicToAllOrPrivateToExplicitSubscribersForBugTask,
    )
from lp.registry.model.person import Person
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount


class TestLoadPeople(TestCaseWithFactory):
    """Tests for `load_people`."""

    layer = DatabaseFunctionalLayer

    def test(self):
        expected = [
            self.factory.makePerson(),
            self.factory.makeTeam(),
            ]
        observed = load_people(
            Person.id.is_in(person.id for person in expected))
        self.assertContentEqual(expected, observed)


class TestSubscriptionRelatedSets(TestCaseWithFactory):
    """Tests for *Set classes related to subscriptions."""

    layer = DatabaseFunctionalLayer

    name_pairs = ("A", "xa"), ("C", "xd"), ("B", "xb"), ("C", "xc")
    name_pairs_sorted = ("A", "xa"), ("B", "xb"), ("C", "xc"), ("C", "xd")

    def setUp(self):
        super(TestSubscriptionRelatedSets, self).setUp()
        make_person = lambda (displayname, name): (
            self.factory.makePerson(displayname=displayname, name=name))
        subscribers = dict(
            (name_pair, make_person(name_pair))
            for name_pair in self.name_pairs)
        self.subscribers_set = frozenset(subscribers.itervalues())
        self.subscribers_sorted = tuple(
            subscribers[name_pair] for name_pair in self.name_pairs_sorted)

    def test_BugSubscriberSet(self):
        subscriber_set = BugSubscriberSet(self.subscribers_set)
        self.assertIsInstance(subscriber_set, frozenset)
        self.assertEqual(self.subscribers_set, subscriber_set)
        self.assertEqual(self.subscribers_sorted, subscriber_set.sorted)

    def test_BugSubscriptionSet(self):
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            subscriptions = frozenset(
                bug.subscribe(subscriber, subscriber)
                for subscriber in self.subscribers_set)
        subscription_set = BugSubscriptionSet(subscriptions)
        self.assertIsInstance(subscription_set, frozenset)
        self.assertEqual(subscriptions, subscription_set)
        # BugSubscriptionSet.sorted returns a tuple of subscriptions ordered
        # by subscribers.
        self.assertEqual(
            self.subscribers_sorted, tuple(
                subscription.person
                for subscription in subscription_set.sorted))
        # BugSubscriptionSet.subscribers returns a BugSubscriberSet of the
        # subscription's subscribers.
        self.assertIsInstance(subscription_set.subscribers, BugSubscriberSet)
        self.assertEqual(self.subscribers_set, subscription_set.subscribers)

    def test_StructuralSubscriptionSet(self):
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            subscriptions = frozenset(
                product.addSubscription(subscriber, subscriber)
                for subscriber in self.subscribers_set)
        subscription_set = StructuralSubscriptionSet(subscriptions)
        self.assertIsInstance(subscription_set, frozenset)
        self.assertEqual(subscriptions, subscription_set)
        # StructuralSubscriptionSet.sorted returns a tuple of subscriptions
        # ordered by subscribers.
        self.assertEqual(
            self.subscribers_sorted, tuple(
                subscription.subscriber
                for subscription in subscription_set.sorted))
        # StructuralSubscriptionSet.subscribers returns a BugSubscriberSet of
        # the subscription's subscribers.
        self.assertIsInstance(subscription_set.subscribers, BugSubscriberSet)
        self.assertEqual(self.subscribers_set, subscription_set.subscribers)


class TestBugSubscriptionInfo(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionInfo, self).setUp()
        self.target = self.factory.makeProduct(
            bug_supervisor=self.factory.makePerson())
        self.bug = self.factory.makeBug(target=self.target)
        # Unsubscribe the bug filer to make the tests more readable.
        with person_logged_in(self.bug.owner):
            self.bug.unsubscribe(self.bug.owner, self.bug.owner)

    def getInfo(self, level=BugNotificationLevel.LIFECYCLE):
        return BugSubscriptionInfo(self.bug, level)

    def _create_direct_subscriptions(self):
        subscribers = (
            self.factory.makePerson(),
            self.factory.makePerson())
        with person_logged_in(self.bug.owner):
            subscriptions = tuple(
                self.bug.subscribe(subscriber, subscriber)
                for subscriber in subscribers)
        return subscribers, subscriptions

    def test_forTask(self):
        # `forTask` returns a new `BugSubscriptionInfo` narrowed to the given
        # bugtask.
        info = self.getInfo()
        self.assertIs(None, info.bugtask)
        # If called with the current bugtask the same `BugSubscriptionInfo`
        # instance is returned.
        self.assertIs(info, info.forTask(info.bugtask))
        # If called with a different bugtask a new `BugSubscriptionInfo` is
        # created.
        bugtask = self.bug.default_bugtask
        info_for_task = info.forTask(bugtask)
        self.assertIs(bugtask, info_for_task.bugtask)
        self.assertIsNot(info, info_for_task)
        # The instances share a cache of `BugSubscriptionInfo` instances.
        expected_cache = {
            info.cache_key: info,
            info_for_task.cache_key: info_for_task,
            }
        self.assertEqual(expected_cache, info.cache)
        self.assertIs(info.cache, info_for_task.cache)
        # Calling `forTask` again looks in the cache first.
        self.assertIs(info, info_for_task.forTask(info.bugtask))
        self.assertIs(info_for_task, info.forTask(info_for_task.bugtask))
        # The level is the same.
        self.assertEqual(info.level, info_for_task.level)

    def test_forLevel(self):
        # `forLevel` returns a new `BugSubscriptionInfo` narrowed to the given
        # subscription level.
        info = self.getInfo(BugNotificationLevel.LIFECYCLE)
        # If called with the current level the same `BugSubscriptionInfo`
        # instance is returned.
        self.assertIs(info, info.forLevel(info.level))
        # If called with a different level a new `BugSubscriptionInfo` is
        # created.
        level = BugNotificationLevel.METADATA
        info_for_level = info.forLevel(level)
        self.assertEqual(level, info_for_level.level)
        self.assertIsNot(info, info_for_level)
        # The instances share a cache of `BugSubscriptionInfo` instances.
        expected_cache = {
            info.cache_key: info,
            info_for_level.cache_key: info_for_level,
            }
        self.assertEqual(expected_cache, info.cache)
        self.assertIs(info.cache, info_for_level.cache)
        # Calling `forLevel` again looks in the cache first.
        self.assertIs(info, info_for_level.forLevel(info.level))
        self.assertIs(info_for_level, info.forLevel(info_for_level.level))
        # The bugtask is the same.
        self.assertIs(info.bugtask, info_for_level.bugtask)

    def test_muted(self):
        # The set of muted subscribers for the bug.
        subscribers, subscriptions = self._create_direct_subscriptions()
        sub1, sub2 = subscribers
        with person_logged_in(sub1):
            self.bug.mute(sub1, sub1)
        self.assertContentEqual([sub1], self.getInfo().muted_subscribers)

    def test_direct(self):
        # The set of direct subscribers.
        subscribers, subscriptions = self._create_direct_subscriptions()
        found_subscriptions = self.getInfo().direct_subscriptions
        self.assertContentEqual(subscriptions, found_subscriptions)
        self.assertContentEqual(subscribers, found_subscriptions.subscribers)

    def test_direct_muted(self):
        # If a direct is muted, it is not listed.
        subscribers, subscriptions = self._create_direct_subscriptions()
        with person_logged_in(subscribers[0]):
            self.bug.mute(subscribers[0], subscribers[0])
        found_subscriptions = self.getInfo().direct_subscriptions
        self.assertContentEqual([subscriptions[1]], found_subscriptions)

    def test_all_direct(self):
        # The set of all direct subscribers, regardless of level.
        subscribers, subscriptions = self._create_direct_subscriptions()
        # Change the first subscription to be for comments only.
        sub1, sub2 = subscriptions
        with person_logged_in(sub1.person):
            sub1.bug_notification_level = BugNotificationLevel.LIFECYCLE
        info = self.getInfo(BugNotificationLevel.COMMENTS)
        self.assertContentEqual([sub2], info.direct_subscriptions)
        self.assertContentEqual(
            [sub1, sub2], info.direct_subscriptions_at_all_levels)

    def _create_duplicate_subscription(self):
        duplicate_bug = self.factory.makeBug(target=self.target)
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(self.bug)
            duplicate_bug_subscription = (
                duplicate_bug.getSubscriptionForPerson(
                    duplicate_bug.owner))
        return duplicate_bug, duplicate_bug_subscription

    def test_duplicate(self):
        # The set of subscribers from duplicate bugs.
        found_subscriptions = self.getInfo().duplicate_subscriptions
        self.assertContentEqual([], found_subscriptions)
        self.assertContentEqual([], found_subscriptions.subscribers)
        duplicate_bug, duplicate_bug_subscription = (
            self._create_duplicate_subscription())
        found_subscriptions = self.getInfo().duplicate_subscriptions
        self.assertContentEqual(
            [duplicate_bug_subscription],
            found_subscriptions)
        self.assertContentEqual(
            [duplicate_bug.owner],
            found_subscriptions.subscribers)

    def test_duplicate_muted(self):
        # If a duplicate is muted, it is not listed.
        duplicate_bug, duplicate_bug_subscription = (
            self._create_duplicate_subscription())
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.mute(duplicate_bug.owner, duplicate_bug.owner)
        found_subscriptions = self.getInfo().duplicate_subscriptions
        self.assertContentEqual([], found_subscriptions)

    def test_duplicate_other_mute(self):
        # If some other bug is muted, the dupe is still listed.
        duplicate_bug, duplicate_bug_subscription = (
            self._create_duplicate_subscription())
        with person_logged_in(duplicate_bug.owner):
            self.factory.makeBug().mute(
                duplicate_bug.owner, duplicate_bug.owner)
        found_subscriptions = self.getInfo().duplicate_subscriptions
        self.assertContentEqual(
            [duplicate_bug_subscription], found_subscriptions)

    def test_duplicate_only(self):
        # The set of duplicate subscriptions where the subscriber has no other
        # subscriptions.
        duplicate_bug = self.factory.makeBug(target=self.target)
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(self.bug)
            duplicate_bug_subscription = (
                duplicate_bug.getSubscriptionForPerson(
                    duplicate_bug.owner))
        found_subscriptions = self.getInfo().duplicate_only_subscriptions
        self.assertContentEqual(
            [duplicate_bug_subscription],
            found_subscriptions)
        # If a user is subscribed to a duplicate bug and is a bugtask
        # assignee, for example, their duplicate subscription will not be
        # included.
        with person_logged_in(self.target.owner):
            self.bug.default_bugtask.transitionToAssignee(
                duplicate_bug_subscription.person)
        found_subscriptions = self.getInfo().duplicate_only_subscriptions
        self.assertContentEqual([], found_subscriptions)

    def test_structural_subscriptions(self):
        # The set of structural subscriptions.
        subscribers = (
            self.factory.makePerson(),
            self.factory.makePerson())
        with person_logged_in(self.bug.owner):
            subscriptions = tuple(
                self.target.addBugSubscription(subscriber, subscriber)
                for subscriber in subscribers)
        found_subscriptions = self.getInfo().structural_subscriptions
        self.assertContentEqual(subscriptions, found_subscriptions)

    def test_structural_subscriptions_muted(self):
        # The set of structural subscriptions DOES NOT exclude muted
        # subscriptions.
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            self.bug.mute(subscriber, subscriber)
        with person_logged_in(self.bug.owner):
            subscription = self.target.addBugSubscription(
                subscriber, subscriber)
        found_subscriptions = self.getInfo().structural_subscriptions
        self.assertContentEqual([subscription], found_subscriptions)

    def test_structural_subscribers(self):
        # The set of structural subscribers.
        subscribers = (
            self.factory.makePerson(),
            self.factory.makePerson())
        with person_logged_in(self.bug.owner):
            for subscriber in subscribers:
                self.target.addBugSubscription(subscriber, subscriber)
        found_subscribers = self.getInfo().structural_subscribers
        self.assertContentEqual(subscribers, found_subscribers)

    def test_structural_subscribers_muted(self):
        # The set of structural subscribers DOES NOT exclude muted
        # subscribers.
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            self.bug.mute(subscriber, subscriber)
        with person_logged_in(self.bug.owner):
            self.target.addBugSubscription(subscriber, subscriber)
        found_subscribers = self.getInfo().structural_subscribers
        self.assertContentEqual([subscriber], found_subscribers)

    def test_all_assignees(self):
        # The set of bugtask assignees for bugtasks that have been assigned.
        found_assignees = self.getInfo().all_assignees
        self.assertContentEqual([], found_assignees)
        bugtask = self.bug.default_bugtask
        with person_logged_in(bugtask.pillar.bug_supervisor):
            bugtask.transitionToAssignee(self.bug.owner)
        found_assignees = self.getInfo().all_assignees
        self.assertContentEqual([self.bug.owner], found_assignees)
        bugtask2 = self.factory.makeBugTask(bug=self.bug)
        with person_logged_in(bugtask2.pillar.owner):
            bugtask2.transitionToAssignee(bugtask2.owner)
        found_assignees = self.getInfo().all_assignees
        self.assertContentEqual(
            [self.bug.owner, bugtask2.owner],
            found_assignees)
        # Getting info for a specific bugtask will return the assignee for
        # that bugtask only.
        self.assertContentEqual(
            [bugtask2.owner],
            self.getInfo().forTask(bugtask2).all_assignees)

    def _create_also_notified_subscribers(self):
        # Add an assignee, a bug supervisor and a structural subscriber.
        bugtask = self.bug.default_bugtask
        assignee = self.factory.makePerson()
        with person_logged_in(bugtask.pillar.bug_supervisor):
            bugtask.transitionToAssignee(assignee)
        supervisor = self.factory.makePerson()
        with person_logged_in(bugtask.target.owner):
            bugtask.target.bug_supervisor = supervisor
        structural_subscriber = self.factory.makePerson()
        with person_logged_in(structural_subscriber):
            bugtask.target.addSubscription(
                structural_subscriber, structural_subscriber)
        return assignee, supervisor, structural_subscriber

    def test_also_notified_subscribers(self):
        # The set of also notified subscribers.
        found_subscribers = self.getInfo().also_notified_subscribers
        self.assertContentEqual([], found_subscribers)
        assignee, supervisor, structural_subscriber = (
            self._create_also_notified_subscribers())
        # Add a direct subscription.
        direct_subscriber = self.factory.makePerson()
        with person_logged_in(self.bug.owner):
            self.bug.subscribe(direct_subscriber, direct_subscriber)
        # The direct subscriber does not appear in the also notified set, but
        # the assignee, supervisor and structural subscriber do.
        found_subscribers = self.getInfo().also_notified_subscribers
        self.assertContentEqual(
            [assignee, structural_subscriber], found_subscribers)

    def test_also_notified_subscribers_muted(self):
        # If someone is muted, they are not listed in the
        # also_notified_subscribers.
        assignee, supervisor, structural_subscriber = (
            self._create_also_notified_subscribers())
        # As a control, we first show that the
        # the assignee, supervisor and structural subscriber do show up
        # when they are not muted.
        found_subscribers = self.getInfo().also_notified_subscribers
        self.assertContentEqual(
            [assignee, structural_subscriber], found_subscribers)
        # Now we mute all of the subscribers.
        with person_logged_in(assignee):
            self.bug.mute(assignee, assignee)
        with person_logged_in(structural_subscriber):
            self.bug.mute(structural_subscriber, structural_subscriber)
        # Now we don't see them.
        found_subscribers = self.getInfo().also_notified_subscribers
        self.assertContentEqual([], found_subscribers)


class TestBugSubscriptionInfoPermissions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test(self):
        bug = self.factory.makeBug()
        info = bug.getSubscriptionInfo()
        checker = getChecker(info)

        # BugSubscriptionInfo objects are immutable.
        self.assertEqual({}, checker.set_permissions)

        # All attributes require launchpad.View.
        permissions = set(checker.get_permissions.itervalues())
        self.assertContentEqual(["launchpad.View"], permissions)

        # The security adapter for launchpad.View lets anyone reference the
        # attributes unless the bug is private, in which case only explicit
        # subscribers are permitted.
        adapter = queryAdapter(info, IAuthorization, "launchpad.View")
        self.assertIsInstance(
            adapter, PublicToAllOrPrivateToExplicitSubscribersForBugTask)


class TestBugSubscriptionInfoQueries(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionInfoQueries, self).setUp()
        self.target = self.factory.makeProduct()
        self.bug = self.factory.makeBug(target=self.target)
        self.info = BugSubscriptionInfo(
            self.bug, BugNotificationLevel.LIFECYCLE)
        # Get the Storm cache into a known state.
        self.store = Store.of(self.bug)
        self.store.invalidate()
        self.store.reload(self.bug)
        self.bug.bugtasks
        self.bug.tags

    @contextmanager
    def exactly_x_queries(self, count):
        # Assert that there are exactly `count` queries sent to the database
        # in this context. Flush first to ensure we don't count things that
        # happened before entering this context.
        self.store.flush()
        condition = HasQueryCount(Equals(count))
        with StormStatementRecorder() as recorder:
            yield recorder
        self.assertThat(recorder, condition)

    def exercise_subscription_set(self, set_name, counts=(1, 1, 0)):
        """Test the number of queries it takes to inspect a subscription set.

        :param set_name: The name of the set, e.g. "direct_subscriptions".
        :param counts: A triple of the expected query counts for each of three
            operations: get the set, get the set's subscribers, get the set's
            subscribers in order.
        """
        # Looking up subscriptions takes a single query.
        with self.exactly_x_queries(counts[0]):
            getattr(self.info, set_name)
        # Getting the subscribers results in one additional query.
        with self.exactly_x_queries(counts[1]):
            getattr(self.info, set_name).subscribers
        # Everything is now cached so no more queries are needed.
        with self.exactly_x_queries(counts[2]):
            getattr(self.info, set_name).subscribers
            getattr(self.info, set_name).subscribers.sorted

    def exercise_subscription_set_sorted_first(
        self, set_name, counts=(1, 1, 0)):
        """Test the number of queries it takes to inspect a subscription set.

        This differs from `exercise_subscription_set` in its second step, when
        it looks at the sorted subscription list instead of the subscriber
        set.

        :param set_name: The name of the set, e.g. "direct_subscriptions".
        :param counts: A triple of the expected query counts for each of three
            operations: get the set, get the set in order, get the set's
            subscribers in order.
        """
        # Looking up subscriptions takes a single query.
        with self.exactly_x_queries(counts[0]):
            getattr(self.info, set_name)
        # Getting the sorted subscriptions takes one additional query.
        with self.exactly_x_queries(counts[1]):
            getattr(self.info, set_name).sorted
        # Everything is now cached so no more queries are needed.
        with self.exactly_x_queries(counts[2]):
            getattr(self.info, set_name).subscribers
            getattr(self.info, set_name).subscribers.sorted

    def test_direct_subscriptions(self):
        self.exercise_subscription_set(
            "direct_subscriptions")

    def test_direct_subscriptions_sorted_first(self):
        self.exercise_subscription_set_sorted_first(
            "direct_subscriptions")

    def test_direct_subscriptions_at_all_levels(self):
        self.exercise_subscription_set(
            "direct_subscriptions_at_all_levels")

    def make_duplicate_bug(self):
        duplicate_bug = self.factory.makeBug(target=self.target)
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(self.bug)

    def test_duplicate_subscriptions(self):
        self.make_duplicate_bug()
        self.exercise_subscription_set(
            "duplicate_subscriptions")

    def test_duplicate_subscriptions_sorted_first(self):
        self.make_duplicate_bug()
        self.exercise_subscription_set_sorted_first(
            "duplicate_subscriptions")

    def test_duplicate_subscriptions_for_private_bug(self):
        self.make_duplicate_bug()
        with person_logged_in(self.bug.owner):
            self.bug.setPrivate(True, self.bug.owner)
        with self.exactly_x_queries(1):
            self.info.duplicate_subscriptions
        with self.exactly_x_queries(0):
            self.info.duplicate_subscriptions.subscribers

    def add_structural_subscriber(self):
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            self.target.addSubscription(subscriber, subscriber)

    def test_structural_subscriptions(self):
        self.add_structural_subscriber()
        self.exercise_subscription_set(
            "structural_subscriptions", (2, 1, 0))

    def test_structural_subscriptions_sorted_first(self):
        self.add_structural_subscriber()
        self.exercise_subscription_set_sorted_first(
            "structural_subscriptions", (2, 1, 0))

    def test_all_assignees(self):
        with self.exactly_x_queries(1):
            self.info.all_assignees

    def test_also_notified_subscribers(self):
        with self.exactly_x_queries(5):
            self.info.also_notified_subscribers

    def test_also_notified_subscribers_later(self):
        # When also_notified_subscribers is referenced after some other sets
        # in BugSubscriptionInfo are referenced, everything comes from cache.
        self.info.all_assignees
        self.info.direct_subscriptions.subscribers
        self.info.structural_subscribers
        with self.exactly_x_queries(1):
            self.info.also_notified_subscribers

    def test_indirect_subscribers(self):
        with self.exactly_x_queries(6):
            self.info.indirect_subscribers

    def test_indirect_subscribers_later(self):
        # When indirect_subscribers is referenced after some other sets in
        # BugSubscriptionInfo are referenced, everything comes from cache.
        self.info.also_notified_subscribers
        self.info.duplicate_subscriptions.subscribers
        with self.exactly_x_queries(0):
            self.info.indirect_subscribers
