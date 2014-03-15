# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Checkwatches unit tests."""

__metaclass__ = type

from datetime import datetime
import threading
import unittest
from xmlrpclib import ProtocolError

import transaction
from zope.component import getUtility

from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.externalbugtracker.bugzilla import BugzillaAPI
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTaskSet,
    )
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTrackerSet,
    )
from lp.bugs.interfaces.bugwatch import BugWatchActivityStatus
from lp.bugs.scripts import checkwatches
from lp.bugs.scripts.checkwatches.base import WorkingBase
from lp.bugs.scripts.checkwatches.core import (
    CheckwatchesMaster,
    LOGIN,
    TwistedThreadScheduler,
    )
from lp.bugs.scripts.checkwatches.remotebugupdater import RemoteBugUpdater
from lp.bugs.tests.externalbugtracker import (
    new_bugtracker,
    TestBugzillaAPIXMLRPCTransport,
    TestExternalBugTracker,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.testing import (
    login,
    TestCaseWithFactory,
    ZopeTestInSubProcess,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class BugzillaAPIWithoutProducts(BugzillaAPI):
    """None of the remote bugs have products."""

    def getProductsForRemoteBugs(self, remote_bug_ids):
        return {}


def always_BugzillaAPIWithoutProducts_get_external_bugtracker(bugtracker):
    """get_external_bugtracker that returns BugzillaAPIWithoutProducts."""
    return BugzillaAPIWithoutProducts(bugtracker.baseurl)


class NonConnectingBugzillaAPI(BugzillaAPI):
    """A non-connected version of the BugzillaAPI ExternalBugTracker."""

    bugs = {
        1: {'product': 'test-product'},
        }

    def getCurrentDBTime(self):
        return None

    def getExternalBugTrackerToUse(self):
        return self


class NoBugWatchesByRemoteBugUpdater(RemoteBugUpdater):
    """A subclass of RemoteBugUpdater with methods overridden for testing."""

    def _getBugWatchesForRemoteBug(self):
        """Return an empty list.

        This method overrides _getBugWatchesForRemoteBug() so that bug
        497141 can be regression-tested.
        """
        return []


class TestCheckwatchesWithSyncableGnomeProducts(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestCheckwatchesWithSyncableGnomeProducts, self).setUp()
        transaction.commit()

        # We monkey-patch externalbugtracker.get_external_bugtracker()
        # so that it always returns what we want.
        self.original_get_external_bug_tracker = (
            checkwatches.core.externalbugtracker.get_external_bugtracker)
        checkwatches.core.externalbugtracker.get_external_bugtracker = (
            always_BugzillaAPIWithoutProducts_get_external_bugtracker)

        # Create an updater with a limited set of syncable gnome
        # products.
        self.updater = checkwatches.CheckwatchesMaster(
            transaction.manager, BufferLogger(), ['test-product'])

    def tearDown(self):
        checkwatches.externalbugtracker.get_external_bugtracker = (
            self.original_get_external_bug_tracker)
        super(TestCheckwatchesWithSyncableGnomeProducts, self).tearDown()

    def test_bug_496988(self):
        # Regression test for bug 496988. KeyErrors when looking for the
        # remote product for a given bug shouldn't travel upwards and
        # cause the script to abort.
        gnome_bugzilla = getUtility(ILaunchpadCelebrities).gnome_bugzilla
        bug_watch_1 = self.factory.makeBugWatch(
            remote_bug=1, bugtracker=gnome_bugzilla)
        bug_watch_2 = self.factory.makeBugWatch(
            remote_bug=2, bugtracker=gnome_bugzilla)

        # The bug watch updater expects to begin and end all
        # transactions.
        transaction.commit()

        # Calling this method shouldn't raise a KeyError, even though
        # there's no bug 2 on the bug tracker that we pass to it.
        self.updater._getExternalBugTrackersAndWatches(
            gnome_bugzilla, [bug_watch_1, bug_watch_2])

    def test__getExternalBugTrackersAndWatches(self):
        # When there are no syncable products defined, only one remote
        # system should be returned, and it should have been modified
        # to disable comment syncing
        gnome_bugzilla = getUtility(ILaunchpadCelebrities).gnome_bugzilla
        transaction.commit()
        # If there are syncable GNOME products set, two remote systems
        # are returned from _getExternalBugTrackersAndWatches().
        remote_systems_and_watches = (
            self.updater._getExternalBugTrackersAndWatches(
                gnome_bugzilla, []))
        self.failUnlessEqual(2, len(remote_systems_and_watches))
        # One will have comment syncing enabled.
        self.failUnless(
            any(remote_system.sync_comments
                for (remote_system, watches) in remote_systems_and_watches))
        # One will have comment syncing disabled.
        self.failUnless(
            any(not remote_system.sync_comments
                for (remote_system, watches) in remote_systems_and_watches))
        # When there are no syncable products, only one remote system
        # is returned, and comment syncing is disabled.
        self.updater._syncable_gnome_products = []
        remote_systems_and_watches = (
            self.updater._getExternalBugTrackersAndWatches(
                gnome_bugzilla, []))
        self.failUnlessEqual(1, len(remote_systems_and_watches))
        [(remote_system, watches)] = remote_systems_and_watches
        self.failIf(remote_system.sync_comments)


class BrokenCheckwatchesMaster(CheckwatchesMaster):

    error_code = None

    def _getExternalBugTrackersAndWatches(self, bug_tracker, bug_watches):
        raise ProtocolError(
            "http://example.com/", self.error_code, "Borked", "")


class TestCheckwatchesMaster(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestCheckwatchesMaster, self).setUp()
        transaction.abort()

    def test_bug_497141(self):
        # Regression test for bug 497141. KeyErrors raised in
        # RemoteBugUpdater.updateRemoteBug() shouldn't cause
        # checkwatches to abort.
        (bug_tracker, bug_watches) = self.factory.makeBugTrackerWithWatches()

        # Use a test XML-RPC transport to ensure no connections happen.
        test_transport = TestBugzillaAPIXMLRPCTransport(bug_tracker.baseurl)
        remote_system = NonConnectingBugzillaAPI(
            bug_tracker.baseurl, xmlrpc_transport=test_transport)

        working_base = WorkingBase()
        working_base.init(LOGIN, transaction.manager, BufferLogger())

        for bug_watch in bug_watches:
            # we want to know that an oops was raised
            oops_count = len(self.oopses)
            updater = NoBugWatchesByRemoteBugUpdater(
                working_base, remote_system, bug_watch.remotebug,
                [bug_watch.id], [], datetime.now())

            # Calling updateRemoteBug() shouldn't raise a KeyError,
            # even though with our broken updater
            # _getExternalBugTrackersAndWatches() will return an empty
            # dict.
            updater.updateRemoteBug()

            # A single oops will have been logged instead of the KeyError
            # being raised.
            self.assertEqual(oops_count + 1, len(self.oopses))
            last_oops = self.oopses[-1]
            self.assertStartsWith(
                last_oops['value'], 'Spurious remote bug ID')

    def test_suggest_batch_size(self):

        class RemoteSystem:
            pass

        remote_system = RemoteSystem()
        # When the batch_size is None, suggest_batch_size() will set
        # it accordingly.
        remote_system.batch_size = None
        checkwatches.core.suggest_batch_size(remote_system, 1)
        self.failUnlessEqual(100, remote_system.batch_size)
        remote_system.batch_size = None
        checkwatches.core.suggest_batch_size(remote_system, 12350)
        self.failUnlessEqual(247, remote_system.batch_size)
        # If the batch_size is already set, it will not be changed.
        checkwatches.core.suggest_batch_size(remote_system, 99999)
        self.failUnlessEqual(247, remote_system.batch_size)

    def test_xmlrpc_connection_errors_set_activity_properly(self):
        # HTTP status codes of 502, 503 and 504 indicate connection
        # errors. An XML-RPC request that fails with one of those is
        # logged as a connection failure, not an OOPS.
        master = BrokenCheckwatchesMaster(
            transaction.manager, logger=BufferLogger())
        master.error_code = 503
        (bug_tracker, bug_watches) = self.factory.makeBugTrackerWithWatches(
            base_url='http://example.com/')
        transaction.commit()
        master._updateBugTracker(bug_tracker)
        for bug_watch in bug_watches:
            self.assertEquals(
                BugWatchActivityStatus.CONNECTION_ERROR,
                bug_watch.last_error_type)
        self.assertEqual(
            "INFO 'Connection Error' error updating http://example.com/: "
            "<ProtocolError for http://example.com/: 503 Borked>\n",
            master.logger.getLogBuffer())

    def test_xmlrpc_other_errors_set_activity_properly(self):
        # HTTP status codes that indicate anything other than a
        # connection error still aren't OOPSes. They are logged as an
        # unknown error instead.
        master = BrokenCheckwatchesMaster(
            transaction.manager, logger=BufferLogger())
        master.error_code = 403
        (bug_tracker, bug_watches) = self.factory.makeBugTrackerWithWatches(
            base_url='http://example.com/')
        transaction.commit()
        master._updateBugTracker(bug_tracker)
        for bug_watch in bug_watches:
            self.assertEquals(
                BugWatchActivityStatus.UNKNOWN,
                bug_watch.last_error_type)
        self.assertEqual(
            "INFO 'Unknown' error updating http://example.com/: "
            "<ProtocolError for http://example.com/: 403 Borked>\n",
            master.logger.getLogBuffer())


class TestUpdateBugsWithLinkedQuestions(unittest.TestCase):
    """Tests for updating bugs with linked questions."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Set up bugs, watches and questions to test with."""
        super(TestUpdateBugsWithLinkedQuestions, self).setUp()

        # For test_can_update_bug_with_questions we need a bug that has
        # a question linked to it.
        bug_with_question = getUtility(IBugSet).get(10)
        question = getUtility(IQuestionSet).get(1)

        # XXX gmb 2007-12-11 bug 175545:
        #     We shouldn't have to login() here, but since
        #     database.buglinktarget.BugLinkTargetMixin.linkBug()
        #     doesn't accept a user parameter, instead depending on the
        #     currently logged in user, we get an exception if we don't.
        login('test@canonical.com')
        question.linkBug(bug_with_question)

        # We subscribe launchpad_developers to the question since this
        # indirectly subscribes foo.bar@canonical.com to it, too. We can
        # then use this to test the updating of a question with indirect
        # subscribers from a bug watch.
        question.subscribe(
            getUtility(ILaunchpadCelebrities).launchpad_developers)

        # We now need to switch to the checkwatches DB user so that
        # we're testing with the correct set of permissions.
        switch_dbuser(config.checkwatches.dbuser)

        # For test_can_update_bug_with_questions we also need a bug
        # watch and by extension a bug tracker.
        sample_person = getUtility(IPersonSet).getByEmail(
            'test@canonical.com')
        bugtracker = new_bugtracker(BugTrackerType.ROUNDUP)
        self.bugtask_with_question = getUtility(IBugTaskSet).createTask(
            bug_with_question, sample_person,
            getUtility(IProductSet).getByName('firefox'))
        self.bugwatch_with_question = bug_with_question.addWatch(
            bugtracker, '1', getUtility(ILaunchpadCelebrities).janitor)
        self.bugtask_with_question.bugwatch = self.bugwatch_with_question
        transaction.commit()

    def test_can_update_bug_with_questions(self):
        """Test whether bugs with linked questions can be updated.

        This will also test whether indirect subscribers of linked
        questions will be notified of the changes made when the bugwatch
        is updated.
        """
        # We need to check that the bug task we created in setUp() is
        # still being referenced by our bug watch.
        self.assertEqual(self.bugwatch_with_question.bugtasks[0].id,
            self.bugtask_with_question.id)

        # We can now update the bug watch, which will in turn update the
        # bug task and the linked question.
        self.bugwatch_with_question.updateStatus('some status',
            BugTaskStatus.INPROGRESS)
        self.assertEqual(self.bugwatch_with_question.bugtasks[0].status,
            BugTaskStatus.INPROGRESS,
            "BugTask status is inconsistent. Expected %s but got %s" %
            (BugTaskStatus.INPROGRESS.title,
            self.bugtask_with_question.status.title))


class TestSchedulerBase:

    def test_args_and_kwargs(self):

        def func(name, aptitude):
            self.failUnlessEqual("Robin Hood", name)
            self.failUnlessEqual("Riding through the glen", aptitude)

        # Positional args specified when adding a job are passed to
        # the job function at run time.
        self.scheduler.schedule(
            func, "Robin Hood", "Riding through the glen")
        # Keyword args specified when adding a job are passed to the
        # job function at run time.
        self.scheduler.schedule(
            func, name="Robin Hood", aptitude="Riding through the glen")
        # Positional and keyword args can both be specified.
        self.scheduler.schedule(
            func, "Robin Hood", aptitude="Riding through the glen")
        # Run everything.
        self.scheduler.run()


class TestSerialScheduler(TestSchedulerBase, unittest.TestCase):
    """Test SerialScheduler."""

    def setUp(self):
        self.scheduler = checkwatches.SerialScheduler()

    def test_ordering(self):
        # The numbers list will be emptied in the order we add jobs to
        # the scheduler.
        numbers = [1, 2, 3]
        # Remove 3 and check.
        self.scheduler.schedule(
            list.remove, numbers, 3)
        self.scheduler.schedule(
            lambda: self.failUnlessEqual([1, 2], numbers))
        # Remove 1 and check.
        self.scheduler.schedule(
            list.remove, numbers, 1)
        self.scheduler.schedule(
            lambda: self.failUnlessEqual([2], numbers))
        # Remove 2 and check.
        self.scheduler.schedule(
            list.remove, numbers, 2)
        self.scheduler.schedule(
            lambda: self.failUnlessEqual([], numbers))
        # Run the scheduler.
        self.scheduler.run()


class TestTwistedThreadScheduler(
    TestSchedulerBase, ZopeTestInSubProcess, unittest.TestCase):
    """Test TwistedThreadScheduler.

    By default, updateBugTrackers() runs jobs serially, but a
    different scheduling policy can be plugged in. One such policy,
    for running several jobs in parallel, is TwistedThreadScheduler.
    """

    def setUp(self):
        self.scheduler = checkwatches.TwistedThreadScheduler(
            num_threads=5, install_signal_handlers=False)


class OutputFileForThreads:
    """Collates writes according to thread name."""

    def __init__(self):
        self.output = {}
        self.lock = threading.Lock()

    def write(self, data):
        thread_name = threading.currentThread().getName()
        with self.lock:
            if thread_name in self.output:
                self.output[thread_name].append(data)
            else:
                self.output[thread_name] = [data]


class ExternalBugTrackerForThreads(TestExternalBugTracker):
    """Fake which records interesting activity to a file."""

    def __init__(self, output_file):
        super(ExternalBugTrackerForThreads, self).__init__()
        self.output_file = output_file

    def getRemoteStatus(self, bug_id):
        self.output_file.write("getRemoteStatus(bug_id=%r)" % bug_id)
        return 'UNKNOWN'

    def getCurrentDBTime(self):
        return None


class CheckwatchesMasterForThreads(CheckwatchesMaster):
    """Fake updater.

    Plumbs an `ExternalBugTrackerForThreads` into a given output file,
    which is expected to be an instance of `OutputFileForThreads`, and
    suppresses normal log activity.
    """

    def __init__(self, output_file):
        logger = BufferLogger()
        super(CheckwatchesMasterForThreads, self).__init__(
            transaction.manager, logger)
        self.output_file = output_file

    def _getExternalBugTrackersAndWatches(self, bug_trackers, bug_watches):
        return [(ExternalBugTrackerForThreads(self.output_file), bug_watches)]


class TestTwistedThreadSchedulerInPlace(
    ZopeTestInSubProcess, TestCaseWithFactory):
    """Test TwistedThreadScheduler in place.

    As in, driving as much of the bug watch machinery as is possible
    without making external connections.
    """

    layer = LaunchpadZopelessLayer

    def test(self):
        # Prepare test data.
        self.owner = self.factory.makePerson()
        self.trackers = [
            getUtility(IBugTrackerSet).ensureBugTracker(
                "http://butterscotch.example.com", self.owner,
                BugTrackerType.BUGZILLA, name="butterscotch"),
            getUtility(IBugTrackerSet).ensureBugTracker(
                "http://strawberry.example.com", self.owner,
                BugTrackerType.BUGZILLA, name="strawberry"),
            ]
        self.bug = self.factory.makeBug(owner=self.owner)
        for tracker in self.trackers:
            for num in (1, 2, 3):
                self.factory.makeBugWatch(
                    "%s-%d" % (tracker.name, num),
                    tracker, self.bug, self.owner)
        # Commit so that threads all see the same database state.
        transaction.commit()
        # Prepare the updater with the Twisted scheduler.
        output_file = OutputFileForThreads()
        threaded_bug_watch_updater = CheckwatchesMasterForThreads(output_file)
        threaded_bug_watch_scheduler = TwistedThreadScheduler(
            num_threads=10, install_signal_handlers=False)
        # Run the updater.
        threaded_bug_watch_updater.updateBugTrackers(
            bug_tracker_names=['butterscotch', 'strawberry'],
            batch_size=5, scheduler=threaded_bug_watch_scheduler)
        # The thread names should match the tracker names.
        self.assertEqual(
            ['butterscotch', 'strawberry'], sorted(output_file.output))
        # Check that getRemoteStatus() was called.
        self.assertEqual(
            ["getRemoteStatus(bug_id=u'butterscotch-1')",
             "getRemoteStatus(bug_id=u'butterscotch-2')",
             "getRemoteStatus(bug_id=u'butterscotch-3')"],
            output_file.output['butterscotch'])
        self.assertEqual(
            ["getRemoteStatus(bug_id=u'strawberry-1')",
             "getRemoteStatus(bug_id=u'strawberry-2')",
             "getRemoteStatus(bug_id=u'strawberry-3')"],
            output_file.output['strawberry'])
