# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BugTrackerPerson database class."""

__metaclass__ = type
__all__ = [
    'BugTrackerPerson',
    ]

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.bugs.interfaces.bugtrackerperson import IBugTrackerPerson
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase


class BugTrackerPerson(SQLBase):
    """See `IBugTrackerPerson`."""

    implements(IBugTrackerPerson)

    bugtracker = ForeignKey(
        dbName='bugtracker', foreignKey='BugTracker', notNull=True)
    person = ForeignKey(
        dbName='person', foreignKey='Person', notNull=True)
    name = StringCol(notNull=True)
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
