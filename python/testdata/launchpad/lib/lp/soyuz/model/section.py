# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'Section',
    'SectionSelection',
    'SectionSet'
    ]

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.services.database.sqlbase import SQLBase
from lp.soyuz.interfaces.section import (
    ISection,
    ISectionSelection,
    ISectionSet,
    )


class Section(SQLBase):
    """See ISection"""
    implements(ISection)

    _defaultOrder = ['id']

    name = StringCol(notNull=True, alternateID=True)


class SectionSelection(SQLBase):
    """See ISectionSelection."""

    implements(ISectionSelection)

    _defaultOrder = ['id']

    distroseries = ForeignKey(dbName='distroseries',
        foreignKey='DistroSeries', notNull=True)
    section = ForeignKey(dbName='section',
        foreignKey='Section', notNull=True)


class SectionSet:
    """See ISectionSet."""
    implements(ISectionSet)

    def __iter__(self):
        """See ISectionSet."""
        return iter(Section.select())

    def __getitem__(self, name):
        """See ISectionSet."""
        section = Section.selectOneBy(name=name)
        if section is not None:
            return section
        raise NotFoundError(name)

    def get(self, section_id):
        """See ISectionSet."""
        return Section.get(section_id)

    def ensure(self, name):
        """See ISectionSet."""
        section = Section.selectOneBy(name=name)
        if section is not None:
            return section
        return self.new(name)

    def new(self, name):
        """See ISectionSet."""
        return Section(name=name)

