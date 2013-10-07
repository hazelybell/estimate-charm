# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Soyuz buildd slave manager logic."""

__metaclass__ = type

__all__ = [
    'BuilddManager',
    'BUILDD_MANAGER_LOG_NAME',
    ]

import datetime
import logging

from storm.expr import LeftJoin
import transaction
from twisted.application import service
from twisted.internet import (
    defer,
    reactor,
    )
from twisted.internet.task import LoopingCall
from twisted.python import log
from zope.component import getUtility

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interactor import (
    BuilderInteractor,
    extract_vitals_from_db,
    )
from lp.buildmaster.interfaces.builder import (
    BuildDaemonError,
    BuildSlaveFailure,
    CannotBuild,
    CannotFetchFile,
    CannotResumeHost,
    IBuilderSet,
    )
from lp.buildmaster.model.builder import Builder
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.services.database.interfaces import IStore
from lp.services.propertycache import get_property_cache


BUILDD_MANAGER_LOG_NAME = "slave-scanner"


class BuilderFactory:
    """A dumb builder factory that just talks to the DB."""

    def update(self):
        """Update the factory's view of the world.

        For the basic BuilderFactory this is a no-op, but others might do
        something.
        """
        return

    def prescanUpdate(self):
        """Update the factory's view of the world before each scan.

        For the basic BuilderFactory this means ending the transaction
        to ensure that data retrieved is up to date.
        """
        transaction.abort()

    @property
    def date_updated(self):
        return datetime.datetime.utcnow()

    def __getitem__(self, name):
        """Get the named `Builder` Storm object."""
        return getUtility(IBuilderSet).getByName(name)

    def getVitals(self, name):
        """Get the named `BuilderVitals` object."""
        return extract_vitals_from_db(self[name])

    def iterVitals(self):
        """Iterate over all `BuilderVitals` objects."""
        return (
            extract_vitals_from_db(b)
            for b in getUtility(IBuilderSet).__iter__())


class PrefetchedBuilderFactory:
    """A smart builder factory that does efficient bulk queries.

    `getVitals` and `iterVitals` don't touch the DB directly. They work
    from cached data updated by `update`.
    """

    date_updated = None

    def update(self):
        """See `BuilderFactory`."""
        transaction.abort()
        builders_and_bqs = IStore(Builder).using(
            Builder, LeftJoin(BuildQueue, BuildQueue.builderID == Builder.id)
            ).find((Builder, BuildQueue))
        self.vitals_map = dict(
            (b.name, extract_vitals_from_db(b, bq))
            for b, bq in builders_and_bqs)
        transaction.abort()
        self.date_updated = datetime.datetime.utcnow()

    def prescanUpdate(self):
        """See `BuilderFactory`.

        This is a no-op, as the data was already brought sufficiently up
        to date by update().
        """
        return

    def __getitem__(self, name):
        """See `BuilderFactory`."""
        return getUtility(IBuilderSet).getByName(name)

    def getVitals(self, name):
        """See `BuilderFactory`."""
        return self.vitals_map[name]

    def iterVitals(self):
        """See `BuilderFactory`."""
        return (b for n, b in sorted(self.vitals_map.iteritems()))


@defer.inlineCallbacks
def assessFailureCounts(logger, vitals, builder, slave, interactor, exception):
    """View builder/job failure_count and work out which needs to die.

    :return: A Deferred that fires either immediately or after a virtual
        slave has been reset.
    """
    # builder.currentjob hides a complicated query, don't run it twice.
    # See bug 623281 (Note that currentjob is a cachedproperty).

    del get_property_cache(builder).currentjob
    current_job = builder.currentjob
    if current_job is None:
        job_failure_count = 0
    else:
        job_failure_count = current_job.specific_job.build.failure_count

    if builder.failure_count == job_failure_count and current_job is not None:
        # If the failure count for the builder is the same as the
        # failure count for the job being built, then we cannot
        # tell whether the job or the builder is at fault. The  best
        # we can do is try them both again, and hope that the job
        # runs against a different builder.
        current_job.reset()
        del get_property_cache(builder).currentjob
        return

    if builder.failure_count > job_failure_count:
        # The builder has failed more than the jobs it's been
        # running.

        # Re-schedule the build if there is one.
        if current_job is not None:
            current_job.reset()

        # We are a little more tolerant with failing builders than
        # failing jobs because sometimes they get unresponsive due to
        # human error, flaky networks etc.  We expect the builder to get
        # better, whereas jobs are very unlikely to get better.
        if builder.failure_count >= (
                Builder.RESET_THRESHOLD * Builder.RESET_FAILURE_THRESHOLD):
            # We've already tried resetting it enough times, so we have
            # little choice but to give up.
            builder.failBuilder(str(exception))
        elif builder.failure_count % Builder.RESET_THRESHOLD == 0:
            # The builder is dead, but in the virtual case it might be worth
            # resetting it.
            yield interactor.resetOrFail(
                vitals, slave, builder, logger, exception)
    else:
        # The job is the culprit!  Override its status to 'failed'
        # to make sure it won't get automatically dispatched again,
        # and remove the buildqueue request.  The failure should
        # have already caused any relevant slave data to be stored
        # on the build record so don't worry about that here.
        builder.resetFailureCount()
        build_job = current_job.specific_job.build
        build_job.updateStatus(BuildStatus.FAILEDTOBUILD)
        builder.currentjob.destroySelf()

        # N.B. We could try and call _handleStatus_PACKAGEFAIL here
        # but that would cause us to query the slave for its status
        # again, and if the slave is non-responsive it holds up the
        # next buildd scan.
    del get_property_cache(builder).currentjob


class SlaveScanner:
    """A manager for a single builder."""

    # The interval between each poll cycle, in seconds.  We'd ideally
    # like this to be lower but 15 seems a reasonable compromise between
    # responsivity and load on the database server, since in each cycle
    # we can run quite a few queries.
    #
    # NB. This used to be as low as 5 but as more builders are added to
    # the farm this rapidly increases the query count, PG load and this
    # process's load.  It's backed off until we come up with a better
    # algorithm for polling.
    SCAN_INTERVAL = 15

    # The time before deciding that a cancelling builder has failed, in
    # seconds.  This should normally be a multiple of SCAN_INTERVAL, and
    # greater than abort_timeout in launchpad-buildd's slave BuildManager.
    CANCEL_TIMEOUT = 180

    def __init__(self, builder_name, builder_factory, logger, clock=None,
                 interactor_factory=BuilderInteractor,
                 slave_factory=BuilderInteractor.makeSlaveFromVitals,
                 behavior_factory=BuilderInteractor.getBuildBehavior):
        self.builder_name = builder_name
        self.builder_factory = builder_factory
        self.logger = logger
        self.interactor_factory = interactor_factory
        self.slave_factory = slave_factory
        self.behavior_factory = behavior_factory
        # Use the clock if provided, so that tests can advance it.  Use the
        # reactor by default.
        if clock is None:
            clock = reactor
        self._clock = clock
        self.date_cancel = None
        self.date_scanned = None

        # We cache the build cookie, keyed on the BuildQueue, to avoid
        # hitting the DB on every scan.
        self._cached_build_cookie = None
        self._cached_build_queue = None

    def startCycle(self):
        """Scan the builder and dispatch to it or deal with failures."""
        self.loop = LoopingCall(self.singleCycle)
        self.loop.clock = self._clock
        self.stopping_deferred = self.loop.start(self.SCAN_INTERVAL)
        return self.stopping_deferred

    def stopCycle(self):
        """Terminate the LoopingCall."""
        self.loop.stop()

    def singleCycle(self):
        # Inhibit scanning if the BuilderFactory hasn't updated since
        # the last run. This doesn't matter for the base BuilderFactory,
        # as it's always up to date, but PrefetchedBuilderFactory caches
        # heavily, and we don't want to eg. forget that we dispatched a
        # build in the previous cycle.
        if (self.date_scanned is not None
            and self.date_scanned > self.builder_factory.date_updated):
            self.logger.debug(
                "Skipping builder %s (cache out of date)" % self.builder_name)
            return defer.succeed(None)

        self.logger.debug("Scanning builder %s" % self.builder_name)
        d = self.scan()
        d.addErrback(self._scanFailed)
        d.addBoth(self._updateDateScanned)
        return d

    def _updateDateScanned(self, ignored):
        self.date_scanned = datetime.datetime.utcnow()

    @defer.inlineCallbacks
    def _scanFailed(self, failure):
        """Deal with failures encountered during the scan cycle.

        1. Print the error in the log
        2. Increment and assess failure counts on the builder and job.

        :return: A Deferred that fires either immediately or after a virtual
            slave has been reset.
        """
        # Make sure that pending database updates are removed as it
        # could leave the database in an inconsistent state (e.g. The
        # job says it's running but the buildqueue has no builder set).
        transaction.abort()

        # If we don't recognise the exception include a stack trace with
        # the error.
        error_message = failure.getErrorMessage()
        if failure.check(
            BuildSlaveFailure, CannotBuild, CannotResumeHost,
            BuildDaemonError, CannotFetchFile):
            self.logger.info("Scanning %s failed with: %s" % (
                self.builder_name, error_message))
        else:
            self.logger.info("Scanning %s failed with: %s\n%s" % (
                self.builder_name, failure.getErrorMessage(),
                failure.getTraceback()))

        # Decide if we need to terminate the job or reset/fail the builder.
        vitals = self.builder_factory.getVitals(self.builder_name)
        builder = self.builder_factory[self.builder_name]
        try:
            builder.handleFailure(self.logger)
            yield assessFailureCounts(
                self.logger, vitals, builder, self.slave_factory(vitals),
                self.interactor_factory(), failure.value)
            transaction.commit()
        except Exception:
            # Catastrophic code failure! Not much we can do.
            self.logger.error(
                "Miserable failure when trying to handle failure:\n",
                exc_info=True)
            transaction.abort()

    @defer.inlineCallbacks
    def checkCancellation(self, vitals, slave, interactor):
        """See if there is a pending cancellation request.

        If the current build is in status CANCELLING then terminate it
        immediately.

        :return: A deferred whose value is True if we recovered the builder
            by resuming a slave host, so that there is no need to update its
            status.
        """
        if vitals.build_queue is None:
            self.date_cancel = None
            defer.returnValue(False)
        build = vitals.build_queue.specific_job.build
        if build.status != BuildStatus.CANCELLING:
            self.date_cancel = None
            defer.returnValue(False)

        try:
            if self.date_cancel is None:
                self.logger.info("Cancelling build '%s'" % build.title)
                yield slave.abort()
                self.date_cancel = self._clock.seconds() + self.CANCEL_TIMEOUT
                defer.returnValue(False)
            else:
                # The BuildFarmJob will normally set the build's status to
                # something other than CANCELLING once the builder responds to
                # the cancel request.  This timeout is in case it doesn't.
                if self._clock.seconds() < self.date_cancel:
                    self.logger.info(
                        "Waiting for build '%s' to cancel" % build.title)
                    defer.returnValue(False)
                else:
                    raise BuildSlaveFailure(
                        "Build '%s' cancellation timed out" % build.title)
        except Exception as e:
            self.logger.info(
                "Build '%s' on %s failed to cancel" %
                (build.title, vitals.name))
            self.date_cancel = None
            vitals.build_queue.cancel()
            transaction.commit()
            value = yield interactor.resetOrFail(
                vitals, slave, self.builder_factory[vitals.name], self.logger,
                e)
            # value is not None if we resumed a slave host.
            defer.returnValue(value is not None)

    def getExpectedCookie(self, vitals):
        """Return the build cookie expected to be held by the slave.

        Calculating this requires hitting the DB, so it's cached based
        on the current BuildQueue.
        """
        if vitals.build_queue != self._cached_build_queue:
            if vitals.build_queue is not None:
                behavior = self.behavior_factory(
                    vitals.build_queue, self.builder_factory[vitals.name],
                    None)
                self._cached_build_cookie = behavior.getBuildCookie()
            else:
                self._cached_build_cookie = None
            self._cached_build_queue = vitals.build_queue
        return self._cached_build_cookie

    @defer.inlineCallbacks
    def scan(self):
        """Probe the builder and update/dispatch/collect as appropriate.

        :return: A Deferred that fires when the scan is complete.
        """
        self.logger.debug("Scanning %s." % self.builder_name)
        self.builder_factory.prescanUpdate()
        vitals = self.builder_factory.getVitals(self.builder_name)
        interactor = self.interactor_factory()
        slave = self.slave_factory(vitals)

        # Confirm that the DB and slave sides are in a valid, mutually
        # agreeable state.
        lost_reason = None
        if not vitals.builderok:
            lost_reason = '%s is disabled' % vitals.name
        else:
            cancelled = yield self.checkCancellation(vitals, slave, interactor)
            if cancelled:
                return
            lost = yield interactor.rescueIfLost(
                vitals, slave, self.getExpectedCookie(vitals), self.logger)
            if lost:
                lost_reason = '%s is lost' % vitals.name

        # The slave is lost or the builder is disabled. We can't
        # continue to update the job status or dispatch a new job, so
        # just rescue the assigned job, if any, so it can be dispatched
        # to another slave.
        if lost_reason is not None:
            if vitals.build_queue is not None:
                self.logger.warn(
                    "%s. Resetting BuildQueue %d.", lost_reason,
                    vitals.build_queue.id)
                vitals.build_queue.reset()
                transaction.commit()
            return

        # We've confirmed that the slave state matches the DB. Continue
        # with updating the job status, or dispatching a new job if the
        # builder is idle.
        if vitals.build_queue is not None:
            # Scan the slave and get the logtail, or collect the build
            # if it's ready.  Yes, "updateBuild" is a bad name.
            yield interactor.updateBuild(
                vitals, slave, self.builder_factory, self.behavior_factory)
        elif vitals.manual:
            # If the builder is in manual mode, don't dispatch anything.
            self.logger.debug(
                '%s is in manual mode, not dispatching.' % vitals.name)
        else:
            # See if there is a job we can dispatch to the builder slave.
            builder = self.builder_factory[self.builder_name]
            yield interactor.findAndStartJob(vitals, builder, slave)
            if builder.currentjob is not None:
                # After a successful dispatch we can reset the
                # failure_count.
                builder.resetFailureCount()
                transaction.commit()


class NewBuildersScanner:
    """If new builders appear, create a scanner for them."""

    # How often to check for new builders, in seconds.
    SCAN_INTERVAL = 15

    def __init__(self, manager, clock=None):
        self.manager = manager
        # Use the clock if provided, it's so that tests can
        # advance it.  Use the reactor by default.
        if clock is None:
            clock = reactor
        self._clock = clock
        self.current_builders = []

    def stop(self):
        """Terminate the LoopingCall."""
        self.loop.stop()

    def scheduleScan(self):
        """Schedule a callback SCAN_INTERVAL seconds later."""
        self.loop = LoopingCall(self.scan)
        self.loop.clock = self._clock
        self.stopping_deferred = self.loop.start(self.SCAN_INTERVAL)
        return self.stopping_deferred

    def scan(self):
        """If a new builder appears, create a SlaveScanner for it."""
        self.manager.builder_factory.update()
        new_builders = self.checkForNewBuilders()
        self.manager.addScanForBuilders(new_builders)

    def checkForNewBuilders(self):
        """See if any new builders were added."""
        new_builders = set(
            vitals.name for vitals in
            self.manager.builder_factory.iterVitals())
        old_builders = set(self.current_builders)
        extra_builders = new_builders.difference(old_builders)
        self.current_builders.extend(extra_builders)
        return list(extra_builders)


class BuilddManager(service.Service):
    """Main Buildd Manager service class."""

    def __init__(self, clock=None, builder_factory=None):
        self.builder_slaves = []
        self.builder_factory = builder_factory or PrefetchedBuilderFactory()
        self.logger = self._setupLogger()
        self.new_builders_scanner = NewBuildersScanner(
            manager=self, clock=clock)

    def _setupLogger(self):
        """Set up a 'slave-scanner' logger that redirects to twisted.

        Make it less verbose to avoid messing too much with the old code.
        """
        level = logging.INFO
        logger = logging.getLogger(BUILDD_MANAGER_LOG_NAME)

        # Redirect the output to the twisted log module.
        channel = logging.StreamHandler(log.StdioOnnaStick())
        channel.setLevel(level)
        channel.setFormatter(logging.Formatter('%(message)s'))

        logger.addHandler(channel)
        logger.setLevel(level)
        return logger

    def startService(self):
        """Service entry point, called when the application starts."""
        # Ask the NewBuildersScanner to add and start SlaveScanners for
        # each current builder, and any added in the future.
        self.new_builders_scanner.scheduleScan()

    def stopService(self):
        """Callback for when we need to shut down."""
        # XXX: lacks unit tests
        # All the SlaveScanner objects need to be halted gracefully.
        deferreds = [slave.stopping_deferred for slave in self.builder_slaves]
        deferreds.append(self.new_builders_scanner.stopping_deferred)

        self.new_builders_scanner.stop()
        for slave in self.builder_slaves:
            slave.stopCycle()

        # The 'stopping_deferred's are called back when the loops are
        # stopped, so we can wait on them all at once here before
        # exiting.
        d = defer.DeferredList(deferreds, consumeErrors=True)
        return d

    def addScanForBuilders(self, builders):
        """Set up scanner objects for the builders specified."""
        for builder in builders:
            slave_scanner = SlaveScanner(
                builder, self.builder_factory, self.logger)
            self.builder_slaves.append(slave_scanner)
            slave_scanner.startCycle()

        # Return the slave list for the benefit of tests.
        return self.builder_slaves
