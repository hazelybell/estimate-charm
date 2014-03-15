# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A utility module for the update-bugtasktargetnamecaches.py cronscript."""

__metaclass__ = type
__all__ = ['BugTaskTargetNameCacheUpdater']

from collections import defaultdict

from zope.interface import implements

from lp.bugs.model.bugtask import (
    bug_target_from_key,
    BugTask,
    )
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.product import Product
from lp.registry.model.productseries import ProductSeries
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.interfaces import (
    IMasterStore,
    ISlaveStore,
    )
from lp.services.looptuner import (
    ITunableLoop,
    LoopTuner,
    )

# These two tuples must be in the same order. They specify the ID
# columns to get from BugTask, and the classes that they correspond to.
target_columns = (
    BugTask.productID, BugTask.productseriesID, BugTask.distributionID,
    BugTask.distroseriesID, BugTask.sourcepackagenameID,
    BugTask.targetnamecache)
target_classes = (
    Product, ProductSeries, Distribution, DistroSeries, SourcePackageName)


class BugTaskTargetNameCachesTunableLoop(object):
    """An `ITunableLoop` for updating BugTask targetname caches."""

    implements(ITunableLoop)

    def __init__(self, transaction, logger, offset=0):
        self.transaction = transaction
        self.logger = logger
        self.offset = offset
        self.total_updated = 0

        self.logger.info("Calculating targets.")
        self.transaction.begin()
        self.candidates = self.determineCandidates()
        self.transaction.abort()
        self.logger.info("Will check %i targets." % len(self.candidates))

    def determineCandidates(self):
        """Find all distinct BugTask targets with their cached names.

        Returns a list of (target, set_of_cached_names) pairs, where target is
        a tuple of IDs from the columns in target_columns.
        """
        store = ISlaveStore(BugTask)
        candidate_set = store.find(target_columns).config(distinct=True)
        candidates = defaultdict(set)
        for candidate in candidate_set:
            candidates[candidate[:-1]].add(candidate[-1])
        return list(candidates.iteritems())

    def isDone(self):
        """See `ITunableLoop`."""
        return self.offset >= len(self.candidates)

    def __call__(self, chunk_size):
        """Take a batch of targets and update their BugTasks' name caches.

        See `ITunableLoop`.
        """
        # XXX 2008-03-05 gmb:
        #     We cast chunk_size to an integer to ensure that we're not
        #     trying to slice using floats or anything similarly
        #     foolish. We shouldn't have to do this, but bug #198767
        #     means that we do.
        chunk_size = int(chunk_size)

        start = self.offset
        end = self.offset + chunk_size

        chunk = self.candidates[start:end]

        self.transaction.begin()
        store = IMasterStore(BugTask)

        # Transpose the target rows into lists of object IDs to retrieve.
        ids_to_cache = zip(*(target for (target, names) in chunk))
        for index, cls in enumerate(target_classes):
            # Get all of the objects that we will need into the cache.
            list(store.find(cls, cls.id.is_in(set(ids_to_cache[index]))))

        for target_bits, cached_names in chunk:
            self.offset += 1
            # Resolve the IDs to objects, and get the actual IBugTarget.
            # If the ID is None, don't even try to get an object.
            target_objects = (
                (store.get(cls, id) if id is not None else None)
                for cls, id in zip(target_classes, target_bits))
            target = bug_target_from_key(*target_objects)
            new_name = target.bugtargetdisplayname
            cached_names.discard(new_name)
            # If there are any outdated names cached, update them all in
            # a single query.
            if len(cached_names) > 0:
                self.logger.info(
                    "Updating %r to '%s'." % (tuple(cached_names), new_name))
                self.total_updated += len(cached_names)
                conditions = (
                    col == id for col, id in zip(target_columns, target_bits))
                to_update = store.find(
                    BugTask,
                    BugTask.targetnamecache.is_in(cached_names),
                    *conditions)
                to_update.set(targetnamecache=new_name)

        self.logger.info("Checked %i targets." % len(chunk))

        self.transaction.commit()


class BugTaskTargetNameCacheUpdater:
    """A runnable class which updates the bugtask target name caches."""

    def __init__(self, transaction, logger):
        self.transaction = transaction
        self.logger = logger

    def run(self):
        """Update the bugtask target name caches."""
        self.logger.info("Updating targetname cache of bugtasks.")
        loop = BugTaskTargetNameCachesTunableLoop(
            self.transaction, self.logger)

        # We use the LoopTuner class to try and get an ideal number of
        # bugtasks updated for each iteration of the loop (see the
        # LoopTuner documentation for more details).
        loop_tuner = LoopTuner(loop, 2)
        loop_tuner.run()

        self.logger.info("Updated %i target names." % loop.total_updated)
        self.logger.info("Finished updating targetname cache of bugtasks.")
