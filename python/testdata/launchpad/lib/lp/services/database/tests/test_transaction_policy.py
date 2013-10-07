# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `TransactionPolicy`."""

__metaclass__ = type

from psycopg2 import InternalError
import transaction

from lp.registry.model.person import Person
from lp.services.database.interfaces import IStore
from lp.services.database.isolation import (
    check_no_transaction,
    TransactionInProgress,
    )
from lp.services.database.transaction_policy import DatabaseTransactionPolicy
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer


class TestTransactionPolicy(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTransactionPolicy, self).setUp()
        # Start each test with a clean slate: no ongoing transaction
        # unless the test says so.
        transaction.abort()

    def readFromDatabase(self):
        """Perform a database read."""
        IStore(Person).find(Person, Person.name == "arbitrary").first()

    def writeToDatabase(self):
        """Write an object to the database.

        :return: A token that `hasDatabaseBeenWrittenTo` can look for.
        """
        name = self.factory.getUniqueString()
        self.factory.makePerson(name=name)
        return name

    def hasDatabaseBeenWrittenTo(self, test_token):
        """Is the object made by `writeToDatabase` present in the database?

        :param test_token: The return value from `writeToDatabase`.
        :return: Has the change represented by `test_token` been made to the
            database?
        """
        query = IStore(Person).find(Person, Person.name == test_token)
        return query.one() is not None

    def test_can_be_empty(self):
        # An empty transaction policy works fine.
        with DatabaseTransactionPolicy():
            pass
        # You still end up with a clean slate, transaction-wise.
        check_no_transaction()

    def test_writable_permits_updates(self):
        # Writes to the database work just fine in a non-read-only
        # policy.
        with DatabaseTransactionPolicy(read_only=False):
            self.writeToDatabase()
            transaction.commit()
        # The test is that we get here without failure.
        pass

    def test_readonly_forbids_updates(self):
        # A read-only policy forbids writes to the database.
        def make_forbidden_update():
            with DatabaseTransactionPolicy(read_only=True):
                self.writeToDatabase()
                transaction.commit()

        self.assertRaises(InternalError, make_forbidden_update)

    def test_will_not_start_in_ongoing_transaction(self):
        # You cannot enter a DatabaseTransactionPolicy while already in
        # a transaction.
        def enter_policy():
            with DatabaseTransactionPolicy():
                pass

        self.writeToDatabase()
        self.assertRaises(TransactionInProgress, enter_policy)

    def test_successful_exit_requires_commit_or_abort(self):
        # If a read-write policy exits normally (which would probably
        # indicate successful completion of its code), it requires that
        # any ongoing transaction be committed or aborted first.
        test_token = None

        def leave_transaction_open():
            with DatabaseTransactionPolicy(read_only=False):
                self.writeToDatabase()

        self.assertRaises(TransactionInProgress, leave_transaction_open)
        # As a side effect of the error, the transaction is rolled back.
        self.assertFalse(self.hasDatabaseBeenWrittenTo(test_token))

    def test_successful_read_only_exit_commits_or_aborts_implicitly(self):
        # When a read-only policy exits normally, there is no need to
        # complete the transaction.  It aborts or commits implicitly.
        # (The choice is up to the implementation; the point of
        # read-only is that you can't tell the difference.)
        with DatabaseTransactionPolicy(read_only=True):
            self.readFromDatabase()

        # No transaction ongoing at this point.
        check_no_transaction()

    def test_aborts_on_failure(self):
        # If the context handler exits with an exception, it aborts the
        # transaction.
        class CompleteFailure(Exception):
            pass

        try:
            with DatabaseTransactionPolicy(read_only=False):
                test_token = self.writeToDatabase()
                raise CompleteFailure()
        except CompleteFailure:
            pass

        # No transaction ongoing at this point.
        check_no_transaction()
        # The change has rolled back.
        self.assertFalse(self.hasDatabaseBeenWrittenTo(test_token))

    def test_nested_policy_overrides_previous_policy(self):
        # When one policy is nested in another, the nested one
        # determines what is allowed.
        def allows_updates(read_only=True):
            """Does the given policy permit database updates?"""
            try:
                with DatabaseTransactionPolicy(read_only=read_only):
                    self.writeToDatabase()
                    transaction.commit()
                return True
            except InternalError:
                return False

        # Map (previous policy, nested policy) to whether the
        # combination makes the store read-only.
        effects = {}

        for previous_policy in [False, True]:
            for nested_policy in [False, True]:
                experiment = (previous_policy, nested_policy)
                with DatabaseTransactionPolicy(read_only=previous_policy):
                    is_read_only = not allows_updates(nested_policy)
                    effects[experiment] = is_read_only

        # Only the nested policy (the second element of the key tuple)
        # determines whether writes are allowed (the value associated
        # with the key).
        self.assertEqual({
            (False, False): False,
            (False, True): True,
            (True, False): False,
            (True, True): True,
            },
            effects)

    def test_policy_restores_previous_policy_on_success(self):
        # A transaction policy, once exited, restores the previously
        # applicable policy.
        with DatabaseTransactionPolicy(read_only=False):
            with DatabaseTransactionPolicy(read_only=True):
                self.readFromDatabase()
            self.assertTrue(
                self.hasDatabaseBeenWrittenTo(self.writeToDatabase()))
            transaction.commit()
        self.assertTrue(
            self.hasDatabaseBeenWrittenTo(self.writeToDatabase()))

    def test_propagates_failure(self):
        # Exceptions raised inside a transaction policy are not
        # swallowed.
        class Kaboom(Exception):
            pass

        def fail_within_policy():
            with DatabaseTransactionPolicy():
                raise Kaboom()

        self.assertRaises(Kaboom, fail_within_policy)

    def test_policy_restores_previous_policy_on_failure(self):
        # A transaction policy restores the previously applicable policy
        # even when it exits abnormally.
        class HorribleFailure(Exception):
            pass

        try:
            with DatabaseTransactionPolicy(read_only=True):
                raise HorribleFailure()
        except HorribleFailure:
            pass

        self.assertTrue(
            self.hasDatabaseBeenWrittenTo(self.writeToDatabase()))

    def test_policy_can_span_transactions(self):
        # It's okay to commit within a policy; the policy will still
        # apply to the next transaction inside the same policy.
        def write_and_commit():
            self.writeToDatabase()
            transaction.commit()

        test_token = self.writeToDatabase()
        transaction.commit()

        with DatabaseTransactionPolicy(read_only=True):
            self.hasDatabaseBeenWrittenTo(test_token)
            transaction.commit()
            self.assertRaises(InternalError, write_and_commit)
            transaction.abort()

    def test_policy_survives_abort(self):
        # Even after aborting the initial transaction, a transaction
        # policy still applies.
        def write_and_commit():
            self.writeToDatabase()
            transaction.commit()

        with DatabaseTransactionPolicy(read_only=True):
            self.readFromDatabase()
            transaction.abort()
            self.assertRaises(InternalError, write_and_commit)
            transaction.abort()
