# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BranchRevision interfaces."""

__metaclass__ = type
__all__ = [
    'IBranchRevision',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import Int

from lp import _


class IBranchRevision(Interface):
    """The association between a revision and a branch.

    BranchRevision records the relation of all revisions that are part of the
    ancestry of a branch. History revisions have an integer sequence, merged
    revisions have sequence set to None.
    """
    sequence = Int(
        title=_("Revision number"), required=True,
        description=_("The index of the revision within the branch's history."
            " None for merged revisions which are not part of the history."))
    branch = Attribute("The branch this revision is included in.")
    revision = Attribute("A revision that is included in the branch.")
