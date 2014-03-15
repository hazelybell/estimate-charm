# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for recording changes done to a bug."""

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectModifiedEvent,
    )
from lazr.lifecycle.snapshot import Snapshot
from testtools.matchers import (
    MatchesStructure,
    StartsWith,
    )
from zope.component import getUtility
from zope.event import notify
from zope.interface import providedBy

from lp.app.enums import InformationType
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.cve import ICveSet
from lp.bugs.model.bugnotification import BugNotification
from lp.bugs.scripts.bugnotification import construct_email_notifications
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    api_url,
    launchpadlib_for,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestBugChanges(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBugChanges, self).setUp('foo.bar@canonical.com')
        self.admin_user = getUtility(ILaunchBag).user
        self.user = self.factory.makePerson(
            displayname='Arthur Dent', selfgenerated_bugnotifications=True)
        self.product = self.factory.makeProduct(
            owner=self.user, official_malone=True)
        self.bug = self.factory.makeBug(target=self.product, owner=self.user)
        self.bug_task = self.bug.bugtasks[0]

        # Add some structural subscribers to show that notifications
        # aren't sent to LIFECYCLE subscribers by default.
        self.product_lifecycle_subscriber = self.newSubscriber(
            self.product, "product-lifecycle", BugNotificationLevel.LIFECYCLE)
        self.product_metadata_subscriber = self.newSubscriber(
            self.product, "product-metadata", BugNotificationLevel.METADATA)

        self.saveOldChanges()

    def newSubscriber(self, target, name, level):
        # Create a new bug subscription with a new person.
        subscriber = self.factory.makePerson(name=name)
        subscription = target.addBugSubscription(subscriber, subscriber)
        with person_logged_in(subscriber):
            filter = subscription.bug_filters.one()
            filter.bug_notification_level = level
        return subscriber

    def saveOldChanges(self, bug=None, append=False):
        """Save old activity and notifications for a test.

        This method should be called after setup.  Removing the
        initial bug-created activity and notification messages
        allows for a more accurate check of new activity and
        notifications.

        The append parameter can be used to save activity/notifications
        for more than one bug in a single test, as when dealing
        with duplicates.
        """
        if bug is None:
            bug = self.bug
        old_activities = set(bug.activity)
        old_notification_ids = set(
            notification.id for notification in (
                BugNotification.selectBy(bug=bug)))

        if append:
            self.old_activities.update(old_activities)
            self.old_notification_ids.update(old_notification_ids)
        else:
            self.old_activities = old_activities
            self.old_notification_ids = old_notification_ids
        bug.clearBugNotificationRecipientsCache()

    def changeAttribute(self, obj, attribute, new_value):
        """Set the value of `attribute` on `obj` to `new_value`.

        :return: The value of `attribute` before modification.
        """
        obj_before_modification = Snapshot(obj, providing=providedBy(obj))
        if attribute == 'duplicateof':
            obj.markAsDuplicate(new_value)
        else:
            setattr(obj, attribute, new_value)
        notify(ObjectModifiedEvent(
            obj, obj_before_modification, [attribute], self.user))

        return getattr(obj_before_modification, attribute)

    def getNewNotifications(self, bug=None):
        if bug is None:
            bug = self.bug
        bug_notifications = BugNotification.selectBy(
            bug=bug, orderBy='id')
        new_notifications = [
            notification for notification in bug_notifications
            if notification.id not in self.old_notification_ids]
        return new_notifications

    def assertRecordedChange(self, expected_activity=None,
                             expected_notification=None, bug=None):
        """Assert that things were recorded as expected."""
        if bug is None:
            bug = self.bug
        new_activities = [
            activity for activity in bug.activity
            if activity not in self.old_activities]
        new_notifications = self.getNewNotifications(bug)

        if expected_activity is None:
            self.assertEqual(0, len(new_activities))
        else:
            if isinstance(expected_activity, dict):
                expected_activities = [expected_activity]
            else:
                expected_activities = expected_activity
            self.assertEqual(len(expected_activities), len(new_activities))
            for expected_activity in expected_activities:
                added_activity = new_activities.pop(0)
                self.assertThat(added_activity, MatchesStructure.byEquality(
                    person=expected_activity['person'],
                    whatchanged=expected_activity['whatchanged'],
                    oldvalue=expected_activity.get('oldvalue'),
                    newvalue=expected_activity.get('newvalue'),
                    message=expected_activity.get('message')))

        if expected_notification is None:
            self.assertEqual(0, len(new_notifications))
        else:
            if isinstance(expected_notification, dict):
                expected_notifications = [expected_notification]
            else:
                expected_notifications = expected_notification
            self.assertEqual(
                len(expected_notifications), len(new_notifications))
            for expected_notification in expected_notifications:
                added_notification = new_notifications.pop(0)
                self.assertEqual(
                    expected_notification['text'],
                    added_notification.message.text_contents)
                self.assertEqual(
                    expected_notification['person'],
                    added_notification.message.owner)
                self.assertEqual(
                    expected_notification.get('is_comment', False),
                    added_notification.is_comment)
                expected_recipients = expected_notification.get('recipients')
                expected_recipient_reasons = (
                    expected_notification.get('recipient_reasons'))
                if expected_recipients is None:
                    expected_recipients = bug.getBugNotificationRecipients(
                        level=BugNotificationLevel.METADATA)
                self.assertEqual(
                    set(expected_recipients),
                    set(recipient.person
                        for recipient in added_notification.recipients))
                if expected_recipient_reasons:
                    self.assertEqual(
                        set(expected_recipient_reasons),
                        set(recipient.reason_header
                            for recipient in added_notification.recipients))

    def assertRecipients(self, expected_recipients):
        notifications = self.getNewNotifications()
        notifications, omitted, messages = construct_email_notifications(
            notifications)
        recipients = set(message['to'] for message in messages)

        self.assertEqual(
            set(recipient.preferredemail.email
                for recipient in expected_recipients),
            recipients)

    def test_subscribe(self):
        # Subscribing someone to a bug adds an item to the activity log,
        # but doesn't send an e-mail notification.
        subscriber = self.factory.makePerson(displayname='Mom')
        bug_subscription = self.bug.subscribe(self.user, subscriber)
        notify(ObjectCreatedEvent(bug_subscription, user=subscriber))
        subscribe_activity = dict(
            whatchanged='bug',
            message='added subscriber Arthur Dent',
            person=subscriber)
        self.assertRecordedChange(expected_activity=subscribe_activity)

    def test_unsubscribe(self):
        # Unsubscribing someone from a bug adds an item to the activity
        # log, but doesn't send an e-mail notification.
        subscriber = self.factory.makePerson(displayname='Mom')
        self.bug.subscribe(self.user, subscriber)
        self.saveOldChanges()
        # Only the user can unsubscribe him or her self.
        self.bug.unsubscribe(self.user, self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'removed_subscriber')
        self.assertEqual(activity.target, None)

        unsubscribe_activity = dict(
            whatchanged='removed subscriber Arthur Dent', person=self.user)
        self.assertRecordedChange(expected_activity=unsubscribe_activity)

    def test_unsubscribe_private_bug(self):
        # Test that a person can unsubscribe themselves from a private bug
        # that they are not assigned to.
        subscriber = self.factory.makePerson(displayname='Mom')
        # Create the private bug.
        bug = self.factory.makeBug(
            target=self.product, owner=self.user,
            information_type=InformationType.USERDATA)
        bug.subscribe(subscriber, self.user)
        self.saveOldChanges(bug=bug)
        bug.unsubscribe(subscriber, subscriber)
        unsubscribe_activity = dict(
            whatchanged=u'removed subscriber Mom', person=subscriber)
        self.assertRecordedChange(
            expected_activity=unsubscribe_activity, bug=bug)

    def test_title_changed(self):
        # Changing the title of a Bug adds items to the activity log and
        # the Bug's notifications.
        old_title = self.changeAttribute(self.bug, 'title', '42')

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'title')
        self.assertEqual(activity.target, None)

        title_change_activity = {
            'whatchanged': 'summary',
            'oldvalue': old_title,
            'newvalue': "42",
            'person': self.user,
            }

        title_change_notification = {
            'text': (
                "** Summary changed:\n\n"
                "- %s\n"
                "+ 42" % old_title),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=title_change_activity,
            expected_notification=title_change_notification)

    def test_description_changed(self):
        # Changing the description of a Bug adds items to the activity
        # log and the Bug's notifications.
        old_description = self.changeAttribute(
            self.bug, 'description', 'Hello, world')

        description_change_activity = {
            'person': self.user,
            'whatchanged': 'description',
            'oldvalue': old_description,
            'newvalue': 'Hello, world',
            }

        description_change_notification = {
            'text': (
                "** Description changed:\n\n"
                "- %s\n"
                "+ Hello, world" % old_description),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_notification=description_change_notification,
            expected_activity=description_change_activity)

    def test_bugwatch_added(self):
        # Adding a BugWatch to a bug adds items to the activity
        # log and the Bug's notifications.
        bugtracker = self.factory.makeBugTracker()
        bug_watch = self.bug.addWatch(bugtracker, '42', self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'watches')
        self.assertEqual(activity.target, None)

        bugwatch_activity = {
            'person': self.user,
            'whatchanged': 'bug watch added',
            'newvalue': bug_watch.url,
            }

        bugwatch_notification = {
            'text': (
                "** Bug watch added: %s #%s\n"
                "   %s" % (
                    bug_watch.bugtracker.title, bug_watch.remotebug,
                    bug_watch.url)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_notification=bugwatch_notification,
            expected_activity=bugwatch_activity)

    def test_bugwatch_added_from_comment(self):
        # Adding a bug comment containing a URL that looks like a link
        # to a remote bug causes a BugWatch to be added to the
        # bug. This adds to the activity log and sends a notification.
        self.assertEqual(self.bug.watches.count(), 0)
        self.bug.newMessage(
            content="http://bugs.example.com/view.php?id=1234",
            owner=self.user)
        self.assertEqual(self.bug.watches.count(), 1)
        [bug_watch] = self.bug.watches

        bugwatch_activity = {
            'person': self.user,
            'whatchanged': 'bug watch added',
            'newvalue': bug_watch.url,
            }

        bugwatch_notification = {
            'text': (
                "** Bug watch added: %s #%s\n"
                "   %s" % (
                    bug_watch.bugtracker.title, bug_watch.remotebug,
                    bug_watch.url)),
            'person': self.user,
            'recipients': [
                self.user, self.product_metadata_subscriber],
            }

        comment_notification = {
            'text': "http://bugs.example.com/view.php?id=1234",
            'person': self.user,
            'is_comment': True,
            'recipients': [self.user],
            }

        self.assertRecordedChange(
            expected_activity=bugwatch_activity,
            expected_notification=[
                bugwatch_notification, comment_notification])

    def test_bugwatch_removed(self):
        # Removing a BugWatch from a bug adds items to the activity
        # log and the Bug's notifications.
        bugtracker = self.factory.makeBugTracker()
        bug_watch = self.bug.addWatch(bugtracker, '42', self.user)
        self.saveOldChanges()
        self.bug.removeWatch(bug_watch, self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'watches')
        self.assertEqual(activity.target, None)

        bugwatch_activity = {
            'person': self.user,
            'whatchanged': 'bug watch removed',
            'oldvalue': bug_watch.url,
            }

        bugwatch_notification = {
            'text': (
                "** Bug watch removed: %s #%s\n"
                "   %s" % (
                    bug_watch.bugtracker.title, bug_watch.remotebug,
                    bug_watch.url)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_notification=bugwatch_notification,
            expected_activity=bugwatch_activity)

    def test_bugwatch_modified(self):
        # Modifying a BugWatch is like removing and re-adding it.
        bugtracker = self.factory.makeBugTracker()
        bug_watch = self.bug.addWatch(bugtracker, '42', self.user)
        old_url = bug_watch.url
        self.saveOldChanges()
        old_remotebug = self.changeAttribute(bug_watch, 'remotebug', '84')

        bugwatch_removal_activity = {
            'person': self.user,
            'whatchanged': 'bug watch removed',
            'oldvalue': old_url,
            }
        bugwatch_addition_activity = {
            'person': self.user,
            'whatchanged': 'bug watch added',
            'newvalue': bug_watch.url,
            }

        bugwatch_removal_notification = {
            'text': (
                "** Bug watch removed: %s #%s\n"
                "   %s" % (
                    bug_watch.bugtracker.title, old_remotebug,
                    old_url)),
            'person': self.user,
            }
        bugwatch_addition_notification = {
            'text': (
                "** Bug watch added: %s #%s\n"
                "   %s" % (
                    bug_watch.bugtracker.title, bug_watch.remotebug,
                    bug_watch.url)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_notification=[bugwatch_removal_notification,
                                   bugwatch_addition_notification],
            expected_activity=[bugwatch_removal_activity,
                               bugwatch_addition_activity])

    def test_bugwatch_not_modified(self):
        # Firing off a modified event without actually modifying
        # anything intersting doesn't cause anything to be added to the
        # activity log.
        bug_watch = self.factory.makeBugWatch(bug=self.bug)
        self.saveOldChanges()
        self.changeAttribute(bug_watch, 'remotebug', bug_watch.remotebug)

        self.assertRecordedChange()

    def test_link_branch(self):
        # Linking a branch to a bug adds both to the activity log and
        # sends an e-mail notification.
        branch = self.factory.makeBranch()
        self.bug.linkBranch(branch, self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'linked_branches')
        self.assertEqual(activity.target, None)

        added_activity = {
            'person': self.user,
            'whatchanged': 'branch linked',
            'newvalue': branch.bzr_identity,
            }
        added_notification = {
            'text': "** Branch linked: %s" % branch.bzr_identity,
            'person': self.user,
            }
        self.assertRecordedChange(
            expected_activity=added_activity,
            expected_notification=added_notification)

    def test_link_branch_to_complete_bug(self):
        # Linking a branch to a bug that is "complete" (see
        # IBug.is_complete) adds to the activity log but does *not*
        # send an e-mail notification.
        for bug_task in self.bug.bugtasks:
            bug_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, user=self.user)
        self.failUnless(self.bug.is_complete)
        self.saveOldChanges()
        branch = self.factory.makeBranch()
        self.bug.linkBranch(branch, self.user)
        expected_activity = {
            'person': self.user,
            'whatchanged': 'branch linked',
            'newvalue': branch.bzr_identity,
            }
        self.assertRecordedChange(
            expected_activity=expected_activity)

    def test_link_private_branch(self):
        # Linking a *private* branch to a bug adds *nothing* to the
        # activity log and does *not* send an e-mail notification.
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        self.bug.linkBranch(branch, self.user)
        self.assertRecordedChange()

    def test_unlink_branch(self):
        # Unlinking a branch from a bug adds both to the activity log and
        # sends an e-mail notification.
        branch = self.factory.makeBranch()
        self.bug.linkBranch(branch, self.user)
        self.saveOldChanges()
        self.bug.unlinkBranch(branch, self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'linked_branches')
        self.assertEqual(activity.target, None)

        added_activity = {
            'person': self.user,
            'whatchanged': 'branch unlinked',
            'oldvalue': branch.bzr_identity,
            }
        added_notification = {
            'text': "** Branch unlinked: %s" % branch.bzr_identity,
            'person': self.user,
            }
        self.assertRecordedChange(
            expected_activity=added_activity,
            expected_notification=added_notification)

    def test_unlink_branch_from_complete_bug(self):
        # Unlinking a branch from a bug that is "complete" (see
        # IBug.is_complete) adds to the activity log but does *not*
        # send an e-mail notification.
        for bug_task in self.bug.bugtasks:
            bug_task.transitionToStatus(
                BugTaskStatus.FIXRELEASED, user=self.user)
        self.failUnless(self.bug.is_complete)
        branch = self.factory.makeBranch()
        self.bug.linkBranch(branch, self.user)
        self.saveOldChanges()
        self.bug.unlinkBranch(branch, self.user)
        expected_activity = {
            'person': self.user,
            'whatchanged': 'branch unlinked',
            'oldvalue': branch.bzr_identity,
            }
        self.assertRecordedChange(
            expected_activity=expected_activity)

    def test_unlink_private_branch(self):
        # Unlinking a *private* branch from a bug adds *nothing* to
        # the activity log and does *not* send an e-mail notification.
        branch = self.factory.makeBranch(
            information_type=InformationType.USERDATA)
        self.bug.linkBranch(branch, self.user)
        self.saveOldChanges()
        self.bug.unlinkBranch(branch, self.user)
        self.assertRecordedChange()

    def test_change_information_type(self):
        # Changing the information type of a bug adds items to the activity
        # log and notifications.
        bug = self.factory.makeBug()
        self.saveOldChanges(bug=bug)
        bug_before_modification = Snapshot(bug, providing=providedBy(bug))
        bug.transitionToInformationType(
            InformationType.PRIVATESECURITY, self.user)
        notify(ObjectModifiedEvent(
            bug, bug_before_modification, ['information_type'],
            user=self.user))

        information_type_change_activity = {
            'person': self.user,
            'whatchanged': 'information type',
            'oldvalue': 'Public',
            'newvalue': 'Private Security',
            }
        information_type_change_notification = {
            'text': '** Information type changed from Public to Private '
                'Security',
            'person': self.user,
            }
        self.assertRecordedChange(
            expected_activity=information_type_change_activity,
            expected_notification=information_type_change_notification,
            bug=bug)

    def test_change_information_type_using_api(self):
        # Changing the information type of a bug adds items to the activity
        # log and notifications.
        person = self.factory.makePerson()
        bug = self.factory.makeBug(owner=person)
        self.saveOldChanges(bug=bug)
        webservice = launchpadlib_for('test', person)
        lp_bug = webservice.load(api_url(bug))
        lp_bug.transitionToInformationType(information_type='Private Security')

        information_type_change_activity = {
            'person': person,
            'whatchanged': 'information type',
            'oldvalue': 'Public',
            'newvalue': 'Private Security',
            }
        information_type_change_notification = {
            'text': '** Information type changed from Public to Private '
                'Security',
            'person': person,
            }
        with person_logged_in(person):
            self.assertRecordedChange(
                expected_activity=information_type_change_activity,
                expected_notification=information_type_change_notification,
                bug=bug)

    def test_tags_added(self):
        # Adding tags to a bug will add BugActivity and BugNotification
        # entries.
        self.changeAttribute(
            self.bug, 'tags', ['first-new-tag', 'second-new-tag'])

        tag_change_activity = {
            'person': self.user,
            'whatchanged': 'tags',
            'oldvalue': '',
            'newvalue': 'first-new-tag second-new-tag',
            }

        tag_change_notification = {
            'person': self.user,
            'text': '** Tags added: first-new-tag second-new-tag',
            }

        self.assertRecordedChange(
            expected_activity=tag_change_activity,
            expected_notification=tag_change_notification)

    def test_tags_removed(self):
        # Removing tags from a bug adds BugActivity and BugNotification
        # entries.
        self.bug.tags = ['first-new-tag', 'second-new-tag']
        self.saveOldChanges()
        self.changeAttribute(
            self.bug, 'tags', ['first-new-tag'])

        tag_change_activity = {
            'person': self.user,
            'whatchanged': 'tags',
            'oldvalue': 'first-new-tag second-new-tag',
            'newvalue': 'first-new-tag',
            }

        tag_change_notification = {
            'person': self.user,
            'text': '** Tags removed: second-new-tag',
            }

        self.assertRecordedChange(
            expected_activity=tag_change_activity,
            expected_notification=tag_change_notification)

    def test_link_cve(self):
        # Linking a CVE to a bug adds to the bug's activity log and
        # sends a notification.
        cve = getUtility(ICveSet)['1999-8979']
        self.bug.linkCVE(cve, self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'cves')
        self.assertEqual(activity.target, None)

        cve_linked_activity = {
            'person': self.user,
            'whatchanged': 'cve linked',
            'oldvalue': None,
            'newvalue': cve.sequence,
            }

        cve_linked_notification = {
            'text': (
                '** CVE added: http://www.cve.mitre.org/'
                'cgi-bin/cvename.cgi?name=1999-8979'),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=cve_linked_activity,
            expected_notification=cve_linked_notification)

    def test_unlink_cve(self):
        # Unlinking a CVE from a bug adds to the bug's activity log and
        # sends a notification.
        cve = getUtility(ICveSet)['1999-8979']
        self.bug.linkCVE(cve, self.user)
        self.saveOldChanges()
        self.bug.unlinkCVE(cve, self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'cves')
        self.assertEqual(activity.target, None)

        cve_unlinked_activity = {
            'person': self.user,
            'whatchanged': 'cve unlinked',
            'oldvalue': cve.sequence,
            'newvalue': None,
            }

        cve_unlinked_notification = {
            'text': (
                '** CVE removed: http://www.cve.mitre.org/'
                'cgi-bin/cvename.cgi?name=1999-8979'),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=cve_unlinked_activity,
            expected_notification=cve_unlinked_notification)

    def test_attachment_added(self):
        # Adding an attachment to a bug adds entries in both BugActivity
        # and BugNotification.
        message = self.factory.makeMessage(owner=self.user)
        self.bug.linkMessage(message)
        self.saveOldChanges()

        attachment = self.factory.makeBugAttachment(
            bug=self.bug, owner=self.user, comment=message)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'attachments')
        self.assertIsNone(activity.target)

        attachment_added_activity = {
            'person': self.user,
            'whatchanged': 'attachment added',
            'oldvalue': None,
            'newvalue': '%s %s' % (
                attachment.title,
                ProxiedLibraryFileAlias(
                    attachment.libraryfile, attachment).http_url),
            }

        attachment_added_notification = {
            'person': self.user,
            'text': '** Attachment added: "%s"\n   %s' % (
                attachment.title,
                ProxiedLibraryFileAlias(
                    attachment.libraryfile, attachment).http_url),
            }

        self.assertRecordedChange(
            expected_notification=attachment_added_notification,
            expected_activity=attachment_added_activity)

    def test_attachment_removed(self):
        # Removing an attachment from a bug adds entries in both BugActivity
        # and BugNotification.
        attachment = self.factory.makeBugAttachment(
            bug=self.bug, owner=self.user)
        self.saveOldChanges()
        download_url = ProxiedLibraryFileAlias(
            attachment.libraryfile, attachment).http_url

        attachment.removeFromBug(user=self.user)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'attachments')
        self.assertEqual(activity.target, None)

        attachment_removed_activity = {
            'person': self.user,
            'whatchanged': 'attachment removed',
            'newvalue': None,
            'oldvalue': '%s %s' % (
                attachment.title, download_url),
            }

        attachment_removed_notification = {
            'person': self.user,
            'text': '** Attachment removed: "%s"\n   %s' % (
                attachment.title, download_url),
            }

        self.assertRecordedChange(
            expected_notification=attachment_removed_notification,
            expected_activity=attachment_removed_activity)

    def test_bugtask_added(self):
        # Adding a bug task adds entries in both BugActivity and
        # BugNotification.
        target = self.factory.makeProduct()
        added_task = self.bug.addTask(self.user, target)
        notify(ObjectCreatedEvent(added_task, user=self.user))

        task_added_activity = {
            'person': self.user,
            'whatchanged': 'bug task added',
            'newvalue': target.bugtargetname,
            }

        task_added_notification = {
            'person': self.user,
            'text': (
                '** Also affects: %s\n'
                '   Importance: %s\n'
                '       Status: %s' % (
                    target.bugtargetname, added_task.importance.title,
                    added_task.status.title)),
            }

        self.assertRecordedChange(
            expected_notification=task_added_notification,
            expected_activity=task_added_activity)

    def test_bugtask_added_with_assignee(self):
        # Adding an assigned bug task adds entries in both BugActivity
        # and BugNotification.
        target = self.factory.makeProduct()
        added_task = self.bug.addTask(self.user, target)
        added_task.transitionToAssignee(self.factory.makePerson())
        notify(ObjectCreatedEvent(added_task, user=self.user))

        task_added_activity = {
            'person': self.user,
            'whatchanged': 'bug task added',
            'newvalue': target.bugtargetname,
            }

        task_added_notification = {
            'person': self.user,
            'text': (
                '** Also affects: %s\n'
                '   Importance: %s\n'
                '     Assignee: %s (%s)\n'
                '       Status: %s' % (
                    target.bugtargetname, added_task.importance.title,
                    added_task.assignee.displayname, added_task.assignee.name,
                    added_task.status.title)),
            }

        self.assertRecordedChange(
            expected_notification=task_added_notification,
            expected_activity=task_added_activity)

    def test_bugtask_added_with_bugwatch(self):
        # Adding a bug task with a bug watch adds entries in both
        # BugActivity and BugNotification.
        target = self.factory.makeProduct()
        bug_watch = self.factory.makeBugWatch(bug=self.bug)
        self.saveOldChanges()
        added_task = self.bug.addTask(self.user, target)
        added_task.bugwatch = bug_watch
        notify(ObjectCreatedEvent(added_task, user=self.user))

        task_added_activity = {
            'person': self.user,
            'whatchanged': 'bug task added',
            'newvalue': target.bugtargetname,
            }

        task_added_notification = {
            'person': self.user,
            'text': (
                '** Also affects: %s via\n'
                '   %s\n'
                '   Importance: %s\n'
                '       Status: %s' % (
                    target.bugtargetname, bug_watch.url,
                    added_task.importance.title, added_task.status.title)),
            }

        self.assertRecordedChange(
            expected_notification=task_added_notification,
            expected_activity=task_added_activity)

    def test_change_bugtask_importance(self):
        # When a bugtask's importance is changed, BugActivity and
        # BugNotification get updated.
        bug_task_before_modification = Snapshot(
            self.bug_task, providing=providedBy(self.bug_task))
        self.bug_task.transitionToImportance(
            BugTaskImportance.HIGH, user=self.user)
        notify(ObjectModifiedEvent(
            self.bug_task, bug_task_before_modification,
            ['importance'], user=self.user))

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'importance')
        self.assertThat(activity.target, StartsWith(u'product-name'))

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: importance' % self.bug_task.bugtargetname,
            'oldvalue': 'Undecided',
            'newvalue': 'High',
            'message': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n   Importance: Undecided => High' %
                self.bug_task.bugtargetname),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_change_bugtask_status(self):
        # When a bugtask's status is changed, BugActivity and
        # BugNotification get updated.
        bug_task_before_modification = Snapshot(
            self.bug_task, providing=providedBy(self.bug_task))
        self.bug_task.transitionToStatus(
            BugTaskStatus.FIXCOMMITTED, user=self.user)
        notify(ObjectModifiedEvent(
            self.bug_task, bug_task_before_modification, ['status'],
            user=self.user))

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: status' % self.bug_task.bugtargetname,
            'oldvalue': 'New',
            'newvalue': 'Fix Committed',
            'message': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n       Status: New => Fix Committed' %
                self.bug_task.bugtargetname),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_target_bugtask_to_product(self):
        # When a bugtask's target is changed, BugActivity and
        # BugNotification get updated.
        bug_task_before_modification = Snapshot(
            self.bug_task, providing=providedBy(self.bug_task))

        new_target = self.factory.makeProduct(owner=self.user)
        self.bug_task.transitionToTarget(new_target, self.user)
        notify(ObjectModifiedEvent(
            self.bug_task, bug_task_before_modification,
            ['target', 'product'], user=self.user))

        expected_activity = {
            'person': self.user,
            'whatchanged': 'affects',
            'oldvalue': bug_task_before_modification.bugtargetname,
            'newvalue': self.bug_task.bugtargetname,
            }

        expected_notification = {
            'text': u"** Project changed: %s => %s" % (
                bug_task_before_modification.bugtargetname,
                self.bug_task.bugtargetname),
            'person': self.user,
            'recipients': [
                self.user, self.product_metadata_subscriber],
            }

        # The person who was subscribed to meta data changes for the old
        # product was notified.
        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_target_bugtask_to_sourcepackage(self):
        # When a bugtask's target is changed, BugActivity and
        # BugNotification get updated.
        target = self.factory.makeDistributionSourcePackage()
        metadata_subscriber = self.newSubscriber(
            target, "dsp-metadata", BugNotificationLevel.METADATA)
        self.newSubscriber(
            target, "dsp-lifecycle", BugNotificationLevel.LIFECYCLE)
        new_target = self.factory.makeDistributionSourcePackage(
            distribution=target.distribution)

        source_package_bug = self.factory.makeBug(owner=self.user)
        source_package_bug_task = source_package_bug.addTask(
            owner=self.user, target=target)
        self.saveOldChanges(source_package_bug)

        bug_task_before_modification = Snapshot(
            source_package_bug_task,
            providing=providedBy(source_package_bug_task))
        source_package_bug_task.transitionToTarget(new_target, self.user)

        notify(ObjectModifiedEvent(
            source_package_bug_task, bug_task_before_modification,
            ['target', 'sourcepackagename'], user=self.user))

        expected_activity = {
            'person': self.user,
            'whatchanged': 'affects',
            'oldvalue': bug_task_before_modification.bugtargetname,
            'newvalue': source_package_bug_task.bugtargetname,
            }

        expected_recipients = [self.user, metadata_subscriber]
        expected_recipients.extend(
            bug_task.pillar.owner
            for bug_task in source_package_bug.bugtasks
            if bug_task.pillar.official_malone)
        expected_notification = {
            'text': u"** Package changed: %s => %s" % (
                bug_task_before_modification.bugtargetname,
                source_package_bug_task.bugtargetname),
            'person': self.user,
            'recipients': expected_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification,
            bug=source_package_bug)

    def test_private_bug_target_change_doesnt_add_everyone(self):
        # Retargeting a private bug doesn't add all subscribers for the
        # target.
        old_product = self.factory.makeProduct()
        new_product = self.factory.makeProduct()
        subscriber = self.factory.makePerson()
        new_product.addBugSubscription(subscriber, subscriber)
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(
            target=old_product, owner=owner,
            information_type=InformationType.USERDATA)
        bug.default_bugtask.transitionToTarget(new_product, owner)
        self.assertNotIn(subscriber, bug.getDirectSubscribers())
        self.assertNotIn(subscriber, bug.getIndirectSubscribers())

    def test_add_bugwatch_to_bugtask(self):
        # Adding a BugWatch to a bug task records an entry in
        # BugActivity and BugNotification.
        bug_watch = self.factory.makeBugWatch()
        self.saveOldChanges()

        self.changeAttribute(self.bug_task, 'bugwatch', bug_watch)

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: remote watch' % self.product.bugtargetname,
            'oldvalue': None,
            'newvalue': bug_watch.title,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n Remote watch: None => %s' % (
                self.bug_task.bugtargetname, bug_watch.title)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_remove_bugwatch_from_bugtask(self):
        # Removing a BugWatch from a bug task records an entry in
        # BugActivity and BugNotification.
        bug_watch = self.factory.makeBugWatch()
        self.changeAttribute(self.bug_task, 'bugwatch', bug_watch)
        self.saveOldChanges()

        self.changeAttribute(self.bug_task, 'bugwatch', None)

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: remote watch' % self.product.bugtargetname,
            'oldvalue': bug_watch.title,
            'newvalue': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n Remote watch: %s => None' % (
                self.bug_task.bugtargetname, bug_watch.title)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_assign_bugtask(self):
        # Assigning a bug task to someone adds entries to the bug
        # activity and notifications sets.
        bug_task_before_modification = Snapshot(
            self.bug_task, providing=providedBy(self.bug_task))

        self.bug_task.transitionToAssignee(self.user)
        notify(ObjectModifiedEvent(
            self.bug_task, bug_task_before_modification,
            ['assignee'], user=self.user))

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: assignee' % self.bug_task.bugtargetname,
            'oldvalue': None,
            'newvalue': self.user.unique_displayname,
            'message': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n'
                u'     Assignee: (unassigned) => %s' % (
                    self.bug_task.bugtargetname,
                    self.user.unique_displayname)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def _test_unassign_bugtask(self, bug_task, expected_recipients):
        # A helper method used by tests for unassigning public and private bug
        # tasks.
        # Unassigning a bug task assigned to someone adds entries to the
        # bug activity and notifications sets.

        old_assignee = bug_task.assignee
        bug_task_before_modification = Snapshot(
            bug_task, providing=providedBy(bug_task))

        bug_task.transitionToAssignee(None)

        notify(ObjectModifiedEvent(
            bug_task, bug_task_before_modification,
            ['assignee'], user=self.user))

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: assignee' % bug_task.bugtargetname,
            'oldvalue': old_assignee.unique_displayname,
            'newvalue': None,
            'message': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n'
                u'     Assignee: %s => (unassigned)' % (
                    bug_task.bugtargetname,
                    old_assignee.unique_displayname)),
            'person': self.user,
            'recipients': expected_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification,
            bug=bug_task.bug)

    def test_unassign_bugtask(self):
        # Test that unassigning a public bug task adds entries to the
        # bug activity and notifications sets.
        old_assignee = self.factory.makePerson()
        self.bug_task.transitionToAssignee(old_assignee)
        self.saveOldChanges()
        # The old assignee got notified about the change, in addition
        # to the default recipients.
        expected_recipients = [
            self.user, self.product_metadata_subscriber, old_assignee]
        self._test_unassign_bugtask(self.bug_task, expected_recipients)

    def test_target_bugtask_to_milestone(self):
        # When a bugtask is targetted to a milestone BugActivity and
        # BugNotification records will be created.
        milestone = self.factory.makeMilestone(product=self.product)
        self.changeAttribute(self.bug_task, 'milestone', milestone)

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: milestone' % self.bug_task.bugtargetname,
            'oldvalue': None,
            'newvalue': milestone.name,
            'message': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n    Milestone: None => %s' % (
                self.bug_task.bugtargetname, milestone.name)),
            'person': self.user,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_untarget_bugtask_from_milestone(self):
        # When a bugtask is untargetted from a milestone both
        # BugActivity and BugNotification records will be created.
        milestone = self.factory.makeMilestone(product=self.product)
        self.changeAttribute(self.bug_task, 'milestone', milestone)
        self.saveOldChanges()
        old_milestone_subscriber = self.factory.makePerson()
        milestone.addBugSubscription(
            old_milestone_subscriber, old_milestone_subscriber)

        self.changeAttribute(self.bug_task, 'milestone', None)

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: milestone' % self.bug_task.bugtargetname,
            'newvalue': None,
            'oldvalue': milestone.name,
            'message': None,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n    Milestone: %s => None' % (
                self.bug_task.bugtargetname, milestone.name)),
            'person': self.user,
            'recipients': [
                self.user, self.product_metadata_subscriber,
                old_milestone_subscriber,
                ],
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_change_bugtask_milestone(self):
        # When a bugtask is retargeted from one milestone to another,
        # both BugActivity and BugNotification records are created.
        old_milestone = self.factory.makeMilestone(product=self.product)
        old_milestone_subscriber = self.factory.makePerson()
        old_milestone.addBugSubscription(
            old_milestone_subscriber, old_milestone_subscriber)
        new_milestone = self.factory.makeMilestone(product=self.product)
        new_milestone_subscriber = self.factory.makePerson()
        new_milestone.addBugSubscription(
            new_milestone_subscriber, new_milestone_subscriber)

        self.changeAttribute(self.bug_task, 'milestone', old_milestone)
        self.saveOldChanges()
        self.changeAttribute(self.bug_task, 'milestone', new_milestone)

        expected_activity = {
            'person': self.user,
            'whatchanged': '%s: milestone' % self.bug_task.bugtargetname,
            'newvalue': new_milestone.name,
            'oldvalue': old_milestone.name,
            }

        expected_notification = {
            'text': (
                u'** Changed in: %s\n'
                u'    Milestone: %s => %s' % (
                    self.bug_task.bugtargetname,
                    old_milestone.name, new_milestone.name)),
            'person': self.user,
            'recipients': [
                self.user, self.product_metadata_subscriber,
                old_milestone_subscriber, new_milestone_subscriber,
                ],
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_bugtask_deleted(self):
        # Deleting a bug task adds entries in both BugActivity and
        # BugNotification.
        target = self.factory.makeProduct()
        task_to_delete = self.bug.addTask(self.user, target)
        self.saveOldChanges()

        login_person(self.user)
        task_to_delete.delete()

        task_deleted_activity = {
            'person': self.user,
            'whatchanged': 'bug task deleted',
            'oldvalue': target.bugtargetname,
            }

        task_deleted_notification = {
            'person': self.user,
            'text': (
                "** No longer affects: %s" % target.bugtargetname),
            }

        self.assertRecordedChange(
            expected_notification=task_deleted_notification,
            expected_activity=task_deleted_activity)

    def test_product_series_nominated(self):
        # Nominating a bug to be fixed in a product series adds an item
        # to the activity log only.
        product = self.factory.makeProduct()
        series = self.factory.makeProductSeries(product=product)
        self.bug.addTask(self.user, product)
        self.saveOldChanges()

        nomination = self.bug.addNomination(self.user, series)
        self.assertFalse(nomination.isApproved())

        expected_activity = {
            'person': self.user,
            'whatchanged': 'nominated for series',
            'newvalue': series.bugtargetname,
            }

        self.assertRecordedChange(expected_activity=expected_activity)

    def test_distro_series_nominated(self):
        # Nominating a bug to be fixed in a product series adds an item
        # to the activity log only.
        distribution = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distribution)
        self.bug.addTask(self.user, distribution)
        self.saveOldChanges()

        nomination = self.bug.addNomination(self.user, series)
        self.assertFalse(nomination.isApproved())

        expected_activity = {
            'person': self.user,
            'whatchanged': 'nominated for series',
            'newvalue': series.bugtargetname,
            }

        self.assertRecordedChange(expected_activity=expected_activity)

    def test_nomination_approved(self):
        # When a nomination is approved, it's like adding a new bug
        # task for the series directly.
        product = self.factory.makeProduct()
        product.driver = product.owner
        series = self.factory.makeProductSeries(product=product)
        self.bug.addTask(self.user, product)

        nomination = self.bug.addNomination(self.user, series)
        self.assertFalse(nomination.isApproved())
        self.saveOldChanges()
        nomination.approve(product.owner)

        expected_activity = {
            'person': product.owner,
            'newvalue': series.bugtargetname,
            'whatchanged': 'bug task added',
            'newvalue': series.bugtargetname,
            }

        task_added_notification = {
            'person': product.owner,
            'text': (
                '** Also affects: %s\n'
                '   Importance: Undecided\n'
                '       Status: New' % (
                    series.bugtargetname)),
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=task_added_notification)

    def test_marked_as_duplicate(self):
        # When a bug is marked as a duplicate, activity is recorded
        # and a notification is sent.
        duplicate_bug = self.factory.makeBug()
        self.saveOldChanges(duplicate_bug)
        self.saveOldChanges(self.bug, append=True)
        # Save the initial "bug created" notifications before
        # marking this bug a duplicate, so that we don't get
        # extra notifications by mistake.
        duplicate_bug_recipients = duplicate_bug.getBugNotificationRecipients(
            level=BugNotificationLevel.METADATA).getRecipients()
        self.changeAttribute(duplicate_bug, 'duplicateof', self.bug)

        # This checks the activity's attribute and target attributes.
        activity = duplicate_bug.activity[-1]
        self.assertEqual(activity.attribute, 'duplicateof')
        self.assertEqual(activity.target, None)

        expected_activity = {
            'person': self.user,
            'whatchanged': 'marked as duplicate',
            'oldvalue': None,
            'newvalue': str(self.bug.id),
            }

        expected_notification = {
            'person': self.user,
            'text': ("** This bug has been marked a duplicate of bug %d\n"
                     "   %s" % (self.bug.id, self.bug.title)),
            'recipients': duplicate_bug_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification,
            bug=duplicate_bug)

        # Ensure that only the people subscribed to the bug that
        # gets marked as a duplicate are notified.
        master_notifications = BugNotification.selectBy(
            bug=self.bug, orderBy='id')
        new_notifications = [
            notification for notification in master_notifications
            if notification.id not in self.old_notification_ids]
        self.assertEqual(len(list(new_notifications)), 0)

    def test_unmarked_as_duplicate(self):
        # When a bug is unmarked as a duplicate, activity is recorded
        # and a notification is sent.
        duplicate_bug = self.factory.makeBug()
        duplicate_bug_recipients = duplicate_bug.getBugNotificationRecipients(
            level=BugNotificationLevel.METADATA).getRecipients()
        duplicate_bug.markAsDuplicate(self.bug)
        self.saveOldChanges(duplicate_bug)
        self.changeAttribute(duplicate_bug, 'duplicateof', None)

        # This checks the activity's attribute and target attributes.
        activity = duplicate_bug.activity[-1]
        self.assertEqual(activity.attribute, 'duplicateof')
        self.assertEqual(activity.target, None)

        expected_activity = {
            'person': self.user,
            'whatchanged': 'removed duplicate marker',
            'oldvalue': str(self.bug.id),
            'newvalue': None,
            }

        expected_notification = {
            'person': self.user,
            'text': ("** This bug is no longer a duplicate of bug %d\n"
                     "   %s" % (self.bug.id, self.bug.title)),
            'recipients': duplicate_bug_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification,
            bug=duplicate_bug)

    def test_changed_duplicate(self):
        # When a bug is changed from being a duplicate of one bug to
        # being a duplicate of another, activity is recorded and a
        # notification is sent.
        bug_one = self.factory.makeBug()
        bug_two = self.factory.makeBug()
        bug_recipients = self.bug.getBugNotificationRecipients(
            level=BugNotificationLevel.METADATA).getRecipients()
        self.bug.markAsDuplicate(bug_one)
        self.saveOldChanges()
        self.changeAttribute(self.bug, 'duplicateof', bug_two)

        # This checks the activity's attribute and target attributes.
        activity = self.bug.activity[-1]
        self.assertEqual(activity.attribute, 'duplicateof')
        self.assertEqual(activity.target, None)

        expected_activity = {
            'person': self.user,
            'whatchanged': 'changed duplicate marker',
            'oldvalue': str(bug_one.id),
            'newvalue': str(bug_two.id),
            }

        expected_notification = {
            'person': self.user,
            'text': ("** This bug is no longer a duplicate of bug %d\n"
                     "   %s\n"
                     "** This bug has been marked a duplicate of bug %d\n"
                     "   %s" % (bug_one.id, bug_one.title,
                                bug_two.id, bug_two.title)),
            'recipients': bug_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification)

    def test_duplicate_private_bug(self):
        # When a bug is marked as the duplicate of a private bug the
        # private bug's summary won't be included in the notification.
        private_bug = self.factory.makeBug()
        private_bug.setPrivate(True, self.user)
        public_bug = self.factory.makeBug()
        self.saveOldChanges(private_bug)
        self.saveOldChanges(public_bug)

        # Save the initial "bug created" notifications before
        # marking this bug a duplicate, so that we don't get
        # extra notifications by mistake.
        public_bug_recipients = public_bug.getBugNotificationRecipients(
            level=BugNotificationLevel.METADATA).getRecipients()
        self.changeAttribute(public_bug, 'duplicateof', private_bug)

        # This checks the activity's attribute and target attributes.
        activity = public_bug.activity[-1]
        self.assertEqual(activity.attribute, 'duplicateof')
        self.assertEqual(activity.target, None)

        expected_activity = {
            'person': self.user,
            'whatchanged': 'marked as duplicate',
            'oldvalue': None,
            'newvalue': str(private_bug.id),
            }

        expected_notification = {
            'person': self.user,
            'text': (
                "** This bug has been marked a duplicate of private bug %d"
                % private_bug.id),
            'recipients': public_bug_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification,
            bug=public_bug)

    def test_unmarked_as_duplicate_of_private_bug(self):
        # When a bug is unmarked as a duplicate of a private bug,
        # the private bug's summary isn't sent in the notification.
        private_bug = self.factory.makeBug()
        private_bug.setPrivate(True, self.user)
        public_bug = self.factory.makeBug()

        # Save the initial "bug created" notifications before
        # marking this bug a duplicate, so that we don't get
        # extra notifications by mistake.
        public_bug_recipients = public_bug.getBugNotificationRecipients(
            level=BugNotificationLevel.METADATA).getRecipients()
        self.changeAttribute(public_bug, 'duplicateof', private_bug)

        self.saveOldChanges(private_bug)
        self.saveOldChanges(public_bug)

        self.changeAttribute(public_bug, 'duplicateof', None)

        # This checks the activity's attribute and target attributes.
        activity = public_bug.activity[-1]
        self.assertEqual(activity.attribute, 'duplicateof')
        self.assertEqual(activity.target, None)

        expected_activity = {
            'person': self.user,
            'whatchanged': 'removed duplicate marker',
            'oldvalue': str(private_bug.id),
            'newvalue': None,
            }

        expected_notification = {
            'person': self.user,
            'text': (
                "** This bug is no longer a duplicate of private bug %d"
                % private_bug.id),
            'recipients': public_bug_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification,
            bug=public_bug)

    def test_changed_private_duplicate(self):
        # When a bug is change from being the duplicate of a private bug
        # to being the duplicate of a public bug, the private bug's
        # summary won't be sent in the notification.
        private_bug = self.factory.makeBug()
        private_bug.setPrivate(True, self.user)
        duplicate_bug = self.factory.makeBug()
        public_bug = self.factory.makeBug()
        bug_recipients = duplicate_bug.getBugNotificationRecipients(
            level=BugNotificationLevel.METADATA).getRecipients()

        self.changeAttribute(duplicate_bug, 'duplicateof', private_bug)
        self.saveOldChanges(duplicate_bug)

        self.changeAttribute(duplicate_bug, 'duplicateof', public_bug)

        # This checks the activity's attribute and target attributes.
        activity = duplicate_bug.activity[-1]
        self.assertEqual(activity.attribute, 'duplicateof')
        self.assertEqual(activity.target, None)

        expected_activity = {
            'person': self.user,
            'whatchanged': 'changed duplicate marker',
            'oldvalue': str(private_bug.id),
            'newvalue': str(public_bug.id),
            }

        expected_notification = {
            'person': self.user,
            'text': (
                "** This bug is no longer a duplicate of private bug %d\n"
                "** This bug has been marked a duplicate of bug %d\n"
                "   %s" % (private_bug.id, public_bug.id,
                           public_bug.title)),
            'recipients': bug_recipients,
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification, bug=duplicate_bug)

    def test_convert_to_question_no_comment(self):
        # When a bug task is converted to a question, its status is
        # first set to invalid, which causes the normal notifications for
        # that to be added to the activity log and sent out as e-mail
        # notification. After that another item is added to the activity
        # log saying that the bug was converted to a question.
        self.product.official_answers = True
        self.bug.convertToQuestion(self.user)
        converted_question = self.bug.getQuestionCreatedFromBug()

        conversion_activity = {
            'person': self.user,
            'whatchanged': 'converted to question',
            'newvalue': str(converted_question.id),
            }
        status_activity = {
            'person': self.user,
            'whatchanged': '%s: status' % self.bug_task.bugtargetname,
            'newvalue': 'Invalid',
            'oldvalue': 'New',
            }

        conversion_notification = {
            'person': self.user,
            'text': (
                '** Converted to question:\n'
                '   %s' % canonical_url(converted_question)),
            }
        status_notification = {
            'text': (
                '** Changed in: %s\n'
                '       Status: New => Invalid' %
                self.bug_task.bugtargetname),
            'person': self.user,
            'recipients': self.bug.getBugNotificationRecipients(
                level=BugNotificationLevel.LIFECYCLE),
            }

        self.assertRecordedChange(
            expected_activity=[status_activity, conversion_activity],
            expected_notification=[status_notification,
                                   conversion_notification])

    def test_create_bug(self):
        # When a bug is created, activity is recorded and a comment
        # notification is sent.
        new_bug = self.factory.makeBug(
            target=self.product, owner=self.user, comment="ENOTOWEL")

        expected_activity = {
            'person': self.user,
            'whatchanged': 'bug',
            'message': u"added bug",
            }

        expected_notification = {
            'person': self.user,
            'text': u"ENOTOWEL",
            'is_comment': True,
            'recipients': new_bug.getBugNotificationRecipients(
                level=BugNotificationLevel.COMMENTS),
            }

        self.assertRecordedChange(
            expected_activity=expected_activity,
            expected_notification=expected_notification, bug=new_bug)

    def test_description_changed_no_self_email(self):
        # Users who have selfgenerated_bugnotifications set to False
        # do not get any bug email that they generated themselves.
        self.user.selfgenerated_bugnotifications = False

        self.changeAttribute(
            self.bug, 'description', 'New description')

        # self.user is not included among the recipients.
        self.assertRecipients(
            [self.product_metadata_subscriber])

    def test_description_changed_no_self_email_indirect(self):
        # Users who have selfgenerated_bugnotifications set to False
        # do not get any bug email that they generated themselves,
        # even if a subscription is through a team membership.
        team = self.factory.makeTeam()
        team.addMember(self.user, team.teamowner)
        self.bug.subscribe(team, self.user)

        self.user.selfgenerated_bugnotifications = False

        self.changeAttribute(
            self.bug, 'description', 'New description')

        # self.user is not included among the recipients.
        self.assertRecipients(
            [self.product_metadata_subscriber, team.teamowner])

    def test_description_changed_no_muted_email(self):
        # Users who have muted a bug do not get any bug email for a bug,
        # even if they are subscribed through a team membership.
        team = self.factory.makeTeam()
        team.addMember(self.user, team.teamowner)
        self.bug.subscribe(team, self.user)
        self.bug.mute(self.user, self.user)

        self.changeAttribute(
            self.bug, 'description', 'New description')

        # self.user is not included among the recipients.
        self.assertRecipients(
            [self.product_metadata_subscriber, team.teamowner])

    def test_no_lifecycle_email_despite_structural_subscription(self):
        # If a person has a structural METADATA subscription,
        # and a direct LIFECYCLE subscription, they should
        # get no emails for a non-LIFECYCLE change (bug 713382).
        self.bug.subscribe(
            self.product_metadata_subscriber, self.product_metadata_subscriber,
            level=BugNotificationLevel.LIFECYCLE)
        self.changeAttribute(
            self.bug, 'description', 'New description')

        # self.product_metadata_subscriber is not included among the
        # recipients.
        self.assertRecipients([self.user])
