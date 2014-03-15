# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations relating to Bazaar formats."""

__metaclass__ = type
__all__ = [
    'branch_changed',
    'BranchFormat',
    'ControlFormat',
    'CURRENT_BRANCH_FORMATS',
    'CURRENT_REPOSITORY_FORMATS',
    'branch_revision_history',
    'get_ancestry',
    'get_branch_formats',
    'RepositoryFormat',
    ]


# FIRST Ensure correct plugins are loaded. Do not delete this comment or the
# line below this comment.
import lp.codehosting

# Silence lint warning.
lp.codehosting

from bzrlib.branch import (
    BranchReferenceFormat,
    BzrBranchFormat6,
    BzrBranchFormat7,
    )
from bzrlib.branchfmt.fullhistory import BzrBranchFormat5
from bzrlib.bzrdir import (
    BzrDirMetaFormat1,
    BzrDirMetaFormat1Colo,
    )
from bzrlib.errors import (
    NotStacked,
    NoSuchRevision,
    UnstackableBranchFormat,
    )
from bzrlib.plugins.loom.branch import (
    BzrBranchLoomFormat1,
    BzrBranchLoomFormat6,
    )
from bzrlib.plugins.weave_fmt.branch import BzrBranchFormat4
from bzrlib.plugins.weave_fmt.bzrdir import (
    BzrDirFormat4,
    BzrDirFormat5,
    BzrDirFormat6,
    )
from bzrlib.plugins.weave_fmt.repository import (
    RepositoryFormat4,
    RepositoryFormat5,
    RepositoryFormat6,
    RepositoryFormat7,
    )
from bzrlib.repofmt.groupcompress_repo import RepositoryFormat2a
from bzrlib.repofmt.knitpack_repo import (
    RepositoryFormatKnitPack1,
    RepositoryFormatKnitPack3,
    RepositoryFormatKnitPack4,
    RepositoryFormatKnitPack5,
    )
from bzrlib.revision import (
    is_null,
    NULL_REVISION,
    )
from bzrlib.repofmt.knitrepo import (
    RepositoryFormatKnit1,
    RepositoryFormatKnit3,
    RepositoryFormatKnit4,
    )
from bzrlib.tsort import topo_sort
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )


def _format_enum(num, format, format_string=None, description=None):
    instance = format()
    if format_string is None:
        format_string = instance.get_format_string()
    if description is None:
        description = instance.get_format_description()
    return DBItem(num, format_string, description)


class BazaarFormatEnum(DBEnumeratedType):
    """Base class for the format enums."""

    @classmethod
    def get_enum(klass, format_name):
        """Find the matching enum value for the format name specified."""
        for value in klass.items:
            if value.title == format_name:
                return value
        else:
            return klass.UNRECOGNIZED


class BranchFormat(BazaarFormatEnum):
    """Branch on-disk format.

    This indicates which (Bazaar) format is used on-disk.  The list must be
    updated as the list of formats supported by Bazaar is updated.
    """

    UNRECOGNIZED = DBItem(1000, '!Unrecognized!', 'Unrecognized format')

    # Branch 4 was only used with all-in-one formats, so it didn't have its
    # own marker.  It was implied by the control directory marker.
    BZR_BRANCH_4 = _format_enum(
        4, BzrBranchFormat4, 'Fake Bazaar Branch 4 marker')

    BRANCH_REFERENCE = _format_enum(1, BranchReferenceFormat)

    BZR_BRANCH_5 = _format_enum(5, BzrBranchFormat5)

    BZR_BRANCH_6 = _format_enum(6, BzrBranchFormat6)

    BZR_BRANCH_7 = _format_enum(7, BzrBranchFormat7)

    # Format string copied from Bazaar 1.15 code. This should be replaced with
    # a line that looks like _format_enum(8, BzrBranchFormat8) when we upgrade
    # to Bazaar 1.15.
    BZR_BRANCH_8 = DBItem(
        8, "Bazaar Branch Format 8 (needs bzr 1.15)\n", "Branch format 8")

    BZR_LOOM_1 = _format_enum(101, BzrBranchLoomFormat1)

    BZR_LOOM_2 = _format_enum(106, BzrBranchLoomFormat6)

    BZR_LOOM_3 = DBItem(
        107, "Bazaar-NG Loom branch format 7\n", "Loom branch format 7")


class RepositoryFormat(BazaarFormatEnum):
    """Repository on-disk format.

    This indicates which (Bazaar) format is used on-disk.  The list must be
    updated as the list of formats supported by Bazaar is updated.
    """

    UNRECOGNIZED = DBItem(1000, '!Unrecognized!', 'Unrecognized format')

    # Repository formats prior to format 7 had no marker because they
    # were implied by the control directory format.
    BZR_REPOSITORY_4 = _format_enum(
        4, RepositoryFormat4, 'Fake Bazaar repository 4 marker')

    BZR_REPOSITORY_5 = _format_enum(
        5, RepositoryFormat5, 'Fake Bazaar repository 5 marker')

    BZR_REPOSITORY_6 = _format_enum(
        6, RepositoryFormat6, 'Fake Bazaar repository 6 marker')

    BZR_REPOSITORY_7 = _format_enum(7, RepositoryFormat7)

    BZR_KNIT_1 = _format_enum(101, RepositoryFormatKnit1)

    BZR_KNIT_3 = _format_enum(103, RepositoryFormatKnit3)

    BZR_KNIT_4 = _format_enum(104, RepositoryFormatKnit4)

    BZR_KNITPACK_1 = _format_enum(201, RepositoryFormatKnitPack1)

    BZR_KNITPACK_3 = _format_enum(203, RepositoryFormatKnitPack3)

    BZR_KNITPACK_4 = _format_enum(204, RepositoryFormatKnitPack4)

    BZR_KNITPACK_5 = _format_enum(
        205, RepositoryFormatKnitPack5,
        description='Packs 5 (needs bzr 1.6, supports stacking)\n')

    BZR_KNITPACK_5_RRB = DBItem(206,
        'Bazaar RepositoryFormatKnitPack5RichRoot (bzr 1.6)\n',
        'Packs 5-Rich Root (needs bzr 1.6, supports stacking)'
        )

    BZR_KNITPACK_5_RR = DBItem(207,
        'Bazaar RepositoryFormatKnitPack5RichRoot (bzr 1.6.1)\n',
        'Packs 5 rich-root (adds stacking support, requires bzr 1.6.1)',
        )

    BZR_KNITPACK_6 = DBItem(208,
        'Bazaar RepositoryFormatKnitPack6 (bzr 1.9)\n',
        'Packs 6 (uses btree indexes, requires bzr 1.9)'
        )

    BZR_KNITPACK_6_RR = DBItem(209,
        'Bazaar RepositoryFormatKnitPack6RichRoot (bzr 1.9)\n',
        'Packs 6 rich-root (uses btree indexes, requires bzr 1.9)'
        )

    BZR_PACK_DEV_0 = DBItem(300,
        'Bazaar development format 0 (needs bzr.dev from before 1.3)\n',
        'Development repository format, currently the same as pack-0.92',
        )

    BZR_PACK_DEV_0_SUBTREE = DBItem(301,
        'Bazaar development format 0 with subtree support (needs bzr.dev from'
        ' before 1.3)\n',
        'Development repository format, currently the same as'
        ' pack-0.92-subtree\n',
        )

    BZR_DEV_1 = DBItem(302,
        "Bazaar development format 1 (needs bzr.dev from before 1.6)\n",
        "Development repository format, currently the same as "
        "pack-0.92 with external reference support.\n"
        )

    BZR_DEV_1_SUBTREE = DBItem(303,
        "Bazaar development format 1 with subtree support "
        "(needs bzr.dev from before 1.6)\n",
        "Development repository format, currently the same as "
        "pack-0.92-subtree with external reference support.\n"
        )

    BZR_DEV_2 = DBItem(304,
        "Bazaar development format 2 (needs bzr.dev from before 1.8)\n",
        "Development repository format, currently the same as "
            "1.6.1 with B+Trees.\n"
        )

    BZR_DEV_2_SUBTREE = DBItem(305,
       "Bazaar development format 2 with subtree support "
        "(needs bzr.dev from before 1.8)\n",
        "Development repository format, currently the same as "
        "1.6.1-subtree with B+Tree indices.\n"
        )

    BZR_DEV_8 = DBItem(306,
        "Bazaar development format 8\n",
        "2a repository format with support for nested trees.\n"
        )

    BZR_CHK1 = DBItem(400,
        "Bazaar development format - group compression and chk inventory"
        " (needs bzr.dev from 1.14)\n",
        "Development repository format - rich roots, group compression"
        " and chk inventories\n",
        )

    BZR_CHK2 = DBItem(410,
        "Bazaar development format - chk repository with bencode revision"
        " serialization (needs bzr.dev from 1.16)\n",
        "Development repository format - rich roots, group compression"
        " and chk inventories\n",
        )

    BZR_CHK_2A = _format_enum(415, RepositoryFormat2a)


class ControlFormat(BazaarFormatEnum):
    """Control directory (BzrDir) format.

    This indicates what control directory format is on disk.  Must be updated
    as new formats become available.
    """

    UNRECOGNIZED = DBItem(1000, '!Unrecognized!', 'Unrecognized format')

    BZR_DIR_4 = _format_enum(4, BzrDirFormat4)

    BZR_DIR_5 = _format_enum(5, BzrDirFormat5)

    BZR_DIR_6 = _format_enum(6, BzrDirFormat6)

    BZR_METADIR_1 = _format_enum(1, BzrDirMetaFormat1)

    BZR_METADIR_1_COLO = _format_enum(2, BzrDirMetaFormat1Colo)


# A tuple of branch formats that should not suggest upgrading.
CURRENT_BRANCH_FORMATS = (
    None,
    BranchFormat.UNRECOGNIZED,
    BranchFormat.BRANCH_REFERENCE,
    BranchFormat.BZR_BRANCH_7,
    BranchFormat.BZR_BRANCH_8,
    BranchFormat.BZR_LOOM_1,
    BranchFormat.BZR_LOOM_2,
    BranchFormat.BZR_LOOM_3)

# A tuple of repository formats that should not suggest upgrading.
CURRENT_REPOSITORY_FORMATS = (
    None,
    RepositoryFormat.UNRECOGNIZED,
    RepositoryFormat.BZR_PACK_DEV_0,
    RepositoryFormat.BZR_PACK_DEV_0_SUBTREE,
    RepositoryFormat.BZR_DEV_1,
    RepositoryFormat.BZR_DEV_1_SUBTREE,
    RepositoryFormat.BZR_DEV_2,
    RepositoryFormat.BZR_DEV_2_SUBTREE,
    RepositoryFormat.BZR_DEV_8,
    RepositoryFormat.BZR_CHK1,
    RepositoryFormat.BZR_CHK2,
    RepositoryFormat.BZR_CHK_2A)


def get_branch_formats(bzr_branch):
    """Return a tuple of format enumerations for the bazaar branch.

    :returns: tuple of (ControlFormat, BranchFormat, RepositoryFormat)
    """
    control_string = bzr_branch.bzrdir._format.get_format_string()
    branch_string = bzr_branch._format.get_format_string()
    repository_string = bzr_branch.repository._format.get_format_string()
    return (ControlFormat.get_enum(control_string),
            BranchFormat.get_enum(branch_string),
            RepositoryFormat.get_enum(repository_string))


def branch_changed(db_branch, bzr_branch=None):
    """Mark a database branch as changed.

    :param db_branch: The branch to mark changed.
    :param bzr_branch: (optional) The bzr branch to use to mark the branch
        changed.
    """
    if bzr_branch is None:
        bzr_branch = db_branch.getBzrBranch()
    try:
        stacked_on = bzr_branch.get_stacked_on_url()
    except (NotStacked, UnstackableBranchFormat):
        stacked_on = None
    last_revision = bzr_branch.last_revision()
    formats = get_branch_formats(bzr_branch)
    db_branch.branchChanged(stacked_on, last_revision, *formats)


def branch_revision_history(branch):
    """Find the revision history of a branch.

    This is a compatibility wrapper for code that still requires
    access to the full branch mainline and previously used
    Branch.revision_history(), which is now deprecated.

    :param branch: Branch object
    :return: Revision ids on the main branch
    """
    branch.lock_read()
    try:
        graph = branch.repository.get_graph()
        ret = list(graph.iter_lefthand_ancestry(
                branch.last_revision(), (NULL_REVISION,)))
        ret.reverse()
        return ret
    finally:
        branch.unlock()


def get_ancestry(repository, revision_id):
    """Return a list of revision-ids integrated by a revision.

    The first element of the list is always None, indicating the origin
    revision.  This might change when we have history horizons, or
    perhaps we should have a new API.

    This is topologically sorted.
    """
    if is_null(revision_id):
        return set()
    if not repository.has_revision(revision_id):
        raise NoSuchRevision(repository, revision_id)
    repository.lock_read()
    try:
        graph = repository.get_graph()
        keys = set()
        search = graph._make_breadth_first_searcher([revision_id])
        while True:
            try:
                found, ghosts = search.next_with_ghosts()
            except StopIteration:
                break
            keys.update(found)
        if NULL_REVISION in keys:
            keys.remove(NULL_REVISION)
    finally:
        repository.unlock()
    return keys
