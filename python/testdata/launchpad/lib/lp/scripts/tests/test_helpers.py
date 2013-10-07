# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the helpers."""

__metaclass__ = type

from testtools.testcase import ExpectedException
import transaction

from lp.scripts.helpers import TransactionFreeOperation
from lp.testing import TestCase


class TestTransactionFreeOperation(TestCase):

    def setUp(self):
        """We can ignore transactions in general, but this test case cares."""
        super(TestTransactionFreeOperation, self).setUp()
        transaction.abort()

    def test_pending_transaction(self):
        """When a transaction is pending before the operation, raise."""
        transaction.begin()
        with ExpectedException(
            AssertionError, 'Transaction open before operation'):
            with TransactionFreeOperation():
                pass

    def test_transaction_during_operation(self):
        """When the operation creates a transaction, raise."""
        with ExpectedException(
            AssertionError, 'Operation opened transaction!'):
            with TransactionFreeOperation():
                transaction.begin()

    def test_transaction_free(self):
        """When there are no transactions, do not raise."""
        with TransactionFreeOperation():
            pass

    def test_require_no_TransactionFreeOperation(self):
        """If TransactionFreeOperation is not used, raise."""
        with ExpectedException(
                AssertionError, 'TransactionFreeOperation was not used.'):
            with TransactionFreeOperation.require():
                pass

    def test_require_with_TransactionFreeOperation(self):
        """If TransactionFreeOperation is used, do not raise."""
        with TransactionFreeOperation.require():
            with TransactionFreeOperation():
                pass
