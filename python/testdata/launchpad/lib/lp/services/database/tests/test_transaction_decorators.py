# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import unittest

import transaction

from lp.services.database import (
    read_transaction,
    write_transaction,
    )
from lp.services.database.interfaces import IStore
from lp.services.librarian.model import LibraryFileContent
from lp.services.librarianserver import db
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class TestTransactionDecorators(unittest.TestCase):
    """Tests for the transaction decorators used by the librarian."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        switch_dbuser('librarian')
        self.store = IStore(LibraryFileContent)
        self.content_id = db.Library().add('deadbeef', 1234, 'abababab', 'ba')
        self.file_content = self._getTestFileContent()
        transaction.commit()

    def _getTestFileContent(self):
        """Return the file content object that created."""
        return self.store.find(LibraryFileContent, id=self.content_id).one()

    def test_read_transaction_reset_store(self):
        """Make sure that the store is reset after the transaction."""
        @read_transaction
        def no_op():
            pass
        no_op()
        self.failIf(
            self.file_content is self._getTestFileContent(),
            "Store wasn't reset properly.")

    def test_write_transaction_reset_store(self):
        """Make sure that the store is reset after the transaction."""
        @write_transaction
        def no_op():
            pass
        no_op()
        self.failIf(
            self.file_content is self._getTestFileContent(),
            "Store wasn't reset properly.")

    def test_write_transaction_reset_store_with_raise(self):
        """Make sure that the store is reset after the transaction."""
        @write_transaction
        def no_op():
            raise RuntimeError('an error occured')
        self.assertRaises(RuntimeError, no_op)
        self.failIf(
            self.file_content is self._getTestFileContent(),
            "Store wasn't reset properly.")

    def test_writing_transaction_reset_store_on_commit_failure(self):
        """The store should be reset even if committing the transaction fails.
        """
        class TransactionAborter:
            """Make the next commit() fails."""
            def newTransaction(self, txn):
                pass

            def beforeCompletion(self, txn):
                raise RuntimeError('the commit will fail')
        aborter = TransactionAborter()
        transaction.manager.registerSynch(aborter)
        try:
            @write_transaction
            def no_op():
                pass
            self.assertRaises(RuntimeError, no_op)
            self.failIf(
                self.file_content is self._getTestFileContent(),
                "Store wasn't reset properly.")
        finally:
            transaction.manager.unregisterSynch(aborter)
