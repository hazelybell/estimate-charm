# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The lp.services.database package."""

__metaclass__ = type
__all__ = [
    'read_transaction',
    'write_transaction',
    ]

from psycopg2.extensions import TransactionRollbackError
from storm.exceptions import (
    DisconnectionError,
    IntegrityError,
    )
import transaction
from twisted.python.util import mergeFunctionMetadata

from lp.services.database.sqlbase import reset_store


RETRY_ATTEMPTS = 3


def retry_transaction(func):
    """Decorator used to retry database transaction failures.

    The function being decorated should not have side effects outside
    of the transaction.
    """
    def retry_transaction_decorator(*args, **kwargs):
        attempt = 0
        while True:
            attempt += 1
            try:
                return func(*args, **kwargs)
            except (DisconnectionError, IntegrityError,
                    TransactionRollbackError):
                if attempt >= RETRY_ATTEMPTS:
                    raise # tried too many times
    return mergeFunctionMetadata(func, retry_transaction_decorator)


def read_transaction(func):
    """Decorator used to run the function inside a read only transaction.

    The transaction will be aborted on successful completion of the
    function.  The transaction will be retried if appropriate.
    """
    @reset_store
    def read_transaction_decorator(*args, **kwargs):
        transaction.begin()
        try:
            return func(*args, **kwargs)
        finally:
            transaction.abort()
    return retry_transaction(mergeFunctionMetadata(
        func, read_transaction_decorator))


def write_transaction(func):
    """Decorator used to run the function inside a write transaction.

    The transaction will be committed on successful completion of the
    function, and aborted on failure.  The transaction will be retried
    if appropriate.
    """
    @reset_store
    def write_transaction_decorator(*args, **kwargs):
        transaction.begin()
        try:
            ret = func(*args, **kwargs)
        except:
            transaction.abort()
            raise
        transaction.commit()
        return ret
    return retry_transaction(mergeFunctionMetadata(
        func, write_transaction_decorator))

