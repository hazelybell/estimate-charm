# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Security adapters for the soyuz module."""

__metaclass__ = type
__all__ = [
    'ViewProcessor',
    ]

from lp.app.security import AnonymousAuthorization
from lp.soyuz.interfaces.processor import IProcessor


class ViewProcessor(AnonymousAuthorization):
    """Anyone can view an `IProcessor`."""
    usedfor = IProcessor
