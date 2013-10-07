# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Tests for construction bug notification emails for sending."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
import logging
import re
import StringIO
import unittest

import pytz
from storm.store import Store
from testtools.matchers import Not
from transaction import commit
from zope.component import (
    getSiteManager,
    getUtility,
    )
from zope.interface import implements

from lp.app.enums import InformationType
from lp.bugs.adapters.bugchange import (
    BranchLinkedToBug,
    BranchUnlinkedFromBug,
    BugAttachmentChange,
    BugDuplicateChange,
    BugInformationTypeChange,
    BugTagsChange,
    BugTaskStatusChange,
    BugTitleChange,
    BugWatchAdded,
    BugWatchRemoved,
    CveLinkedToBug,
    CveUnlinkedFromBug,
    )
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBug,
    IBugSet,
    )
from lp.bugs.interfaces.bugnotification import IBugNotificationSet
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.mail.bugnotificationrecipients import BugNotificationRecipients
from lp.bugs.model.bugnotification import (
    BugNotification,
    BugNotificationFilter,
    BugNotificationRecipient,
    )
from lp.bugs.model.bugsubscriptionfilter import BugSubscriptionFilterMute
from lp.bugs.model.bugtask import BugTask
from lp.bugs.scripts.bugnotification import (
    construct_email_notifications,
    get_activity_key,
    get_email_notifications,
    notification_batches,
    notification_comment_batches,
    process_deferred_notifications,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    flush_database_updates,
    sqlvalues,
    )
from lp.services.mail.helpers import (
    get_contact_email_addresses,
    get_email_template,
    )
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.propertycache import cachedproperty
from lp.testing import (
    login,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import (
    lp_dbuser,
    switch_dbuser,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.matchers import Contains


class MockBug:
    """A bug which has only the attributes get_email_notifications() needs."""
    implements(IBug)

    duplicateof = None
    information_type = InformationType.PUBLIC
    messages = []

    def __init__(self, id, owner):
        self.id = id
        self.initial_message = getUtility(IMessageSet).fromText(
            'Bug Title', 'Initial message.', owner=owner)
        self.owner = owner
        self.bugtasks = []
        self.tags = []

    @property
    def title(self):
        return "Mock Bug #%s" % self.id

    def getBugNotificationRecipients(self, level=None):
        recipients = BugNotificationRecipients()
        no_priv = getUtility(IPersonSet).getByEmail(
            'no-priv@canonical.com')
        recipients.addDirectSubscriber(no_priv)
        return recipients

    def __eq__(self, other):
        """Compare by id to make different subclasses of MockBug be equal."""
        return self.id == other.id


class ExceptionBug(MockBug):
    """A bug which causes an exception to be raised."""

    def getBugNotificationRecipients(self, level=None):
        raise Exception('FUBAR')


class DBExceptionBug(MockBug):
    """A bug which causes a DB constraint to be triggered."""

    def getBugNotificationRecipients(self, level=None):
        # Trigger a DB constraint, resulting in the transaction being
        # unusable.
        firefox = getUtility(IProductSet).getByName('firefox')
        bug_one = getUtility(IBugSet).get(1)
        BugTask(bug=bug_one, product=firefox, owner=self.owner)


class MockBugNotificationRecipient:
    """A mock BugNotificationRecipient for testing."""

    def __init__(self):
        self.person = getUtility(IPersonSet).getByEmail(
            'no-priv@canonical.com')
        self.reason_header = 'Test Rationale'
        self.reason_body = 'Test Reason'


class MockBugNotification:
    """A mock BugNotification used for testing.

    Using a real BugNotification won't allow us to set the bug to a mock
    object.
    """

    def __init__(self, message, bug, is_comment, date_emailed):
        self.message = message
        self.bug = bug
        self.is_comment = is_comment
        self.date_emailed = date_emailed
        self.recipients = [MockBugNotificationRecipient()]
        self.activity = None


class FakeNotification:
    """An even simpler fake notification.

    Used by TestGetActivityKey, TestNotificationCommentBatches and
    TestNotificationBatches."""

    class Message(object):
        pass

    def __init__(self, is_comment=False, bug=None, owner=None):
        self.is_comment = is_comment
        self.bug = bug
        self.message = self.Message()
        self.message.owner = owner
        self.activity = None


class FakeBugNotificationSetUtility:
    """A notification utility used for testing."""

    implements(IBugNotificationSet)

    def getRecipientFilterData(self, bug, recipient_to_sources,
                               notifications):
        return dict(
            (recipient, {'sources': sources, 'filter descriptions': []})
            for recipient, sources in recipient_to_sources.items())


class MockBugActivity:
    """A mock BugActivity used for testing."""

    def __init__(self, target=None, attribute=None,
                 oldvalue=None, newvalue=None):
        self.target = target
        self.attribute = attribute
        self.oldvalue = oldvalue
        self.newvalue = newvalue


class TestGetActivityKey(TestCase):
    """Tests for get_activity_key()."""

    def test_no_activity(self):
        self.assertEqual(get_activity_key(FakeNotification()), None)

    def test_normal_bug_attribute_activity(self):
        notification = FakeNotification()
        notification.activity = MockBugActivity(attribute='title')
        self.assertEqual(get_activity_key(notification), 'title')

    def test_collection_bug_attribute_added_activity(self):
        notification = FakeNotification()
        notification.activity = MockBugActivity(
            attribute='cves', newvalue='some cve identifier')
        self.assertEqual(get_activity_key(notification),
                         'cves:some cve identifier')

    def test_collection_bug_attribute_removed_activity(self):
        notification = FakeNotification()
        notification.activity = MockBugActivity(
            attribute='cves', oldvalue='some cve identifier')
        self.assertEqual(get_activity_key(notification),
                         'cves:some cve identifier')

    def test_bugtask_attribute_activity(self):
        notification = FakeNotification()
        notification.activity = MockBugActivity(
            attribute='status', target='some bug task identifier')
        self.assertEqual(get_activity_key(notification),
                         'some bug task identifier:status')


class TestGetEmailNotifications(TestCase):
    """Tests for the exception handling in get_email_notifications()."""
    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Set up some mock bug notifications to use."""
        super(TestGetEmailNotifications, self).setUp()
        switch_dbuser(config.malone.bugnotification_dbuser)
        sample_person = getUtility(IPersonSet).getByEmail(
            'test@canonical.com')
        self.now = datetime.now(pytz.timezone('UTC'))

        # A normal comment notification for bug 1
        msg = getUtility(IMessageSet).fromText(
            'Subject', "Comment on bug 1", owner=sample_person)
        self.bug_one_notification = MockBugNotification(
            message=msg, bug=MockBug(1, sample_person),
            is_comment=True, date_emailed=None)

        # Another normal comment notification for bug one.
        msg = getUtility(IMessageSet).fromText(
            'Subject', "Comment on bug 1", owner=sample_person)
        self.bug_one_another_notification = MockBugNotification(
            message=msg, bug=MockBug(1, sample_person),
            is_comment=True, date_emailed=None)

        # A comment notification for bug one which raises an exception.
        msg = getUtility(IMessageSet).fromText(
            'Subject', "Comment on bug 1", owner=sample_person)
        self.bug_one_exception_notification = MockBugNotification(
            message=msg, bug=ExceptionBug(1, sample_person),
            is_comment=True, date_emailed=None)

        # A comment notification for bug one which raises a DB exception.
        msg = getUtility(IMessageSet).fromText(
            'Subject', "Comment on bug 1", owner=sample_person)
        self.bug_one_dbexception_notification = MockBugNotification(
            message=msg, bug=DBExceptionBug(1, sample_person),
            is_comment=True, date_emailed=None)

        # We need to commit the transaction, since the error handling
        # will abort the current transaction.
        commit()

        sm = getSiteManager()
        self._original_utility = sm.getUtility(IBugNotificationSet)
        sm.unregisterUtility(self._original_utility)
        self._fake_utility = FakeBugNotificationSetUtility()
        sm.registerUtility(self._fake_utility)

    def tearDown(self):
        super(TestGetEmailNotifications, self).tearDown()
        sm = getSiteManager()
        sm.unregisterUtility(self._fake_utility)
        sm.registerUtility(self._original_utility)

    def _getAndCheckSentNotifications(self, notifications_to_send):
        """Return the notifications that were successfully sent.

        It calls get_email_notifications() with the supplied
        notifications and return the ones that were actually sent. It
        also checks that the notifications got sent to the correct
        addresses.
        """
        email_notifications = get_email_notifications(notifications_to_send)
        to_addresses = set()
        sent_notifications = []
        for notifications, omitted, messages in email_notifications:
            for message in messages:
                to_addresses.add(message['to'])
            recipients = {}
            for notification in notifications:
                for recipient in notification.recipients:
                    for address in get_contact_email_addresses(
                        recipient.person):
                        recipients[address] = recipient
            expected_to_addresses = recipients.keys()
            self.assertEqual(
                sorted(expected_to_addresses), sorted(to_addresses))
            sent_notifications += notifications
        return sent_notifications

    def test_catch_simple_exception_last(self):
        # Make sure that the first notification is sent even if the
        # last one causes an exception to be raised.
        notifications_to_send = [
            self.bug_one_notification,
            self.bug_one_exception_notification,
            ]
        sent_notifications = self._getAndCheckSentNotifications(
            notifications_to_send)
        self.assertEqual(sent_notifications, notifications_to_send)

    def test_catch_simple_exception_in_the_middle(self):
        # Make sure that the first and last notifications are sent even
        # if the middle one causes an exception to be raised.
        notifications_to_send = [
            self.bug_one_notification,
            self.bug_one_exception_notification,
            self.bug_one_another_notification,
            ]
        sent_notifications = self._getAndCheckSentNotifications(
            notifications_to_send)
        self.assertEqual(
            sent_notifications,
            notifications_to_send)

    def test_catch_db_exception_last(self):
        # Make sure that the first notification is sent even if the
        # last one causes an exception to be raised. Also make sure that
        # the current transaction is in a usable state.
        notifications_to_send = [
            self.bug_one_notification,
            self.bug_one_dbexception_notification,
            ]
        sent_notifications = self._getAndCheckSentNotifications(
            notifications_to_send)
        self.assertEqual(sent_notifications, notifications_to_send)

        # The transaction should have been rolled back and restarted
        # properly, so getting something from the database shouldn't
        # cause any errors.
        bug_four = getUtility(IBugSet).get(4)
        self.assertEqual(bug_four.id, 4)

    def test_catch_db_exception_in_the_middle(self):
        # Make sure that the first and last notifications are sent even
        # if the middle one causes an exception to be raised. Also make
        # sure that the current transaction is in a usable state.
        notifications_to_send = [
            self.bug_one_notification,
            self.bug_one_dbexception_notification,
            self.bug_one_another_notification,
            ]
        sent_notifications = self._getAndCheckSentNotifications(
            notifications_to_send)
        self.assertEqual(
            sent_notifications, notifications_to_send)

        # The transaction should have been rolled back and restarted
        # properly, so getting something from the database shouldn't
        # cause any errors.
        bug_four = getUtility(IBugSet).get(4)
        self.assertEqual(bug_four.id, 4)

    def test_early_exit(self):
        # When not-yet-exhausted generators need to be deallocated Python
        # raises a GeneratorExit exception at the point of their last yield.
        # The get_email_notifications generator was catching that exception in
        # a try/except and logging it, leading to bug 994694.  This test
        # verifies that the fix for that bug (re-raising the exception) stays
        # in place.

        # Set up logging so we can later assert that no exceptions are logged.
        log_output = StringIO.StringIO()
        logger = logging.getLogger()
        log_handler = logging.StreamHandler(log_output)
        logger.addHandler(logging.StreamHandler(log_output))
        self.addCleanup(logger.removeHandler, log_handler)

        # Make some data to feed to get_email_notifications.
        person = getUtility(IPersonSet).getByEmail('test@canonical.com')
        msg = getUtility(IMessageSet).fromText('', '', owner=person)
        bug = MockBug(1, person)
        # We need more than one notification because we want the generator to
        # stay around after being started.  Consuming the first starts it but
        # since the second exists, the generator stays active.
        notifications = [
            MockBugNotification(
                message=msg, bug=bug, is_comment=True, date_emailed=None),
            MockBugNotification(
                message=msg, bug=bug, is_comment=True, date_emailed=None),
            ]

        # Now we create the generator, start it, and then close it, triggering
        # a GeneratorExit exception inside the generator.
        email_notifications = get_email_notifications(notifications)
        email_notifications.next()
        email_notifications.close()

        # Verify that no "Error while building email notifications." is logged.
        self.assertEqual('', log_output.getvalue())


class TestNotificationCommentBatches(unittest.TestCase):
    """Tests of `notification_comment_batches`."""

    def test_with_nothing(self):
        # Nothing is generated if an empty list is passed in.
        self.assertEquals([], list(notification_comment_batches([])))

    def test_with_one_non_comment_notification(self):
        # Given a single non-comment notification, a single tuple is
        # generated.
        notification = FakeNotification(False)
        self.assertEquals(
            [(1, notification)],
            list(notification_comment_batches([notification])))

    def test_with_one_comment_notification(self):
        # Given a single comment notification, a single tuple is generated.
        notification = FakeNotification(True)
        self.assertEquals(
            [(1, notification)],
            list(notification_comment_batches([notification])))

    def test_with_two_notifications_comment_first(self):
        # Given two notifications, one a comment, one not, and the comment
        # first, two tuples are generated, both in the same group.
        notification1 = FakeNotification(True)
        notification2 = FakeNotification(False)
        notifications = [notification1, notification2]
        self.assertEquals(
            [(1, notification1), (1, notification2)],
            list(notification_comment_batches(notifications)))

    def test_with_two_notifications_comment_last(self):
        # Given two notifications, one a comment, one not, and the comment
        # last, two tuples are generated, both in the same group.
        notification1 = FakeNotification(False)
        notification2 = FakeNotification(True)
        notifications = [notification1, notification2]
        self.assertEquals(
            [(1, notification1), (1, notification2)],
            list(notification_comment_batches(notifications)))

    def test_with_three_notifications_comment_in_middle(self):
        # Given three notifications, one a comment, two not, and the comment
        # in the middle, three tuples are generated, all in the same group.
        notification1 = FakeNotification(False)
        notification2 = FakeNotification(True)
        notification3 = FakeNotification(False)
        notifications = [notification1, notification2, notification3]
        self.assertEquals(
            [(1, notification1), (1, notification2), (1, notification3)],
            list(notification_comment_batches(notifications)))

    def test_with_more_notifications(self):
        # Given four notifications - non-comment, comment, non-comment,
        # comment - four tuples are generated. The first three notifications
        # are in the first group, the last notification is in a group on its
        # own.
        notification1 = FakeNotification(False)
        notification2 = FakeNotification(True)
        notification3 = FakeNotification(False)
        notification4 = FakeNotification(True)
        notifications = [
            notification1, notification2,
            notification3, notification4,
            ]
        self.assertEquals(
            [(1, notification1), (1, notification2),
             (1, notification3), (2, notification4)],
            list(notification_comment_batches(notifications)))


class TestNotificationBatches(unittest.TestCase):
    """Tests of `notification_batches`."""

    def test_with_nothing(self):
        # Nothing is generated if an empty list is passed in.
        self.assertEquals([], list(notification_batches([])))

    def test_with_one_non_comment_notification(self):
        # Given a single non-comment notification, a single batch is
        # generated.
        notification = FakeNotification(False)
        self.assertEquals(
            [[notification]],
            list(notification_batches([notification])))

    def test_with_one_comment_notification(self):
        # Given a single comment notification, a single batch is generated.
        notification = FakeNotification(True)
        self.assertEquals(
            [[notification]],
            list(notification_batches([notification])))

    def test_with_two_notifications_comment_first(self):
        # Given two similar notifications, one a comment, one not, and the
        # comment first, a single batch is generated.
        notification1 = FakeNotification(True)
        notification2 = FakeNotification(False)
        notifications = [notification1, notification2]
        self.assertEquals(
            [[notification1, notification2]],
            list(notification_batches(notifications)))

    def test_with_two_notifications_comment_last(self):
        # Given two similar notifications, one a comment, one not, and the
        # comment last, a single batch is generated.
        notification1 = FakeNotification(False)
        notification2 = FakeNotification(True)
        notifications = [notification1, notification2]
        self.assertEquals(
            [[notification1, notification2]],
            list(notification_batches(notifications)))

    def test_with_three_notifications_comment_in_middle(self):
        # Given three similar notifications, one a comment, two not, and the
        # comment in the middle, one batch is generated.
        notification1 = FakeNotification(False)
        notification2 = FakeNotification(True)
        notification3 = FakeNotification(False)
        notifications = [notification1, notification2, notification3]
        self.assertEquals(
            [[notification1, notification2, notification3]],
            list(notification_batches(notifications)))

    def test_with_more_notifications(self):
        # Given four similar notifications - non-comment, comment,
        # non-comment, comment - two batches are generated. The first three
        # notifications are in the first batch.
        notification1 = FakeNotification(False)
        notification2 = FakeNotification(True)
        notification3 = FakeNotification(False)
        notification4 = FakeNotification(True)
        notifications = [
            notification1, notification2,
            notification3, notification4,
            ]
        self.assertEquals(
            [[notification1, notification2, notification3], [notification4]],
            list(notification_batches(notifications)))

    def test_notifications_for_same_bug(self):
        # Batches are grouped by bug.
        notifications = [FakeNotification(bug=1) for number in range(5)]
        observed = list(notification_batches(notifications))
        self.assertEquals([notifications], observed)

    def test_notifications_for_different_bugs(self):
        # Batches are grouped by bug.
        notifications = [FakeNotification(bug=number) for number in range(5)]
        expected = [[notification] for notification in notifications]
        observed = list(notification_batches(notifications))
        self.assertEquals(expected, observed)

    def test_notifications_for_same_owner(self):
        # Batches are grouped by owner.
        notifications = [FakeNotification(owner=1) for number in range(5)]
        observed = list(notification_batches(notifications))
        self.assertEquals([notifications], observed)

    def test_notifications_for_different_owners(self):
        # Batches are grouped by owner.
        notifications = [
            FakeNotification(owner=number) for number in range(5)]
        expected = [[notification] for notification in notifications]
        observed = list(notification_batches(notifications))
        self.assertEquals(expected, observed)

    def test_notifications_with_mixed_bugs_and_owners(self):
        # Batches are grouped by bug and owner.
        notifications = [
            FakeNotification(bug=1, owner=1),
            FakeNotification(bug=1, owner=2),
            FakeNotification(bug=2, owner=2),
            FakeNotification(bug=2, owner=1),
            ]
        expected = [[notification] for notification in notifications]
        observed = list(notification_batches(notifications))
        self.assertEquals(expected, observed)

    def test_notifications_with_mixed_bugs_and_owners_2(self):
        # Batches are grouped by bug and owner.
        notifications = [
            FakeNotification(bug=1, owner=1),
            FakeNotification(bug=1, owner=1),
            FakeNotification(bug=2, owner=2),
            FakeNotification(bug=2, owner=2),
            ]
        expected = [notifications[0:2], notifications[2:4]]
        observed = list(notification_batches(notifications))
        self.assertEquals(expected, observed)

    def test_notifications_with_mixed_bugs_owners_and_comments(self):
        # Batches are grouped by bug, owner and comments.
        notifications = [
            FakeNotification(is_comment=False, bug=1, owner=1),
            FakeNotification(is_comment=False, bug=1, owner=1),
            FakeNotification(is_comment=True, bug=1, owner=1),
            FakeNotification(is_comment=False, bug=1, owner=2),
            ]
        expected = [notifications[0:3], notifications[3:4]]
        observed = list(notification_batches(notifications))
        self.assertEquals(expected, observed)


class EmailNotificationTestBase(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(EmailNotificationTestBase, self).setUp()
        login('foo.bar@canonical.com')
        self.product_owner = self.factory.makePerson(name="product-owner")
        self.person = self.factory.makePerson(name="sample-person")
        self.product = self.factory.makeProduct(owner=self.product_owner)
        self.product_subscriber = self.factory.makePerson(
            name="product-subscriber")
        self.product.addBugSubscription(
            self.product_subscriber, self.product_subscriber)
        self.bug_subscriber = self.factory.makePerson(name="bug-subscriber")
        self.bug_owner = self.factory.makePerson(name="bug-owner")
        self.bug = self.factory.makeBug(
            target=self.product, owner=self.bug_owner,
            information_type=InformationType.USERDATA)
        self.reporter = self.bug.owner
        self.bug.subscribe(self.bug_subscriber, self.reporter)
        [self.product_bugtask] = self.bug.bugtasks
        commit()
        login('test@canonical.com')
        switch_dbuser(config.malone.bugnotification_dbuser)
        self.now = datetime.now(pytz.UTC)
        self.ten_minutes_ago = self.now - timedelta(minutes=10)
        self.notification_set = getUtility(IBugNotificationSet)
        for notification in self.notification_set.getNotificationsToSend():
            notification.date_emailed = self.now
        flush_database_updates()

    def tearDown(self):
        for notification in self.notification_set.getNotificationsToSend():
            notification.date_emailed = self.now
        flush_database_updates()
        super(EmailNotificationTestBase, self).tearDown()

    def get_messages(self):
        notifications = self.notification_set.getNotificationsToSend()
        email_notifications = get_email_notifications(notifications)
        for (bug_notifications,
             omitted_notifications,
             messages) in email_notifications:
            for message in messages:
                yield message, message.get_payload(decode=True)


class EmailNotificationsBugMixin:

    change_class = change_name = old = new = alt = unexpected_text = None

    def change(self, old, new):
        self.bug.addChange(
            self.change_class(
                self.ten_minutes_ago, self.person, self.change_name,
                old, new))

    def change_other(self):
        self.bug.addChange(
            BugInformationTypeChange(
                self.ten_minutes_ago, self.person, "information_type",
                InformationType.PUBLIC, InformationType.USERDATA))

    def test_change_seen(self):
        # A smoketest.
        self.change(self.old, self.new)
        message, body = self.get_messages().next()
        self.assertThat(body, Contains(self.unexpected_text))

    def test_undone_change_sends_no_emails(self):
        self.change(self.old, self.new)
        self.change(self.new, self.old)
        self.assertEqual(list(self.get_messages()), [])

    def test_undone_change_is_not_included(self):
        self.change(self.old, self.new)
        self.change(self.new, self.old)
        self.change_other()
        message, body = self.get_messages().next()
        self.assertThat(body, Not(Contains(self.unexpected_text)))

    def test_multiple_undone_changes_sends_no_emails(self):
        self.change(self.old, self.new)
        self.change(self.new, self.alt)
        self.change(self.alt, self.old)
        self.assertEqual(list(self.get_messages()), [])


class EmailNotificationsBugNotRequiredMixin(EmailNotificationsBugMixin):
    # This test collection is for attributes that can be None.
    def test_added_removed_sends_no_emails(self):
        self.change(None, self.old)
        self.change(self.old, None)
        self.assertEqual(list(self.get_messages()), [])

    def test_removed_added_sends_no_emails(self):
        self.change(self.old, None)
        self.change(None, self.old)
        self.assertEqual(list(self.get_messages()), [])

    def test_duplicate_marked_changed_removed_sends_no_emails(self):
        self.change(None, self.old)
        self.change(self.old, self.new)
        self.change(self.new, None)
        self.assertEqual(list(self.get_messages()), [])


class EmailNotificationsBugTaskMixin(EmailNotificationsBugMixin):

    def change(self, old, new, index=0):
        self.bug.addChange(
            self.change_class(
                self.bug.bugtasks[index], self.ten_minutes_ago,
                self.person, self.change_name, old, new))

    def test_changing_on_different_bugtasks_is_not_undoing(self):
        with lp_dbuser():
            product2 = self.factory.makeProduct(owner=self.product_owner)
            self.bug.addTask(self.product_owner, product2)
        self.change(self.old, self.new, index=0)
        self.change(self.new, self.old, index=1)
        message, body = self.get_messages().next()
        self.assertThat(body, Contains(self.unexpected_text))


class EmailNotificationsAddedRemovedMixin:

    old = new = added_message = removed_message = None

    def add(self, item):
        raise NotImplementedError
    remove = add

    def test_added_seen(self):
        self.add(self.old)
        message, body = self.get_messages().next()
        self.assertThat(body, Contains(self.added_message))

    def test_added_removed_sends_no_emails(self):
        self.add(self.old)
        self.remove(self.old)
        self.assertEqual(list(self.get_messages()), [])

    def test_removed_added_sends_no_emails(self):
        self.remove(self.old)
        self.add(self.old)
        self.assertEqual(list(self.get_messages()), [])

    def test_added_another_removed_sends_emails(self):
        self.add(self.old)
        self.remove(self.new)
        message, body = self.get_messages().next()
        self.assertThat(body, Contains(self.added_message))
        self.assertThat(body, Contains(self.removed_message))


class TestEmailNotificationsBugTitle(
    EmailNotificationsBugMixin, EmailNotificationTestBase):

    change_class = BugTitleChange
    change_name = "title"
    old = "Old summary"
    new = "New summary"
    alt = "Another summary"
    unexpected_text = '** Summary changed:'


class TestEmailNotificationsBugTags(
    EmailNotificationsBugMixin, EmailNotificationTestBase):

    change_class = BugTagsChange
    change_name = "tags"
    old = ['foo', 'bar', 'baz']
    new = ['foo', 'bar']
    alt = ['bing', 'shazam']
    unexpected_text = '** Tags'

    def test_undone_ordered_set_sends_no_email(self):
        # Tags use ordered sets to generate change descriptions, which we
        # demonstrate here.
        self.change(['foo', 'bar', 'baz'], ['foo', 'bar'])
        self.change(['foo', 'bar'], ['baz', 'bar', 'foo', 'bar'])
        self.assertEqual(list(self.get_messages()), [])


class TestEmailNotificationsBugDuplicate(
    EmailNotificationsBugNotRequiredMixin, EmailNotificationTestBase):

    change_class = BugDuplicateChange
    change_name = "duplicateof"
    unexpected_text = 'duplicate'

    def _bug(self):
        with lp_dbuser():
            return self.factory.makeBug()

    old = cachedproperty('old')(_bug)
    new = cachedproperty('new')(_bug)
    alt = cachedproperty('alt')(_bug)


class TestEmailNotificationsBugTaskStatus(
    EmailNotificationsBugTaskMixin, EmailNotificationTestBase):

    change_class = BugTaskStatusChange
    change_name = "status"
    old = BugTaskStatus.TRIAGED
    new = BugTaskStatus.INPROGRESS
    alt = BugTaskStatus.INVALID
    unexpected_text = 'Status: '


class TestEmailNotificationsBugWatch(
    EmailNotificationsAddedRemovedMixin, EmailNotificationTestBase):

    # Note that this is for bugwatches added to bugs.  Bugwatches added
    # to bugtasks are separate animals AIUI, and we don't try to combine
    # them here for notifications.  Bugtasks have only zero or one
    # bugwatch, so they can be handled just as a simple bugtask attribute
    # change, like status.

    added_message = '** Bug watch added:'
    removed_message = '** Bug watch removed:'

    @cachedproperty
    def tracker(self):
        with lp_dbuser():
            return self.factory.makeBugTracker()

    def _watch(self, identifier='123'):
        with lp_dbuser():
            # This actually creates a notification all by itself.  However,
            # it won't be sent out for another five minutes.  Therefore,
            # we send out separate change notifications.
            return self.bug.addWatch(
                self.tracker, identifier, self.product_owner)

    old = cachedproperty('old')(_watch)
    new = cachedproperty('new')(lambda self: self._watch('456'))

    def add(self, item):
        with lp_dbuser():
            self.bug.addChange(
                BugWatchAdded(
                    self.ten_minutes_ago, self.product_owner, item))

    def remove(self, item):
        with lp_dbuser():
            self.bug.addChange(
                BugWatchRemoved(
                    self.ten_minutes_ago, self.product_owner, item))


class TestEmailNotificationsBranch(
    EmailNotificationsAddedRemovedMixin, EmailNotificationTestBase):

    added_message = '** Branch linked:'
    removed_message = '** Branch unlinked:'

    def _branch(self):
        with lp_dbuser():
            return self.factory.makeBranch()

    old = cachedproperty('old')(_branch)
    new = cachedproperty('new')(_branch)

    def add(self, item):
        with lp_dbuser():
            self.bug.addChange(
                BranchLinkedToBug(
                    self.ten_minutes_ago, self.person, item, self.bug))

    def remove(self, item):
        with lp_dbuser():
            self.bug.addChange(
                BranchUnlinkedFromBug(
                    self.ten_minutes_ago, self.person, item, self.bug))


class TestEmailNotificationsCVE(
    EmailNotificationsAddedRemovedMixin, EmailNotificationTestBase):

    added_message = '** CVE added:'
    removed_message = '** CVE removed:'

    def _cve(self, sequence):
        with lp_dbuser():
            return self.factory.makeCVE(sequence)

    old = cachedproperty('old')(lambda self: self._cve('2020-1234'))
    new = cachedproperty('new')(lambda self: self._cve('2020-5678'))

    def add(self, item):
        with lp_dbuser():
            self.bug.addChange(
                CveLinkedToBug(
                    self.ten_minutes_ago, self.person, item))

    def remove(self, item):
        with lp_dbuser():
            self.bug.addChange(
                CveUnlinkedFromBug(
                    self.ten_minutes_ago, self.person, item))


class TestEmailNotificationsAttachments(
    EmailNotificationsAddedRemovedMixin, EmailNotificationTestBase):

    added_message = '** Attachment added:'
    removed_message = '** Attachment removed:'

    def _attachment(self):
        with lp_dbuser():
            # This actually creates a notification all by itself, via an
            # event subscriber.  However, it won't be sent out for
            # another five minutes.  Therefore, we send out separate
            # change notifications.
            return self.bug.addAttachment(
                self.person, 'content', 'a comment', 'stuff.txt')

    old = cachedproperty('old')(_attachment)
    new = cachedproperty('new')(_attachment)

    def add(self, item):
        with lp_dbuser():
            self.bug.addChange(
                BugAttachmentChange(
                    self.ten_minutes_ago, self.person, 'attachment',
                    None, item))

    def remove(self, item):
        with lp_dbuser():
            self.bug.addChange(
                BugAttachmentChange(
                    self.ten_minutes_ago, self.person, 'attachment',
                    item, None))


class TestEmailNotificationsWithFilters(TestCaseWithFactory):
    """Ensure outgoing mails have corresponding headers, accounting for mutes.

    Every filter that could have potentially caused a notification to
    go off has a `BugNotificationFilter` record linking a `BugNotification`
    and a `BugSubscriptionFilter`.

    From those records, we include all BugSubscriptionFilter.description
    in X-Subscription-Filter-Description headers in each email.

    Every team filter that caused notifications might be muted for a
    given recipient.  These can cause headers to be omitted, and if all
    filters that caused the notifications are omitted then the
    notification itself will not be sent.
    """

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestEmailNotificationsWithFilters, self).setUp()
        self.bug = self.factory.makeBug()
        subscriber = self.factory.makePerson()
        self.subscription = self.bug.default_bugtask.target.addSubscription(
            subscriber, subscriber)
        self.filter_count = 0
        self.notification = self.addNotification(subscriber)

    def addNotificationRecipient(self, notification, person):
        # Manually insert BugNotificationRecipient for
        # construct_email_notifications to work.
        # Not sure why using SQLObject constructor doesn't work (it
        # tries to insert a row with only the ID which fails).
        Store.of(notification).execute("""
            INSERT INTO BugNotificationRecipient
              (bug_notification, person, reason_header, reason_body)
              VALUES (%s, %s, %s, %s)""" % sqlvalues(
                          notification, person,
                          u'reason header', u'reason body'))

    def addNotification(self, person):
        # Add a notification along with recipient data.
        # This is generally done with BugTaskSet.addNotification()
        # but that requires a more complex set-up.
        message = self.factory.makeMessage()
        notification = BugNotification(
            message=message, activity=None, bug=self.bug,
            is_comment=False, date_emailed=None)
        self.addNotificationRecipient(notification, person)
        return notification

    def addFilter(self, description, subscription=None):
        if subscription is None:
            subscription = self.subscription
            filter_count = self.filter_count
            self.filter_count += 1
        else:
            # For a non-default subscription, always use
            # the initial filter.
            filter_count = 0

        # If no filters have been requested before,
        # use the initial auto-created filter for a subscription.
        if filter_count == 0:
            bug_filter = subscription.bug_filters.one()
        else:
            bug_filter = subscription.newBugFilter()
        bug_filter.description = description
        BugNotificationFilter(
            bug_notification=self.notification,
            bug_subscription_filter=bug_filter)

    def getSubscriptionEmailHeaders(self, by_person=False):
        filtered, omitted, messages = construct_email_notifications(
            [self.notification])
        if by_person:
            headers = {}
        else:
            headers = set()
        for message in messages:
            if by_person:
                headers[message['to']] = message.get_all(
                    "X-Launchpad-Subscription", [])
            else:
                headers = headers.union(
                    set(message.get_all(
                        "X-Launchpad-Subscription", [])))
        return headers

    def getSubscriptionEmailBody(self, by_person=False):
        filtered, omitted, messages = construct_email_notifications(
            [self.notification])
        if by_person:
            filter_texts = {}
        else:
            filter_texts = set()
        for message in messages:
            filters_line = None
            for line in message.get_payload().splitlines():
                if line.startswith("Matching subscriptions: "):
                    filters_line = line
                    break
            if filters_line is not None:
                if by_person:
                    filter_texts[message['to']] = filters_line
                else:
                    filter_texts.add(filters_line)
        return filter_texts

    def test_header_empty(self):
        # An initial filter with no description doesn't cause any
        # headers to be added.
        self.assertContentEqual([],
                                self.getSubscriptionEmailHeaders())

    def test_header_single(self):
        # A single filter with a description makes all emails
        # include that particular filter description in a header.
        self.addFilter(u"Test filter")

        self.assertContentEqual([u"Test filter"],
                                self.getSubscriptionEmailHeaders())

    def test_header_multiple(self):
        # Multiple filters with a description make all emails
        # include all filter descriptions in the header.
        self.addFilter(u"First filter")
        self.addFilter(u"Second filter")

        self.assertContentEqual([u"First filter", u"Second filter"],
                                self.getSubscriptionEmailHeaders())

    def test_header_other_subscriber_by_person(self):
        # Filters for a different subscribers are included only
        # in email messages relevant to them, even if they might
        # all be for the same notification.
        other_person = self.factory.makePerson()
        other_subscription = self.bug.default_bugtask.target.addSubscription(
            other_person, other_person)
        self.addFilter(u"Someone's filter", other_subscription)
        self.addNotificationRecipient(self.notification, other_person)

        self.addFilter(u"Test filter")

        the_subscriber = self.subscription.subscriber
        self.assertEquals(
            {other_person.preferredemail.email: [u"Someone's filter"],
             the_subscriber.preferredemail.email: [u"Test filter"]},
            self.getSubscriptionEmailHeaders(by_person=True))

    def test_body_empty(self):
        # An initial filter with no description doesn't cause any
        # text to be added to the email body.
        self.assertContentEqual([],
                                self.getSubscriptionEmailBody())

    def test_body_single(self):
        # A single filter with a description makes all emails
        # include that particular filter description in the body.
        self.addFilter(u"Test filter")

        self.assertContentEqual([u"Matching subscriptions: Test filter"],
                                self.getSubscriptionEmailBody())

    def test_body_multiple(self):
        # Multiple filters with description make all emails
        # include them in the email body.
        self.addFilter(u"First filter")
        self.addFilter(u"Second filter")

        self.assertContentEqual(
            [u"Matching subscriptions: First filter, Second filter"],
            self.getSubscriptionEmailBody())

    def test_muted(self):
        self.addFilter(u"Test filter")
        BugSubscriptionFilterMute(
            person=self.subscription.subscriber,
            filter=self.notification.bug_filters.one())
        filtered, omitted, messages = construct_email_notifications(
            [self.notification])
        self.assertEqual(list(messages), [])

    def test_header_multiple_one_muted(self):
        # Multiple filters with a description make all emails
        # include all filter descriptions in the header.
        self.addFilter(u"First filter")
        self.addFilter(u"Second filter")
        BugSubscriptionFilterMute(
            person=self.subscription.subscriber,
            filter=self.notification.bug_filters[0])

        self.assertContentEqual([u"Second filter"],
                                self.getSubscriptionEmailHeaders())


def fetch_notifications(subscriber, bug):
    return IStore(BugNotification).find(
        BugNotification,
        BugNotification.id == BugNotificationRecipient.bug_notificationID,
        BugNotificationRecipient.personID == subscriber.id,
        BugNotification.bug == bug)


class TestEmailNotificationsWithFiltersWhenBugCreated(TestCaseWithFactory):
    # See bug 720147.

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestEmailNotificationsWithFiltersWhenBugCreated, self).setUp()
        self.subscriber = self.factory.makePerson()
        self.submitter = self.factory.makePerson()
        self.product = self.factory.makeProduct(
            bug_supervisor=self.submitter)
        self.subscription = self.product.addSubscription(
            self.subscriber, self.subscriber)
        self.filter = self.subscription.bug_filters[0]
        self.filter.description = u'Needs triage'
        self.filter.statuses = [BugTaskStatus.NEW, BugTaskStatus.INCOMPLETE]

    def test_filters_match_when_bug_is_created(self):
        message = u"this is an unfiltered comment"
        params = CreateBugParams(
            title=u"crashes all the time",
            comment=message, owner=self.submitter,
            status=BugTaskStatus.NEW)
        bug = self.product.createBug(params)
        notification = fetch_notifications(self.subscriber, bug).one()
        self.assertEqual(notification.message.text_contents, message)

    def test_filters_do_not_match_when_bug_is_created(self):
        message = u"this is a filtered comment"
        params = CreateBugParams(
            title=u"crashes all the time",
            comment=message, owner=self.submitter,
            status=BugTaskStatus.TRIAGED,
            importance=BugTaskImportance.HIGH)
        bug = self.product.createBug(params)
        notifications = fetch_notifications(self.subscriber, bug)
        self.assertTrue(notifications.is_empty())


class TestManageNotificationsMessage(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_manage_notifications_message_is_included(self):
        # Set up a subscription to a product.
        subscriber = self.factory.makePerson()
        submitter = self.factory.makePerson()
        product = self.factory.makeProduct(
            bug_supervisor=submitter)
        product.addSubscription(subscriber, subscriber)
        # Create a bug that will match the subscription.
        bug = product.createBug(CreateBugParams(
            title=self.factory.getUniqueString(),
            comment=self.factory.getUniqueString(),
            owner=submitter))
        notification = fetch_notifications(subscriber, bug).one()
        _, _, (message,) = construct_email_notifications([notification])
        payload = message.get_payload()
        self.assertThat(payload, Contains(
            'To manage notifications about this bug go to:\nhttp://'))


class TestNotificationSignatureSeparator(TestCase):

    def test_signature_separator(self):
        # Email signatures are often separated from the body of a message by a
        # special separator so user agents can identify the signature for
        # special treatment (hiding, stripping when replying, colorizing,
        # etc.).  The bug notification messages follow the convention.
        names = ['bug-notification-verbose.txt', 'bug-notification.txt']
        for name in names:
            template = get_email_template(name, 'bugs')
            self.assertTrue(re.search('^-- $', template, re.MULTILINE))


class TestDeferredNotifications(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestDeferredNotifications, self).setUp()
        self.notification_set = getUtility(IBugNotificationSet)
        # Ensure there are no outstanding notifications.
        for notification in self.notification_set.getNotificationsToSend():
            notification.destroySelf()
        self.ten_minutes_ago = datetime.now(pytz.UTC) - timedelta(minutes=10)

    def _make_deferred_notification(self):
        bug = self.factory.makeBug()
        empty_recipients = BugNotificationRecipients()
        message = getUtility(IMessageSet).fromText(
            'subject', 'a comment.', bug.owner,
            datecreated=self.ten_minutes_ago)
        self.notification_set.addNotification(
            bug, False, message, empty_recipients, None, deferred=True)

    def test_deferred_notifications(self):
        # Create some deferred notifications and show that processing them
        # puts then in the state where they are ready to send.
        num = 5
        for i in xrange(num):
            self._make_deferred_notification()
        deferred = self.notification_set.getDeferredNotifications()
        self.assertEqual(num, deferred.count())
        process_deferred_notifications(deferred)
        # Now that are all in the PENDING state.
        ready_to_send = self.notification_set.getNotificationsToSend()
        self.assertEqual(num, len(ready_to_send))
        # And there are no longer any deferred.
        deferred = self.notification_set.getDeferredNotifications()
        self.assertEqual(0, deferred.count())
