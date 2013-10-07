# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the bugsubscription module."""

__metaclass__ = type

from storm.store import Store
from zope.security.interfaces import Unauthorized
from zope.security.proxy import ProxyFactory

from lp.app.enums import InformationType
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.model.bugsubscriptionfilter import (
    BugSubscriptionFilter,
    BugSubscriptionFilterImportance,
    BugSubscriptionFilterInformationType,
    BugSubscriptionFilterStatus,
    BugSubscriptionFilterTag,
    )
from lp.bugs.model.structuralsubscription import StructuralSubscription
from lp.services import searchbuilder
from lp.services.database.interfaces import IStore
from lp.testing import (
    anonymous_logged_in,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugSubscriptionFilter(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionFilter, self).setUp()
        self.target = self.factory.makeProduct()
        self.subscriber = self.target.owner
        login_person(self.subscriber)
        self.subscription = self.target.addBugSubscription(
            self.subscriber, self.subscriber)

    def test_basics(self):
        """Test the basic operation of `BugSubscriptionFilter` objects."""
        # Create.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.structural_subscription = self.subscription
        bug_subscription_filter.bug_notification_level = (
            BugNotificationLevel.METADATA)
        bug_subscription_filter.find_all_tags = True
        bug_subscription_filter.include_any_tags = True
        bug_subscription_filter.exclude_any_tags = True
        bug_subscription_filter.other_parameters = u"foo"
        bug_subscription_filter.description = u"bar"
        # Flush and reload.
        IStore(bug_subscription_filter).flush()
        IStore(bug_subscription_filter).reload(bug_subscription_filter)
        # Check.
        self.assertIsNot(None, bug_subscription_filter.id)
        self.assertEqual(
            self.subscription.id,
            bug_subscription_filter.structural_subscription_id)
        self.assertEqual(
            self.subscription,
            bug_subscription_filter.structural_subscription)
        self.assertIs(True, bug_subscription_filter.find_all_tags)
        self.assertIs(True, bug_subscription_filter.include_any_tags)
        self.assertIs(True, bug_subscription_filter.exclude_any_tags)
        self.assertEqual(
            BugNotificationLevel.METADATA,
            bug_subscription_filter.bug_notification_level)
        self.assertEqual(u"foo", bug_subscription_filter.other_parameters)
        self.assertEqual(u"bar", bug_subscription_filter.description)

    def test_description(self):
        """Test the description property."""
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.description = u"foo"
        self.assertEqual(u"foo", bug_subscription_filter.description)

    def test_defaults(self):
        """Test the default values of `BugSubscriptionFilter` objects."""
        # Create.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.structural_subscription = self.subscription
        # Check.
        self.assertEqual(
            BugNotificationLevel.COMMENTS,
            bug_subscription_filter.bug_notification_level)
        self.assertIs(False, bug_subscription_filter.find_all_tags)
        self.assertIs(False, bug_subscription_filter.include_any_tags)
        self.assertIs(False, bug_subscription_filter.exclude_any_tags)
        self.assertIs(None, bug_subscription_filter.other_parameters)
        self.assertIs(None, bug_subscription_filter.description)

    def test_delete(self):
        """`BugSubscriptionFilter` objects can be deleted.

        Child objects - like `BugSubscriptionFilterTags` - will also be
        deleted.
        """
        # This is a second filter for the subscription.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.structural_subscription = self.subscription
        bug_subscription_filter.importances = [BugTaskImportance.LOW]
        bug_subscription_filter.statuses = [BugTaskStatus.NEW]
        bug_subscription_filter.tags = [u"foo"]
        IStore(bug_subscription_filter).flush()
        self.assertIsNot(None, Store.of(bug_subscription_filter))
        # Delete.
        bug_subscription_filter.delete()
        IStore(bug_subscription_filter).flush()
        # It doesn't exist in the database anymore.
        self.assertIs(None, Store.of(bug_subscription_filter))

    def test_delete_final(self):
        # If you delete the final remaining `BugSubscriptionFilter`, the
        # parent structural subscription will also be deleted.
        bug_subscription_filter = self.subscription.bug_filters.one()
        bug_subscription_filter.bug_notification_level = (
            BugNotificationLevel.LIFECYCLE)
        bug_subscription_filter.find_all_tags = True
        bug_subscription_filter.exclude_any_tags = True
        bug_subscription_filter.include_any_tags = True
        bug_subscription_filter.description = u"Description"
        bug_subscription_filter.importances = [BugTaskImportance.LOW]
        bug_subscription_filter.statuses = [BugTaskStatus.NEW]
        bug_subscription_filter.tags = [u"foo"]
        IStore(bug_subscription_filter).flush()
        self.assertIsNot(None, Store.of(bug_subscription_filter))

        # Delete.
        bug_subscription_filter.delete()
        IStore(bug_subscription_filter).flush()

        # It is deleted from the database.  Note that the object itself has
        # not been updated because Storm called the SQL deletion directly,
        # so we have to be a bit more verbose to show that it is gone.
        self.assertIs(
            None,
            IStore(bug_subscription_filter).find(
                BugSubscriptionFilter,
                BugSubscriptionFilter.id == bug_subscription_filter.id).one())
        # The structural subscription is gone too.
        self.assertIs(
            None,
            IStore(self.subscription).find(
                StructuralSubscription,
                StructuralSubscription.id == self.subscription.id).one())

    def test_statuses(self):
        # The statuses property is a frozenset of the statuses that are
        # filtered upon.
        bug_subscription_filter = BugSubscriptionFilter()
        self.assertEqual(frozenset(), bug_subscription_filter.statuses)

    def test_statuses_set(self):
        # Assigning any iterable to statuses updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.statuses = [
            BugTaskStatus.NEW, BugTaskStatus.INCOMPLETE]
        self.assertEqual(
            frozenset((BugTaskStatus.NEW, BugTaskStatus.INCOMPLETE)),
            bug_subscription_filter.statuses)
        # Assigning a subset causes the other status filters to be removed.
        bug_subscription_filter.statuses = [BugTaskStatus.NEW]
        self.assertEqual(
            frozenset((BugTaskStatus.NEW,)),
            bug_subscription_filter.statuses)

    def test_statuses_set_all(self):
        # Setting all statuses is normalized into setting no statuses.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.statuses = list(BugTaskStatus.items)
        self.assertEqual(frozenset(), bug_subscription_filter.statuses)

    def test_statuses_set_empty(self):
        # Assigning an empty iterable to statuses updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.statuses = []
        self.assertEqual(frozenset(), bug_subscription_filter.statuses)

    def test_importances(self):
        # The importances property is a frozenset of the importances that are
        # filtered upon.
        bug_subscription_filter = BugSubscriptionFilter()
        self.assertEqual(frozenset(), bug_subscription_filter.importances)

    def test_importances_set(self):
        # Assigning any iterable to importances updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.importances = [
            BugTaskImportance.HIGH, BugTaskImportance.LOW]
        self.assertEqual(
            frozenset((BugTaskImportance.HIGH, BugTaskImportance.LOW)),
            bug_subscription_filter.importances)
        # Assigning a subset causes the other importance filters to be
        # removed.
        bug_subscription_filter.importances = [BugTaskImportance.HIGH]
        self.assertEqual(
            frozenset((BugTaskImportance.HIGH,)),
            bug_subscription_filter.importances)

    def test_importances_set_all(self):
        # Setting all importances is normalized into setting no importances.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.importances = list(BugTaskImportance.items)
        self.assertEqual(frozenset(), bug_subscription_filter.importances)

    def test_importances_set_empty(self):
        # Assigning an empty iterable to importances updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.importances = []
        self.assertEqual(frozenset(), bug_subscription_filter.importances)

    def test_information_types(self):
        # The information_types property is a frozenset of the
        # information_types that are filtered upon.
        bug_subscription_filter = BugSubscriptionFilter()
        self.assertEqual(
            frozenset(), bug_subscription_filter.information_types)

    def test_information_types_set(self):
        # Assigning any iterable to information_types updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.information_types = [
            InformationType.PRIVATESECURITY, InformationType.USERDATA]
        self.assertEqual(
            frozenset((InformationType.PRIVATESECURITY,
                InformationType.USERDATA)),
            bug_subscription_filter.information_types)
        # Assigning a subset causes the other status filters to be removed.
        bug_subscription_filter.information_types = [
            InformationType.USERDATA]
        self.assertEqual(
            frozenset((InformationType.USERDATA,)),
            bug_subscription_filter.information_types)

    def test_information_types_set_all(self):
        # Setting all information_types is normalized into setting no
        # information_types.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.information_types = list(
            InformationType.items)
        self.assertEqual(
            frozenset(), bug_subscription_filter.information_types)

    def test_information_types_set_empty(self):
        # Assigning an empty iterable to information_types updates the
        # database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.information_types = []
        self.assertEqual(
            frozenset(), bug_subscription_filter.information_types)

    def test_tags(self):
        # The tags property is a frozenset of the tags that are filtered upon.
        bug_subscription_filter = BugSubscriptionFilter()
        self.assertEqual(frozenset(), bug_subscription_filter.tags)

    def test_tags_set(self):
        # Assigning any iterable to tags updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.tags = [u"foo", u"-bar"]
        self.assertEqual(
            frozenset((u"foo", u"-bar")),
            bug_subscription_filter.tags)
        # Assigning a subset causes the other tag filters to be removed.
        bug_subscription_filter.tags = [u"foo"]
        self.assertEqual(
            frozenset((u"foo",)),
            bug_subscription_filter.tags)

    def test_tags_set_empty(self):
        # Assigning an empty iterable to tags updates the database.
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.tags = []
        self.assertEqual(frozenset(), bug_subscription_filter.tags)

    def test_tags_set_wildcard(self):
        # Setting one or more wildcard tags may update include_any_tags or
        # exclude_any_tags.
        bug_subscription_filter = BugSubscriptionFilter()
        self.assertEqual(frozenset(), bug_subscription_filter.tags)
        self.assertFalse(bug_subscription_filter.include_any_tags)
        self.assertFalse(bug_subscription_filter.exclude_any_tags)

        bug_subscription_filter.tags = [u"*"]
        self.assertEqual(frozenset((u"*",)), bug_subscription_filter.tags)
        self.assertTrue(bug_subscription_filter.include_any_tags)
        self.assertFalse(bug_subscription_filter.exclude_any_tags)

        bug_subscription_filter.tags = [u"-*"]
        self.assertEqual(frozenset((u"-*",)), bug_subscription_filter.tags)
        self.assertFalse(bug_subscription_filter.include_any_tags)
        self.assertTrue(bug_subscription_filter.exclude_any_tags)

        bug_subscription_filter.tags = [u"*", u"-*"]
        self.assertEqual(
            frozenset((u"*", u"-*")), bug_subscription_filter.tags)
        self.assertTrue(bug_subscription_filter.include_any_tags)
        self.assertTrue(bug_subscription_filter.exclude_any_tags)

        bug_subscription_filter.tags = []
        self.assertEqual(frozenset(), bug_subscription_filter.tags)
        self.assertFalse(bug_subscription_filter.include_any_tags)
        self.assertFalse(bug_subscription_filter.exclude_any_tags)

    def test_tags_with_any_and_all(self):
        # If the tags are bundled in a c.l.searchbuilder.any or .all, the
        # find_any_tags attribute will also be updated.
        bug_subscription_filter = BugSubscriptionFilter()
        self.assertEqual(frozenset(), bug_subscription_filter.tags)
        self.assertFalse(bug_subscription_filter.find_all_tags)

        bug_subscription_filter.tags = searchbuilder.all(u"foo")
        self.assertEqual(frozenset((u"foo",)), bug_subscription_filter.tags)
        self.assertTrue(bug_subscription_filter.find_all_tags)

        # Not using `searchbuilder.any` or `.all` leaves find_all_tags
        # unchanged.
        bug_subscription_filter.tags = [u"-bar"]
        self.assertEqual(frozenset((u"-bar",)), bug_subscription_filter.tags)
        self.assertTrue(bug_subscription_filter.find_all_tags)

        bug_subscription_filter.tags = searchbuilder.any(u"baz")
        self.assertEqual(frozenset((u"baz",)), bug_subscription_filter.tags)
        self.assertFalse(bug_subscription_filter.find_all_tags)


class TestBugSubscriptionFilterPermissions(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionFilterPermissions, self).setUp()
        self.target = self.factory.makeProduct()
        self.subscriber = self.target.owner
        with person_logged_in(self.subscriber):
            self.subscription = self.target.addBugSubscription(
                self.subscriber, self.subscriber)

    def test_read_to_all(self):
        """`BugSubscriptionFilter`s can be read by anyone."""
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.structural_subscription = self.subscription
        bug_subscription_filter = ProxyFactory(bug_subscription_filter)
        with person_logged_in(self.subscriber):
            bug_subscription_filter.find_all_tags
        with person_logged_in(self.factory.makePerson()):
            bug_subscription_filter.find_all_tags
        with anonymous_logged_in():
            bug_subscription_filter.find_all_tags

    def test_write_to_subscribers(self):
        """`BugSubscriptionFilter`s can only be modifed by subscribers."""
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.structural_subscription = self.subscription
        bug_subscription_filter = ProxyFactory(bug_subscription_filter)
        # The subscriber can edit the filter.
        with person_logged_in(self.subscriber):
            bug_subscription_filter.find_all_tags = True
        # Any other person is denied rights to edit the filter.
        with person_logged_in(self.factory.makePerson()):
            self.assertRaises(
                Unauthorized, setattr, bug_subscription_filter,
                "find_all_tags", True)
        # Anonymous users are also denied.
        with anonymous_logged_in():
            self.assertRaises(
                Unauthorized, setattr, bug_subscription_filter,
                "find_all_tags", True)

    def test_delete_by_subscribers(self):
        """`BugSubscriptionFilter`s can only be deleted by subscribers."""
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter.structural_subscription = self.subscription
        bug_subscription_filter = ProxyFactory(bug_subscription_filter)
        # Anonymous users are denied rights to delete the filter.
        with anonymous_logged_in():
            self.assertRaises(
                Unauthorized, getattr, bug_subscription_filter, "delete")
        # Any other person is also denied.
        with person_logged_in(self.factory.makePerson()):
            self.assertRaises(
                Unauthorized, getattr, bug_subscription_filter, "delete")
        # The subscriber can delete the filter.
        with person_logged_in(self.subscriber):
            bug_subscription_filter.delete()

    def test_write_to_any_user_when_no_subscription(self):
        """
        `BugSubscriptionFilter`s can be modifed by any logged-in user when
        there is no related subscription.
        """
        bug_subscription_filter = BugSubscriptionFilter()
        bug_subscription_filter = ProxyFactory(bug_subscription_filter)
        # The subscriber can edit the filter.
        with person_logged_in(self.subscriber):
            bug_subscription_filter.find_all_tags = True
        # Any other person can edit the filter.
        with person_logged_in(self.factory.makePerson()):
            bug_subscription_filter.find_all_tags = True
        # Anonymous users are denied rights to edit the filter.
        with anonymous_logged_in():
            self.assertRaises(
                Unauthorized, setattr, bug_subscription_filter,
                "find_all_tags", True)


class TestBugSubscriptionFilterImportance(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionFilterImportance, self).setUp()
        self.target = self.factory.makeProduct()
        self.subscriber = self.target.owner
        login_person(self.subscriber)
        self.subscription = self.target.addBugSubscription(
            self.subscriber, self.subscriber)
        self.subscription_filter = BugSubscriptionFilter()
        self.subscription_filter.structural_subscription = self.subscription

    def test_basics(self):
        """Test the basics of `BugSubscriptionFilterImportance` objects."""
        # Create.
        bug_sub_filter_importance = BugSubscriptionFilterImportance()
        bug_sub_filter_importance.filter = self.subscription_filter
        bug_sub_filter_importance.importance = BugTaskImportance.HIGH
        # Flush and reload.
        IStore(bug_sub_filter_importance).flush()
        IStore(bug_sub_filter_importance).reload(bug_sub_filter_importance)
        # Check.
        self.assertEqual(
            self.subscription_filter.id, bug_sub_filter_importance.filter_id)
        self.assertEqual(
            self.subscription_filter, bug_sub_filter_importance.filter)
        self.assertEqual(
            BugTaskImportance.HIGH, bug_sub_filter_importance.importance)


class TestBugSubscriptionFilterStatus(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionFilterStatus, self).setUp()
        self.target = self.factory.makeProduct()
        self.subscriber = self.target.owner
        login_person(self.subscriber)
        self.subscription = self.target.addBugSubscription(
            self.subscriber, self.subscriber)
        self.subscription_filter = BugSubscriptionFilter()
        self.subscription_filter.structural_subscription = self.subscription

    def test_basics(self):
        """Test the basics of `BugSubscriptionFilterStatus` objects."""
        # Create.
        bug_sub_filter_status = BugSubscriptionFilterStatus()
        bug_sub_filter_status.filter = self.subscription_filter
        bug_sub_filter_status.status = BugTaskStatus.NEW
        # Flush and reload.
        IStore(bug_sub_filter_status).flush()
        IStore(bug_sub_filter_status).reload(bug_sub_filter_status)
        # Check.
        self.assertEqual(
            self.subscription_filter.id, bug_sub_filter_status.filter_id)
        self.assertEqual(
            self.subscription_filter, bug_sub_filter_status.filter)
        self.assertEqual(BugTaskStatus.NEW, bug_sub_filter_status.status)


class TestBugSubscriptionFilterTag(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionFilterTag, self).setUp()
        self.target = self.factory.makeProduct()
        self.subscriber = self.target.owner
        login_person(self.subscriber)
        self.subscription = self.target.addBugSubscription(
            self.subscriber, self.subscriber)
        self.subscription_filter = BugSubscriptionFilter()
        self.subscription_filter.structural_subscription = self.subscription

    def test_basics(self):
        """Test the basics of `BugSubscriptionFilterTag` objects."""
        # Create.
        bug_sub_filter_tag = BugSubscriptionFilterTag()
        bug_sub_filter_tag.filter = self.subscription_filter
        bug_sub_filter_tag.include = True
        bug_sub_filter_tag.tag = u"foo"
        # Flush and reload.
        IStore(bug_sub_filter_tag).flush()
        IStore(bug_sub_filter_tag).reload(bug_sub_filter_tag)
        # Check.
        self.assertIsNot(None, bug_sub_filter_tag.id)
        self.assertEqual(
            self.subscription_filter.id,
            bug_sub_filter_tag.filter_id)
        self.assertEqual(
            self.subscription_filter,
            bug_sub_filter_tag.filter)
        self.assertIs(True, bug_sub_filter_tag.include)
        self.assertEqual(u"foo", bug_sub_filter_tag.tag)

    def test_qualified_tag(self):
        """
        `BugSubscriptionFilterTag.qualified_tag` returns a tag with a
        preceding hyphen if `include` is `False`.
        """
        bug_sub_filter_tag = BugSubscriptionFilterTag()
        bug_sub_filter_tag.tag = u"foo"
        bug_sub_filter_tag.include = True
        self.assertEqual(u"foo", bug_sub_filter_tag.qualified_tag)
        bug_sub_filter_tag.include = False
        self.assertEqual(u"-foo", bug_sub_filter_tag.qualified_tag)


class TestBugSubscriptionFilterInformationType(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriptionFilterInformationType, self).setUp()
        self.target = self.factory.makeProduct()
        self.subscriber = self.target.owner
        login_person(self.subscriber)
        self.subscription = self.target.addBugSubscription(
            self.subscriber, self.subscriber)
        self.subscription_filter = BugSubscriptionFilter()
        self.subscription_filter.structural_subscription = self.subscription

    def test_basics(self):
        # Test the basics of `BugSubscriptionFilterInformationType` objects.
        # Create.
        bug_sub_filter_itype = BugSubscriptionFilterInformationType()
        bug_sub_filter_itype.filter = self.subscription_filter
        bug_sub_filter_itype.information_type = InformationType.USERDATA
        # Flush and reload.
        IStore(bug_sub_filter_itype).flush()
        IStore(bug_sub_filter_itype).reload(bug_sub_filter_itype)
        # Check.
        self.assertEqual(
            self.subscription_filter.id, bug_sub_filter_itype.filter_id)
        self.assertEqual(
            self.subscription_filter, bug_sub_filter_itype.filter)
        self.assertEqual(
            InformationType.USERDATA, bug_sub_filter_itype.information_type)
