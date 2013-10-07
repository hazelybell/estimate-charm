# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'IWikiName',
    'IWikiNameSet',
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
from lp.services.fields import URIField


class IWikiName(IHasOwner):
    """Wiki for Users"""
    export_as_webservice_entry(publish_web_link=False)
    id = Int(title=_("Database ID"), required=True, readonly=True)
    # schema=Interface will be overridden in person.py because of circular
    # dependencies.
    person = exported(
        Reference(
            title=_("Owner"), schema=Interface, required=True, readonly=True))
    wiki = exported(
        URIField(title=_("Wiki host"),
                 allowed_schemes=['http', 'https'],
                 required=True))
    wikiname = exported(
        TextLine(title=_("Wikiname"), required=True))
    url = exported(
        TextLine(title=_("The URL for this wiki home page."), readonly=True))

    def destroySelf():
        """Remove this WikiName from the database."""


class IWikiNameSet(Interface):
    """The set of WikiNames."""

    def getByWikiAndName(wiki, wikiname):
        """Return the WikiName with the given wiki and wikiname.

        Return None if it doesn't exists.
        """

    def get(id):
        """Return the WikiName with the given id or None."""

    def new(person, wiki, wikiname):
        """Create a new WikiName pointing to the given Person."""
