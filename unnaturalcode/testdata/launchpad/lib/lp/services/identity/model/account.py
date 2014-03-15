# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation classes for Account and associates."""

__metaclass__ = type
__all__ = [
    'Account',
    'AccountSet',
    ]

from sqlobject import StringCol
from storm.locals import ReferenceSet
from zope.interface import implements

from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import SQLBase
from lp.services.identity.interfaces.account import (
    AccountCreationRationale,
    AccountStatus,
    IAccount,
    IAccountSet,
    )
from lp.services.openid.model.openididentifier import OpenIdIdentifier


class AccountStatusEnumCol(EnumCol):

    def __set__(self, obj, value):
        if self.__get__(obj) == value:
            return
        IAccount['status'].bind(obj)._validate(value)
        super(AccountStatusEnumCol, self).__set__(obj, value)


class Account(SQLBase):
    """An Account."""

    implements(IAccount)

    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    displayname = StringCol(dbName='displayname', notNull=True)

    creation_rationale = EnumCol(
        dbName='creation_rationale', schema=AccountCreationRationale,
        notNull=True)
    status = AccountStatusEnumCol(
        enum=AccountStatus, default=AccountStatus.NOACCOUNT, notNull=True)
    date_status_set = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    status_comment = StringCol(dbName='status_comment', default=None)

    openid_identifiers = ReferenceSet(
        "Account.id", OpenIdIdentifier.account_id)

    def __repr__(self):
        displayname = self.displayname.encode('ASCII', 'backslashreplace')
        return "<%s '%s' (%s)>" % (
            self.__class__.__name__, displayname, self.status)

    def reactivate(self, comment):
        """See `IAccountSpecialRestricted`."""
        self.status = AccountStatus.ACTIVE
        self.status_comment = comment


class AccountSet:
    """See `IAccountSet`."""
    implements(IAccountSet)

    def new(self, rationale, displayname, openid_identifier=None):
        """See `IAccountSet`."""

        account = Account(
            displayname=displayname, creation_rationale=rationale)

        # Create an OpenIdIdentifier record if requested.
        if openid_identifier is not None:
            assert isinstance(openid_identifier, unicode)
            identifier = OpenIdIdentifier()
            identifier.account = account
            identifier.identifier = openid_identifier
            IMasterStore(OpenIdIdentifier).add(identifier)

        return account

    def get(self, id):
        """See `IAccountSet`."""
        account = IStore(Account).get(Account, id)
        if account is None:
            raise LookupError(id)
        return account

    def getByOpenIDIdentifier(self, openid_identifier):
        """See `IAccountSet`."""
        store = IStore(Account)
        account = store.find(
            Account,
            Account.id == OpenIdIdentifier.account_id,
            OpenIdIdentifier.identifier == openid_identifier).one()
        if account is None:
            raise LookupError(openid_identifier)
        return account
