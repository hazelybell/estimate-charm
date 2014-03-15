# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for Person Location.

The location of the person includes their geographic coordinates (latitude
and longitude) and their time zone. We only store this information for
people who have provided it, so we put it in a separate table which
decorates Person.
"""

__metaclass__ = type
__all__ = [
    'PersonLocation',
    ]

from sqlobject import (
    BoolCol,
    FloatCol,
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.registry.interfaces.location import IPersonLocation
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase


class PersonLocation(SQLBase):
    """A person's location."""

    implements(IPersonLocation)
 
    _defaultOrder = ['id']

    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True, unique=True)
    latitude = FloatCol(notNull=False)
    longitude = FloatCol(notNull=False)
    time_zone = StringCol(notNull=True)
    last_modified_by = ForeignKey(
        dbName='last_modified_by', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    date_last_modified = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    visible = BoolCol(notNull=True, default=True)
