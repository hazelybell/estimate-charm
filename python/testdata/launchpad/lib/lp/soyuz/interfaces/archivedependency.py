# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchiveDependency interface."""

__metaclass__ = type

__all__ = [
    'IArchiveDependency',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Choice,
    Datetime,
    Int,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.interfaces.archive import IArchive


class IArchiveDependency(Interface):
    """ArchiveDependency interface."""
    export_as_webservice_entry(publish_web_link=False)

    id = Int(title=_("The archive ID."), readonly=True)

    date_created = exported(
        Datetime(
            title=_("Instant when the dependency was created."),
            required=False, readonly=True))

    archive = exported(
        Reference(
            schema=IArchive, required=True, readonly=True,
            title=_('Target archive'),
            description=_("The archive affected by this dependecy.")))

    dependency = exported(
        Reference(
            schema=IArchive, required=False, readonly=True,
            title=_("The archive set as a dependency.")))

    pocket = exported(
        Choice(
            title=_("Pocket"), required=True, readonly=True,
            vocabulary=PackagePublishingPocket))

    component = Choice(
        title=_("Component"), required=True, readonly=True,
        vocabulary='Component')

    # We don't want to export IComponent, so the name is exported specially.
    component_name = exported(
        TextLine(
            title=_("Component name"),
            required=True, readonly=True))

    title = exported(
        TextLine(title=_("Archive dependency title."), readonly=True))
