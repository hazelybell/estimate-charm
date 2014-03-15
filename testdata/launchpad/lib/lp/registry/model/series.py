# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common implementations for a series."""

__metaclass__ = type

__all__ = [
    'ACTIVE_STATUSES',
    'SeriesMixin',
    ]

from operator import attrgetter

from sqlobject import StringCol
from zope.interface import implements

from lp.registry.interfaces.series import (
    ISeriesMixin,
    SeriesStatus,
    )
from lp.registry.model.hasdrivers import HasDriversMixin


ACTIVE_STATUSES = [
    SeriesStatus.DEVELOPMENT,
    SeriesStatus.FROZEN,
    SeriesStatus.CURRENT,
    SeriesStatus.SUPPORTED,
    ]


class SeriesMixin(HasDriversMixin):
    """See `ISeriesMixin`."""

    implements(ISeriesMixin)

    summary = StringCol(notNull=True)

    @property
    def active(self):
        return self.status in ACTIVE_STATUSES

    @property
    def bug_supervisor(self):
        """See `ISeriesMixin`."""
        return self.parent.bug_supervisor

    @property
    def drivers(self):
        """See `IHasDrivers`."""
        drivers = set()
        drivers.add(self.driver)
        drivers = drivers.union(self.parent.drivers)
        drivers.discard(None)
        return sorted(drivers, key=attrgetter('displayname'))
