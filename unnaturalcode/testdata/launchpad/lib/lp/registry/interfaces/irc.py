# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IRC interfaces."""

__metaclass__ = type

__all__ = [
    'IIrcID',
    'IIrcIDSet',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Int,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.role import IHasOwner


class IIrcID(IHasOwner):
    """A person's nickname on an IRC network."""
    export_as_webservice_entry('irc_id')
    id = Int(title=_("Database ID"), required=True, readonly=True)
    # schema=Interface will be overridden in person.py because of circular
    # dependencies.
    person = exported(
        Reference(
            title=_("Owner"), required=True, schema=Interface, readonly=True))
    network = exported(
        TextLine(title=_("IRC network"), required=True))
    nickname = exported(
        TextLine(title=_("Nickname"), required=True))

    def destroySelf():
        """Delete this `IIrcID` from the database."""


class IIrcIDSet(Interface):
    """The set of `IIrcID`s."""

    def new(person, network, nickname):
        """Create a new `IIrcID` pointing to the given Person."""

    def get(id):
        """Return the `IIrcID` with the given id or None."""
