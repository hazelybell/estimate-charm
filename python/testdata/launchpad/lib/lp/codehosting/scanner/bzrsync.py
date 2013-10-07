#!/usr/bin/python
#
# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Import version control metadata from a Bazaar branch into the database."""

__metaclass__ = type

__all__ = [
    "BzrSync",
    'schedule_diff_updates',
    'schedule_translation_templates_build',
    'schedule_translation_upload',
    ]

import logging

from bzrlib.graph import DictParentsProvider
from bzrlib.revision import NULL_REVISION
import pytz
from storm.locals import Store
import transaction
from zope.component import getUtility
from zope.event import notify

from lp.code.bzr import (
    branch_revision_history,
    get_ancestry,
    )
from lp.code.interfaces.branchjob import IRosettaUploadJobSource
from lp.code.interfaces.revision import IRevisionSet
from lp.code.model.branchrevision import BranchRevision
from lp.code.model.revision import Revision
from lp.codehosting.scanner import events
from lp.services.config import config
from lp.services.utils import iter_list_chunks
from lp.translations.interfaces.translationtemplatesbuildjob import (
    ITranslationTemplatesBuildJobSource,
    )


UTC = pytz.timezone('UTC')


class BzrSync:
    """Import version control metadata from a Bazaar branch into the database.
    """

    def __init__(self, branch, logger=None):
        self.db_branch = branch
        if logger is None:
            logger = logging.getLogger(self.__class__.__name__)
        self.logger = logger
        self.revision_set = getUtility(IRevisionSet)

    def syncBranchAndClose(self, bzr_branch=None):
        """Synchronize the database with a Bazaar branch, handling locking.
        """
        if bzr_branch is None:
            bzr_branch = self.db_branch.getBzrBranch()
        bzr_branch.lock_read()
        try:
            self.syncBranch(bzr_branch)
        finally:
            bzr_branch.unlock()

    def syncBranch(self, bzr_branch):
        """Synchronize the database view of a branch with Bazaar data.

        `bzr_branch` must be read locked.

        Several tables must be updated:

        * Revision: there must be one Revision row for each revision in the
          branch ancestry. If the row for a revision that has just been added
          to the branch is already present, it must be checked for
          consistency.

        * BranchRevision: there must be one BrancheRevision row for each
          revision in the branch ancestry. If history revisions became merged
          revisions, the corresponding rows must be changed.

        * Branch: the branch-scanner status information must be updated when
          the sync is complete.
        """
        self.logger.info("Scanning branch: %s", self.db_branch.unique_name)
        self.logger.info("    from %s", bzr_branch.base)
        # Get the history and ancestry from the branch first, to fail early
        # if something is wrong with the branch.
        self.logger.info("Retrieving history from bzrlib.")
        bzr_history = branch_revision_history(bzr_branch)
        # The BranchRevision, Revision and RevisionParent tables are only
        # written to by the branch-scanner, so they are not subject to
        # write-lock contention. Update them all in a single transaction to
        # improve the performance and allow garbage collection in the future.
        db_ancestry, db_history = self.retrieveDatabaseAncestry()

        (new_ancestry, branchrevisions_to_delete,
            revids_to_insert) = self.planDatabaseChanges(
            bzr_branch, bzr_history, db_ancestry, db_history)
        new_db_revs = (
            new_ancestry - getUtility(IRevisionSet).onlyPresent(new_ancestry))
        self.logger.info("Adding %s new revisions.", len(new_db_revs))
        for revids in iter_list_chunks(list(new_db_revs), 10000):
            revisions = self.getBazaarRevisions(bzr_branch, revids)
            self.syncRevisions(bzr_branch, revisions, revids_to_insert)
        self.deleteBranchRevisions(branchrevisions_to_delete)
        self.insertBranchRevisions(bzr_branch, revids_to_insert)
        transaction.commit()
        # Synchronize the RevisionCache for this branch.
        getUtility(IRevisionSet).updateRevisionCacheForBranch(self.db_branch)
        transaction.commit()

        # Notify any listeners that the tip of the branch has changed, but
        # before we've actually updated the database branch.
        initial_scan = (len(db_history) == 0)
        notify(events.TipChanged(self.db_branch, bzr_branch, initial_scan))

        # The Branch table is modified by other systems, including the web UI,
        # so we need to update it in a short transaction to avoid causing
        # timeouts in the webapp. This opens a small race window where the
        # revision data is updated in the database, but the Branch table has
        # not been updated. Since this has no ill-effect, and can only err on
        # the pessimistic side (tell the user the data has not yet been
        # updated although it has), the race is acceptable.
        self.updateBranchStatus(bzr_history)
        notify(
            events.ScanCompleted(
                self.db_branch, bzr_branch, self.logger, new_ancestry))
        transaction.commit()

    def retrieveDatabaseAncestry(self):
        """Efficiently retrieve ancestry from the database."""
        self.logger.info("Retrieving ancestry from database.")
        db_ancestry, db_history = self.db_branch.getScannerData()
        return db_ancestry, db_history

    def _getRevisionGraph(self, bzr_branch, db_last):
        if bzr_branch.repository.has_revision(db_last):
            return bzr_branch.repository.get_graph()
        revisions = Store.of(self.db_branch).find(Revision,
                BranchRevision.branch_id == self.db_branch.id,
                Revision.id == BranchRevision.revision_id)
        parent_map = dict(
            (r.revision_id, r.parent_ids) for r in revisions)
        parents_provider = DictParentsProvider(parent_map)

        class PPSource:

            @staticmethod
            def _make_parents_provider():
                return parents_provider

        return bzr_branch.repository.get_graph(PPSource)

    def getAncestryDelta(self, bzr_branch):
        bzr_last = bzr_branch.last_revision()
        db_last = self.db_branch.last_scanned_id
        if db_last is None:
            added_ancestry = get_ancestry(bzr_branch.repository, bzr_last)
            removed_ancestry = set()
        else:
            graph = self._getRevisionGraph(bzr_branch, db_last)
            added_ancestry, removed_ancestry = (
                graph.find_difference(bzr_last, db_last))
            added_ancestry.discard(NULL_REVISION)
        return added_ancestry, removed_ancestry

    def getHistoryDelta(self, bzr_history, db_history):
        self.logger.info("Calculating history delta.")
        common_len = min(len(bzr_history), len(db_history))
        while common_len > 0:
            # The outer conditional improves efficiency. Without it, the
            # algorithm is O(history-size * change-size), which can be
            # excessive if a long branch is replaced by another long branch
            # with a distant (or no) common mainline parent. The inner
            # conditional is needed for correctness with branches where the
            # history does not follow the line of leftmost parents.
            if db_history[common_len - 1] == bzr_history[common_len - 1]:
                if db_history[:common_len] == bzr_history[:common_len]:
                    break
            common_len -= 1
        # Revision added or removed from the branch's history. These lists may
        # include revisions whose history position has merely changed.
        removed_history = db_history[common_len:]
        added_history = bzr_history[common_len:]
        return added_history, removed_history

    def planDatabaseChanges(self, bzr_branch, bzr_history, db_ancestry,
                            db_history):
        """Plan database changes to synchronize with bzrlib data.

        Use the data retrieved by `retrieveDatabaseAncestry` and
        `retrieveBranchDetails` to plan the changes to apply to the database.
        """
        self.logger.info("Planning changes.")
        # Find the length of the common history.
        added_history, removed_history = self.getHistoryDelta(
            bzr_history, db_history)
        added_ancestry, removed_ancestry = self.getAncestryDelta(bzr_branch)

        notify(
            events.RevisionsRemoved(
                self.db_branch, bzr_branch, removed_history))

        # We must delete BranchRevision rows for all revisions which where
        # removed from the ancestry or whose sequence value has changed.
        branchrevisions_to_delete = set(removed_history)
        branchrevisions_to_delete.update(removed_ancestry)
        branchrevisions_to_delete.update(
            set(added_history).difference(added_ancestry))

        # We must insert BranchRevision rows for all revisions which were
        # added to the ancestry or whose sequence value has changed.
        last_revno = len(bzr_history)
        revids_to_insert = dict(
            self.revisionsToInsert(
                added_history, last_revno, added_ancestry))
        # We must remove any stray BranchRevisions that happen to already be
        # present.
        existing_branchrevisions = Store.of(self.db_branch).find(
            Revision.revision_id, BranchRevision.branch == self.db_branch,
            BranchRevision.revision_id == Revision.id,
            Revision.revision_id.is_in(revids_to_insert))
        branchrevisions_to_delete.update(existing_branchrevisions)

        return (added_ancestry, list(branchrevisions_to_delete),
                revids_to_insert)

    def getBazaarRevisions(self, bzr_branch, revisions):
        """Like ``get_revisions(revisions)`` but filter out ghosts first.

        :param revisions: the set of Bazaar revision IDs to return bzrlib
            Revision objects for.
        """
        revisions = bzr_branch.repository.get_parent_map(revisions)
        return bzr_branch.repository.get_revisions(revisions.keys())

    def syncRevisions(self, bzr_branch, bzr_revisions, revids_to_insert):
        """Import the supplied revisions.

        :param bzr_branch: The Bazaar branch that's being scanned.
        :param bzr_revisions: the revisions to import
        :type bzr_revision: bzrlib.revision.Revision
        :param revids_to_insert: a dict of revision ids to integer
            revno. Non-mainline revisions will be mapped to None.
        """
        self.revision_set.newFromBazaarRevisions(bzr_revisions)
        mainline_revisions = []
        for bzr_revision in bzr_revisions:
            if revids_to_insert[bzr_revision.revision_id] is None:
                continue
            mainline_revisions.append(bzr_revision)
        notify(events.NewMainlineRevisions(
            self.db_branch, bzr_branch, mainline_revisions))

    @staticmethod
    def revisionsToInsert(added_history, last_revno, added_ancestry):
        """Calculate the revisions to insert and their revnos.

        :param added_history: A list of revision ids added to the revision
            history in parent-to-child order.
        :param last_revno: The revno of the last revision.
        :param added_ancestry: A set of revisions that have been added to the
            ancestry of the branch.  May overlap with added_history.
        """
        start_revno = last_revno - len(added_history) + 1
        for (revno, revision_id) in enumerate(added_history, start_revno):
            yield revision_id, revno
        for revision_id in added_ancestry.difference(added_history):
            yield revision_id, None

    def deleteBranchRevisions(self, revision_ids_to_delete):
        """Delete a batch of BranchRevision rows."""
        self.logger.info("Deleting %d branchrevision records.",
            len(revision_ids_to_delete))
        # Use a config value to work out how many to delete at a time.
        # Deleting more than one at a time is significantly more efficient
        # than doing one at a time, but the actual optimal count is a bit up
        # in the air.
        batch_size = config.branchscanner.branch_revision_delete_count
        while revision_ids_to_delete:
            batch = revision_ids_to_delete[:batch_size]
            revision_ids_to_delete[:batch_size] = []
            self.db_branch.removeBranchRevisions(batch)

    def insertBranchRevisions(self, bzr_branch, revids_to_insert):
        """Insert a batch of BranchRevision rows."""
        self.logger.info("Inserting %d branchrevision records.",
            len(revids_to_insert))
        revid_seq_pairs = revids_to_insert.items()
        for revid_seq_pair_chunk in iter_list_chunks(revid_seq_pairs, 10000):
            self.db_branch.createBranchRevisionFromIDs(revid_seq_pair_chunk)

    def updateBranchStatus(self, bzr_history):
        """Update the branch-scanner status in the database Branch table."""
        # Record that the branch has been updated.
        revision_count = len(bzr_history)
        if revision_count > 0:
            last_revision = bzr_history[-1]
            revision = getUtility(IRevisionSet).getByRevisionId(last_revision)
        else:
            revision = None
        self.logger.info(
            "Updating branch scanner status: %s revs", revision_count)
        self.db_branch.updateScannedDetails(revision, revision_count)


def schedule_translation_upload(tip_changed):
    getUtility(IRosettaUploadJobSource).create(
        tip_changed.db_branch, tip_changed.old_tip_revision_id)


def schedule_translation_templates_build(tip_changed):
    utility = getUtility(ITranslationTemplatesBuildJobSource)
    utility.scheduleTranslationTemplatesBuild(tip_changed.db_branch)


def schedule_diff_updates(tip_changed):
    tip_changed.db_branch.scheduleDiffUpdates()


def update_recipes(tip_changed):
    for recipe in tip_changed.db_branch.recipes:
        recipe.is_stale = True
