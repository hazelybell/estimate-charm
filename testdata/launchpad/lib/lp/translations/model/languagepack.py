# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Language pack store."""

__metaclass__ = type

__all__ = [
    'LanguagePack',
    'LanguagePackSet',
    ]

from sqlobject import ForeignKey
from zope.interface import implements

from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.translations.enums import LanguagePackType
from lp.translations.interfaces.languagepack import (
    ILanguagePack,
    ILanguagePackSet,
    )


class LanguagePack(SQLBase):
    implements(ILanguagePack)

    _table = 'LanguagePack'

    file = ForeignKey(
        foreignKey='LibraryFileAlias', dbName='file', notNull=True)

    date_exported = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    distroseries = ForeignKey(
        foreignKey='DistroSeries', dbName='distroseries', notNull=True)

    type = EnumCol(
        enum=LanguagePackType, notNull=True, default=LanguagePackType.FULL)

    updates = ForeignKey(
        foreignKey='LanguagePack', dbName='updates',
        notNull=False, default=None)


class LanguagePackSet:
    implements(ILanguagePackSet)

    def addLanguagePack(self, distroseries, file_alias, type):
        """See `ILanguagePackSet`."""
        assert type in LanguagePackType, (
            'Unknown language pack type: %s' % type.name)

        if (type == LanguagePackType.DELTA and
            distroseries.language_pack_base is None):
            raise AssertionError(
                "There is no base language pack available for %s's %s to get"
                " deltas from." % sqlvalues(
                    distroseries.distribution.name, distroseries.name))

        updates = None
        if type == LanguagePackType.DELTA:
            updates = distroseries.language_pack_base

        return LanguagePack(
            file=file_alias, date_exported=UTC_NOW, distroseries=distroseries,
            type=type, updates=updates)
