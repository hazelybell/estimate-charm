# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'IBranchRef',
    ]

from zope.interface import Interface
from zope.schema import Choice

from lp import _


class IBranchRef(Interface):
    """A branch reference '.bzr' directory.

    This interface is for use in the browser code to implement these
    directories.
    """

    branch = Choice(
        title=_('Series Branch'),
        vocabulary='Branch',
        readonly=True,
        description=_("The Bazaar branch for this series."))
