# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'AdvisoryLockHeld',
    'LockType',
    'try_advisory_lock',
]

from contextlib import contextmanager

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from storm.locals import Select

from lp.services.database.stormexpr import (
    AdvisoryUnlock,
    TryAdvisoryLock,
    )


class AdvisoryLockHeld(Exception):
    """An attempt to acquire an advisory lock failed; it is already held."""


class LockType(DBEnumeratedType):

    BRANCH_SCAN = DBItem(0, """Branch scan.

        Branch scan.
        """)


@contextmanager
def try_advisory_lock(lock_type, lock_id, store):
    """Try to acquire an advisory lock.

    If the lock is currently held, AdvisoryLockHeld will be raised.
    """
    result = store.execute(Select(TryAdvisoryLock(lock_type.value, lock_id)))
    if not result.get_one()[0]:
        raise AdvisoryLockHeld()
    try:
        yield
    finally:
        store.execute(Select(AdvisoryUnlock(lock_type.value, lock_id)))
