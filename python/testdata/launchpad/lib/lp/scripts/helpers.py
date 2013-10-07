# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for command line tools."""

__metaclass__ = type
__all__ = ["LPOptionParser", "TransactionFreeOperation", ]

import contextlib
from copy import copy
from datetime import datetime
from optparse import (
    Option,
    OptionParser,
    OptionValueError,
    )

import transaction

from lp.services.scripts.logger import logger_options


def _check_datetime(option, opt, value):
    "Type checker for optparse datetime option type."
    # We support 5 valid ISO8601 formats.
    formats = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        ]
    for format in formats:
        try:
            return datetime.strptime(value, format)
        except ValueError:
            pass
    raise OptionValueError(
        "option %s: invalid datetime value: %r" % (opt, value))


class LPOption(Option):
    """Extended optparse Option class.

    Adds a 'datetime' option type.
    """
    TYPES = Option.TYPES + ("datetime", datetime)
    TYPE_CHECKER = copy(Option.TYPE_CHECKER)
    TYPE_CHECKER["datetime"] = _check_datetime
    TYPE_CHECKER[datetime] = _check_datetime


class LPOptionParser(OptionParser):
    """Extended optparse OptionParser.

    Adds a 'datetime' option type.

    Automatically adds our standard --verbose, --quiet options that
    tie into our logging system.
    """

    def __init__(self, *args, **kw):
        kw.setdefault('option_class', LPOption)
        OptionParser.__init__(self, *args, **kw)
        logger_options(self)


class TransactionFreeOperation:
    """Ensure that an operation has no active transactions.

    This helps ensure that long-running operations do not hold a database
    transaction.  Long-running operations that hold a database transaction
    may have their database connection killed, and hold locks that interfere
    with other updates.
    """

    count = 0

    @staticmethod
    def any_active_transactions():
        return transaction.manager._txn

    @classmethod
    def __enter__(cls):
        if cls.any_active_transactions():
            raise AssertionError('Transaction open before operation!')

    @classmethod
    def __exit__(cls, exc_type, exc_value, traceback):
        if cls.any_active_transactions():
            raise AssertionError('Operation opened transaction!')
        cls.count += 1

    @classmethod
    @contextlib.contextmanager
    def require(cls):
        """Require that TransactionFreeOperation is used at least once."""
        old_count = cls.count
        try:
            yield
        finally:
            if old_count >= cls.count:
                raise AssertionError('TransactionFreeOperation was not used.')
