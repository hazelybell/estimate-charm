# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Jabber interfaces."""

__metaclass__ = type

__all__ = [
    'IJabberID',
    'IJabberIDSet',
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


class IJabberID(IHasOwner):
    """Jabber specific user ID """
    export_as_webservice_entry('jabber_id')
    id = Int(title=_("Database ID"), required=True, readonly=True)
    # schema=Interface will be overridden in person.py because of circular
    # dependencies.
    person = exported(
        Reference(
            title=_("Owner"), required=True, schema=Interface, readonly=True))
    jabberid = exported(
        TextLine(title=_("New Jabber user ID"), required=True))

    def destroySelf():
        """Delete this JabberID from the database."""


class IJabberIDSet(Interface):
    """The set of JabberIDs."""

    def new(person, jabberid):
        """Create a new JabberID pointing to the given Person."""

    def getByJabberID(jabberid):
        """Return the JabberID with the given jabberid or None."""

    def getByPerson(person):
        """Return all JabberIDs for the given person."""
