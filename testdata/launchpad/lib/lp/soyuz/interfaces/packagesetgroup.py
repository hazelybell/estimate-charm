# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Packageset Group interface."""

__metaclass__ = type

__all__ = [
    'IPackagesetGroup',
    ]

from lazr.restful.fields import Reference
from zope.schema import (
    Datetime,
    Int,
    )

from lp import _
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.role import IHasOwner


class IPackagesetGroup(IHasOwner):
    """A group of related package sets across distroseries' 

    This class is used internally to group related packagesets across
    distroseries.  For example, if in Karmic there is a 'gnome-games'
    package set, and this package set is cloned initially for Lucid,
    then both packagesets would refer to the same packageset-group.

    Packageset-groups are not exposed at all.  The date_created and
    owner fields are present for internal use only.
    """
    id = Int(title=_('ID'), required=True, readonly=True)

    date_created = Datetime(
        title=_("Date Created"), required=True, readonly=True,
        description=_("The creation date/time for this packageset group."))

    owner = Reference(
        IPerson, title=_("Person"), required=True, readonly=True,
        description=_("The person who created this packageset group."))

