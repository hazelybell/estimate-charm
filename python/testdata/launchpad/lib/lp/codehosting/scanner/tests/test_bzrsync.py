#!/usr/bin/python
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import datetime
import os
import random
import time

from bzrlib.revision import (
    NULL_REVISION,
    Revision as BzrRevision,
    )
from bzrlib.tests import TestCaseWithTransport
from bzrlib.uncommit import uncommit
from fixtures import TempDir
import pytz
from storm.locals import Store
from twisted.python.util import mergeFunctionMetadata
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.bzr import branch_revision_history
from lp.code.interfaces.branchjob import IRosettaUploadJobSource
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.revision import IRevisionSet
from lp.code.model.branchmergeproposaljob import (
    BranchMergeProposalJobSource,
    BranchMergeProposalJobType,
    )
from lp.code.model.branchrevision import BranchRevision
from lp.code.model.revision import (
    Revision,
    RevisionAuthor,
    RevisionParent,
    )
from lp.code.model.tests.test_diff import commit_file
from lp.codehosting.bzrutils import (
    read_locked,
    write_locked,
    )
from lp.codehosting.safe_open import SafeBranchOpener
from lp.codehosting.scanner.bzrsync import BzrSync
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.osutils import override_environ
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import (
    dbuser,
    lp_dbuser,
    switch_dbuser,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )


def run_as_db_user(username):
    """Create a decorator that will run a function as the given database user.
    """

    def _run_with_different_user(f):

        def decorated(*args, **kwargs):
            with dbuser(username):
                return f(*args, **kwargs)
        return mergeFunctionMetadata(f, decorated)

    return _run_with_different_user


class BzrSyncTestCase(TestCaseWithTransport, TestCaseWithFactory):
    """Common base for BzrSync test cases."""

    layer = LaunchpadZopelessLayer

    LOG = "Log message"

    def setUp(self):
        super(BzrSyncTestCase, self).setUp()
        SafeBranchOpener.install_hook()
        self.disable_directory_isolation()
        self.useBzrBranches(direct_database=True)
        self.makeFixtures()
        switch_dbuser("branchscanner")
        # Catch both constraints and permissions for the db user.
        self.addCleanup(Store.of(self.db_branch).flush)

    def tearDown(self):
        super(BzrSyncTestCase, self).tearDown()

    def makeFixtures(self):
        """Makes test fixtures before we switch to the scanner db user."""
        self.db_branch, self.bzr_tree = self.create_branch_and_tree(
            db_branch=self.makeDatabaseBranch())
        self.bzr_branch = self.bzr_tree.branch

    def syncBazaarBranchToDatabase(self, bzr_branch, db_branch):
        """Sync `bzr_branch` into the database as `db_branch`."""
        syncer = self.makeBzrSync(db_branch)
        syncer.syncBranchAndClose(bzr_branch)

    def makeDatabaseBranch(self, *args, **kwargs):
        """Make an arbitrary branch in the database."""
        LaunchpadZopelessLayer.txn.begin()
        new_branch = self.factory.makeAnyBranch(*args, **kwargs)
        # Unsubscribe the implicit owner subscription.
        new_branch.unsubscribe(new_branch.owner, new_branch.owner)
        LaunchpadZopelessLayer.txn.commit()
        return new_branch

    def getCounts(self):
        """Return the number of rows in core revision-related tables.

        :return: (num_revisions, num_branch_revisions, num_revision_parents,
            num_revision_authors)
        """
        store = IStore(Revision)
        return (
            store.find(Revision).count(),
            store.find(BranchRevision).count(),
            store.find(RevisionParent).count(),
            store.find(RevisionAuthor).count())

    def assertCounts(self, counts, new_revisions=0, new_numbers=0,
                     new_parents=0, new_authors=0):
        (old_revision_count,
         old_revisionnumber_count,
         old_revisionparent_count,
         old_revisionauthor_count) = counts
        (new_revision_count,
         new_revisionnumber_count,
         new_revisionparent_count,
         new_revisionauthor_count) = self.getCounts()
        self.assertEqual(
            new_revisions,
            new_revision_count - old_revision_count,
            "Wrong number of new database Revisions.")
        self.assertEqual(
            new_numbers,
            new_revisionnumber_count - old_revisionnumber_count,
            "Wrong number of new BranchRevisions.")
        self.assertEqual(
            new_parents,
            new_revisionparent_count - old_revisionparent_count,
            "Wrong number of new RevisionParents.")
        self.assertEqual(
            new_authors,
            new_revisionauthor_count - old_revisionauthor_count,
            "Wrong number of new RevisionAuthors.")

    def makeBzrSync(self, db_branch):
        """Create a BzrSync instance for the test branch.

        This method allow subclasses to instrument the BzrSync instance used
        in syncBranch.
        """
        return BzrSync(db_branch)

    def syncAndCount(self, db_branch=None, new_revisions=0, new_numbers=0,
                     new_parents=0, new_authors=0):
        """Run BzrSync and assert the number of rows added to each table."""
        if db_branch is None:
            db_branch = self.db_branch
        counts = self.getCounts()
        self.makeBzrSync(db_branch).syncBranchAndClose()
        self.assertCounts(
            counts, new_revisions=new_revisions, new_numbers=new_numbers,
            new_parents=new_parents, new_authors=new_authors)

    def commitRevision(self, message=None, committer=None,
                       extra_parents=None, rev_id=None,
                       timestamp=None, timezone=None, revprops=None):
        if message is None:
            message = self.LOG
        if committer is None:
            committer = self.factory.getUniqueString()
        if extra_parents is not None:
            self.bzr_tree.add_pending_merge(*extra_parents)
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            return self.bzr_tree.commit(
                message, committer=committer, rev_id=rev_id,
                timestamp=timestamp, timezone=timezone, allow_pointless=True,
                revprops=revprops)

    def uncommitRevision(self):
        branch = self.bzr_tree.branch
        uncommit(branch, tree=self.bzr_tree)

    def makeBranchWithMerge(self, base_rev_id, trunk_rev_id, branch_rev_id,
                            merge_rev_id):
        """Make a branch that has had another branch merged into it.

        Creates two Bazaar branches and two database branches associated with
        them. The first branch has three commits: the base revision, the
        'trunk' revision and the 'merged' revision.

        The second branch is branched from the base revision, has the 'branch'
        revision committed to it and is then merged into the first branch.

        Or, in other words::

               merge
                 |  \
                 |   \
                 |    \
               trunk   branch
                 |    /
                 |   /
                 |  /
                base

        :param base_rev_id: The revision ID of the initial commit.
        :param trunk_rev_id: The revision ID of the mainline commit.
        :param branch_rev_id: The revision ID of the revision committed to
            the branch that is merged into the mainline.
        :param merge_rev_id: The revision ID of the revision that merges the
            branch into the mainline branch.
        :return: (db_trunk, trunk_tree), (db_branch, branch_tree).
        """

        with lp_dbuser():
            # Make the base revision.
            db_branch = self.makeDatabaseBranch()
            db_branch, trunk_tree = self.create_branch_and_tree(
                db_branch=db_branch)
            # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
            # required to generate the revision-id.
            with override_environ(BZR_EMAIL='me@example.com'):
                trunk_tree.commit(u'base revision', rev_id=base_rev_id)

                # Branch from the base revision.
                new_db_branch = self.makeDatabaseBranch(
                    product=db_branch.product)
                new_db_branch, branch_tree = self.create_branch_and_tree(
                    db_branch=new_db_branch)
                branch_tree.pull(trunk_tree.branch)

                # Commit to both branches.
                trunk_tree.commit(u'trunk revision', rev_id=trunk_rev_id)
                branch_tree.commit(u'branch revision', rev_id=branch_rev_id)

                # Merge branch into trunk.
                trunk_tree.merge_from_branch(branch_tree.branch)
                trunk_tree.commit(u'merge revision', rev_id=merge_rev_id)

        return (db_branch, trunk_tree), (new_db_branch, branch_tree)

    def getBranchRevisions(self, db_branch):
        """Get a set summarizing the BranchRevision rows in the database.

        :return: A set of tuples (sequence, revision-id) for all the
            BranchRevisions rows belonging to self.db_branch.
        """
        return set(IStore(BranchRevision).find(
            (BranchRevision.sequence, Revision.revision_id),
            Revision.id == BranchRevision.revision_id,
            BranchRevision.branch == db_branch))

    def writeToFile(self, filename="file", contents=None):
        """Set the contents of the specified file.

        This also adds the file to the bzr working tree if
        it isn't already there.
        """
        file = open(os.path.join(self.bzr_tree.basedir, filename), "w")
        if contents is None:
            file.write(str(time.time() + random.random()))
        else:
            file.write(contents)
        file.close()
        self.bzr_tree.lock_write()
        try:
            inventory = self.bzr_tree.read_working_inventory()
            if not inventory.has_filename(filename):
                self.bzr_tree.add(filename)
        finally:
            self.bzr_tree.unlock()


class TestBzrSync(BzrSyncTestCase):

    def isMainline(self, db_branch, revision_id):
        """Is `revision_id` in the mainline history of `db_branch`?"""
        for branch_revision in db_branch.revision_history:
            if branch_revision.revision.revision_id == revision_id:
                return True
        return False

    def assertInMainline(self, revision_id, db_branch):
        """Assert that `revision_id` is in the mainline of `db_branch`."""
        self.failUnless(
            self.isMainline(db_branch, revision_id),
            "%r not in mainline of %r" % (revision_id, db_branch))

    def assertNotInMainline(self, revision_id, db_branch):
        """Assert that `revision_id` is not in the mainline of `db_branch`."""
        self.failIf(
            self.isMainline(db_branch, revision_id),
            "%r in mainline of %r" % (revision_id, db_branch))

    def test_empty_branch(self):
        # Importing an empty branch does nothing.
        self.syncAndCount()
        self.assertEqual(self.db_branch.revision_count, 0)

    def test_import_revision(self):
        # Importing a revision in history adds one revision and number.
        self.commitRevision()
        self.syncAndCount(new_revisions=1, new_numbers=1, new_authors=1)
        self.assertEqual(self.db_branch.revision_count, 1)

    def test_import_uncommit(self):
        # Second import honours uncommit.
        self.commitRevision()
        self.syncAndCount(new_revisions=1, new_numbers=1, new_authors=1)
        self.uncommitRevision()
        self.syncAndCount(new_numbers=-1)
        self.assertEqual(self.db_branch.revision_count, 0)

    def test_import_recommit(self):
        # Second import honours uncommit followed by commit.
        # When scanning the uncommit and new commit
        # there should be an email generated saying that
        # 1 (in this case) revision has been removed,
        # and another email with the diff and log message.
        self.commitRevision('first')
        self.syncAndCount(new_revisions=1, new_numbers=1, new_authors=1)
        self.assertEqual(self.db_branch.revision_count, 1)
        self.uncommitRevision()
        self.commitRevision('second')
        self.syncAndCount(new_revisions=1, new_authors=1)
        self.assertEqual(self.db_branch.revision_count, 1)
        [revno] = self.db_branch.revision_history
        self.assertEqual(revno.revision.log_body, 'second')

    def test_import_revision_with_url(self):
        # Importing a revision passing the url parameter works.
        self.commitRevision()
        counts = self.getCounts()
        bzrsync = BzrSync(self.db_branch)
        bzrsync.syncBranchAndClose()
        self.assertCounts(
            counts, new_revisions=1, new_numbers=1, new_authors=1)

    def test_new_author(self):
        # Importing a different committer adds it as an author.
        author = "Another Author <another@example.com>"
        self.commitRevision(committer=author)
        self.syncAndCount(new_revisions=1, new_numbers=1, new_authors=1)
        db_author = RevisionAuthor.selectOneBy(name=author)
        self.assertEquals(db_author.name, author)

    def test_new_parent(self):
        # Importing two revisions should import a new parent.
        self.commitRevision()
        self.commitRevision()
        self.syncAndCount(
            new_revisions=2, new_numbers=2, new_parents=1, new_authors=2)

    def test_sync_updates_branch(self):
        # test that the last scanned revision ID is recorded
        self.syncAndCount()
        self.assertEquals(NULL_REVISION, self.db_branch.last_scanned_id)
        last_modified = self.db_branch.date_last_modified
        last_scanned = self.db_branch.last_scanned
        self.commitRevision()
        self.syncAndCount(new_revisions=1, new_numbers=1, new_authors=1)
        self.assertEquals(self.bzr_branch.last_revision(),
                          self.db_branch.last_scanned_id)
        self.assertTrue(self.db_branch.last_scanned > last_scanned,
                        "last_scanned was not updated")
        self.assertTrue(self.db_branch.date_last_modified > last_modified,
                        "date_last_modifed was not updated")

    def test_timestamp_parsing(self):
        # Test that the timezone selected does not affect the
        # timestamp recorded in the database.
        self.commitRevision(rev_id='rev-1',
                            timestamp=1000000000.0, timezone=0)
        self.commitRevision(rev_id='rev-2',
                            timestamp=1000000000.0, timezone=28800)
        self.syncAndCount(
            new_revisions=2, new_numbers=2, new_parents=1, new_authors=2)
        rev_1 = Revision.selectOneBy(revision_id='rev-1')
        rev_2 = Revision.selectOneBy(revision_id='rev-2')
        UTC = pytz.timezone('UTC')
        dt = datetime.datetime.fromtimestamp(1000000000.0, UTC)
        self.assertEqual(rev_1.revision_date, dt)
        self.assertEqual(rev_2.revision_date, dt)

    def getAncestryDelta_test(self, clean_repository=False):
        """"Test various ancestry delta calculations.

        :param clean_repository: If True, perform calculations with a branch
            whose repository contains only revisions in the ancestry of the
            tip.
        """
        (db_branch, bzr_tree), ignored = self.makeBranchWithMerge(
            'base', 'trunk', 'branch', 'merge')
        bzr_branch = bzr_tree.branch
        self.factory.makeBranchRevision(db_branch, 'base', 0)
        self.factory.makeBranchRevision(
            db_branch, 'trunk', 1, parent_ids=['base'])
        self.factory.makeBranchRevision(
            db_branch, 'branch', None, parent_ids=['base'])
        self.factory.makeBranchRevision(
            db_branch, 'merge', 2, parent_ids=['trunk', 'branch'])
        sync = self.makeBzrSync(db_branch)
        self.useContext(write_locked(bzr_branch))

        def get_delta(bzr_rev, db_rev):
            db_branch.last_scanned_id = db_rev
            graph = bzr_branch.repository.get_graph()
            revno = graph.find_distance_to_null(bzr_rev, [])
            if clean_repository:
                tempdir = self.useFixture(TempDir()).path
                delta_branch = self.createBranchAtURL(tempdir)
                self.useContext(write_locked(delta_branch))
                delta_branch.pull(bzr_branch, stop_revision=bzr_rev)
            else:
                bzr_branch.set_last_revision_info(revno, bzr_rev)
                delta_branch = bzr_branch
            return sync.getAncestryDelta(delta_branch)

        added_ancestry, removed_ancestry = get_delta('merge', None)
        # All revisions are new for an unscanned branch
        self.assertEqual(
            set(['base', 'trunk', 'branch', 'merge']), added_ancestry)
        self.assertEqual(set(), removed_ancestry)
        added_ancestry, removed_ancestry = get_delta('merge', 'base')
        self.assertEqual(
            set(['trunk', 'branch', 'merge']), added_ancestry)
        self.assertEqual(set(), removed_ancestry)
        added_ancestry, removed_ancestry = get_delta(NULL_REVISION, 'merge')
        self.assertEqual(
            set(), added_ancestry)
        self.assertEqual(
            set(['base', 'trunk', 'branch', 'merge']), removed_ancestry)
        added_ancestry, removed_ancestry = get_delta('base', 'merge')
        self.assertEqual(
            set(), added_ancestry)
        self.assertEqual(
            set(['trunk', 'branch', 'merge']), removed_ancestry)
        added_ancestry, removed_ancestry = get_delta('trunk', 'branch')
        self.assertEqual(set(['trunk']), added_ancestry)
        self.assertEqual(set(['branch']), removed_ancestry)

    def test_getAncestryDelta(self):
        """"Test ancestry delta calculations with a dirty repository."""
        return self.getAncestryDelta_test()

    def test_getAncestryDelta_clean_repository(self):
        """"Test ancestry delta calculations with a clean repository."""
        return self.getAncestryDelta_test(clean_repository=True)

    def test_revisionsToInsert_empty(self):
        # An empty branch should have no revisions.
        self.assertEqual(
            [], list(BzrSync.revisionsToInsert([], 0, set())))

    def test_revisionsToInsert_linear(self):
        # If the branch has a linear ancestry, revisionsToInsert() should
        # yield each revision along with a sequence number, starting at 1.
        self.commitRevision(rev_id='rev-1')
        bzrsync = self.makeBzrSync(self.db_branch)
        bzr_history = branch_revision_history(self.bzr_branch)
        added_ancestry = bzrsync.getAncestryDelta(self.bzr_branch)[0]
        result = bzrsync.revisionsToInsert(
            bzr_history, self.bzr_branch.revno(), added_ancestry)
        self.assertEqual({'rev-1': 1}, dict(result))

    def test_revisionsToInsert_branched(self):
        # Confirm that these revisions are generated by getRevisions with None
        # as the sequence 'number'.
        (db_branch, bzr_tree), ignored = self.makeBranchWithMerge(
            'base', 'trunk', 'branch', 'merge')
        bzrsync = self.makeBzrSync(db_branch)
        bzr_history = branch_revision_history(bzr_tree.branch)
        added_ancestry = bzrsync.getAncestryDelta(bzr_tree.branch)[0]
        expected = {'base': 1, 'trunk': 2, 'merge': 3, 'branch': None}
        self.assertEqual(
            expected, dict(bzrsync.revisionsToInsert(bzr_history,
                bzr_tree.branch.revno(), added_ancestry)))

    def test_sync_with_merged_branches(self):
        # Confirm that when we syncHistory, all of the revisions are included
        # correctly in the BranchRevision table.
        (db_branch, branch_tree), ignored = self.makeBranchWithMerge(
            'r1', 'r2', 'r1.1.1', 'r3')
        self.makeBzrSync(db_branch).syncBranchAndClose()
        expected = set(
            [(1, 'r1'), (2, 'r2'), (3, 'r3'), (None, 'r1.1.1')])
        self.assertEqual(self.getBranchRevisions(db_branch), expected)

    def test_sync_merged_to_merging(self):
        # A revision's sequence in the BranchRevision table will change from
        # not NULL to NULL if that revision changes from mainline to not
        # mainline when synced.

        (db_trunk, trunk_tree), (db_branch, branch_tree) = (
            self.makeBranchWithMerge('base', 'trunk', 'branch', 'merge'))

        self.syncBazaarBranchToDatabase(trunk_tree.branch, db_branch)
        self.assertInMainline('trunk', db_branch)

        self.syncBazaarBranchToDatabase(branch_tree.branch, db_branch)
        self.assertNotInMainline('trunk', db_branch)
        self.assertInMainline('branch', db_branch)

    def test_sync_merging_to_merged(self):
        # When replacing a branch by one of the branches it merged, the
        # database must be updated appropriately.
        (db_trunk, trunk_tree), (db_branch, branch_tree) = (
            self.makeBranchWithMerge('base', 'trunk', 'branch', 'merge'))
        # First, sync with the merging branch.
        self.syncBazaarBranchToDatabase(trunk_tree.branch, db_trunk)
        # Then sync with the merged branch.
        self.syncBazaarBranchToDatabase(branch_tree.branch, db_trunk)
        expected = set([(1, 'base'), (2, 'branch')])
        self.assertEqual(self.getBranchRevisions(db_trunk), expected)

    def test_retrieveDatabaseAncestry(self):
        # retrieveDatabaseAncestry should set db_ancestry and db_history to
        # Launchpad's current understanding of the branch state.
        # db_branch_revision_map should map Bazaar revision_ids to
        # BranchRevision.ids.

        # Use the sampledata for this test, so we do not have to rely on
        # BzrSync to fill the database. That would cause a circular
        # dependency, as the test setup would depend on
        # retrieveDatabaseAncestry.
        branch = getUtility(IBranchLookup).getByUniqueName(
            '~name12/+junk/junk.contrib')
        branch_revisions = IStore(BranchRevision).find(
            BranchRevision, BranchRevision.branch == branch)
        sampledata = list(branch_revisions.order_by(BranchRevision.sequence))
        expected_ancestry = set(branch_revision.revision.revision_id
            for branch_revision in sampledata)
        expected_history = [branch_revision.revision.revision_id
            for branch_revision in sampledata
            if branch_revision.sequence is not None]

        self.create_branch_and_tree(db_branch=branch)

        bzrsync = self.makeBzrSync(branch)
        db_ancestry, db_history = (
            bzrsync.retrieveDatabaseAncestry())
        self.assertEqual(expected_ancestry, set(db_ancestry))
        self.assertEqual(expected_history, list(db_history))


class TestPlanDatabaseChanges(BzrSyncTestCase):

    def test_ancestry_already_present(self):
        # If a BranchRevision is being added, and it's already in the DB, but
        # not found through the graph operations, we should schedule it for
        # deletion anyway.
        rev1_id = self.bzr_tree.commit(
            'initial commit', committer='me@example.org')
        merge_tree = self.bzr_tree.bzrdir.sprout('merge').open_workingtree()
        merge_id = merge_tree.commit(
            'mergeable commit', committer='me@example.org')
        self.bzr_tree.merge_from_branch(merge_tree.branch)
        rev2_id = self.bzr_tree.commit(
            'merge', committer='me@example.org')
        self.useContext(read_locked(self.bzr_tree))
        syncer = BzrSync(self.db_branch)
        syncer.syncBranchAndClose(self.bzr_tree.branch)
        self.assertEqual(rev2_id, self.db_branch.last_scanned_id)
        self.db_branch.last_scanned_id = rev1_id
        db_ancestry, db_history = self.db_branch.getScannerData()
        branchrevisions_to_delete = syncer.planDatabaseChanges(
            self.bzr_branch, [rev1_id, rev2_id], db_ancestry, db_history)[1]
        self.assertIn(merge_id, branchrevisions_to_delete)


class TestBzrSyncRevisions(BzrSyncTestCase):
    """Tests for `BzrSync.syncRevisions`."""

    def setUp(self):
        BzrSyncTestCase.setUp(self)
        self.bzrsync = self.makeBzrSync(self.db_branch)

    def test_ancient_revision(self):
        # Test that we can sync revisions with negative, fractional
        # timestamps.

        # Make a negative, fractional timestamp and equivalent datetime
        UTC = pytz.timezone('UTC')
        old_timestamp = -0.5
        old_date = datetime.datetime(1969, 12, 31, 23, 59, 59, 500000, UTC)

        # Fake revision with negative timestamp.
        fake_rev = BzrRevision(
            revision_id='rev42', parent_ids=['rev1', 'rev2'],
            committer=self.factory.getUniqueString(), message=self.LOG,
            timestamp=old_timestamp, timezone=0, properties={})

        # Sync the revision.  The second parameter is a dict of revision ids
        # to revnos, and will error if the revision id is not in the dict.
        self.bzrsync.syncRevisions(None, [fake_rev], {'rev42': None})

        # Find the revision we just synced and check that it has the correct
        # date.
        revision = getUtility(IRevisionSet).getByRevisionId(
            fake_rev.revision_id)
        self.assertEqual(old_date, revision.revision_date)


class TestBzrTranslationsUploadJob(BzrSyncTestCase):
    """Tests BzrSync support for generating TranslationsUploadJobs."""

    def _makeProductSeries(self, mode=None):
        """Switch to the Launchpad db user to create and configure a
        product series that is linked to the branch.
        """
        with lp_dbuser():
            self.product_series = self.factory.makeProductSeries()
            self.product_series.branch = self.db_branch
            if mode is not None:
                self.product_series.translations_autoimport_mode = mode

    def test_upload_on_new_revision_no_series(self):
        # Syncing a branch with a changed tip does not create a
        # new RosettaUploadJob if no series is linked to this branch.
        self.commitRevision()
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        ready_jobs = list(getUtility(IRosettaUploadJobSource).iterReady())
        self.assertEqual([], ready_jobs)

    def test_upload_on_new_revision_series_not_configured(self):
        # Syncing a branch with a changed tip does not create a
        # new RosettaUploadJob if the linked product series is not
        # configured for translation uploads.
        self._makeProductSeries()
        self.commitRevision()
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        ready_jobs = list(getUtility(IRosettaUploadJobSource).iterReady())
        self.assertEqual([], ready_jobs)

    def test_upload_on_new_revision(self):
        # Syncing a branch with a changed tip creates a new RosettaUploadJob.
        self._makeProductSeries(
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        revision_id = self.commitRevision()
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        self.db_branch.last_mirrored_id = revision_id
        self.db_branch.last_scanned_id = revision_id
        ready_jobs = list(getUtility(IRosettaUploadJobSource).iterReady())
        self.assertEqual(1, len(ready_jobs))
        job = ready_jobs[0]
        # The right job will have our branch.
        self.assertEqual(self.db_branch, job.branch)


class TestUpdatePreviewDiffJob(BzrSyncTestCase):
    """Test the scheduling of jobs to update preview diffs."""

    @run_as_db_user(config.launchpad.dbuser)
    def test_create_on_new_revision(self):
        """When branch tip changes, a job is created."""
        bmp = self.factory.makeBranchMergeProposal(
            source_branch=self.db_branch)
        removeSecurityProxy(bmp).target_branch.last_scanned_id = 'rev'
        # The creation of a merge proposal has created an update preview diff
        # job, so we'll mark that one as done.
        bmp.next_preview_diff_job.start()
        bmp.next_preview_diff_job.complete()
        self.assertIs(None, bmp.next_preview_diff_job)
        switch_dbuser("branchscanner")
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        self.assertIsNot(None, bmp.next_preview_diff_job)


class TestGenerateIncrementalDiffJob(BzrSyncTestCase):
    """Test the scheduling of GenerateIncrementalDiffJobs."""

    def getPending(self):
        return list(
            BranchMergeProposalJobSource.iterReady(
                BranchMergeProposalJobType.GENERATE_INCREMENTAL_DIFF
                )
            )

    @run_as_db_user(config.launchpad.dbuser)
    def test_create_on_new_revision(self):
        """When branch tip changes, a job is created."""
        parent_id = commit_file(self.db_branch, 'foo', 'bar')
        self.factory.makeBranchRevision(self.db_branch, parent_id,
                revision_date=self.factory.getUniqueDate())
        self.db_branch.last_scanned_id = parent_id
        # Make sure that the merge proposal is created in the past.
        date_created = (
            datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=7))
        bmp = self.factory.makeBranchMergeProposal(
            source_branch=self.db_branch,
            date_created=date_created)
        revision_id = commit_file(self.db_branch, 'foo', 'baz')
        removeSecurityProxy(bmp).target_branch.last_scanned_id = 'rev'
        self.assertEqual([], self.getPending())
        switch_dbuser("branchscanner")
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        (job,) = self.getPending()
        self.assertEqual(revision_id, job.new_revision_id)
        self.assertEqual(parent_id, job.old_revision_id)


class TestSetRecipeStale(BzrSyncTestCase):
    """Test recipes associated with the branch are marked stale."""

    @run_as_db_user(config.launchpad.dbuser)
    def test_base_branch_recipe(self):
        """On tip change, recipes where this branch is base become stale."""
        recipe = self.factory.makeSourcePackageRecipe(
            branches=[self.db_branch])
        removeSecurityProxy(recipe).is_stale = False
        switch_dbuser("branchscanner")
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        self.assertEqual(True, recipe.is_stale)

    @run_as_db_user(config.launchpad.dbuser)
    def test_instruction_branch_recipe(self):
        """On tip change, recipes including this branch become stale."""
        recipe = self.factory.makeSourcePackageRecipe(
            branches=[self.factory.makeBranch(), self.db_branch])
        removeSecurityProxy(recipe).is_stale = False
        switch_dbuser("branchscanner")
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        self.assertEqual(True, recipe.is_stale)

    @run_as_db_user(config.launchpad.dbuser)
    def test_unrelated_branch_recipe(self):
        """On tip unrelated recipes are left alone."""
        recipe = self.factory.makeSourcePackageRecipe()
        removeSecurityProxy(recipe).is_stale = False
        switch_dbuser("branchscanner")
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        self.assertEqual(False, recipe.is_stale)


class TestRevisionProperty(BzrSyncTestCase):
    """Tests for storting revision properties."""

    def test_revision_properties(self):
        # Revisions with properties should have records stored in the
        # RevisionProperty table, accessible through Revision.getProperties().
        properties = {'name': 'value'}
        self.commitRevision(rev_id='rev1', revprops=properties)
        self.makeBzrSync(self.db_branch).syncBranchAndClose()
        # Check that properties were saved to the revision.
        bzr_revision = self.bzr_branch.repository.get_revision('rev1')
        self.assertEquals(properties, bzr_revision.properties)
        # Check that properties are stored in the database.
        db_revision = getUtility(IRevisionSet).getByRevisionId('rev1')
        self.assertEquals(properties, db_revision.getProperties())
