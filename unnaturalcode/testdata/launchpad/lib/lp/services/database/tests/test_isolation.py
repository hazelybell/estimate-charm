# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the isolation module."""

__metaclass__ = type

from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from storm.zope.interfaces import IZStorm
import transaction
from zope.component import getUtility

from lp.services.database import isolation
from lp.testing import TestCase
from lp.testing.layers import LaunchpadZopelessLayer


class TestIsolation(TestCase):

    layer = LaunchpadZopelessLayer

    def createTransaction(self):
        stores = list(store for _, store in getUtility(IZStorm).iterstores())
        self.failUnless(len(stores) > 0, "No stores to test.")
        # One or more of the stores may be set to auto-commit. The transaction
        # status remains unchanged for these stores hence they are not useful
        # for these tests, so execute a query in every store; one of them will
        # have a transactional state.
        for store in stores:
            store.execute('SELECT 1')

    def test_gen_store_statuses(self):
        # All stores are either disconnected or idle when all
        # transactions have been aborted.
        transaction.abort()
        for name, status in isolation.gen_store_statuses():
            self.assertIsInstance(name, (str, unicode))
            self.failUnless(status in (None, TRANSACTION_STATUS_IDLE))
        # At least one store will not be idle when a transaction has
        # begun.
        self.createTransaction()
        self.failUnless(
            any(status not in (None, TRANSACTION_STATUS_IDLE)
                for _, status in isolation.gen_store_statuses()))

    def test_is_transaction_in_progress(self):
        # is_transaction_in_progress() returns False when all
        # transactions have been aborted.
        transaction.abort()
        self.failIf(isolation.is_transaction_in_progress())
        # is_transaction_in_progress() returns True when a
        # transactions has begun.
        self.createTransaction()
        self.failUnless(isolation.is_transaction_in_progress())

    def test_check_no_transaction(self):
        # check_no_transaction() should be a no-op when there are no
        # transactions in operation.
        transaction.abort()
        isolation.check_no_transaction()
        # check_no_transaction() raises TransactionInProgress when a
        # transaction has begun.
        self.createTransaction()
        self.assertRaises(
            isolation.TransactionInProgress,
            isolation.check_no_transaction)

    def test_ensure_no_transaction(self):
        # ensure_no_transaction() is a decorator that raises
        # TransactionInProgress if a transaction has begun, else it
        # simply calls the wrapped function.
        @isolation.ensure_no_transaction
        def echo(*args, **kwargs):
            return args, kwargs
        # echo() will just return the given args no transaction is in
        # progress.
        transaction.abort()
        self.failUnlessEqual(
            ((1, 2, 3), {'a': 4, 'b': 5, 'c': 6}),
            echo(1, 2, 3, a=4, b=5, c=6))
        # echo() will break with TransactionInProgress when a
        # transaction has begun.
        self.createTransaction()
        self.assertRaises(isolation.TransactionInProgress, echo)
