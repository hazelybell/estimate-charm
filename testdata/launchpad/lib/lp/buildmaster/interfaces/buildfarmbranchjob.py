# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for `IBuildFarmJob`s that are also `IBranchJob`s."""

__metaclass__ = type
__all__ = [
    'IBuildFarmBranchJob'
    ]

from zope.interface import Attribute

from lp.code.interfaces.branchjob import IBranchJob


class IBuildFarmBranchJob(IBranchJob):
    """An `IBuildFarmJob` that's also an `IBranchJob`.

    Use this interface for `IBuildFarmJob` implementations that do not
    have a "build" attribute but do implement `IBranchJob`, so that the
    UI can render appropriate status information.
    """

    build = Attribute("The `IBuildFarmJob` associated with this job.")
