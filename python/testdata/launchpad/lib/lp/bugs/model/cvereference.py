# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['CveReference']

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.bugs.interfaces.cvereference import ICveReference
from lp.services.database.sqlbase import SQLBase


class CveReference(SQLBase):
    """A CVE reference to some other tracking system."""

    implements(ICveReference)

    _table = 'CveReference'

    # db field names
    cve = ForeignKey(dbName='cve', foreignKey='Cve', notNull=True)
    source = StringCol(notNull=True)
    content = StringCol(notNull=True)
    url = StringCol(notNull=False, default=None)


