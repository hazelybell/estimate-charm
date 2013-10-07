# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to bugs."""

__metaclass__ = type

__all__ = [
    'IHasBug',
    ]


from zope.interface import Interface
from zope.schema import Int

from lp import _


class IHasBug(Interface):
    """An object linked to a bug, e.g., a bugtask or a bug branch."""

    bug = Int(title=_("Bug #"))
