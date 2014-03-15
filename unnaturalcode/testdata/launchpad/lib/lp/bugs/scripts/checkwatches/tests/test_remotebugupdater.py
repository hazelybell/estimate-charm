# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the checkwatches remotebugupdater module."""

__metaclass__ = type

import transaction

from lp.bugs.externalbugtracker.base import (
    UnknownRemoteImportanceError,
    UnknownRemoteStatusError,
    )
from lp.bugs.externalbugtracker.bugzilla import Bugzilla
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.scripts.checkwatches.core import CheckwatchesMaster
from lp.bugs.scripts.checkwatches.remotebugupdater import RemoteBugUpdater
from lp.bugs.tests.externalbugtracker import TestExternalBugTracker
from lp.services.log.logger import BufferLogger
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class StatusConvertingExternalBugTracker(TestExternalBugTracker):

    def convertRemoteStatus(self, remote_status):
        if remote_status == 'new':
            return BugTaskStatus.NEW
        else:
            raise UnknownRemoteStatusError(remote_status)


class ImportanceConvertingExternalBugTracker(TestExternalBugTracker):

    def convertRemoteImportance(self, remote_importance):
        if remote_importance == 'low':
            return BugTaskImportance.LOW
        else:
            raise UnknownRemoteImportanceError(remote_importance)


class RemoteBugUpdaterTestCase(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def makeUpdater(self, remote_system=None, remote_bug_id=None,
                    bug_watch_ids=None, unmodified_remote_ids=None,
                    logger=None):
        checkwatches_master = CheckwatchesMaster(transaction)
        if logger is not None:
            checkwatches_master.logger = logger
        return checkwatches_master.remote_bug_updater_factory(
            checkwatches_master, remote_system, remote_bug_id,
            bug_watch_ids, unmodified_remote_ids, None)

    def test_create(self):
        # CheckwatchesMaster.remote_bug_updater_factory points to the
        # RemoteBugUpdater class, so it can be used to create
        # RemoteBugUpdaters.
        remote_system = Bugzilla('http://example.com')
        remote_bug_id = '42'
        bug_watch_ids = [1, 2]
        unmodified_remote_ids = ['76']
        updater = self.makeUpdater(
            remote_system, remote_bug_id, bug_watch_ids,
            unmodified_remote_ids)
        self.assertTrue(
            isinstance(updater, RemoteBugUpdater),
            "updater should be an instance of RemoteBugUpdater.")
        self.assertEqual(
            remote_system, updater.external_bugtracker,
            "Unexpected external_bugtracker for RemoteBugUpdater.")
        self.assertEqual(
            remote_bug_id, updater.remote_bug,
            "RemoteBugUpdater's remote_bug should be '%s', was '%s'" %
            (remote_bug_id, updater.remote_bug))
        self.assertEqual(
            bug_watch_ids, updater.bug_watch_ids,
            "RemoteBugUpdater's bug_watch_ids should be '%s', were '%s'" %
            (bug_watch_ids, updater.bug_watch_ids))
        self.assertEqual(
            unmodified_remote_ids, updater.unmodified_remote_ids,
            "RemoteBugUpdater's unmodified_remote_ids should be '%s', "
            "were '%s'" %
            (unmodified_remote_ids, updater.unmodified_remote_ids))

    def test_convertRemoteStatus(self):
        updater = self.makeUpdater(
            remote_system=StatusConvertingExternalBugTracker())
        self.assertEqual(
            BugTaskStatus.NEW, updater._convertRemoteStatus('new'))

    def test_convertRemoteStatus_logs_unknown_values(self):
        updater = self.makeUpdater(
            remote_system=StatusConvertingExternalBugTracker(),
            remote_bug_id=42,
            logger=BufferLogger())
        self.assertEqual(
            BugTaskStatus.UNKNOWN, updater._convertRemoteStatus('spam'))
        self.assertEqual(
            "INFO Unknown remote status 'spam' for bug 42 on "
            "http://example.com.\n", updater.logger.getLogBuffer())

    def test_convertRemoteImportance(self):
        updater = self.makeUpdater(
            remote_system=ImportanceConvertingExternalBugTracker())
        self.assertEqual(
            BugTaskImportance.LOW, updater._convertRemoteImportance('low'))

    def test_convertRemoteImportance_logs_unknown_values(self):
        updater = self.makeUpdater(
            remote_system=ImportanceConvertingExternalBugTracker(),
            remote_bug_id=42,
            logger=BufferLogger())
        self.assertEqual(
            BugTaskImportance.UNKNOWN,
            updater._convertRemoteImportance('spam'))
        self.assertEqual(
            "INFO Unknown remote importance 'spam' for bug 42 on "
            "http://example.com.\n", updater.logger.getLogBuffer())
