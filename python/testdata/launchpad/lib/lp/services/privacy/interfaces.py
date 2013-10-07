# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'IObjectPrivacy',
    ]

from zope.interface import Interface
from zope.schema import Bool

from lp import _


class IObjectPrivacy(Interface):
    """Privacy-related information about an object."""

    is_private = Bool(title=_("Whether access to the object is restricted."))
