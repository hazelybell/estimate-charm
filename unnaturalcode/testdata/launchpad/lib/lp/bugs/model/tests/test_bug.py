# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

from lazr.lifecycle.event import ObjectCreatedEvent
from pytz import UTC
from storm.store import Store
from testtools.testcase import ExpectedException
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.adapters.bugchange import BugTitleChange
from lp.bugs.enums import (
    BugNotificationLevel,
    BugNotificationStatus,
    )
from lp.bugs.interfaces.bugnotification import IBugNotificationSet
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.mail.bugnotificationrecipients import BugNotificationRecipients
from lp.bugs.model.bug import (
    BugNotification,
    BugSubscriptionInfo,
    )
from lp.registry.enums import BugSharingPolicy
from lp.registry.errors import CannotChangeInformationType
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactSource,
    IAccessPolicyArtifactSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.person import PersonVisibility
from lp.registry.tests.test_accesspolicy import get_policies_for_artifact
from lp.testing import (
    admin_logged_in,
    EventRecorder,
    feature_flags,
    login_person,
    person_logged_in,
    record_two_runs,
    set_feature_flag,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import (
    Equals,
    HasQueryCount,
    LessThan,
    )


class TestBug(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_getNominationFor_sourcepackage(self):
        sourcepackage = self.factory.makeSourcePackage()
        series = sourcepackage.distroseries
        bug = self.factory.makeBug(target=series.distribution)
        with person_logged_in(series.owner):
            bug.addNomination(series.owner, series)
        nomination = bug.getNominationFor(sourcepackage)
        self.assertEqual(series, nomination.target)

    def makeManyNominations(self):
        target = self.factory.makeSourcePackage()
        series = target.distroseries
        with person_logged_in(series.distribution.owner):
            nomination = self.factory.makeBugNomination(target=target)
        bug = nomination.bug
        other_series = self.factory.makeProductSeries()
        other_target = other_series.product
        self.factory.makeBugTask(bug=bug, target=other_target)
        with person_logged_in(other_target.owner):
            other_nomination = bug.addNomination(
                other_target.owner, other_series)
        return bug, [nomination, other_nomination]

    def test_getNominations(self):
        # The getNominations() method returns all the nominations for the bug.
        bug, nominations = self.makeManyNominations()
        self.assertContentEqual(nominations, bug.getNominations())

    def test_getNominations_with_target(self):
        # The target argument filters the nominations to just one pillar.
        bug, nominations = self.makeManyNominations()
        pillar = nominations[0].target.pillar
        self.assertContentEqual([nominations[0]], bug.getNominations(pillar))

    def test_markAsDuplicate_None(self):
        # Calling markAsDuplicate(None) on a bug that is not currently a
        # duplicate works correctly, and does not raise an AttributeError.
        bug = self.factory.makeBug()
        with ExpectedException(AssertionError, 'AttributeError not raised'):
            with ExpectedException(AttributeError, ''):
                with person_logged_in(self.factory.makePerson()):
                    bug.markAsDuplicate(None)

    def test_get_subscribers_for_person_unsubscribed(self):
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        self.assertTrue(bug.getSubscribersForPerson(person).is_empty())

    def test_get_subscribers_for_person_direct_subscription(self):
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            bug.subscribe(person, person)
        self.assertEqual([person], list(bug.getSubscribersForPerson(person)))

    def test_get_subscribers_for_person_indirect_subscription(self):
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        team1 = self.factory.makeTeam(members=[person])
        self.factory.makeTeam(members=[person])
        with person_logged_in(person):
            bug.subscribe(team1, person)
        self.assertEqual([team1], list(bug.getSubscribersForPerson(person)))

    def test_get_subscribers_for_person_many_subscriptions(self):
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        team1 = self.factory.makeTeam(members=[person])
        team2 = self.factory.makeTeam(members=[person])
        with person_logged_in(person):
            bug.subscribe(team1, person)
            bug.subscribe(team2, person)
            bug.subscribe(person, person)
        self.assertEqual(
            set([person, team1, team2]),
            set(bug.getSubscribersForPerson(person)))

    def test_get_subscribers_for_person_from_duplicates_too(self):
        bug = self.factory.makeBug()
        real_bug = self.factory.makeBug()
        person = self.factory.makePerson()
        team1 = self.factory.makeTeam(members=[person])
        team2 = self.factory.makeTeam(members=[person])
        with person_logged_in(person):
            bug.subscribe(team1, person)
            bug.subscribe(team2, person)
            bug.subscribe(person, person)
            bug.markAsDuplicate(real_bug)
        self.assertEqual(
            set([person, team1, team2]),
            set(real_bug.getSubscribersForPerson(person)))

    def test_getSubscriptionsFromDuplicates(self):
        # getSubscriptionsFromDuplicates() will return only the earliest
        # subscription if a user is subscribed to a bug via more than one
        # duplicate.
        user = self.factory.makePerson()
        login_person(user)
        bug = self.factory.makeBug(owner=user)
        dupe1 = self.factory.makeBug(owner=user)
        dupe1.markAsDuplicate(bug)
        subscription = dupe1.subscribe(user, user)
        dupe2 = self.factory.makeBug(owner=user)
        dupe2.markAsDuplicate(bug)
        dupe2.subscribe(user, user)
        self.assertEqual(
            [subscription], list(bug.getSubscriptionsFromDuplicates()))

    def test_get_also_notified_subscribers_with_private_team(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        member = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=member, visibility=PersonVisibility.PRIVATE)
        with person_logged_in(member):
            product.addSubscription(team, member)
        self.assertTrue(team in bug.getAlsoNotifiedSubscribers())

    def test_get_indirect_subscribers_with_private_team(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        member = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=member, visibility=PersonVisibility.PRIVATE)
        with person_logged_in(member):
            product.addSubscription(team, member)
        self.assertTrue(team in bug.getIndirectSubscribers())

    def test_get_direct_subscribers_with_private_team(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        member = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=member, visibility=PersonVisibility.PRIVATE)
        with person_logged_in(member):
            bug.subscribe(team, member)
        self.assertTrue(team in bug.getDirectSubscribers())

    def test_get_direct_subscribers_query_count(self):
        bug = self.factory.makeBug()
        # Make lots of subscribers.
        for i in xrange(10):
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                bug.subscribe(subscriber, subscriber)
        Store.of(bug).flush()
        with StormStatementRecorder() as recorder:
            subscribers = list(bug.getDirectSubscribers())
            self.assertThat(len(subscribers), Equals(10 + 1))
            self.assertThat(recorder, HasQueryCount(Equals(2)))

    def test_mark_as_duplicate_query_count(self):
        bug = self.factory.makeBug()
        # Make lots of duplicate bugs.
        previous_dup = None
        for i in xrange(10):
            dup = self.factory.makeBug()
            # Make lots of subscribers.
            for j in xrange(10):
                subscriber = self.factory.makePerson()
                with person_logged_in(subscriber):
                    dup.subscribe(subscriber, subscriber)
            if previous_dup is not None:
                with person_logged_in(previous_dup.owner):
                    previous_dup.markAsDuplicate(dup)
            previous_dup = dup
        with person_logged_in(bug.owner):
            Store.of(bug).flush()
            with StormStatementRecorder() as recorder:
                previous_dup.markAsDuplicate(bug)
                self.assertThat(recorder, HasQueryCount(LessThan(95)))

    def _get_notifications(self, status):
        return self.store.find(
            BugNotification,
            BugNotification.date_emailed == None,
            BugNotification.status == status)

    def _get_pending(self):
        return self._get_notifications(BugNotificationStatus.PENDING)

    def _get_deferred(self):
        return self._get_notifications(BugNotificationStatus.DEFERRED)

    def _add_subscribers(self, bug, number):
        for i in xrange(number):
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                bug.subscribe(subscriber, subscriber)

    def test_duplicate_subscriber_notifications(self):
        # Notifications for duplicate bugs are deferred where notifications
        # for direct subscribers of the original bug are pending.
        bug = self.factory.makeBug(title="bug-0")
        self._add_subscribers(bug, 3)
        self.store = Store.of(bug)
        duplicates = []
        # Make a few duplicate bugs.
        for i in xrange(3):
            duplicates.append(self.factory.makeBug(title="bug-%d" % (i + 1)))

        # Pending messages exist for the bug creation.
        self.assertEqual(4, self._get_pending().count())
        self.assertEqual(0, self._get_deferred().count())

        previous_dup = None
        for dup in duplicates:
            # Make a few subscribers.
            self._add_subscribers(dup, 3)
            if previous_dup is not None:
                with person_logged_in(previous_dup.owner):
                    previous_dup.markAsDuplicate(dup)
            previous_dup = dup

        # Pending messages are still all from bug creation.
        # Only one deferred notification has been created, since notices for
        # the primary bug are not deferred and are created by the calling
        # process (browser or API).
        self.assertEqual(4, self._get_pending().count())
        self.assertEqual(1, self._get_deferred().count())

        with person_logged_in(bug.owner):
            previous_dup.markAsDuplicate(bug)

        # Now there are two new deferred messages, for the duplicates to the
        # last bug.
        self.assertEqual(4, self._get_pending().count())
        self.assertEqual(3, self._get_deferred().count())

        # The method for retrieving deferred notification reports them all.
        deferred = getUtility(IBugNotificationSet).getDeferredNotifications()
        self.assertEqual(3, deferred.count())

    def test_get_subscribers_from_duplicates_with_private_team(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product)
        dupe_bug = self.factory.makeBug()
        member = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=member, visibility=PersonVisibility.PRIVATE)
        with person_logged_in(member):
            dupe_bug.subscribe(team, member)
            dupe_bug.markAsDuplicate(bug)
        self.assertTrue(team in bug.getSubscribersFromDuplicates())

    def test_subscribe_with_level(self):
        # It's possible to subscribe to a bug at a different
        # BugNotificationLevel by passing a `level` parameter to
        # subscribe().
        bug = self.factory.makeBug()
        for level in BugNotificationLevel.items:
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                subscription = bug.subscribe(
                    subscriber, subscriber, level=level)
            self.assertEqual(level, subscription.bug_notification_level)

    def test_resubscribe_with_level(self):
        # If you pass a new level to subscribe with an existing subscription,
        # the level is set on the existing subscription.
        bug = self.factory.makeBug()
        subscriber = self.factory.makePerson()
        levels = list(BugNotificationLevel.items)
        with person_logged_in(subscriber):
            subscription = bug.subscribe(
                subscriber, subscriber, level=levels[-1])
        for level in levels:
            with person_logged_in(subscriber):
                bug.subscribe(subscriber, subscriber, level=level)
            self.assertEqual(level, subscription.bug_notification_level)

    def test_get_direct_subscribers_with_level(self):
        # It's possible to pass a level parameter to
        # getDirectSubscribers() to filter the subscribers returned.
        # When a `level` is passed to getDirectSubscribers(), the
        # subscribers returned will be those of that level of
        # subscription or higher.
        bug = self.factory.makeBug()
        # We unsubscribe the bug's owner because if we don't there will
        # be two COMMENTS-level subscribers.
        with person_logged_in(bug.owner):
            bug.unsubscribe(bug.owner, bug.owner)
        reversed_levels = sorted(
            BugNotificationLevel.items, reverse=True)
        subscribers = []
        for level in reversed_levels:
            subscriber = self.factory.makePerson()
            subscribers.append(subscriber)
            with person_logged_in(subscriber):
                bug.subscribe(subscriber, subscriber, level=level)
            direct_subscribers = bug.getDirectSubscribers(level=level)

            # All the previous subscribers will be included because
            # their level of subscription is such that they also receive
            # notifications at the current level.
            self.assertEqual(
                set(subscribers), set(direct_subscribers),
                "Subscribers did not match expected value.")

    def test_get_direct_subscribers_default_level(self):
        # If no `level` parameter is passed to getDirectSubscribers(),
        # the assumed `level` is BugNotification.LIFECYCLE.
        bug = self.factory.makeBug()
        # We unsubscribe the bug's owner because if we don't there will
        # be two COMMENTS-level subscribers.
        with person_logged_in(bug.owner):
            bug.unsubscribe(bug.owner, bug.owner)
        subscribers = []
        for level in BugNotificationLevel.items:
            subscriber = self.factory.makePerson()
            subscribers.append(subscriber)
            with person_logged_in(subscriber):
                bug.subscribe(subscriber, subscriber, level=level)

        # All the subscribers should be returned by
        # getDirectSubscribers() because it defaults to returning
        # subscribers at level LIFECYCLE, which everything is higher than.
        direct_subscribers = bug.getDirectSubscribers()
        self.assertEqual(
            set(subscribers), set(direct_subscribers),
            "Subscribers did not match expected value.")

    def test_get_direct_subscribers_with_details_other_subscriber(self):
        # getDirectSubscribersWithDetails() returns
        # Person and BugSubscription records in one go as well as the
        # BugSubscription.subscribed_by person.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            # Unsubscribe bug owner so it doesn't taint the result.
            bug.unsubscribe(bug.owner, bug.owner)
        subscriber = self.factory.makePerson()
        subscribee = self.factory.makePerson()
        with person_logged_in(subscriber):
            subscription = bug.subscribe(
                subscribee, subscriber, level=BugNotificationLevel.LIFECYCLE)
        self.assertContentEqual(
            [(subscribee, subscriber, subscription)],
            bug.getDirectSubscribersWithDetails())

    def test_get_direct_subscribers_with_details_self_subscribed(self):
        # getDirectSubscribersWithDetails() returns
        # Person and BugSubscription records in one go as well as the
        # BugSubscription.subscribed_by person.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            # Unsubscribe bug owner so it doesn't taint the result.
            bug.unsubscribe(bug.owner, bug.owner)
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            subscription = bug.subscribe(
                subscriber, subscriber, level=BugNotificationLevel.LIFECYCLE)
        self.assertContentEqual(
            [(subscriber, subscriber, subscription)],
            bug.getDirectSubscribersWithDetails())

    def test_get_direct_subscribers_with_details_mute_excludes(self):
        # getDirectSubscribersWithDetails excludes muted subscriptions.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            # Unsubscribe bug owner so it doesn't taint the result.
            bug.unsubscribe(bug.owner, bug.owner)
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            bug.subscribe(
                subscriber, subscriber, level=BugNotificationLevel.LIFECYCLE)
            bug.mute(subscriber, subscriber)

        self.assertContentEqual(
            [], bug.getDirectSubscribersWithDetails())

    def test_subscribers_from_dupes_uses_level(self):
        # When getSubscribersFromDuplicates() is passed a `level`
        # parameter it will include only subscribers subscribed to
        # duplicates at that BugNotificationLevel or higher.
        bug = self.factory.makeBug()
        duplicate_bug = self.factory.makeBug()
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(bug)
            # We unsubscribe the owner of the duplicate to avoid muddling
            # the results returned by getSubscribersFromDuplicates()
            duplicate_bug.unsubscribe(
                duplicate_bug.owner, duplicate_bug.owner)
        for level in BugNotificationLevel.items:
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                duplicate_bug.subscribe(subscriber, subscriber, level=level)
            # Only the most recently subscribed person will be included
            # because the previous subscribers are subscribed at a lower
            # level.
            self.assertEqual(
                (subscriber,),
                bug.getSubscribersFromDuplicates(level=level))

    def test_subscribers_from_dupes_overrides_using_level(self):
        # Bug.getSubscribersFromDuplicates() does not return subscribers
        # who also have a direct subscription to the master bug provided
        # that the subscription to the master bug is of the same level
        # or higher as the subscription to the duplicate.
        bug = self.factory.makeBug()
        duplicate_bug = self.factory.makeBug()
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(bug)
            # We unsubscribe the owner of the duplicate to avoid muddling
            # the results returned by getSubscribersFromDuplicates()
            duplicate_bug.unsubscribe(
                duplicate_bug.owner, duplicate_bug.owner)
        subscriber = self.factory.makePerson()
        with person_logged_in(subscriber):
            bug.subscribe(
                subscriber, subscriber, level=BugNotificationLevel.LIFECYCLE)
            duplicate_bug.subscribe(
                subscriber, subscriber, level=BugNotificationLevel.METADATA)
        duplicate_subscribers = bug.getSubscribersFromDuplicates()
        self.assertTrue(
            subscriber not in duplicate_subscribers,
            "Subscriber should not be in duplicate_subscribers.")

    def test_getSubscriptionInfo(self):
        # getSubscriptionInfo() returns a BugSubscriptionInfo object.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            info = bug.getSubscriptionInfo()
        self.assertIsInstance(info, BugSubscriptionInfo)
        self.assertEqual(bug, info.bug)
        self.assertEqual(BugNotificationLevel.LIFECYCLE, info.level)
        # A level can also be specified.
        with person_logged_in(bug.owner):
            info = bug.getSubscriptionInfo(BugNotificationLevel.METADATA)
        self.assertEqual(BugNotificationLevel.METADATA, info.level)

    def test_getVisibleLinkedBranches_doesnt_rtn_inaccessible_branches(self):
        # If a Bug has branches linked to it that the current user
        # cannot access, those branches will not be returned in its
        # linked_branches property.
        bug = self.factory.makeBug()
        private_branch_owner = self.factory.makePerson()
        private_branch = self.factory.makeBranch(
            owner=private_branch_owner,
            information_type=InformationType.USERDATA)
        with person_logged_in(private_branch_owner):
            bug.linkBranch(private_branch, private_branch.registrant)
        public_branch_owner = self.factory.makePerson()
        public_branches = [
            self.factory.makeBranch() for i in range(4)]
        with person_logged_in(public_branch_owner):
            for public_branch in public_branches:
                bug.linkBranch(public_branch, public_branch.registrant)
        with StormStatementRecorder() as recorder:
            linked_branches = [
                bug_branch.branch for bug_branch in
                bug.getVisibleLinkedBranches(user=public_branch_owner)]
            # We check that the query count is low, since that's
            # part of the point of the way that linked_branches is
            # implemented. If we try eager-loading all the linked
            # branches the query count jumps up by 6, which is not
            # what we want.
            self.assertThat(recorder, HasQueryCount(LessThan(7)))
        self.assertContentEqual(public_branches, linked_branches)
        self.assertNotIn(private_branch, linked_branches)

    def test_getDirectSubscribers_with_recipients_query_count(self):
        # getDirectSubscribers() uses a constant number of queries when given
        # a recipients argument regardless of the number of subscribers.
        bug = self.factory.makeBug()

        def create_subscriber():
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                bug.subscribe(subscriber, subscriber)

        def get_subscribers():
            recipients = BugNotificationRecipients()
            subs = bug.getDirectSubscribers(recipients=recipients)
            list(subs)  # Ensure they're pulled.

        recorder1, recorder2 = record_two_runs(
            get_subscribers, create_subscriber, 3)
        self.assertThat(
            recorder2, HasQueryCount(Equals(recorder1.count)))

    def test_getSubscribersFromDuplicates_with_recipients_query_count(self):
        # getSubscribersFromDuplicates() uses a constant number of queries
        # when given a recipients argument regardless of the number of
        # subscribers.
        bug = self.factory.makeBug()
        duplicate_bug = self.factory.makeBug()
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(bug)

        def create_subscriber():
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                duplicate_bug.subscribe(subscriber, subscriber)

        def get_subscribers():
            recipients = BugNotificationRecipients()
            subs = bug.getSubscribersFromDuplicates(recipients=recipients)
            list(subs)  # Ensure they're pulled.

        recorder1, recorder2 = record_two_runs(
            get_subscribers, create_subscriber, 3)
        self.assertThat(
            recorder2, HasQueryCount(Equals(recorder1.count)))

    def test_getAlsoNotifiedSubscribers_with_recipients_query_count(self):
        # getAlsoNotifiedSubscribers() uses a constant number of queries when
        # given a recipients argument regardless of the number of subscribers.
        bug = self.factory.makeBug()

        def create_stuff():
            # Create a new bugtask, set its assignee, set its pillar's
            # official_malone=True, and subscribe someone to its target.
            bugtask = self.factory.makeBugTask(bug=bug)
            with person_logged_in(bugtask.owner):
                bugtask.transitionToAssignee(bugtask.owner)
            with person_logged_in(bugtask.pillar.owner):
                bugtask.pillar.official_malone = True
            subscriber = self.factory.makePerson()
            with person_logged_in(subscriber):
                bugtask.target.addSubscription(
                    subscriber, subscriber)

        def get_subscribers():
            recipients = BugNotificationRecipients()
            subs = bug.getAlsoNotifiedSubscribers(recipients=recipients)
            list(subs)  # Ensure they're pulled.

        recorder1, recorder2 = record_two_runs(
            get_subscribers, create_stuff, 3)
        self.assertThat(
            recorder2, HasQueryCount(Equals(recorder1.count)))

    def test_newMessage_default(self):
        # Adding a bug message notifies that is was created.
        bug = self.factory.makeBug()
        login_person(bug.owner)
        with EventRecorder() as recorder:
            bug.newMessage(owner=bug.owner)
            self.assertEqual(1, len(recorder.events))
            self.assertIsInstance(recorder.events[0], ObjectCreatedEvent)

    def test_newMessage_send_notification_false(self):
        # Notifications about new messages can be supressed.
        bug = self.factory.makeBug()
        login_person(bug.owner)
        with EventRecorder() as recorder:
            bug.newMessage(owner=bug.owner, send_notifications=False)
            self.assertEqual(0, len(recorder.events))


class TestBugPrivateAndSecurityRelatedUpdatesProject(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_setPrivate_subscribes_person_who_makes_bug_private(self):
        # When setPrivate(True) is called on a bug, the person who is
        # marking the bug private is subscribed to the bug.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            bug.setPrivate(True, person)
            self.assertTrue(bug.personIsDirectSubscriber(person))

    def test_setPrivate_does_not_subscribe_member_of_subscribed_team(self):
        # When setPrivate(True) is called on a bug, the person who is
        # marking the bug private will not be subscribed if they're
        # already a member of a team which is a direct subscriber and
        # maintains access after transition.
        bug = self.factory.makeBug()
        person = self.factory.makePerson(name='teamowner')
        team = self.factory.makeTeam(owner=person, name='team')
        artifact = self.factory.makeAccessArtifact(bug)
        self.factory.makeAccessArtifactGrant(artifact, team)
        with person_logged_in(person):
            bug.subscribe(team, person)
            bug.setPrivate(True, person)
            self.assertFalse(bug.personIsDirectSubscriber(person))

    def createBugTasksAndSubscribers(self, private_security_related=False):
        # Used with the various setPrivateAndSecurityRelated tests to create
        # a bug and add some initial subscribers.
        bug_owner = self.factory.makePerson(name='bugowner')
        bug_supervisor = self.factory.makePerson(
            name='bugsupervisor', email='bugsupervisor@example.com')
        product_owner = self.factory.makePerson(name='productowner')
        product_driver = self.factory.makePerson(name='productdriver')
        bug_product = self.factory.makeProduct(
            owner=product_owner, bug_supervisor=bug_supervisor,
            driver=product_driver)
        bug = self.factory.makeBug(owner=bug_owner, target=bug_product)
        with person_logged_in(bug_owner):
            if private_security_related:
                information_type = InformationType.PRIVATESECURITY
            else:
                information_type = InformationType.PUBLIC
            bug.transitionToInformationType(information_type, bug_owner)
        owner_a = self.factory.makePerson(name='ownera')
        product_series_a = self.factory.makeProductSeries(
            product=bug_product, owner=owner_a)
        owner_b = self.factory.makePerson(name='ownerb')
        product_series_b = self.factory.makeProductSeries(
            product=bug_product, owner=owner_b)
        bugtask_a = self.factory.makeBugTask(bug=bug, target=product_series_a)
        bugtask_b = self.factory.makeBugTask(bug=bug, target=product_series_b)
        naked_bugtask_a = removeSecurityProxy(bugtask_a)
        naked_bugtask_b = removeSecurityProxy(bugtask_b)
        naked_default_bugtask = removeSecurityProxy(bug).default_bugtask
        return (bug, bug_owner, naked_bugtask_a, naked_bugtask_b,
                naked_default_bugtask)

    def test_transition_to_PRIVATESECURITY_information_type(self):
        # When a bug is marked as PRIVATESECURITY, the direct subscribers
        # should include:
        # - the bug reporter
        # - the person changing the state
        # - and bug/pillar owners, drivers if they are already subscribed

        (bug, bug_owner, bugtask_a, bugtask_b, default_bugtask) = (
            self.createBugTasksAndSubscribers())
        initial_subscribers = set((
            self.factory.makePerson(name='subscriber'), bugtask_a.owner,
            bug_owner, bugtask_a.pillar.driver))
        initial_subscribers.update(bug.getDirectSubscribers())

        with person_logged_in(bug_owner):
            for subscriber in initial_subscribers:
                bug.subscribe(subscriber, bug_owner)
            who = self.factory.makePerson(name='who')
            bug.transitionToInformationType(
                InformationType.PRIVATESECURITY, who=who)
            subscribers = bug.getDirectSubscribers(filter_visible=True)
        expected_subscribers = set((
            default_bugtask.pillar.driver, bug_owner, who))
        self.assertContentEqual(expected_subscribers, subscribers)

    def test_transition_to_USERDATA_information_type(self):
        # When a bug is marked as USERDATA, the direct subscribers should
        # include:
        # - the bug reporter
        # - the person changing the state
        # - and bug/pillar owners, drivers if they are already subscribed

        (bug, bug_owner, bugtask_a, bugtask_b, default_bugtask) = (
                self.createBugTasksAndSubscribers())
        initial_subscribers = set((
            self.factory.makePerson(name='subscriber'), bug_owner,
            bugtask_a.pillar.driver))

        with person_logged_in(bug_owner):
            for subscriber in initial_subscribers:
                bug.subscribe(subscriber, bug_owner)
            who = self.factory.makePerson(name='who')
            bug.transitionToInformationType(InformationType.USERDATA, who)
            subscribers = bug.getDirectSubscribers(filter_visible=True)
        expected_subscribers = set((
            default_bugtask.pillar.bug_supervisor,
            default_bugtask.pillar.driver,
            bug_owner,
            who))
        self.assertContentEqual(expected_subscribers, subscribers)

    def test_transition_to_PUBLICSECURITY_information_type(self):
        # When a security bug is unembargoed, direct subscribers should
        # include:
        # - the bug reporter
        # - and bug/pillar owners, drivers if they are already subscribed

        (bug, bug_owner, bugtask_a, bugtask_b, default_bugtask) = (
            self.createBugTasksAndSubscribers(private_security_related=True))
        initial_subscribers = set((
            self.factory.makePerson(), bug_owner, bugtask_a.pillar.driver,
            bugtask_a.pillar.bug_supervisor))

        with person_logged_in(bug_owner):
            for subscriber in initial_subscribers:
                bug.subscribe(subscriber, bug_owner)
            who = self.factory.makePerson(name='who')
            bug.transitionToInformationType(
                InformationType.PUBLICSECURITY, who)
            subscribers = bug.getDirectSubscribers()
        expected_subscribers = set((default_bugtask.pillar.driver, bug_owner))
        expected_subscribers.update(initial_subscribers)
        self.assertContentEqual(expected_subscribers, subscribers)

    def test_transition_to_PUBLIC_information_type(self):
        # Subscriptions aren't altered when a bug is transitioned to the
        # PUBLIC information type.

        (bug, bug_owner, bugtask_a, bugtask_b, default_bugtask) = (
            self.createBugTasksAndSubscribers(private_security_related=True))
        initial_subscribers = set((
            self.factory.makePerson(name='subscriber'), bug_owner,
            bugtask_a.pillar.driver))

        with person_logged_in(bug_owner):
            for subscriber in initial_subscribers:
                bug.subscribe(subscriber, bug_owner)
            who = self.factory.makePerson(name='who')
            subscribers_before_public = set(bug.getDirectSubscribers())
            bug.transitionToInformationType(InformationType.PUBLIC, who)
        subscribers_after_public = set(bug.getDirectSubscribers())
        self.assertContentEqual(
            subscribers_before_public,
            subscribers_after_public)

    def test_setPillarOwnerSubscribedIfNoBugSupervisor(self):
        # The pillar owner is subscribed if the bug supervisor is not set and
        # the bug is marked as USERDATA.

        bug_owner = self.factory.makePerson(name='bugowner')
        bug = self.factory.makeBug(owner=bug_owner)
        with person_logged_in(bug_owner):
            who = self.factory.makePerson()
            bug.transitionToInformationType(InformationType.USERDATA, who)
            subscribers = bug.getDirectSubscribers()
        naked_bugtask = removeSecurityProxy(bug).default_bugtask
        self.assertContentEqual(
            set((naked_bugtask.pillar.owner, bug_owner, who)),
            subscribers)

    def test_structural_bug_supervisor_becomes_direct_on_private(self):
        # If a bug supervisor has a structural subscription to the bug, and
        # the bug is marked as private, the supervisor should get a direct
        # subscription. Otherwise they should be removed, per other tests.
        bug_supervisor = self.factory.makePerson()
        product = self.factory.makeProduct(bug_supervisor=bug_supervisor)
        bug_owner = self.factory.makePerson()
        bug = self.factory.makeBug(owner=bug_owner, target=product)
        with person_logged_in(product.owner):
            product.addSubscription(bug_supervisor, bug_supervisor)

        self.assertFalse(bug_supervisor in bug.getDirectSubscribers())
        with person_logged_in(bug_owner):
            who = self.factory.makePerson(name="who")
            bug.transitionToInformationType(InformationType.USERDATA, who)
        self.assertTrue(bug_supervisor in bug.getDirectSubscribers())


class TestBugPrivacy(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_multipillar_proprietary_bugs_disallowed(self):
        # A multi-pillar bug cannot be made proprietary.
        p1 = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PUBLIC_OR_PROPRIETARY)
        p2 = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PUBLIC_OR_PROPRIETARY)
        bug = self.factory.makeBug(target=p1)
        self.factory.makeBugTask(bug=bug, target=p2)
        login_person(bug.owner)
        self.assertRaisesWithContent(
            CannotChangeInformationType,
            "Proprietary bugs can only affect one project.",
            bug.transitionToInformationType,
            InformationType.PROPRIETARY, bug.owner)
        bug.transitionToInformationType(InformationType.USERDATA, bug.owner)
        self.assertTrue(bug.private)

    def test_bug_information_type(self):
        # Bugs have the correct corresponding information type.
        # Public security bugs are currently untested since it is impossible
        # to create one at the moment.
        bug = self.factory.makeBug()
        private_bug = self.factory.makeBug(
            information_type=InformationType.USERDATA)
        private_sec_bug = self.factory.makeBug(
            information_type=InformationType.PRIVATESECURITY)
        mapping = (
            (bug, InformationType.PUBLIC),
            (private_bug, InformationType.USERDATA),
            (private_sec_bug, InformationType.PRIVATESECURITY),
            )
        [self.assertEqual(m[1], m[0].information_type) for m in mapping]

    def test_accesspolicyartifacts_updated(self):
        # transitionToTarget updates the AccessPolicyArtifacts related
        # to the bug.
        bug = self.factory.makeBug(
            information_type=InformationType.PRIVATESECURITY)

        with admin_logged_in():
            product = bug.default_bugtask.product
            bug.transitionToInformationType(
                InformationType.USERDATA, bug.owner)

        [policy] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        self.assertContentEqual([policy], get_policies_for_artifact(bug))

    def test_private_to_public_information_type(self):
        # A private bug transitioning to public has the correct information
        # type.
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            information_type=InformationType.USERDATA, owner=owner)
        with person_logged_in(owner):
            bug.setPrivate(False, owner)
        self.assertEqual(InformationType.PUBLIC, bug.information_type)

    def test_private_sec_to_public_sec_information_type(self):
        # A private security bug transitioning to public security has the
        # correct information type.
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            information_type=InformationType.PRIVATESECURITY, owner=owner)
        with person_logged_in(owner):
            bug.setPrivate(False, owner)
        self.assertEqual(
            InformationType.PUBLICSECURITY, bug.information_type)

    def test_private_sec_to_public_information_type(self):
        # A private security bug transitioning to public has the correct
        # information type.
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            information_type=InformationType.PRIVATESECURITY, owner=owner)
        with person_logged_in(owner):
            bug.transitionToInformationType(InformationType.PUBLIC, owner)
        self.assertEqual(InformationType.PUBLIC, bug.information_type)

    def test_public_to_private_information_type(self):
        # A public bug transitioning to private has the correct information
        # type.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            bug.setPrivate(True, bug.owner)
        self.assertEqual(InformationType.USERDATA, bug.information_type)

    def test__reconcileAccess_handles_all_targets(self):
        # _reconcileAccess gets the pillar from any task
        # type.
        product = self.factory.makeProduct()
        productseries = self.factory.makeProductSeries()
        distro = self.factory.makeDistribution()
        distroseries = self.factory.makeDistroSeries()
        dsp = self.factory.makeDistributionSourcePackage()
        sp = self.factory.makeSourcePackage()

        targets = [product, productseries, distro, distroseries, dsp, sp]
        pillars = [
            product, productseries.product, distro, distroseries.distribution,
            dsp.distribution, sp.distribution]

        bug = self.factory.makeBug(
            target=product, information_type=InformationType.USERDATA)
        for target in targets[1:]:
            self.factory.makeBugTask(bug, target=target)
        [artifact] = getUtility(IAccessArtifactSource).ensure([bug])
        getUtility(IAccessPolicyArtifactSource).deleteByArtifact([artifact])
        removeSecurityProxy(bug)._reconcileAccess()
        self.assertContentEqual(
            getUtility(IAccessPolicySource).find(
                (pillar, InformationType.USERDATA) for pillar in pillars),
            get_policies_for_artifact(bug))

    def test_getAllowedInformationTypes(self):
        # A bug's information type must be in the intersection of its
        # pillars' permitted information types. Currently that means
        # it's just one of the usual four.
        self.assertContentEqual(
            [InformationType.PUBLIC, InformationType.PUBLICSECURITY,
             InformationType.PRIVATESECURITY, InformationType.USERDATA],
            self.factory.makeBug().getAllowedInformationTypes(None))

    def test_getAllowedInformationTypes_includes_current(self):
        # A bug's allowed information types must include its current
        # information type even if said type is not in the allowed types.
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            target=product, information_type=InformationType.PUBLICSECURITY)
        removeSecurityProxy(product).bug_sharing_policy = (
            BugSharingPolicy.FORBIDDEN)
        self.assertContentEqual(
            [InformationType.PUBLICSECURITY],
            bug.getAllowedInformationTypes(None))

    def test_transitionToInformationType_respects_allowed_proprietary(self):
        # transitionToInformationType rejects types that aren't allowed
        # for the bug.
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            bug = self.factory.makeBug(target=product)
            self.assertRaisesWithContent(
                CannotChangeInformationType, "Forbidden by project policy.",
                bug.transitionToInformationType,
                InformationType.PROPRIETARY, bug.owner)

    def test_transitionToInformationType_respects_allowed_public(self):
        # transitionToInformationType rejects types that aren't allowed
        # for the bug.
        product = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY)
        with person_logged_in(product.owner):
            bug = self.factory.makeBug(target=product)
            self.assertRaisesWithContent(
                CannotChangeInformationType, "Forbidden by project policy.",
                bug.transitionToInformationType,
                InformationType.PUBLIC, bug.owner)


class TestBugPrivateAndSecurityRelatedUpdatesSpecialCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_transition_special_cased_for_ubuntu(self):
        # When a bug on ubuntu is transitioned to USERDATA from
        # PRIVATESECURITY, the bug supervisor is not subscribed, and the
        # bug's subscribers do not change.
        # This is to protect ubuntu's workflow, which differs from the
        # Launchpad norm.
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        ubuntu = removeSecurityProxy(ubuntu)
        ubuntu.bug_supervisor = self.factory.makePerson(name='supervisor')
        bug = self.factory.makeBug(
            information_type=InformationType.PRIVATESECURITY,
            target=ubuntu)
        bug = removeSecurityProxy(bug)
        initial_subscribers = bug.getDirectSubscribers()
        self.assertTrue(ubuntu.bug_supervisor not in initial_subscribers)
        bug.transitionToInformationType(
            InformationType.USERDATA, who=bug.owner)
        subscribers = bug.getDirectSubscribers()
        self.assertContentEqual(initial_subscribers, subscribers)
        ubuntu.bug_supervisor = None


class TestBugActivityMethods(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugActivityMethods, self).setUp()
        self.now = datetime.now(UTC)

    def _makeActivityForBug(self, bug, activity_ages):
        with person_logged_in(bug.owner):
            for days_ago in activity_ages:
                activity = BugTitleChange(
                    when=self.now - timedelta(days=days_ago),
                    person=bug.owner, what_changed='title',
                    old_value='foo', new_value='baz')
                bug.addChange(activity)

    def test_getActivityForDateRange_returns_items_between_dates(self):
        # Bug.getActivityForDateRange() will return the activity for
        # that bug that falls within a given date range.
        bug = self.factory.makeBug(
            date_created=self.now - timedelta(days=365))
        self._makeActivityForBug(bug, activity_ages=[200, 100])
        start_date = self.now - timedelta(days=250)
        end_date = self.now - timedelta(days=150)
        activity = bug.getActivityForDateRange(
            start_date=start_date, end_date=end_date)
        expected_activity = bug.activity[1:2]
        self.assertContentEqual(expected_activity, activity)

    def test_getActivityForDateRange_is_inclusive_of_date_limits(self):
        # Bug.getActivityForDateRange() will return the activity that
        # falls on the start_ and end_ dates.
        bug = self.factory.makeBug(
            date_created=self.now - timedelta(days=365))
        self._makeActivityForBug(bug, activity_ages=[300, 200, 100])
        start_date = self.now - timedelta(days=300)
        end_date = self.now - timedelta(days=100)
        activity = bug.getActivityForDateRange(
            start_date=start_date, end_date=end_date)
        expected_activity = bug.activity[1:]
        self.assertContentEqual(expected_activity, activity)


class TestBugAutoConfirmation(TestCaseWithFactory):
    """Tests for auto confirming bugs"""

    layer = DatabaseFunctionalLayer

    def test_shouldConfirmBugtasks_initial_False(self):
        # After a bug is created, only one person is affected, and we should
        # not try to confirm bug tasks.
        bug = self.factory.makeBug()
        self.assertFalse(bug.shouldConfirmBugtasks())

    def test_shouldConfirmBugtasks_after_another_positively_affected(self):
        # We should confirm bug tasks if the number of affected users is
        # more than one.
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            bug.markUserAffected(person)
        self.assertTrue(bug.shouldConfirmBugtasks())

    def test_shouldConfirmBugtasks_after_another_persons_dupe(self):
        # We should confirm bug tasks if someone else files a dupe.
        bug = self.factory.makeBug()
        duplicate_bug = self.factory.makeBug()
        with person_logged_in(duplicate_bug.owner):
            duplicate_bug.markAsDuplicate(bug)
        self.assertTrue(bug.shouldConfirmBugtasks())

    def test_shouldConfirmBugtasks_after_same_persons_dupe_False(self):
        # We should not confirm bug tasks if same person files a dupe.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            duplicate_bug = self.factory.makeBug(owner=bug.owner)
            duplicate_bug.markAsDuplicate(bug)
        self.assertFalse(bug.shouldConfirmBugtasks())

    def test_shouldConfirmBugtasks_honors_negatively_affected(self):
        # We should confirm bug tasks if the number of affected users is
        # more than one.
        bug = self.factory.makeBug()
        with person_logged_in(bug.owner):
            bug.markUserAffected(bug.owner, False)
        person = self.factory.makePerson()
        with person_logged_in(person):
            bug.markUserAffected(person)
        self.assertFalse(bug.shouldConfirmBugtasks())

    def test_markUserAffected_autoconfirms(self):
        # markUserAffected will auto confirm if appropriate.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            bug = self.factory.makeBug()
            person = self.factory.makePerson()
            with person_logged_in(person):
                bug.markUserAffected(person)
            self.assertEqual(BugTaskStatus.CONFIRMED, bug.bugtasks[0].status)

    def test_markUserAffected_does_not_autoconfirm_wrongly(self):
        # markUserAffected will not auto confirm if incorrect.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            bug = self.factory.makeBug()
            person = self.factory.makePerson()
            with person_logged_in(bug.owner):
                bug.markUserAffected(bug.owner, False)
            with person_logged_in(person):
                bug.markUserAffected(person)
            self.assertEqual(BugTaskStatus.NEW, bug.bugtasks[0].status)

    def test_markAsDuplicate_autoconfirms(self):
        # markAsDuplicate will auto confirm if appropriate.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            bug = self.factory.makeBug()
            duplicate_bug = self.factory.makeBug()
            with person_logged_in(duplicate_bug.owner):
                duplicate_bug.markAsDuplicate(bug)
            self.assertEqual(BugTaskStatus.CONFIRMED, bug.bugtasks[0].status)

    def test_markAsDuplicate_does_not_autoconfirm_wrongly(self):
        # markAsDuplicate will not auto confirm if incorrect.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            bug = self.factory.makeBug()
            with person_logged_in(bug.owner):
                duplicate_bug = self.factory.makeBug(owner=bug.owner)
                duplicate_bug.markAsDuplicate(bug)
            self.assertEqual(BugTaskStatus.NEW, bug.bugtasks[0].status)
