# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the checkwatches.bugwatchupdater module."""

__metaclass__ = type

from datetime import datetime

import transaction

from lp.bugs.externalbugtracker.base import BugWatchUpdateError
from lp.bugs.externalbugtracker.bugzilla import BugzillaAPI
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.bugwatch import BugWatchActivityStatus
from lp.bugs.scripts.checkwatches.bugwatchupdater import BugWatchUpdater
from lp.bugs.scripts.checkwatches.core import CheckwatchesMaster
from lp.bugs.scripts.checkwatches.remotebugupdater import RemoteBugUpdater
from lp.bugs.tests.externalbugtracker import TestExternalBugTracker
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


def make_bug_watch_updater(checkwatches_master, bug_watch,
                           external_bugtracker, server_time=None,
                           can_import_comments=False,
                           can_push_comments=False, can_back_link=False):
    """Helper function to create a BugWatchUpdater instance."""
    if server_time is None:
        server_time = datetime.now()

    remote_bug_updater = checkwatches_master.remote_bug_updater_factory(
        checkwatches_master, external_bugtracker, bug_watch.remotebug,
        [bug_watch.id], [], server_time)

    bug_watch_updater = BugWatchUpdater(
        remote_bug_updater, bug_watch,
        remote_bug_updater.external_bugtracker)

    bug_watch_updater.can_import_comments = can_import_comments
    bug_watch_updater.can_push_comments = can_push_comments
    bug_watch_updater.can_back_link = can_back_link

    return bug_watch_updater


class BrokenCommentSyncingExternalBugTracker(TestExternalBugTracker):
    """An ExternalBugTracker that can't sync comments.

    Its exceptions are not known, so it should generate OOPSes.
    """

    import_comments_error_message = "Can't import comments, sorry."
    push_comments_error_message = "Can't push comments, sorry."
    back_link_error_message = "Can't back link, sorry."

    def getCommentIds(self, remote_bug_id):
        raise Exception(self.import_comments_error_message)

    def addRemoteComment(self, remote_bug_id, formatted_comment, message_id):
        raise Exception(self.push_comments_error_message)

    def getLaunchpadBugId(self, remote_bug):
        raise Exception(self.back_link_error_message)


class KnownBrokenCommentSyncingExternalBugTracker(TestExternalBugTracker):
    """An ExternalBugTracker that fails in a known manner.

    It should not generate OOPSes.
    """

    import_comments_error_message = "Can't import comments, sorry."

    def getCommentIds(self, remote_bug_id):
        raise BugWatchUpdateError(self.import_comments_error_message)


class LoggingBugWatchUpdater(BugWatchUpdater):
    """A BugWatchUpdater that logs what's going on."""

    import_bug_comments_called = False
    push_bug_comments_called = False
    link_launchpad_bug_called = False

    def importBugComments(self):
        self.import_bug_comments_called = True

    def pushBugComments(self):
        self.push_bug_comments_called = True

    def linkLaunchpadBug(self):
        self.link_launchpad_bug_called = True


class BugWatchUpdaterTestCase(TestCaseWithFactory):
    """Tests the functionality of the BugWatchUpdater class."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(BugWatchUpdaterTestCase, self).setUp()
        self.checkwatches_master = CheckwatchesMaster(transaction)
        self.bug_task = self.factory.makeBugTask()
        self.bug_watch = self.factory.makeBugWatch(bug_task=self.bug_task)

    def _checkLastErrorAndMessage(self, expected_last_error,
                                  expected_message, want_oops=True):
        """Check the latest activity and last_error_type for a BugWatch."""
        latest_activity = self.bug_watch.activity[0]
        self.assertEqual(expected_last_error, self.bug_watch.last_error_type)
        self.assertEqual(expected_last_error, latest_activity.result)
        self.assertEqual(expected_message, latest_activity.message)
        if want_oops:
            self.assertIsNot(None, latest_activity.oops_id)
        else:
            self.assertIs(None, latest_activity.oops_id)

    def test_updateBugWatch(self):
        # Calling BugWatchUpdater.updateBugWatch() will update the
        # updater's current BugWatch.
        bug_watch_updater = make_bug_watch_updater(
            self.checkwatches_master, self.bug_watch,
            TestExternalBugTracker('http://example.com'))

        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW',
            BugTaskImportance.LOW)

        self.assertEqual('FIXED', self.bug_watch.remotestatus)
        self.assertEqual(BugTaskStatus.FIXRELEASED, self.bug_task.status)
        self.assertEqual('LOW', self.bug_watch.remote_importance)
        self.assertEqual(BugTaskImportance.LOW, self.bug_task.importance)
        self.assertEqual(None, self.bug_watch.last_error_type)

        latest_activity = self.bug_watch.activity[0]
        self.assertEqual(
            BugWatchActivityStatus.SYNC_SUCCEEDED, latest_activity.result)

    def test_importBugComments_error_handling(self):
        # If an error occurs when importing bug comments, it will be
        # recorded as BugWatchActivityStatus.COMMENT_IMPORT_FAILED.
        external_bugtracker = BrokenCommentSyncingExternalBugTracker(
            'http://example.com')
        bug_watch_updater = make_bug_watch_updater(
            self.checkwatches_master, self.bug_watch, external_bugtracker,
            can_import_comments=True)

        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW',
            BugTaskImportance.LOW)

        self._checkLastErrorAndMessage(
            BugWatchActivityStatus.COMMENT_IMPORT_FAILED,
            external_bugtracker.import_comments_error_message)

    def test_pushBugComments_error_handling(self):
        # If an error occurs when pushing bug comments, it will be
        # recorded as BugWatchActivityStatus.COMMENT_IMPORT_FAILED.
        external_bugtracker = BrokenCommentSyncingExternalBugTracker(
            'http://example.com')
        bug_watch_updater = make_bug_watch_updater(
            self.checkwatches_master, self.bug_watch, external_bugtracker,
            can_push_comments=True)

        self.factory.makeBugComment(
            bug=self.bug_task.bug, bug_watch=self.bug_watch)

        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW',
            BugTaskImportance.LOW)

        self._checkLastErrorAndMessage(
            BugWatchActivityStatus.COMMENT_PUSH_FAILED,
            external_bugtracker.push_comments_error_message)

    def test_linkLaunchpadBug_error_handling(self):
        # If an error occurs when linking back to a remote bug, it will
        # be recorded as BugWatchActivityStatus.BACKLINK_FAILED.
        external_bugtracker = BrokenCommentSyncingExternalBugTracker(
            'http://example.com')
        bug_watch_updater = make_bug_watch_updater(
            self.checkwatches_master, self.bug_watch, external_bugtracker,
            can_back_link=True)

        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW',
            BugTaskImportance.LOW)

        self._checkLastErrorAndMessage(
            BugWatchActivityStatus.BACKLINK_FAILED,
            external_bugtracker.back_link_error_message)

    def test_known_error_handling(self):
        # Some errors are known to be the remote end's fault, and should
        # not generate OOPSes. These are still logged in
        # BugWatchActivity.
        external_bugtracker = KnownBrokenCommentSyncingExternalBugTracker(
            'http://example.com')
        bug_watch_updater = make_bug_watch_updater(
            self.checkwatches_master, self.bug_watch, external_bugtracker,
            can_import_comments=True)

        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW',
            BugTaskImportance.LOW)

        self._checkLastErrorAndMessage(
            BugWatchActivityStatus.COMMENT_IMPORT_FAILED,
            external_bugtracker.import_comments_error_message,
            want_oops=False)

    def test_comment_bools_inherited(self):
        # BugWatchUpdater.updateBugWatches() doesn't have to be passed
        # values for can_import_comments, can_push_comments and
        # can_back_link. Instead, these can be taken from the parent
        # object passed to it upon instantiation, usually a
        # RemoteBugUpdater.
        # XXX 2010-05-11 gmb bug=578714:
        #     This test can be removed when bug 578714 is fixed.
        remote_bug_updater = RemoteBugUpdater(
            self.checkwatches_master,
            BugzillaAPI("http://example.com"),
            self.bug_watch.remotebug, [self.bug_watch.id],
            [], datetime.now())
        bug_watch_updater = LoggingBugWatchUpdater(
            remote_bug_updater, self.bug_watch,
            remote_bug_updater.external_bugtracker)

        # If all the can_* properties of remote_bug_updater are True,
        # bug_watch_updater will attempt to import, push and backlink.
        self.assertTrue(remote_bug_updater.can_import_comments)
        self.assertTrue(remote_bug_updater.can_push_comments)
        self.assertTrue(remote_bug_updater.can_back_link)
        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW', BugTaskImportance.LOW)

        self.assertTrue(bug_watch_updater.import_bug_comments_called)
        self.assertTrue(bug_watch_updater.push_bug_comments_called)
        self.assertTrue(bug_watch_updater.link_launchpad_bug_called)

        # Otherwise, bug_watch_updater won't attempt those functions
        # whose can_* properties are False.
        remote_bug_updater.can_import_comments = False
        remote_bug_updater.can_push_comments = False
        remote_bug_updater.can_back_link = False
        bug_watch_updater = LoggingBugWatchUpdater(
            remote_bug_updater, self.bug_watch,
            remote_bug_updater.external_bugtracker)
        bug_watch_updater.updateBugWatch(
            'FIXED', BugTaskStatus.FIXRELEASED, 'LOW', BugTaskImportance.LOW)

        self.assertFalse(bug_watch_updater.import_bug_comments_called)
        self.assertFalse(bug_watch_updater.push_bug_comments_called)
        self.assertFalse(bug_watch_updater.link_launchpad_bug_called)
