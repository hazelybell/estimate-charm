# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Diff, etc."""

__metaclass__ = type

from cStringIO import StringIO
from difflib import unified_diff
import logging

from bzrlib import trace
from bzrlib.patches import (
    InsertLine,
    parse_patches,
    RemoveLine,
    )
import transaction
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.code.interfaces.diff import (
    IDiff,
    IIncrementalDiff,
    IPreviewDiff,
    )
from lp.code.model.diff import (
    Diff,
    PreviewDiff,
    )
from lp.code.model.directbranchcommit import DirectBranchCommit
from lp.services.librarian.interfaces.client import (
    LIBRARIAN_SERVER_DEFAULT_TIMEOUT,
    )
from lp.services.webapp import canonical_url
from lp.testing import (
    login,
    login_person,
    monkey_patch,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class RecordLister(logging.Handler):

    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def commit_file(branch, path, contents, merge_parents=None):
    """Create a commit that updates a file to specified contents.

    This will create or modify the file, as needed.
    """
    committer = DirectBranchCommit(
        removeSecurityProxy(branch), no_race_check=True,
        merge_parents=merge_parents)
    committer.writeFile(path, contents)
    try:
        return committer.commit('committing')
    finally:
        committer.unlock()


def create_example_merge(test_case):
    """Create a merge proposal with conflicts and updates."""
    bmp = test_case.factory.makeBranchMergeProposal()
    # Make the branches of the merge proposal look good as far as the
    # model is concerned.
    test_case.factory.makeRevisionsForBranch(bmp.source_branch)
    test_case.factory.makeRevisionsForBranch(bmp.target_branch)
    bzr_target = test_case.createBzrBranch(bmp.target_branch)
    commit_file(bmp.target_branch, 'foo', 'a\n')
    test_case.createBzrBranch(bmp.source_branch, bzr_target)
    source_rev_id = commit_file(bmp.source_branch, 'foo', 'd\na\nb\n')
    target_rev_id = commit_file(bmp.target_branch, 'foo', 'c\na\n')
    return bmp, source_rev_id, target_rev_id


class DiffTestCase(TestCaseWithFactory):

    def createExampleMerge(self):
        self.useBzrBranches(direct_database=True)
        return create_example_merge(self)

    def checkExampleMerge(self, diff_text):
        """Ensure the diff text matches the values for ExampleMerge."""
        # The source branch added a line "b".
        self.assertIn('+b\n', diff_text)
        # The line "a" was present before any changes were made, so it's not
        # considered added.
        self.assertNotIn('+a\n', diff_text)
        # There's a conflict because the source branch added a line "d", but
        # the target branch added the line "c" in the same place.
        self.assertIn(
            '+<<<''<<<< TREE\n c\n+=======\n+d\n+>>>>>''>> MERGE-SOURCE\n',
            diff_text)

    def preparePrerequisiteMerge(self, bmp=None):
        """Prepare a merge scenario with a prerequisite branch."""
        self.useBzrBranches(direct_database=True)
        if bmp is None:
            target = self.factory.makeBranch()
            prerequisite = self.factory.makeBranch()
            source = self.factory.makeBranch()
        else:
            target = bmp.target_branch
            source = bmp.source_branch
            prerequisite = bmp.prerequisite_branch
        target_bzr = self.createBzrBranch(target)
        commit_file(target, 'file', 'target text\n')
        prerequisite_bzr = self.createBzrBranch(prerequisite, target_bzr)
        commit_file(
            prerequisite, 'file', 'target text\nprerequisite text\n')
        source_bzr = self.createBzrBranch(source, prerequisite_bzr)
        source_rev_id = commit_file(
            source, 'file',
            'target text\nprerequisite text\nsource text\n')
        return (source_bzr, source_rev_id, target_bzr, prerequisite_bzr,
                prerequisite)


class TestDiff(DiffTestCase):

    layer = LaunchpadFunctionalLayer

    def test_providesInterface(self):
        verifyObject(IDiff, Diff())

    def _create_diff(self, content):
        # Create a Diff object with the content specified.
        sio = StringIO()
        sio.write(content)
        size = sio.tell()
        sio.seek(0)
        diff = Diff.fromFile(sio, size)
        # Commit to make the alias available for reading.
        transaction.commit()
        return diff

    def test_text_reads_librarian_content(self):
        # IDiff.text will read at most config.diff.max_read_size bytes from
        # the librarian.
        content = ''.join(unified_diff('', "1234567890" * 10))
        diff = self._create_diff(content)
        self.assertEqual(content, diff.text)
        self.assertTrue(diff.diff_text.restricted)

    def test_oversized_normal(self):
        # A diff smaller than config.diff.max_read_size is not oversized.
        content = ''.join(unified_diff('', "1234567890" * 10))
        diff = self._create_diff(content)
        self.assertFalse(diff.oversized)

    def test_text_read_limited_by_config(self):
        # IDiff.text will read at most config.diff.max_read_size bytes from
        # the librarian.
        self.pushConfig("diff", max_read_size=25)
        content = ''.join(unified_diff('', "1234567890" * 10))
        diff = self._create_diff(content)
        self.assertEqual(content[:25], diff.text)

    def test_oversized_for_big_diff(self):
        # A diff larger than config.diff.max_read_size is oversized.
        self.pushConfig("diff", max_read_size=25)
        content = ''.join(unified_diff('', "1234567890" * 10))
        diff = self._create_diff(content)
        self.assertTrue(diff.oversized)

    def test_getDiffTimeout(self):
        # The time permitted to get the diff from the librarian may be None,
        # or 2. If there is not 2 seconds left in the request, the number will
        # will 0.01 smaller or the actual remaining time.
        content = ''.join(unified_diff('', "1234567890" * 10))
        diff = self._create_diff(content)
        value = None

        def fake():
            return value

        from lp.code.model import diff as diff_module
        with monkey_patch(diff_module, get_request_remaining_seconds=fake):
            self.assertIs(
                LIBRARIAN_SERVER_DEFAULT_TIMEOUT, diff._getDiffTimeout())
            value = 3.1
            self.assertEqual(2.0, diff._getDiffTimeout())
            value = 1.11
            self.assertEqual(1.1, diff._getDiffTimeout())
            value = 0.11
            self.assertEqual(0.1, diff._getDiffTimeout())
            value = 0.01
            self.assertEqual(0.01, diff._getDiffTimeout())


class TestDiffInScripts(DiffTestCase):

    layer = LaunchpadZopelessLayer

    def test_mergePreviewFromBranches(self):
        # mergePreviewFromBranches generates the correct diff.
        bmp, source_rev_id, target_rev_id = self.createExampleMerge()
        source_branch = bmp.source_branch.getBzrBranch()
        target_branch = bmp.target_branch.getBzrBranch()
        diff, conflicts = Diff.mergePreviewFromBranches(
            source_branch, source_rev_id, target_branch)
        transaction.commit()
        self.checkExampleMerge(diff.text)

    diff_bytes = (
        "--- bar\t2009-08-26 15:53:34.000000000 -0400\n"
        "+++ bar\t1969-12-31 19:00:00.000000000 -0500\n"
        "@@ -1,3 +0,0 @@\n"
        "-a\n"
        "-b\n"
        "-c\n"
        "--- baz\t1969-12-31 19:00:00.000000000 -0500\n"
        "+++ baz\t2009-08-26 15:53:57.000000000 -0400\n"
        "@@ -0,0 +1,2 @@\n"
        "+a\n"
        "+b\n"
        "--- foo\t2009-08-26 15:53:23.000000000 -0400\n"
        "+++ foo\t2009-08-26 15:56:43.000000000 -0400\n"
        "@@ -1,3 +1,4 @@\n"
        " a\n"
        "-b\n"
        " c\n"
        "+d\n"
        "+e\n")

    diff_bytes_2 = (
        "--- bar\t2009-08-26 15:53:34.000000000 -0400\n"
        "+++ bar\t1969-12-31 19:00:00.000000000 -0500\n"
        "@@ -1,3 +0,0 @@\n"
        "-a\n"
        "-b\n"
        "-c\n"
        "--- baz\t1969-12-31 19:00:00.000000000 -0500\n"
        "+++ baz\t2009-08-26 15:53:57.000000000 -0400\n"
        "@@ -0,0 +1,2 @@\n"
        "+a\n"
        "+b\n"
        "--- foo\t2009-08-26 15:53:23.000000000 -0400\n"
        "+++ foo\t2009-08-26 15:56:43.000000000 -0400\n"
        "@@ -1,3 +1,5 @@\n"
        " a\n"
        "-b\n"
        " c\n"
        "+d\n"
        "+e\n"
        "+f\n")

    def test_mergePreviewWithPrerequisite(self):
        # Changes introduced in the prerequisite branch are ignored.
        (source_bzr, source_rev_id, target_bzr, prerequisite_bzr,
         prerequisite) = self.preparePrerequisiteMerge()
        diff, conflicts = Diff.mergePreviewFromBranches(
            source_bzr, source_rev_id, target_bzr, prerequisite_bzr)
        transaction.commit()
        self.assertIn('+source text\n', diff.text)
        self.assertNotIn('+prerequisite text\n', diff.text)

    def test_mergePreviewWithNewerPrerequisite(self):
        # If the prerequisite branch has unmerged revisions, they do not
        # affect the diff.
        (source_bzr, source_rev_id, target_bzr, prerequisite_bzr,
         prerequisite) = self.preparePrerequisiteMerge()
        commit_file(
            prerequisite, 'file', 'prerequisite text2\n')
        diff, conflicts = Diff.mergePreviewFromBranches(
            source_bzr, source_rev_id, target_bzr, prerequisite_bzr)
        transaction.commit()
        self.assertNotIn('-prerequisite text2\n', diff.text)
        self.assertIn('+source text\n', diff.text)
        self.assertNotIn('+prerequisite text\n', diff.text)

    def test_generateDiffstat(self):
        self.assertEqual(
            {'foo': (2, 1), 'bar': (0, 3), 'baz': (2, 0)},
            Diff.generateDiffstat(self.diff_bytes))

    def test_generateDiffstat_with_CR(self):
        diff_bytes = (
            "--- foo\t2009-08-26 15:53:23.000000000 -0400\n"
            "+++ foo\t2009-08-26 15:56:43.000000000 -0400\n"
            "@@ -1,1 +1,1 @@\n"
            " a\r-b\r c\r+d\r+e\r+f\r")
        self.assertEqual({'foo': (0, 0)}, Diff.generateDiffstat(diff_bytes))

    def test_fromFileSetsDiffstat(self):
        diff = Diff.fromFile(StringIO(self.diff_bytes), len(self.diff_bytes))
        self.assertEqual(
            {'bar': (0, 3), 'baz': (2, 0), 'foo': (2, 1)}, diff.diffstat)

    def test_fromFileAcceptsBinary(self):
        diff_bytes = "Binary files a\t and b\t differ\n"
        diff = Diff.fromFile(StringIO(diff_bytes), len(diff_bytes))
        self.assertEqual({}, diff.diffstat)

    def test_fromFileSets_added_removed(self):
        """fromFile sets added_lines_count, removed_lines_count."""
        diff = Diff.fromFile(
            StringIO(self.diff_bytes_2), len(self.diff_bytes_2))
        self.assertEqual(5, diff.added_lines_count)
        self.assertEqual(4, diff.removed_lines_count)

    def test_fromFile_withError(self):
        # If the diff is formatted such that generating the diffstat fails, we
        # want to record an oops but continue.
        diff_bytes = "not a real diff"
        diff = Diff.fromFile(StringIO(diff_bytes), len(diff_bytes))
        oops = self.oopses[0]
        self.assertEqual('MalformedPatchHeader', oops['type'])
        self.assertIs(None, diff.diffstat)
        self.assertIs(None, diff.added_lines_count)
        self.assertIs(None, diff.removed_lines_count)


class TestPreviewDiff(DiffTestCase):
    """Test that PreviewDiff objects work."""

    layer = LaunchpadFunctionalLayer

    def _createProposalWithPreviewDiff(self, prerequisite_branch=None,
                                       content=None):
        # Create and return a preview diff.
        mp = self.factory.makeBranchMergeProposal(
            prerequisite_branch=prerequisite_branch)
        login_person(mp.registrant)
        if prerequisite_branch is None:
            prerequisite_revision_id = None
        else:
            prerequisite_revision_id = u'rev-c'
        if content is None:
            content = ''.join(unified_diff('', 'content'))
        mp.updatePreviewDiff(
            content, u'rev-a', u'rev-b',
            prerequisite_revision_id=prerequisite_revision_id)
        # Make sure the librarian file is written.
        transaction.commit()
        return mp

    def test_providesInterface(self):
        # In order to test the interface provision, we need to make sure that
        # the associated diff object that is delegated to is also created.
        mp = self._createProposalWithPreviewDiff()
        verifyObject(IPreviewDiff, mp.preview_diff)

    def test_canonicalUrl(self):
        # The canonical_url of the merge diff is '+preview' after the
        # canonical_url of the merge proposal itself.
        mp = self._createProposalWithPreviewDiff()
        self.assertEqual(
            canonical_url(mp) + '/+preview-diff',
            canonical_url(mp.preview_diff))

    def test_empty_diff(self):
        # Once the source is merged into the target, the diff between the
        # branches will be empty.
        mp = self._createProposalWithPreviewDiff(content='')
        preview = mp.preview_diff
        self.assertIs(None, preview.diff_text)
        self.assertEqual(0, preview.diff_lines_count)
        self.assertEqual(mp, preview.branch_merge_proposal)
        self.assertFalse(preview.has_conflicts)

    def test_stale_allInSync(self):
        # If the revision ids of the preview diff match the source and target
        # branches, then not stale.
        mp = self._createProposalWithPreviewDiff()
        # Log in an admin to avoid the launchpad.Edit needs for last_scanned.
        login('admin@canonical.com')
        mp.source_branch.last_scanned_id = 'rev-a'
        mp.target_branch.last_scanned_id = 'rev-b'
        self.assertEqual(False, mp.preview_diff.stale)

    def test_stale_sourceNewer(self):
        # If the source branch has a different rev id, the diff is stale.
        mp = self._createProposalWithPreviewDiff()
        # Log in an admin to avoid the launchpad.Edit needs for last_scanned.
        login('admin@canonical.com')
        mp.source_branch.last_scanned_id = 'rev-c'
        mp.target_branch.last_scanned_id = 'rev-b'
        self.assertEqual(True, mp.preview_diff.stale)

    def test_stale_targetNewer(self):
        # If the source branch has a different rev id, the diff is stale.
        mp = self._createProposalWithPreviewDiff()
        # Log in an admin to avoid the launchpad.Edit needs for last_scanned.
        login('admin@canonical.com')
        mp.source_branch.last_scanned_id = 'rev-a'
        mp.target_branch.last_scanned_id = 'rev-d'
        self.assertEqual(True, mp.preview_diff.stale)

    def test_stale_prerequisiteBranch(self):
        # If the merge proposal has a prerequisite branch, then the tip
        # revision id of the prerequisite branch is also checked.
        dep_branch = self.factory.makeProductBranch()
        mp = self._createProposalWithPreviewDiff(dep_branch)
        # Log in an admin to avoid the launchpad.Edit needs for last_scanned.
        login('admin@canonical.com')
        mp.source_branch.last_scanned_id = 'rev-a'
        mp.target_branch.last_scanned_id = 'rev-b'
        dep_branch.last_scanned_id = 'rev-c'
        self.assertEqual(False, mp.preview_diff.stale)
        dep_branch.last_scanned_id = 'rev-d'
        self.assertEqual(True, mp.preview_diff.stale)

    def test_fromPreviewDiff_with_no_conflicts(self):
        """Test fromPreviewDiff when no conflicts are present."""
        self.useBzrBranches(direct_database=True)
        bmp = self.factory.makeBranchMergeProposal()
        bzr_target = self.createBzrBranch(bmp.target_branch)
        commit_file(bmp.target_branch, 'foo', 'a\n')
        self.createBzrBranch(bmp.source_branch, bzr_target)
        commit_file(bmp.source_branch, 'foo', 'a\nb\n')
        commit_file(bmp.target_branch, 'foo', 'c\na\n')
        diff = PreviewDiff.fromBranchMergeProposal(bmp)
        self.assertEqual('', diff.conflicts)
        self.assertFalse(diff.has_conflicts)

    def test_fromBranchMergeProposal(self):
        # Correctly generates a PreviewDiff from a BranchMergeProposal.
        bmp, source_rev_id, target_rev_id = self.createExampleMerge()
        preview = PreviewDiff.fromBranchMergeProposal(bmp)
        self.assertEqual(source_rev_id, preview.source_revision_id)
        self.assertEqual(target_rev_id, preview.target_revision_id)
        transaction.commit()
        self.checkExampleMerge(preview.text)
        self.assertEqual({'foo': (5, 0)}, preview.diffstat)

    def test_fromBranchMergeProposal_with_prerequisite(self):
        # Correctly generates a PreviewDiff from a BranchMergeProposal.
        prerequisite_branch = self.factory.makeProductBranch()
        bmp = self.factory.makeBranchMergeProposal(
            prerequisite_branch=prerequisite_branch)
        self.preparePrerequisiteMerge(bmp)
        preview = PreviewDiff.fromBranchMergeProposal(bmp)
        transaction.commit()
        self.assertIn('+source text\n', preview.text)
        self.assertNotIn('+prerequisite text\n', preview.text)

    def test_fromBranchMergeProposal_sets_conflicts(self):
        """Conflicts are set on the PreviewDiff."""
        bmp, source_rev_id, target_rev_id = self.createExampleMerge()
        preview = PreviewDiff.fromBranchMergeProposal(bmp)
        self.assertEqual('Text conflict in foo\n', preview.conflicts)
        self.assertTrue(preview.has_conflicts)

    def test_fromBranchMergeProposal_does_not_warn_on_conflicts(self):
        """PreviewDiff generation emits no conflict warnings."""
        reload(trace)
        bmp, source_rev_id, target_rev_id = self.createExampleMerge()
        handler = RecordLister()
        logger = logging.getLogger('bzr')
        logger.addHandler(handler)
        try:
            PreviewDiff.fromBranchMergeProposal(bmp)
            self.assertEqual(handler.records, [])
            # check that our handler would normally intercept warnings.
            trace.warning('foo!')
            self.assertNotEqual(handler.records, [])
        finally:
            logger.removeHandler(handler)

    def test_getFileByName(self):
        diff = self._createProposalWithPreviewDiff().preview_diff
        self.assertEqual(diff.diff_text, diff.getFileByName('preview.diff'))
        self.assertRaises(
            NotFoundError, diff.getFileByName, 'different.name')

    def test_getFileByName_with_no_diff(self):
        diff = self._createProposalWithPreviewDiff(content='').preview_diff
        self.assertRaises(
            NotFoundError, diff.getFileByName, 'preview.diff')


class TestIncrementalDiff(DiffTestCase):
    """Test that IncrementalDiff objects work."""

    layer = LaunchpadFunctionalLayer

    def test_providesInterface(self):
        incremental_diff = self.factory.makeIncrementalDiff()
        verifyObject(IIncrementalDiff, incremental_diff)

    @staticmethod
    def diff_changes(diff_bytes):
        inserted = []
        removed = []
        for patch in parse_patches(diff_bytes.splitlines(True)):
            for hunk in patch.hunks:
                for line in hunk.lines:
                    if isinstance(line, InsertLine):
                        inserted.append(line.contents)
                    if isinstance(line, RemoveLine):
                        removed.append(line.contents)
        return inserted, removed

    def test_generateIncrementalDiff(self):
        """generateIncrementalDiff works.

        Changes merged from the prerequisite and target are ignored in the
        diff.

        We generate an incremental diff from old_revision_id to
        new_revision_id.

        old_revision_id has:
        a
        b
        e

        new_revision_id has:
        d
        a
        c
        e
        f

        Because the prerequisite branch adds "d", this change is ignored.
        Because the target branch adds "f", this change is ignored.
        So the incremental diff shows that "c" was added and "b" was removed.
        """
        self.useBzrBranches(direct_database=True)
        prerequisite_branch = self.factory.makeAnyBranch()
        bmp = self.factory.makeBranchMergeProposal(
            prerequisite_branch=prerequisite_branch)
        target_branch = self.createBzrBranch(bmp.target_branch)
        old_revision_id = commit_file(bmp.target_branch, 'foo', 'a\nb\ne\n')
        old_revision = self.factory.makeRevision(rev_id=old_revision_id)
        source_branch = self.createBzrBranch(
            bmp.source_branch, target_branch)
        commit_file(bmp.source_branch, 'foo', 'a\nc\ne\n')
        prerequisite = self.createBzrBranch(
            bmp.prerequisite_branch, target_branch)
        prerequisite_revision = commit_file(
            bmp.prerequisite_branch, 'foo', 'd\na\nb\ne\n')
        merge_parent = commit_file(bmp.target_branch, 'foo', 'a\nb\ne\nf\n')
        source_branch.repository.fetch(target_branch.repository,
            revision_id=merge_parent)
        commit_file(bmp.source_branch, 'foo', 'a\nc\ne\nf\n', [merge_parent])
        source_branch.repository.fetch(prerequisite.repository,
            revision_id=prerequisite_revision)
        new_revision_id = commit_file(
            bmp.source_branch, 'foo', 'd\na\nc\ne\nf\n',
            [prerequisite_revision])
        new_revision = self.factory.makeRevision(rev_id=new_revision_id)
        incremental_diff = bmp.generateIncrementalDiff(
            old_revision, new_revision)
        transaction.commit()
        inserted, removed = self.diff_changes(incremental_diff.text)
        self.assertEqual(['c\n'], inserted)
        self.assertEqual(['b\n'], removed)
