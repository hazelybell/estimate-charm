# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the `base` module."""

__metaclass__ = type

from contextlib import contextmanager

import transaction

from lp.bugs.scripts.checkwatches.base import WorkingBase
from lp.services.database.isolation import (
    is_transaction_in_progress,
    TransactionInProgress,
    )
from lp.services.log.logger import BufferLogger
from lp.services.webapp.adapter import get_request_statements
from lp.services.webapp.interaction import (
    endInteraction,
    queryInteraction,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class StubTransactionManager:
    def __init__(self):
        self.log = []
    def abort(self):
        self.log.append('abort')
    def commit(self):
        self.log.append('commit')


class TestWorkingBase(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestWorkingBase, self).setUp()
        self.person = self.factory.makePerson()
        self.email = self.person.preferredemail.email
        self.logger = BufferLogger()

    def test_interaction(self):
        # The WorkingBase.interaction context manager will begin an
        # interaction on entry and end it on exit.
        base = WorkingBase()
        base.init(self.email, transaction.manager, self.logger)
        endInteraction()
        self.assertIs(None, queryInteraction())
        with base.interaction:
            self.assertIsNot(None, queryInteraction())
        self.assertIs(None, queryInteraction())

    def test_interaction_nested(self):
        # If an interaction is already in progress, the interaction
        # context manager will not begin a new interaction on entry,
        # nor will it end the interaction on exit.
        base = WorkingBase()
        base.init(self.email, transaction.manager, self.logger)
        endInteraction()
        self.assertIs(None, queryInteraction())
        with base.interaction:
            self.assertIsNot(None, queryInteraction())
            with base.interaction:
                self.assertIsNot(None, queryInteraction())
            self.assertIsNot(None, queryInteraction())
        self.assertIs(None, queryInteraction())

    def test_transaction(self):
        # The WonkingBase.transaction context manager ensures that no
        # transaction is in progress on entry, commits on a successful
        # exit, or aborts the transaction on failure.
        transaction_manager = StubTransactionManager()
        base = WorkingBase()
        base.init(self.email, transaction_manager, self.logger)
        transaction.commit()
        with base.transaction:
            self.assertFalse(is_transaction_in_progress())
            self.assertEqual([], transaction_manager.log)
            self.factory.makeEmail('numpty@example.com', self.person)
            self.assertTrue(is_transaction_in_progress())
            self.assertEqual([], transaction_manager.log)
        self.assertEqual(['commit'], transaction_manager.log)

    def test_transaction_with_open_transaction(self):
        # On entry, WorkingBase.transaction will raise an exception if
        # a transaction is in progress.
        transaction_manager = StubTransactionManager()
        base = WorkingBase()
        base.init(self.email, transaction_manager, self.logger)
        self.assertTrue(is_transaction_in_progress())
        self.assertRaises(TransactionInProgress, base.transaction.__enter__)

    def test_transaction_with_exception(self):
        # If an exception is raised when the transaction context
        # manager is active, the transaction will be aborted and the
        # exception re-raised.
        transaction_manager = StubTransactionManager()
        base = WorkingBase()
        base.init(self.email, transaction_manager, self.logger)
        transaction.commit()
        try:
            with base.transaction:
                raise RuntimeError("Nothing really.")
        except RuntimeError:
            self.assertFalse(is_transaction_in_progress())
            self.assertEqual(['abort'], transaction_manager.log)
        else:
            self.fail("Exception not re-raised from context manager.")

    def test_statement_logging(self):
        # The WorkingBase.statement_logging context manager starts
        # statement logging on entry and stops it on exit.
        base = WorkingBase()
        base.init(self.email, transaction.manager, self.logger)
        self.factory.makeEmail('numpty1@example.com', self.person)
        self.assertEqual(
            0, len(get_request_statements()),
            "The statement log should be empty because "
            "logging is not enabled.")
        with base.statement_logging:
            self.assertEqual(
                0, len(get_request_statements()),
                "There should be no statements in the log yet.")
            self.factory.makeEmail('numpty2@example.com', self.person)
            self.assertTrue(
                len(get_request_statements()) > 0,
                "There should be at least one statement in the log.")
        self.assertEqual(
            0, len(get_request_statements()),
            "SQL statement log not cleared on exit "
            "from base.statement_logging.")

    def test_initFromParent(self):
        base1 = WorkingBase()
        base1.init(self.email, transaction.manager, self.logger)
        base2 = WorkingBase()
        base2.initFromParent(base1)
        self.failUnlessEqual(base1.__dict__, base2.__dict__)


class TestWorkingBaseErrorReporting(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    @contextmanager
    def _test_sql_log_cleared_after_x(self):
        person = self.factory.makePerson()
        email = person.preferredemail.email
        logger = BufferLogger()
        base = WorkingBase()
        base.init(email, transaction.manager, logger)
        with base.statement_logging:
            self.factory.makeEmail('numpty@example.com', person)
            self.assertTrue(
                len(get_request_statements()) > 0,
                "We need at least one statement in the SQL log.")
            yield base
            self.assertTrue(
                len(get_request_statements()) == 0,
                "SQL statement log not cleared by WorkingBase.warning().")

    def test_sql_log_cleared_after_warning(self):
        with self._test_sql_log_cleared_after_x() as base:
            base.warning("Numpty on deck.")

    def test_sql_log_cleared_after_error(self):
        with self._test_sql_log_cleared_after_x() as base:
            base.error("Numpty on deck.")
