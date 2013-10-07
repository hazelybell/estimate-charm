# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Ensure that some operations happen outside of transactions."""

__metaclass__ = type
__all__ = [
    'check_no_transaction',
    'ensure_no_transaction',
    'is_transaction_in_progress',
    'TransactionInProgress',
    ]

from functools import wraps

import psycopg2.extensions
from storm.zope.interfaces import IZStorm
from zope.component import getUtility


TRANSACTION_IN_PROGRESS_STATUSES = {
    psycopg2.extensions.TRANSACTION_STATUS_ACTIVE: 'is active',
    psycopg2.extensions.TRANSACTION_STATUS_INTRANS: 'has started',
    psycopg2.extensions.TRANSACTION_STATUS_INERROR: 'has errored',
    psycopg2.extensions.TRANSACTION_STATUS_UNKNOWN: 'is in an unknown state',
    }


class TransactionInProgress(Exception):
    """Transactions may not be open at this time."""


def gen_store_statuses():
    """Yields (store_name, txn_status) tuples for all stores."""
    for name, store in getUtility(IZStorm).iterstores():
        raw_connection = store._connection._raw_connection
        if raw_connection is None:
            # Not connected.
            yield name, None
        else:
            yield name, raw_connection.get_transaction_status()


def is_transaction_in_progress():
    """Return True if a transaction is in progress for any store."""
    return any(
        status in TRANSACTION_IN_PROGRESS_STATUSES
        for name, status in gen_store_statuses())


def check_no_transaction():
    """Raises TransactionInProgress if transaction is in progress."""
    for name, status in gen_store_statuses():
        if status in TRANSACTION_IN_PROGRESS_STATUSES:
            desc = TRANSACTION_IN_PROGRESS_STATUSES[status]
            raise TransactionInProgress(
                "Transaction %s in %s store." % (desc, name))


def ensure_no_transaction(func):
    """Decorator that calls check_no_transaction before function."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        check_no_transaction()
        return func(*args, **kwargs)
    return wrapper
