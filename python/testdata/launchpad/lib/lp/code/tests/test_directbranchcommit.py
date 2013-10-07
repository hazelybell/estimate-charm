# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `DirectBranchCommit`."""

__metaclass__ = type

from testtools.testcase import ExpectedException
from zope.security.proxy import removeSecurityProxy

from lp.code.errors import StaleLastMirrored
from lp.code.model.directbranchcommit import (
    ConcurrentUpdateError,
    DirectBranchCommit,
    )
from lp.testing import (
    map_branch_contents,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class DirectBranchCommitTestCase:
    """Base class for `DirectBranchCommit` tests."""
    db_branch = None
    committer = None

    def setUp(self):
        super(DirectBranchCommitTestCase, self).setUp()
        self.useBzrBranches(direct_database=True)

        self.series = self.factory.makeProductSeries()
        self.db_branch, self.tree = self.create_branch_and_tree()

        self.series.translations_branch = self.db_branch

        self._setUpCommitter()
        self.addCleanup(self._tearDownCommitter)

    def _setUpCommitter(self, update_last_scanned_id=True):
        """Clean up any existing `DirectBranchCommit`, set up a new one."""
        if self.committer:
            self.committer.unlock()

        self.committer = DirectBranchCommit(self.db_branch)
        if update_last_scanned_id:
            self.committer.last_scanned_id = (
                self.committer.bzrbranch.last_revision())

    def _tearDownCommitter(self):
        if self.committer:
            self.committer.unlock()

    def _getContents(self):
        """Return branch contents as dict mapping filenames to contents."""
        return map_branch_contents(self.committer.db_branch.getBzrBranch())


class TestDirectBranchCommit(DirectBranchCommitTestCase, TestCaseWithFactory):
    """Test `DirectBranchCommit`."""

    layer = LaunchpadZopelessLayer

    def test_defaults_to_branch_owner(self):
        # If no committer is given, DirectBranchCommits defaults to
        # attributing changes to the branch owner.
        self.assertEqual(self.db_branch.owner, self.committer.committer)

    def test_DirectBranchCommit_empty_initial_commit_noop(self):
        # An empty initial commit to a branch is a no-op.
        self.assertEqual('null:', self.tree.branch.last_revision())
        self.committer.commit('')
        self.assertEqual({}, self._getContents())
        self.assertEqual('null:', self.tree.branch.last_revision())

    def _addInitialCommit(self):
        self.committer._getDir('')
        rev_id = self.committer.commit('Commit creation of root dir.')
        self._setUpCommitter()
        return rev_id

    def test_DirectBranchCommit_commits_no_changes(self):
        # Committing nothing to an empty branch leaves its tree empty.
        self.assertEqual('null:', self.tree.branch.last_revision())
        old_rev_id = self.tree.branch.last_revision()
        self._addInitialCommit()
        self.committer.commit('')
        self.assertEqual({}, self._getContents())
        self.assertNotEqual(old_rev_id, self.tree.branch.last_revision())

    def test_DirectBranchCommit_rejects_change_after_commit(self):
        # Changes are not accepted after commit.
        self.committer.commit('')
        self.assertRaises(AssertionError, self.committer.writeFile, 'x', 'y')

    def test_DirectBranchCommit_adds_file(self):
        # DirectBranchCommit can add a new file to the branch.
        self.committer.writeFile('file.txt', 'contents')
        self.committer.commit('')
        self.assertEqual({'file.txt': 'contents'}, self._getContents())

    def test_commit_returns_revision_id(self):
        # DirectBranchCommit.commit returns the new revision_id.
        self.committer.writeFile('file.txt', 'contents')
        revision_id = self.committer.commit('')
        branch_revision_id = self.committer.bzrbranch.last_revision()
        self.assertEqual(branch_revision_id, revision_id)

    def test_commit_uses_merge_parents(self):
        # DirectBranchCommit.commit returns uses merge parents
        self._tearDownCommitter()
        # Merge parents cannot be specified for initial commit, so do an
        # empty commit.
        self.tree.commit('foo', committer='foo@bar', rev_id='foo')
        self.db_branch.last_mirrored_id = 'foo'
        committer = DirectBranchCommit(
            self.db_branch, merge_parents=['parent-1', 'parent-2'])
        committer.last_scanned_id = (
            committer.bzrbranch.last_revision())
        committer.writeFile('file.txt', 'contents')
        committer.commit('')
        branch_revision_id = committer.bzrbranch.last_revision()
        branch_revision = committer.bzrbranch.repository.get_revision(
            branch_revision_id)
        self.assertEqual(
            ['parent-1', 'parent-2'], branch_revision.parent_ids[1:])

    def test_DirectBranchCommit_aborts_cleanly(self):
        # If a DirectBranchCommit is not committed, its changes do not
        # go into the branch.
        self.committer.writeFile('oldfile.txt', 'already here')
        self.committer.commit('')
        self._setUpCommitter()
        self.committer.writeFile('newfile.txt', 'adding this')
        self._setUpCommitter()
        self.assertEqual({'oldfile.txt': 'already here'}, self._getContents())
        self.committer.unlock()

    def test_DirectBranchCommit_updates_file(self):
        # DirectBranchCommit can replace a file in the branch.
        self.committer.writeFile('file.txt', 'contents')
        self.committer.commit('')
        self._setUpCommitter()
        self.committer.writeFile('file.txt', 'changed')
        self.committer.commit('')
        self.assertEqual({'file.txt': 'changed'}, self._getContents())

    def test_DirectBranchCommit_creates_directories(self):
        # Files can be in subdirectories.
        self.committer.writeFile('a/b/c.txt', 'ctext')
        self.committer.commit('')
        self.assertEqual({'a/b/c.txt': 'ctext'}, self._getContents())

    def test_DirectBranchCommit_adds_directories(self):
        # Creating a subdirectory of an existing directory also works.
        self.committer.writeFile('a/n.txt', 'aa')
        self.committer.commit('')
        self._setUpCommitter()
        self.committer.writeFile('a/b/m.txt', 'aa/bb')
        self.committer.commit('')
        expected = {
            'a/n.txt': 'aa',
            'a/b/m.txt': 'aa/bb',
        }
        self.assertEqual(expected, self._getContents())

    def test_DirectBranchCommit_reuses_new_directories(self):
        # If a directory doesn't exist in the committed branch, creating
        # it twice would be an error.  DirectBranchCommit doesn't do
        # that.
        self.committer.writeFile('foo/x.txt', 'x')
        self.committer.writeFile('foo/y.txt', 'y')
        self.committer.commit('')
        expected = {
            'foo/x.txt': 'x',
            'foo/y.txt': 'y',
        }
        self.assertEqual(expected, self._getContents())

    def test_DirectBranchCommit_writes_new_file_twice(self):
        # If you write the same new file multiple times before
        # committing, the original wins.
        self.committer.writeFile('x.txt', 'aaa')
        self.committer.writeFile('x.txt', 'bbb')
        self.committer.commit('')
        self.assertEqual({'x.txt': 'aaa'}, self._getContents())

    def test_DirectBranchCommit_updates_file_twice(self):
        # If you update the same file multiple times before committing,
        # the original wins.
        self.committer.writeFile('y.txt', 'aaa')
        self.committer.commit('')
        self._setUpCommitter()
        self.committer.writeFile('y.txt', 'bbb')
        self.committer.writeFile('y.txt', 'ccc')
        self.committer.commit('')
        self.assertEqual({'y.txt': 'bbb'}, self._getContents())

    def test_DirectBranchCommit_detects_race_condition(self):
        # If the branch has been updated since it was last scanned,
        # attempting to commit to it will raise ConcurrentUpdateError.
        self.committer.writeFile('hi.c', 'main(){puts("hi world");}')
        self.committer.commit('')
        self._setUpCommitter(False)
        self.committer.writeFile('hi.py', 'print "hi world"')
        self.assertRaises(ConcurrentUpdateError, self.committer.commit, '')

    def test_DirectBranchCommit_records_committed_revision_id(self):
        # commit() records the committed revision in the database record for
        # the branch.
        self.committer.writeFile('hi.c', 'main(){puts("hi world");}')
        revid = self.committer.commit('')
        self.assertEqual(revid, self.db_branch.last_mirrored_id)

    def test_commit_uses_getBzrCommitterID(self):
        # commit() passes self.getBzrCommitterID() to bzr as the
        # committer.
        bzr_id = self.factory.getUniqueString()
        self.committer.getBzrCommitterID = FakeMethod(result=bzr_id)
        fake_commit = FakeMethod()
        self.committer.transform_preview.commit = fake_commit

        self.committer.writeFile('x', 'y')
        self.committer.commit('')

        commit_args, commit_kwargs = fake_commit.calls[-1]
        self.assertEqual(bzr_id, commit_kwargs['committer'])


class TestGetDir(DirectBranchCommitTestCase, TestCaseWithFactory):
    """Test `DirectBranchCommit._getDir`."""

    layer = ZopelessDatabaseLayer

    def test_getDir_creates_root(self):
        # An id is created even for the branch root directory.
        self.assertFalse('' in self.committer.path_ids)
        root_id = self.committer._getDir('')
        self.assertNotEqual(None, root_id)
        self.assertTrue('' in self.committer.path_ids)
        self.assertEqual(self.committer.path_ids[''], root_id)

    def test_getDir_creates_dir(self):
        # _getDir will create a new directory, under the root.
        self.assertFalse('dir' in self.committer.path_ids)
        dir_id = self.committer._getDir('dir')
        self.assertTrue('' in self.committer.path_ids)
        self.assertTrue('dir' in self.committer.path_ids)
        self.assertEqual(self.committer.path_ids['dir'], dir_id)
        self.assertNotEqual(self.committer.path_ids[''], dir_id)

    def test_getDir_creates_subdir(self):
        # _getDir will create nested directories.
        subdir_id = self.committer._getDir('dir/subdir')
        self.assertTrue('' in self.committer.path_ids)
        self.assertTrue('dir' in self.committer.path_ids)
        self.assertTrue('dir/subdir' in self.committer.path_ids)
        self.assertEqual(self.committer.path_ids['dir/subdir'], subdir_id)

    def test_getDir_finds_existing_dir(self):
        # _getDir finds directories that already existed in a previously
        # committed version of the branch.
        existing_id = self.committer._getDir('po')
        self._setUpCommitter()
        dir_id = self.committer._getDir('po')
        self.assertEqual(existing_id, dir_id)

    def test_getDir_creates_dir_in_existing_dir(self):
        # _getDir creates directories inside ones that already existed
        # in a previously committed version of the branch.
        self.committer._getDir('po')
        self._setUpCommitter()
        new_dir_id = self.committer._getDir('po/main/files')
        self.assertTrue('po/main' in self.committer.path_ids)
        self.assertTrue('po/main/files' in self.committer.path_ids)
        self.assertEqual(self.committer.path_ids['po/main/files'], new_dir_id)

    def test_getDir_reuses_new_id(self):
        # If a directory was newly created, _getDir will reuse its id.
        dir_id = self.committer._getDir('foo/bar')
        self.assertEqual(dir_id, self.committer._getDir('foo/bar'))


class TestGetBzrCommitterID(TestCaseWithFactory):
    """Test `DirectBranchCommitter.getBzrCommitterID`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGetBzrCommitterID, self).setUp()
        self.useBzrBranches(direct_database=True)

    def _makeBranch(self, **kwargs):
        """Create a branch in the database and in bzr."""
        db_branch, tree = self.create_branch_and_tree(**kwargs)
        return db_branch

    def test_uses_committer_id(self):
        # getBzrCommitterID uses the committer string if provided.
        bzr_id = self.factory.getUniqueString()
        committer = DirectBranchCommit(
            self._makeBranch(), committer_id=bzr_id)
        self.addCleanup(committer.unlock)
        self.assertEqual(bzr_id, committer.getBzrCommitterID())

    def test_uses_committer_email(self):
        # getBzrCommitterID returns the committing person's email address
        # if available (and if no committer string is given).
        branch = self._makeBranch()
        committer = DirectBranchCommit(branch)
        self.addCleanup(committer.unlock)
        self.assertIn(
            removeSecurityProxy(branch.owner).preferredemail.email,
            committer.getBzrCommitterID())

    def test_falls_back_to_noreply(self):
        # If all else fails, getBzrCommitterID uses the noreply
        # address.
        team = self.factory.makeTeam()
        self.assertIs(None, team.preferredemail)
        branch = self._makeBranch(owner=team)
        committer = DirectBranchCommit(branch)
        self.addCleanup(committer.unlock)
        self.assertIn('noreply', committer.getBzrCommitterID())


class TestStaleLastMirroredID(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_raises_StaleLastMirrored(self):
        """Raise if the on-disk revision doesn't match last-mirrored."""
        self.useBzrBranches(direct_database=True)
        bzr_id = self.factory.getUniqueString()
        db_branch, tree = self.create_branch_and_tree()
        tree.commit('unchanged', committer='jrandom@example.com')
        with ExpectedException(StaleLastMirrored, '.*'):
            committer = DirectBranchCommit(
                db_branch, committer_id=bzr_id)
            self.addCleanup(committer.unlock)
            committer.commit('')
