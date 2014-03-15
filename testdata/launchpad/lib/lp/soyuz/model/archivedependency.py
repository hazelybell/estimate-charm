# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for ArchiveDependency."""

__metaclass__ = type

__all__ = ['ArchiveDependency']


from sqlobject import ForeignKey
from zope.interface import implements

from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.soyuz.adapters.archivedependencies import component_dependencies
from lp.soyuz.interfaces.archivedependency import IArchiveDependency


class ArchiveDependency(SQLBase):
    """See `IArchiveDependency`."""

    implements(IArchiveDependency)

    _table = 'ArchiveDependency'
    _defaultOrder = 'id'

    date_created = UtcDateTimeCol(
        dbName='date_created', notNull=True, default=UTC_NOW)

    archive = ForeignKey(
        foreignKey='Archive', dbName='archive', notNull=True)

    dependency = ForeignKey(
        foreignKey='Archive', dbName='dependency', notNull=True)

    pocket = EnumCol(
        dbName='pocket', notNull=True, schema=PackagePublishingPocket)

    component = ForeignKey(
        foreignKey='Component', dbName='component')

    @property
    def component_name(self):
        """See `IArchiveDependency`"""
        if self.component:
            return self.component.name
        else:
            return None

    @property
    def title(self):
        """See `IArchiveDependency`."""
        if self.dependency.is_ppa:
            return self.dependency.displayname

        pocket_title = "%s - %s" % (
            self.dependency.displayname, self.pocket.name)

        if self.component is None:
            return pocket_title

        component_part = ", ".join(
            component_dependencies[self.component.name])

        return "%s (%s)" % (pocket_title, component_part)
