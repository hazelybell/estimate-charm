# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes and logic for the checkwatches cronscript."""

__metaclass__ = type
__all__ = [
    'BaseScheduler',
    'CheckwatchesMaster',
    'CheckWatchesCronScript',
    'SerialScheduler',
    'TooMuchTimeSkew',
    'TwistedThreadScheduler',
    'externalbugtracker',
    ]

from contextlib import contextmanager
from copy import copy
from datetime import (
    datetime,
    timedelta,
    )
from itertools import (
    chain,
    islice,
    )
import socket
import sys
import threading
import time
from xmlrpclib import ProtocolError

import pytz
from twisted.internet import reactor
from twisted.internet.defer import DeferredList
from twisted.internet.threads import deferToThreadPool
from twisted.python.threadpool import ThreadPool
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs import externalbugtracker
from lp.bugs.externalbugtracker import (
    BATCH_SIZE_UNLIMITED,
    BugWatchUpdateError,
    UnknownBugTrackerTypeError,
    )
from lp.bugs.interfaces.bug import CreateBugParams
from lp.bugs.interfaces.bugtracker import IBugTrackerSet
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.bugs.scripts.checkwatches.base import (
    commit_before,
    with_interaction,
    WorkingBase,
    )
from lp.bugs.scripts.checkwatches.remotebugupdater import RemoteBugUpdater
from lp.bugs.scripts.checkwatches.utilities import (
    get_bugwatcherrortype_for_error,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.person import (
    IPersonSet,
    PersonCreationRationale,
    )
from lp.services.database.bulk import reload
from lp.services.database.sqlbase import flush_database_updates
from lp.services.scripts.base import LaunchpadCronScript
from lp.services.scripts.logger import log as default_log

# The login of the user to run as.
LOGIN = 'bugwatch@bugs.launchpad.net'

# A list of product names for which comments should be synchronized.
SYNCABLE_GNOME_PRODUCTS = []

# When syncing with a remote bug tracker that reports its idea of the
# current time, this defined the maximum acceptable skew between the
# local and remote clock.
ACCEPTABLE_TIME_SKEW = timedelta(minutes=10)

# The minimum batch size to suggest to an IExternalBugTracker.
SUGGESTED_BATCH_SIZE_MIN = 100
# The proportion of all watches to suggest as a batch size.
SUGGESTED_BATCH_SIZE_PROPORTION = 0.02


class TooMuchTimeSkew(BugWatchUpdateError):
    """Time difference between ourselves and the remote server is too much."""


def unique(iterator):
    """Generate only unique items from an iterator."""
    seen = set()
    for item in iterator:
        if item not in seen:
            seen.add(item)
            yield item


def suggest_batch_size(remote_system, num_watches):
    """Suggest a value for batch_size if it's not set.

    Given the number of bug watches for a `remote_system`, this sets a
    suggested batch size on it. If `remote_system` already has a batch
    size set, this does not override it.

    :param remote_system: An `ExternalBugTracker`.
    :param num_watches: The number of watches for `remote_system`.
    """
    if remote_system.batch_size is None:
        remote_system.batch_size = max(
            SUGGESTED_BATCH_SIZE_MIN,
            int(SUGGESTED_BATCH_SIZE_PROPORTION * num_watches))


@contextmanager
def record_errors(transaction, bug_watch_ids):
    """Context manager to record errors in BugWatchActivity.

    If an exception occurs, it will be logged in BugWatchActivity
    against all the given watches.
    """
    try:
        yield
    except Exception as e:
        # We record the error against all the bugwatches that should
        # have been updated before re-raising it. We also update the
        # bug watches' lastchecked dates so that checkwatches
        # doesn't keep trying to update them every time it runs.
        with transaction:
            getUtility(IBugWatchSet).bulkSetError(
                bug_watch_ids, get_bugwatcherrortype_for_error(e))
        raise

class CheckwatchesMaster(WorkingBase):
    """Takes responsibility for updating remote bug watches."""

    remote_bug_updater_factory = RemoteBugUpdater

    def __init__(self, transaction_manager, logger=default_log,
                 syncable_gnome_products=None):
        """Initialize a CheckwatchesMaster.

        :param transaction_manager: A transaction manager on which
            `begin()`, `abort()` and `commit()` can be
            called. Additionally, it should be safe for different
            threads to use its methods to manage their own
            transactions (i.e. with thread-local storage).

        :param log: An instance of `logging.Logger`, or something that
            provides a similar interface.

        """
        self.init(LOGIN, transaction_manager, logger)

        # Override SYNCABLE_GNOME_PRODUCTS if necessary.
        if syncable_gnome_products is not None:
            self._syncable_gnome_products = syncable_gnome_products
        else:
            self._syncable_gnome_products = list(SYNCABLE_GNOME_PRODUCTS)

    @with_interaction
    def _bugTrackerUpdaters(self, bug_tracker_names=None):
        """Yields functions that can be used to update each bug tracker."""
        with self.transaction:
            ubuntu_bugzilla = (
                getUtility(ILaunchpadCelebrities).ubuntu_bugzilla)
            # Save the name, so we can use it in other transactions.
            ubuntu_bugzilla_name = ubuntu_bugzilla.name
            # Get all bug tracker names if none have been specified.
            if bug_tracker_names is None:
                bug_tracker_names = sorted(getUtility(IBugTrackerSet).names)

        def make_updater(bug_tracker_name, bug_tracker_id):
            """Returns a function that can update the given bug tracker."""
            def updater(batch_size=None):
                thread = threading.currentThread()
                thread_name = thread.getName()
                thread.setName(bug_tracker_name)
                try:
                    with self.statement_logging:
                        return self.updateBugTracker(
                            bug_tracker_id, batch_size)
                finally:
                    thread.setName(thread_name)
            return updater

        for bug_tracker_name in bug_tracker_names:
            if bug_tracker_name == ubuntu_bugzilla_name:
                # XXX: 2007-09-11 Graham Binns
                #      We automatically ignore the Ubuntu Bugzilla
                #      here as all its bugs have been imported into
                #      Launchpad. Ideally we would have some means
                #      to identify all bug trackers like this so
                #      that hard-coding like this can be genericised
                #      (Bug 138949).
                self.logger.debug(
                    "Skipping updating Ubuntu Bugzilla watches.")
            else:
                with self.transaction:
                    bug_tracker = getUtility(
                        IBugTrackerSet).getByName(bug_tracker_name)
                    bug_tracker_id = bug_tracker.id
                    bug_tracker_active = bug_tracker.active
                    bug_tracker_baseurl = bug_tracker.baseurl

                if bug_tracker_active:
                    yield make_updater(bug_tracker_name, bug_tracker_id)
                else:
                    self.logger.debug(
                        "Updates are disabled for bug tracker at %s" %
                        bug_tracker_baseurl)

    @commit_before
    def updateBugTrackers(
        self, bug_tracker_names=None, batch_size=None, scheduler=None):
        """Update all the bug trackers that have watches pending.

        If bug tracker names are specified in bug_tracker_names only
        those bug trackers will be checked.

        A custom scheduler can be passed in. This should inherit from
        `BaseScheduler`. If no scheduler is given, `SerialScheduler`
        will be used, which simply runs the jobs in order.
        """
        if batch_size is None:
            self.logger.debug("No global batch size specified.")
        elif batch_size == BATCH_SIZE_UNLIMITED:
            self.logger.debug("Using an unlimited global batch size.")
        else:
            self.logger.debug("Using a global batch size of %s" % batch_size)

        # Default to using the very simple SerialScheduler.
        if scheduler is None:
            scheduler = SerialScheduler()

        # Schedule all the jobs to run.
        for updater in self._bugTrackerUpdaters(bug_tracker_names):
            scheduler.schedule(updater, batch_size)

        # Run all the jobs.
        scheduler.run()

    @commit_before
    @with_interaction
    def updateBugTracker(self, bug_tracker, batch_size):
        """Updates the given bug trackers's bug watches.

        If there is an error, logs are updated, and the transaction is
        aborted.

        :param bug_tracker: An IBugTracker or the ID of one, so that this
            method can be called from a different interaction.

        :return: A boolean indicating if the operation was successful.
        """
        with self.transaction:
            # Get the bug tracker.
            if isinstance(bug_tracker, (int, long)):
                bug_tracker = getUtility(IBugTrackerSet).get(bug_tracker)
            # Save the name and url for later, since we might need it
            # to report an error after a transaction has been aborted.
            bug_tracker_name = bug_tracker.name
            bug_tracker_url = bug_tracker.baseurl

        try:
            self._updateBugTracker(bug_tracker, batch_size)
        except (KeyboardInterrupt, SystemExit):
            # We should never catch KeyboardInterrupt or SystemExit.
            raise
        except Exception as error:
            # If something unexpected goes wrong, we log it and
            # continue: a failure shouldn't break the updating of
            # the other bug trackers.
            if isinstance(error, BugWatchUpdateError):
                self.logger.info(
                    "Error updating %s: %s" % (
                        bug_tracker.baseurl, error))
            elif isinstance(error, socket.timeout):
                self.logger.info(
                    "Connection timed out when updating %s" % (
                        bug_tracker.baseurl))
            else:
                # Unknown exceptions are logged as OOPSes.
                info = sys.exc_info()
                properties = [
                    ('bugtracker', bug_tracker_name),
                    ('baseurl', bug_tracker_url)]
                self.error(
                    "An exception was raised when updating %s" %
                    bug_tracker_url,
                    properties=properties, info=info)
            return False
        else:
            return True

    @commit_before
    @with_interaction
    def forceUpdateAll(self, bug_tracker_name, batch_size):
        """Update all the watches for `bug_tracker_name`.

        :param bug_tracker_name: The name of the bug tracker to update.
        :param batch_size: The number of bug watches to update in one
            go. If zero, all bug watches will be updated.
        """
        with self.transaction:
            bug_tracker = getUtility(
                IBugTrackerSet).getByName(bug_tracker_name)
            if bug_tracker is None:
                # If the bug tracker is nonsense then just ignore it.
                self.logger.info(
                    "Bug tracker '%s' doesn't exist. Ignoring." %
                    bug_tracker_name)
                return
            elif bug_tracker.watches.count() == 0:
                # If there are no watches to update, ignore the bug tracker.
                self.logger.info(
                    "Bug tracker '%s' doesn't have any watches. Ignoring." %
                    bug_tracker_name)
                return
            # Reset all the bug watches for the bug tracker.
            self.logger.info(
                "Resetting %s bug watches for bug tracker '%s'" %
                (bug_tracker.watches.count(), bug_tracker_name))
            bug_tracker.resetWatches(
                new_next_check=datetime.now(pytz.timezone('UTC')))

        # Loop over the bug watches in batches as specificed by
        # batch_size until there are none left to update.
        with self.transaction:
            self.logger.info(
                "Updating %s watches on bug tracker '%s'" %
                (bug_tracker.watches.count(), bug_tracker_name))
        has_watches_to_update = True
        while has_watches_to_update:
            if not self.updateBugTracker(bug_tracker, batch_size):
                break
            with self.transaction:
                watches_left = (
                    bug_tracker.watches_needing_update.count())
            self.logger.info(
                "%s watches left to check on bug tracker '%s'" %
                (watches_left, bug_tracker_name))
            has_watches_to_update = watches_left > 0

    def _getExternalBugTrackersAndWatches(self, bug_tracker, bug_watches):
        """Return an `ExternalBugTracker` instance for `bug_tracker`."""
        with self.transaction:
            num_watches = bug_tracker.watches.count()
            remotesystem = (
                externalbugtracker.get_external_bugtracker(bug_tracker))
            # We special-case the Gnome Bugzilla.
            is_gnome_bugzilla = bug_tracker == (
                getUtility(ILaunchpadCelebrities).gnome_bugzilla)

        # Probe the remote system for additional capabilities.
        remotesystem_to_use = remotesystem.getExternalBugTrackerToUse()

        # Try to hint at how many bug watches to check each time.
        suggest_batch_size(remotesystem_to_use, num_watches)

        if (is_gnome_bugzilla and remotesystem_to_use.sync_comments):
            # If there are no products to sync comments for, disable
            # comment sync and return.
            if len(self._syncable_gnome_products) == 0:
                remotesystem_to_use.sync_comments = False
                return [
                    (remotesystem_to_use, bug_watches),
                    ]

            syncable_watches = []
            other_watches = []

            with self.transaction:
                reload(bug_watches)
                remote_bug_ids = [
                    bug_watch.remotebug for bug_watch in bug_watches]

            remote_products = (
                remotesystem_to_use.getProductsForRemoteBugs(
                    remote_bug_ids))

            with self.transaction:
                reload(bug_watches)
                for bug_watch in bug_watches:
                    if (remote_products.get(bug_watch.remotebug) in
                        self._syncable_gnome_products):
                        syncable_watches.append(bug_watch)
                    else:
                        other_watches.append(bug_watch)

            # For bug watches on remote bugs that are against products
            # in the _syncable_gnome_products list - i.e. ones with which
            # we want to sync comments - we return a BugzillaAPI
            # instance with sync_comments=True, otherwise we return a
            # similar BugzillaAPI instance, but with sync_comments=False.
            remotesystem_for_syncables = remotesystem_to_use
            remotesystem_for_others = copy(remotesystem_to_use)
            remotesystem_for_others.sync_comments = False

            return [
                (remotesystem_for_syncables, syncable_watches),
                (remotesystem_for_others, other_watches),
                ]
        else:
            return [
                (remotesystem_to_use, bug_watches),
                ]

    def _updateBugTracker(self, bug_tracker, batch_size=None):
        """Updates the given bug trackers's bug watches."""
        with self.transaction:
            # Never work with more than 1000 bug watches at a
            # time. Especially after a release or an outage, a large
            # bug tracker could have have >10000 bug watches eligible
            # for update.
            bug_watches_to_update = (
                bug_tracker.watches_needing_update.config(limit=1000))
            bug_watches_need_updating = (
                bug_watches_to_update.count() > 0)

        if bug_watches_need_updating:
            # XXX: GavinPanella 2010-01-18 bug=509223 : Ask remote
            # tracker which remote bugs have been modified, and use
            # this to fill up a batch, rather than figuring out
            # batching later in _getRemoteIdsToCheck().
            try:
                trackers_and_watches = self._getExternalBugTrackersAndWatches(
                    bug_tracker, bug_watches_to_update)
            except (UnknownBugTrackerTypeError, ProtocolError) as error:
                # We update all the bug watches to reflect the fact that
                # this error occurred. We also update their last checked
                # date to ensure that they don't get checked for another
                # 24 hours (see above).
                error_type = (
                    get_bugwatcherrortype_for_error(error))
                with self.transaction:
                    getUtility(IBugWatchSet).bulkSetError(
                        bug_watches_to_update, error_type)
                    self.logger.info(
                        "'%s' error updating %s: %s" % (
                            error_type.title, bug_tracker.baseurl, error))
            else:
                for remotesystem, bug_watch_batch in trackers_and_watches:
                    self.updateBugWatches(
                        remotesystem, bug_watch_batch, batch_size=batch_size)
        else:
            with self.transaction:
                self.logger.debug(
                    "No watches to update on %s" % bug_tracker.baseurl)

    def _getRemoteIdsToCheck(self, remotesystem, bug_watches,
                             server_time=None, now=None, batch_size=None):
        """Return the remote bug IDs to check for a set of bug watches.

        The remote bug tracker is queried to find out which of the
        remote bugs in `bug_watches` have changed since they were last
        checked. Those which haven't changed are excluded.

        :param bug_watches: A set of `BugWatch`es to be checked.
        :param remotesystem: The `ExternalBugtracker` on which
            `getModifiedRemoteBugs`() should be called
        :param server_time: The time according to the remote server.
            This may be None when the server doesn't specify a remote time.
        :param now: The current time (used for testing)
        :return: A list of remote bug IDs to be updated.
        """
        # Check that the remote server's notion of time agrees with
        # ours. If not, raise a TooMuchTimeSkew error, since if the
        # server's wrong about the time it'll mess up all our times when
        # we import things.
        if now is None:
            now = datetime.now(pytz.timezone('UTC'))

        if (server_time is not None and
            abs(server_time - now) > ACCEPTABLE_TIME_SKEW):
            raise TooMuchTimeSkew(abs(server_time - now))

        # We limit the number of watches we're updating by the
        # ExternalBugTracker's batch_size. In an ideal world we'd just
        # slice the bug_watches list but for the sake of testing we need
        # to ensure that the list of bug watches is ordered by remote
        # bug id before we do so.
        if batch_size is None:
            # If a batch_size hasn't been passed, use the one specified
            # by the ExternalBugTracker.
            batch_size = remotesystem.batch_size

        with self.transaction:
            reload(bug_watches)
            old_bug_watches = set(
                bug_watch for bug_watch in bug_watches
                if bug_watch.lastchecked is not None)
            if len(old_bug_watches) == 0:
                oldest_lastchecked = None
            else:
                oldest_lastchecked = min(
                    bug_watch.lastchecked for bug_watch in old_bug_watches)
                # Adjust for possible time skew, and some more, just to be
                # safe.
                oldest_lastchecked -= (
                    ACCEPTABLE_TIME_SKEW + timedelta(minutes=1))
            # Collate the remote IDs.
            remote_old_ids = sorted(
                set(bug_watch.remotebug for bug_watch in old_bug_watches))
            remote_new_ids = sorted(
                set(bug_watch.remotebug for bug_watch in bug_watches
                if bug_watch not in old_bug_watches))
            # If the remote system is not configured to sync comments,
            # don't bother checking for any to push.
            if remotesystem.sync_comments:
                remote_ids_with_comments = sorted(
                    bug_watch.remotebug for bug_watch in bug_watches
                    if bug_watch.unpushed_comments.any() is not None)
            else:
                remote_ids_with_comments = []

        # We only make the call to getModifiedRemoteBugs() if there
        # are actually some bugs that we're interested in so as to
        # avoid unnecessary network traffic.
        if server_time is not None and len(remote_old_ids) > 0:
            if batch_size == BATCH_SIZE_UNLIMITED:
                remote_old_ids_to_check = (
                    remotesystem.getModifiedRemoteBugs(
                        remote_old_ids, oldest_lastchecked))
            else:
                # Don't ask the remote system about more than
                # batch_size bugs at once, but keep asking until we
                # run out of bugs to ask about or we have batch_size
                # bugs to check.
                remote_old_ids_to_check = []
                for index in xrange(0, len(remote_old_ids), batch_size):
                    remote_old_ids_to_check.extend(
                        remotesystem.getModifiedRemoteBugs(
                            remote_old_ids[index : index + batch_size],
                            oldest_lastchecked))
                    if len(remote_old_ids_to_check) >= batch_size:
                        break
        else:
            remote_old_ids_to_check = remote_old_ids

        # We'll create our remote_ids_to_check list so that it's
        # prioritized. We include remote IDs in priority order:
        #  1. IDs with comments.
        #  2. IDs that haven't been checked.
        #  3. Everything else.
        remote_ids_to_check = chain(
            remote_ids_with_comments, remote_new_ids, remote_old_ids_to_check)

        if batch_size != BATCH_SIZE_UNLIMITED:
            # Some remote bug IDs may appear in more than one list so
            # we must filter the list before slicing.
            remote_ids_to_check = islice(
                unique(remote_ids_to_check), batch_size)

        # Stuff the IDs in a set.
        remote_ids_to_check = set(remote_ids_to_check)

        # Make sure that unmodified_remote_ids only includes IDs that
        # could have been checked but which weren't modified on the
        # remote server and which haven't been listed for checking
        # otherwise (i.e. because they have comments to be pushed).
        unmodified_remote_ids = set(remote_old_ids)
        unmodified_remote_ids.difference_update(remote_old_ids_to_check)
        unmodified_remote_ids.difference_update(remote_ids_to_check)

        all_remote_ids = remote_ids_to_check.union(unmodified_remote_ids)
        return {
            'remote_ids_to_check': sorted(remote_ids_to_check),
            'all_remote_ids': sorted(all_remote_ids),
            'unmodified_remote_ids': sorted(unmodified_remote_ids),
            }

    @commit_before
    def updateBugWatches(self, remotesystem, bug_watches_to_update, now=None,
                         batch_size=None):
        """Update the given bug watches."""
        # Save the url for later, since we might need it to report an
        # error after a transaction has been aborted.
        bug_tracker_url = remotesystem.baseurl

        # Some tests pass a list of bug watches whilst checkwatches.py
        # will pass a SelectResults instance. We convert bug_watches to a
        # list here to ensure that were're doing sane things with it
        # later on.
        with self.transaction:
            bug_watches = list(bug_watches_to_update)
            bug_watch_ids = [bug_watch.id for bug_watch in bug_watches]

        # Fetch the time on the server. We'll use this in
        # _getRemoteIdsToCheck() and when determining whether we can
        # sync comments or not.
        with record_errors(self.transaction, bug_watch_ids):
            server_time = remotesystem.getCurrentDBTime()
            remote_ids = self._getRemoteIdsToCheck(
                remotesystem, bug_watches, server_time, now, batch_size)

        remote_ids_to_check = remote_ids['remote_ids_to_check']
        all_remote_ids = remote_ids['all_remote_ids']
        unmodified_remote_ids = remote_ids['unmodified_remote_ids']

        # Remove from the list of bug watches any watch whose remote ID
        # doesn't appear in the list of IDs to check.
        with self.transaction:
            reload(bug_watches)
            for bug_watch in list(bug_watches):
                if bug_watch.remotebug not in remote_ids_to_check:
                    bug_watches.remove(bug_watch)

        self.logger.info(
            "Updating %i watches for %i bugs on %s" % (
                len(bug_watches), len(remote_ids_to_check), bug_tracker_url))

        with record_errors(self.transaction, bug_watch_ids):
            remotesystem.initializeRemoteBugDB(remote_ids_to_check)

        for remote_bug_id in all_remote_ids:
            remote_bug_updater = self.remote_bug_updater_factory(
                self, remotesystem, remote_bug_id, bug_watch_ids,
                unmodified_remote_ids, server_time)
            remote_bug_updater.updateRemoteBug()

    def importBug(self, external_bugtracker, bugtracker, bug_target,
                  remote_bug):
        """Import a remote bug into Launchpad.

        :param external_bugtracker: An ISupportsBugImport, which talks
            to the external bug tracker.
        :param bugtracker: An IBugTracker, to which the created bug
            watch will be linked.
        :param bug_target: An IBugTarget, to which the created bug will
            be linked.
        :param remote_bug: The remote bug id as a string.

        :return: The created Launchpad bug.
        """
        assert IDistribution.providedBy(bug_target), (
            'Only imports of bugs for a distribution is implemented.')
        reporter_name, reporter_email = (
            external_bugtracker.getBugReporter(remote_bug))
        reporter = getUtility(IPersonSet).ensurePerson(
            reporter_email, reporter_name, PersonCreationRationale.BUGIMPORT,
            comment='when importing bug #%s from %s' % (
                remote_bug, external_bugtracker.baseurl))
        package_name = external_bugtracker.getBugTargetName(remote_bug)
        package = bug_target.getSourcePackage(package_name)
        if package is not None:
            bug_target = package
        else:
            self.warning(
                'Unknown %s package (#%s at %s): %s' % (
                    bug_target.name, remote_bug,
                    external_bugtracker.baseurl, package_name))
        summary, description = (
            external_bugtracker.getBugSummaryAndDescription(remote_bug))
        bug = bug_target.createBug(
            CreateBugParams(
                reporter, summary, description, subscribe_owner=False,
                filed_by=getUtility(ILaunchpadCelebrities).bug_watch_updater))
        [added_task] = bug.bugtasks
        bug_watch = getUtility(IBugWatchSet).createBugWatch(
            bug=bug,
            owner=getUtility(ILaunchpadCelebrities).bug_watch_updater,
            bugtracker=bugtracker, remotebug=remote_bug)

        added_task.bugwatch = bug_watch
        # Need to flush databse updates, so that the bug watch knows it
        # is linked from a bug task.
        flush_database_updates()

        return bug


class BaseScheduler:
    """Run jobs according to a policy."""

    def schedule(self, func, *args, **kwargs):
        """Add a job to be run."""
        raise NotImplementedError(self.schedule)

    def run(self):
        """Run the jobs."""
        raise NotImplementedError(self.run)


class SerialScheduler(BaseScheduler):
    """Run jobs in order, one at a time."""

    def __init__(self):
        self._jobs = []

    def schedule(self, func, *args, **kwargs):
        self._jobs.append((func, args, kwargs))

    def run(self):
        jobs, self._jobs = self._jobs[:], []
        for (func, args, kwargs) in jobs:
            func(*args, **kwargs)


class TwistedThreadScheduler(BaseScheduler):
    """Run jobs in threads, chaperoned by Twisted."""

    def __init__(self, num_threads, install_signal_handlers=True):
        """Create a new `TwistedThreadScheduler`.

        :param num_threads: The number of threads to allocate to the
          thread pool.
        :type num_threads: int

        :param install_signal_handlers: Whether the Twisted reactor
          should install signal handlers or not. This is intented for
          testing - set to False to avoid layer violations - but may
          be useful in other situations.
        :type install_signal_handlers: bool
        """
        self._thread_pool = ThreadPool(0, num_threads)
        self._install_signal_handlers = install_signal_handlers
        self._jobs = []

    def schedule(self, func, *args, **kwargs):
        self._jobs.append(
            deferToThreadPool(
                reactor, self._thread_pool, func, *args, **kwargs))

    def run(self):
        jobs, self._jobs = self._jobs[:], []
        jobs_done = DeferredList(jobs)
        jobs_done.addBoth(lambda ignore: self._thread_pool.stop())
        jobs_done.addBoth(lambda ignore: reactor.stop())
        reactor.callWhenRunning(self._thread_pool.start)
        reactor.run(self._install_signal_handlers)


class CheckWatchesCronScript(LaunchpadCronScript):

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            '-t', '--bug-tracker', action='append',
            dest='bug_trackers', metavar="BUG_TRACKER",
            help="Only check a given bug tracker. Specifying more than "
                "one bugtracker using this option will check all the "
                "bugtrackers specified.")
        self.parser.add_option(
            '-b', '--batch-size', action='store', type=int, dest='batch_size',
            help="Set the number of watches to be checked per bug "
                 "tracker in this run. If BATCH_SIZE is 0, all watches "
                 "on the bug tracker that are eligible for checking will "
                 "be checked.")
        self.parser.add_option(
            '--reset', action='store_true', dest='update_all',
            help="Update all the watches on the bug tracker, regardless of "
                 "whether or not they need checking.")
        self.parser.add_option(
            '--jobs', action='store', type=int, dest='jobs', default=1,
            help=("The number of simulataneous jobs to run, %default by "
                  "default."))

    def main(self):
        start_time = time.time()

        updater = CheckwatchesMaster(self.txn, self.logger)

        if self.options.update_all and len(self.options.bug_trackers) > 0:
            # The user has requested that we update *all* the watches
            # for these bugtrackers
            for bug_tracker in self.options.bug_trackers:
                updater.forceUpdateAll(bug_tracker, self.options.batch_size)
        else:
            # Otherwise we just update those watches that need updating,
            # and we let the CheckwatchesMaster decide which those are.
            if self.options.jobs <= 1:
                # Use the default scheduler.
                scheduler = None
            else:
                # Run jobs in parallel.
                scheduler = TwistedThreadScheduler(self.options.jobs)
            updater.updateBugTrackers(
                self.options.bug_trackers,
                self.options.batch_size,
                scheduler)

        run_time = time.time() - start_time
        self.logger.info("Time for this run: %.3f seconds." % run_time)
