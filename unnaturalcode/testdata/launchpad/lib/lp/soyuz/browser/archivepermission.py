# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for archivepermission."""

__metaclass__ = type

__all__ = [
    'ArchivePermissionURL',
    ]

from zope.interface import implements

from lp.services.webapp.interfaces import ICanonicalUrlData
from lp.soyuz.enums import ArchivePermissionType


class ArchivePermissionURL:
    """Dynamic URL declaration for `IArchivePermission`."""
    implements(ICanonicalUrlData)
    rootsite = None

    def __init__(self, context):
        self.context = context

    @property
    def inside(self):
        return self.context.archive

    @property
    def path(self):
        if self.context.permission == ArchivePermissionType.UPLOAD:
            perm_type = "+upload"
        elif self.context.permission == ArchivePermissionType.QUEUE_ADMIN:
            perm_type = "+queue-admin"
        else:
            raise AssertionError(
                "Unknown permission type %s" % self.context.permission)

        username = self.context.person.name

        if self.context.component_name is not None:
            item = "type=component&item=%s" % self.context.component_name
        elif self.context.source_package_name is not None:
            item = (
                "type=packagename&item=%s" % self.context.source_package_name)
        elif self.context.package_set_name is not None:
            item = ("type=packageset&item=%s&series=%s" %
                    (self.context.package_set_name,
                     self.context.distro_series_name))
        elif self.context.pocket is not None:
            item = "type=pocket&item=%s" % self.context.pocket.name
            # Queue admin permissions for pockets may be granted by series.
            if self.context.distroseries is not None:
                item += "&series=%s" % self.context.distroseries.name
        else:
            raise AssertionError(
                "One of component, sourcepackagename or package set should "
                "be set")

        return u"%s/%s?%s" % (perm_type, username, item)
