# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation classes for IDiff, etc."""

__metaclass__ = type
__all__ = [
    'Diff',
    'IncrementalDiff',
    'PreviewDiff',
    ]

from contextlib import nested
from cStringIO import StringIO
import sys
from uuid import uuid1

from bzrlib import trace
from bzrlib.diff import show_diff_trees
from bzrlib.merge import Merge3Merger
from bzrlib.patches import (
    parse_patches,
    Patch,
    )
from bzrlib.plugins.difftacular.generate_diff import diff_ignore_branches
from lazr.delegates import delegates
import simplejson
from sqlobject import (
    ForeignKey,
    IntCol,
    StringCol,
    )
from storm.locals import (
    Int,
    Reference,
    Storm,
    Unicode,
    )
from zope.component import getUtility
from zope.error.interfaces import IErrorReportingUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.code.interfaces.diff import (
    IDiff,
    IIncrementalDiff,
    IPreviewDiff,
    )
from lp.codehosting.bzrutils import read_locked
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.interfaces.client import (
    LIBRARIAN_SERVER_DEFAULT_TIMEOUT,
    )
from lp.services.propertycache import get_property_cache
from lp.services.webapp.adapter import get_request_remaining_seconds


class Diff(SQLBase):
    """See `IDiff`."""

    implements(IDiff)

    diff_text = ForeignKey(foreignKey='LibraryFileAlias')

    diff_lines_count = IntCol()

    _diffstat = StringCol(dbName='diffstat')

    def _get_diffstat(self):
        if self._diffstat is None:
            return None
        return dict((key, tuple(value))
                    for key, value
                    in simplejson.loads(self._diffstat).items())

    def _set_diffstat(self, diffstat):
        if diffstat is None:
            self._diffstat = None
            return
        # diffstats should be mappings of path to line counts.
        assert isinstance(diffstat, dict)
        self._diffstat = simplejson.dumps(diffstat)

    diffstat = property(_get_diffstat, _set_diffstat)

    added_lines_count = IntCol()

    removed_lines_count = IntCol()

    @property
    def text(self):
        if self.diff_text is None:
            return ''
        else:
            self.diff_text.open(self._getDiffTimeout())
            try:
                return self.diff_text.read(config.diff.max_read_size)
            finally:
                self.diff_text.close()

    def _getDiffTimeout(self):
        """Return the seconds allocated to get the diff from the librarian.

         the value will be Non for scripts, 2 for the webapp, or if thre is
         little request time left, the number will be smaller or equal to
         the remaining request time.
        """
        remaining = get_request_remaining_seconds()
        if remaining is None:
            return LIBRARIAN_SERVER_DEFAULT_TIMEOUT
        elif remaining > 2.0:
            # The maximum permitted time for webapp requests.
            return 2.0
        elif remaining > 0.01:
            # Shave off 1 hundreth of a second off so that the call site
            # has a chance to recover.
            return remaining - 0.01
        else:
            return remaining

    @property
    def oversized(self):
        # If the size of the content of the librarian file is over the
        # config.diff.max_read_size, then we have an oversized diff.
        if self.diff_text is None:
            return False
        diff_size = self.diff_text.content.filesize
        return diff_size > config.diff.max_read_size

    @classmethod
    def mergePreviewFromBranches(cls, source_branch, source_revision,
                                 target_branch, prerequisite_branch=None):
        """Generate a merge preview diff from the supplied branches.

        :param source_branch: The branch that will be merged.
        :param source_revision: The revision_id of the revision that will be
            merged.
        :param target_branch: The branch that the source will merge into.
        :param prerequisite_branch: The branch that should be merged before
            merging the source.
        :return: A tuple of (`Diff`, `ConflictList`) for a merge preview.
        """
        cleanups = []
        try:
            for branch in [source_branch, target_branch, prerequisite_branch]:
                if branch is not None:
                    branch.lock_read()
                    cleanups.append(branch.unlock)
            merge_target = target_branch.basis_tree()
            if prerequisite_branch is not None:
                prereq_revision = cls._getLCA(
                    source_branch, source_revision, prerequisite_branch)
                from_tree, _ignored_conflicts = cls._getMergedTree(
                    prerequisite_branch, prereq_revision, target_branch,
                    merge_target, cleanups)
            else:
                from_tree = merge_target
            to_tree, conflicts = cls._getMergedTree(
                source_branch, source_revision, target_branch,
                merge_target, cleanups)
            return cls.fromTrees(from_tree, to_tree), conflicts
        finally:
            for cleanup in reversed(cleanups):
                cleanup()

    @classmethod
    def _getMergedTree(cls, source_branch, source_revision, target_branch,
                  merge_target, cleanups):
        """Return a tree that is the result of a merge.

        :param source_branch: The branch to merge.
        :param source_revision: The revision_id of the revision to merge.
        :param target_branch: The branch to merge into.
        :param merge_target: The tree to merge into.
        :param cleanups: A list of cleanup operations to run when all
            operations are complete.  This will be appended to.
        :return: a tuple of a tree and the resulting conflicts.
        """
        lca = cls._getLCA(source_branch, source_revision, target_branch)
        merge_base = source_branch.repository.revision_tree(lca)
        merge_source = source_branch.repository.revision_tree(
            source_revision)
        merger = Merge3Merger(
            merge_target, merge_target, merge_base, merge_source,
            this_branch=target_branch, do_merge=False)

        def dummy_warning(self, *args, **kwargs):
            pass

        real_warning = trace.warning
        trace.warning = dummy_warning
        try:
            transform = merger.make_preview_transform()
        finally:
            trace.warning = real_warning
        cleanups.append(transform.finalize)
        return transform.get_preview_tree(), merger.cooked_conflicts

    @staticmethod
    def _getLCA(source_branch, source_revision, target_branch):
        """Return the unique LCA of two branches.

        :param source_branch: The branch to merge.
        :param source_revision: The revision of the source branch.
        :param target_branch: The branch to merge into.
        """
        graph = target_branch.repository.get_graph(
            source_branch.repository)
        return graph.find_unique_lca(
            source_revision, target_branch.last_revision())

    @classmethod
    def fromTrees(klass, from_tree, to_tree, filename=None):
        """Create a Diff from two Bazaar trees.

        :from_tree: The old tree in the diff.
        :to_tree: The new tree in the diff.
        """
        diff_content = StringIO()
        show_diff_trees(from_tree, to_tree, diff_content, old_label='',
                        new_label='')
        return klass.fromFileAtEnd(diff_content, filename)

    @classmethod
    def fromFileAtEnd(cls, diff_content, filename=None):
        """Make a Diff from a file object that is currently at its end."""
        size = diff_content.tell()
        diff_content.seek(0)
        return cls.fromFile(diff_content, size, filename)

    @classmethod
    def fromFile(cls, diff_content, size, filename=None):
        """Create a Diff from a textual diff.

        :diff_content: The diff text
        :size: The number of bytes in the diff text.
        :filename: The filename to store the content with.  Randomly generated
            if not supplied.
        """
        if size == 0:
            diff_text = None
            diff_lines_count = 0
            diff_content_bytes = ''
        else:
            if filename is None:
                filename = str(uuid1()) + '.txt'
            diff_text = getUtility(ILibraryFileAliasSet).create(
                filename, size, diff_content, 'text/x-diff', restricted=True)
            diff_content.seek(0)
            diff_content_bytes = diff_content.read(size)
            diff_lines_count = len(diff_content_bytes.strip().split('\n'))
        try:
            diffstat = cls.generateDiffstat(diff_content_bytes)
        except Exception:
            getUtility(IErrorReportingUtility).raising(sys.exc_info())
            # Set the diffstat to be empty.
            diffstat = None
            added_lines_count = None
            removed_lines_count = None
        else:
            added_lines_count = 0
            removed_lines_count = 0
            for path, (added, removed) in diffstat.items():
                added_lines_count += added
                removed_lines_count += removed
        return cls(diff_text=diff_text, diff_lines_count=diff_lines_count,
                   diffstat=diffstat, added_lines_count=added_lines_count,
                   removed_lines_count=removed_lines_count)

    @staticmethod
    def generateDiffstat(diff_bytes):
        """Generate statistics about the provided diff.

        :param diff_bytes: A unified diff, as bytes.
        :return: A map of {filename: (added_line_count, removed_line_count)}
        """
        file_stats = {}
        # Set allow_dirty, so we don't raise exceptions for dirty patches.
        patches = parse_patches(diff_bytes.splitlines(True), allow_dirty=True)
        for patch in patches:
            if not isinstance(patch, Patch):
                continue
            path = patch.newname.split('\t')[0]
            file_stats[path] = tuple(patch.stats_values()[:2])
        return file_stats

    @classmethod
    def generateIncrementalDiff(cls, old_revision, new_revision,
            source_branch, ignore_branches):
        """Return a Diff whose contents are an incremental diff.

        The Diff's contents will show the changes made between old_revision
        and new_revision, except those changes introduced by the
        ignore_branches.

        :param old_revision: The `Revision` to show changes from.
        :param new_revision: The `Revision` to show changes to.
        :param source_branch: The bzr branch containing these revisions.
        :param ignore_brances: A collection of branches to ignore merges from.
        :return: a `Diff`.
        """
        diff_content = StringIO()
        read_locks = [read_locked(branch) for branch in [source_branch] +
                ignore_branches]
        with nested(*read_locks):
            diff_ignore_branches(
                source_branch, ignore_branches, old_revision.revision_id,
                new_revision.revision_id, diff_content)
        return cls.fromFileAtEnd(diff_content)


class IncrementalDiff(Storm):
    """See `IIncrementalDiff."""

    implements(IIncrementalDiff)

    delegates(IDiff, context='diff')

    __storm_table__ = 'IncrementalDiff'

    id = Int(primary=True, allow_none=False)

    diff_id = Int(name='diff', allow_none=False)

    diff = Reference(diff_id, 'Diff.id')

    branch_merge_proposal_id = Int(
        name='branch_merge_proposal', allow_none=False)

    branch_merge_proposal = Reference(
        branch_merge_proposal_id, "BranchMergeProposal.id")

    old_revision_id = Int(name='old_revision', allow_none=False)

    old_revision = Reference(old_revision_id, 'Revision.id')

    new_revision_id = Int(name='new_revision', allow_none=False)

    new_revision = Reference(new_revision_id, 'Revision.id')


class PreviewDiff(Storm):
    """See `IPreviewDiff`."""
    implements(IPreviewDiff)
    delegates(IDiff, context='diff')
    __storm_table__ = 'PreviewDiff'

    id = Int(primary=True)

    diff_id = Int(name='diff')
    diff = Reference(diff_id, 'Diff.id')

    source_revision_id = Unicode(allow_none=False)

    target_revision_id = Unicode(allow_none=False)

    prerequisite_revision_id = Unicode(name='dependent_revision_id')

    branch_merge_proposal_id = Int(
        name='branch_merge_proposal', allow_none=False)
    branch_merge_proposal = Reference(
        branch_merge_proposal_id, 'BranchMergeProposal.id')

    date_created = UtcDateTimeCol(
        dbName='date_created', default=UTC_NOW, notNull=True)

    conflicts = Unicode()

    @property
    def has_conflicts(self):
        return self.conflicts is not None and self.conflicts != ''

    @classmethod
    def fromBranchMergeProposal(cls, bmp):
        """Create a `PreviewDiff` from a `BranchMergeProposal`.

        Includes a diff from the source to the target.
        :param bmp: The `BranchMergeProposal` to generate a `PreviewDiff` for.
        :return: A `PreviewDiff`.
        """
        source_branch = bmp.source_branch.getBzrBranch()
        source_revision = source_branch.last_revision()
        target_branch = bmp.target_branch.getBzrBranch()
        target_revision = target_branch.last_revision()
        if bmp.prerequisite_branch is not None:
            prerequisite_branch = bmp.prerequisite_branch.getBzrBranch()
        else:
            prerequisite_branch = None
        diff, conflicts = Diff.mergePreviewFromBranches(
            source_branch, source_revision, target_branch, prerequisite_branch)
        preview = cls()
        preview.source_revision_id = source_revision.decode('utf-8')
        preview.target_revision_id = target_revision.decode('utf-8')
        preview.branch_merge_proposal = bmp
        preview.diff = diff
        preview.conflicts = u''.join(
            unicode(conflict) + '\n' for conflict in conflicts)
        del get_property_cache(bmp).preview_diffs
        del get_property_cache(bmp).preview_diff
        return preview

    @classmethod
    def create(cls, bmp, diff_content, source_revision_id, target_revision_id,
               prerequisite_revision_id, conflicts):
        """Create a PreviewDiff with specified values.

        :param bmp: The `BranchMergeProposal` this diff references.
        :param diff_content: The text of the dift, as bytes.
        :param source_revision_id: The revision_id of the source branch.
        :param target_revision_id: The revision_id of the target branch.
        :param prerequisite_revision_id: The revision_id of the prerequisite
            branch.
        :param conflicts: The conflicts, as text.
        :return: A `PreviewDiff` with specified values.
        """
        filename = str(uuid1()) + '.txt'
        size = len(diff_content)
        diff = Diff.fromFile(StringIO(diff_content), size, filename)

        preview = cls()
        preview.branch_merge_proposal = bmp
        preview.source_revision_id = source_revision_id
        preview.target_revision_id = target_revision_id
        preview.prerequisite_revision_id = prerequisite_revision_id
        preview.conflicts = conflicts
        preview.diff = diff

        return preview

    @property
    def stale(self):
        """See `IPreviewDiff`."""
        # A preview diff is stale if the revision ids used to make the diff
        # are different from the tips of the source or target branches.
        bmp = self.branch_merge_proposal
        if (self.source_revision_id != bmp.source_branch.last_scanned_id or
            self.target_revision_id != bmp.target_branch.last_scanned_id):
            # This is the simple frequent case.
            return True

        # More complex involves the prerequisite branch too.
        if (bmp.prerequisite_branch is not None and
            (self.prerequisite_revision_id !=
             bmp.prerequisite_branch.last_scanned_id)):
            return True
        else:
            return False

    def getFileByName(self, filename):
        """See `IPreviewDiff`."""
        if filename == 'preview.diff' and self.diff_text is not None:
            return self.diff_text
        else:
            raise NotFoundError(filename)
