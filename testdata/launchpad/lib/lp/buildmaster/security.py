# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Security adapters for the buildmaster package."""

__metaclass__ = type
__all__ = [
    'ViewBuilder',
    ]

from lp.app.security import AnonymousAuthorization
from lp.buildmaster.interfaces.builder import IBuilder


class ViewBuilder(AnonymousAuthorization):
    """Anyone can view a `IBuilder`."""
    usedfor = IBuilder
