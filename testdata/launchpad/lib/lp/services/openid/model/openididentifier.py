# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OpenIdIdentifier database class."""

__metaclass__ = type
__all__ = ['OpenIdIdentifier']

from storm.locals import (
    Int,
    Reference,
    Storm,
    Unicode,
    )

from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol


class OpenIdIdentifier(Storm):
    """An OpenId Identifier that can be used to log into an Account"""
    __storm_table__ = "openididentifier"
    identifier = Unicode(primary=True)
    account_id = Int("account")
    account = Reference(account_id, "Account.id")
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
