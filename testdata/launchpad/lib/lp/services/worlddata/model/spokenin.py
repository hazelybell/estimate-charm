# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['SpokenIn']

from sqlobject import ForeignKey
from zope.interface import implements

from lp.services.database.sqlbase import SQLBase
from lp.services.worlddata.interfaces.spokenin import ISpokenIn


class SpokenIn(SQLBase):
    """A way of telling which languages are spoken in which countries.

    This table maps a language which is SpokenIn a country.
    """

    implements(ISpokenIn)

    _table = 'SpokenIn'

    country = ForeignKey(dbName='country', notNull=True, foreignKey='Country')
    language = ForeignKey(dbName='language', notNull=True,
                          foreignKey='Language')

