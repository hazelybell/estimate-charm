# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BranchRevision',
    ]

from storm.locals import (
    Int,
    Reference,
    Storm,
    )
from zope.interface import implements

from lp.code.interfaces.branchrevision import IBranchRevision


class BranchRevision(Storm):
    """See `IBranchRevision`."""
    __storm_table__ = 'BranchRevision'
    __storm_primary__ = ("branch_id", "revision_id")

    implements(IBranchRevision)

    branch_id = Int(name='branch', allow_none=False)
    branch = Reference(branch_id, 'Branch.id')

    revision_id = Int(name='revision', allow_none=False)
    revision = Reference(revision_id, 'Revision.id')

    sequence = Int(name='sequence', allow_none=True)

    def __init__(self, branch, revision, sequence=None):
        self.branch = branch
        self.revision = revision
        self.sequence = sequence
