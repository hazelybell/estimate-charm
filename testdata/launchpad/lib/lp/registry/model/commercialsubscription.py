# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation classes for a CommercialSubscription."""

__metaclass__ = type
__all__ = ['CommercialSubscription']

import datetime

import pytz
from sqlobject import (
    ForeignKey,
    StringCol,
    )
from zope.interface import implements

from lp.registry.errors import CannotDeleteCommercialSubscription
from lp.registry.interfaces.commercialsubscription import (
    ICommercialSubscription,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase


class CommercialSubscription(SQLBase):
    implements(ICommercialSubscription)

    product = ForeignKey(
        dbName='product', foreignKey='Product', notNull=True)
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_last_modified = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_starts = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_expires = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person', default=None,
        storm_validator=validate_public_person)
    purchaser = ForeignKey(
        dbName='purchaser', foreignKey='Person', default=None,
        storm_validator=validate_public_person)
    sales_system_id = StringCol(notNull=True)
    whiteboard = StringCol(default=None)

    @property
    def is_active(self):
        """See `ICommercialSubscription`"""
        now = datetime.datetime.now(pytz.timezone('UTC'))
        return self.date_starts < now < self.date_expires

    def delete(self):
        """See `ICommercialSubscription`"""
        if self.is_active:
            raise CannotDeleteCommercialSubscription(
                "This CommercialSubscription is still active.")
        self.destroySelf()
