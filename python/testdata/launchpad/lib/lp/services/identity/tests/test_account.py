# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `Account` objects."""

__metaclass__ = type
__all__ = []

from lp.services.identity.interfaces.account import (
    AccountStatus,
    AccountStatusError,
    IAccount,
    )
from lp.testing import (
    login_celebrity,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestAccount(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_account_repr_ansii(self):
        # Verify that ANSI displayname is ascii safe.
        distro = self.factory.makeAccount(u'\xdc-account')
        ignore, displayname, status_1, status_2 = repr(distro).rsplit(' ', 3)
        self.assertEqual("'\\xdc-account'", displayname)
        self.assertEqual('(Active account)>', '%s %s' % (status_1, status_2))

    def test_account_repr_unicode(self):
        # Verify that Unicode displayname is ascii safe.
        distro = self.factory.makeAccount(u'\u0170-account')
        ignore, displayname, status_1, status_2 = repr(distro).rsplit(' ', 3)
        self.assertEqual("'\\u0170-account'", displayname)

    def assertCannotTransition(self, account, statuses):
        for status in statuses:
            self.assertFalse(
                IAccount['status'].bind(account).constraint(status))
            self.assertRaises(
                AccountStatusError, setattr, account, 'status', status)

    def assertCanTransition(self, account, statuses):
        for status in statuses:
            self.assertTrue(
                IAccount['status'].bind(account).constraint(status))
        account.status = status
        self.assertEqual(status, account.status)

    def test_status_from_noaccount(self):
        # The status may change from NOACCOUNT to ACTIVE.
        account = self.factory.makeAccount(status=AccountStatus.NOACCOUNT)
        login_celebrity('admin')
        self.assertCannotTransition(
            account, [AccountStatus.DEACTIVATED, AccountStatus.SUSPENDED])
        self.assertCanTransition(account, [AccountStatus.ACTIVE])

    def test_status_from_active(self):
        # The status may change from ACTIVE to DEACTIVATED or SUSPENDED.
        account = self.factory.makeAccount(status=AccountStatus.ACTIVE)
        login_celebrity('admin')
        self.assertCannotTransition(account, [AccountStatus.NOACCOUNT])
        self.assertCanTransition(
            account, [AccountStatus.DEACTIVATED, AccountStatus.SUSPENDED])

    def test_status_from_deactivated(self):
        # The status may change from DEACTIVATED to ACTIVATED.
        account = self.factory.makeAccount()
        login_celebrity('admin')
        account.status = AccountStatus.DEACTIVATED
        self.assertCannotTransition(
            account, [AccountStatus.NOACCOUNT, AccountStatus.SUSPENDED])
        self.assertCanTransition(account, [AccountStatus.ACTIVE])

    def test_status_from_suspended(self):
        # The status may change from SUSPENDED to DEACTIVATED.
        account = self.factory.makeAccount()
        login_celebrity('admin')
        account.status = AccountStatus.SUSPENDED
        self.assertCannotTransition(
            account, [AccountStatus.NOACCOUNT, AccountStatus.ACTIVE])
        self.assertCanTransition(account, [AccountStatus.DEACTIVATED])
