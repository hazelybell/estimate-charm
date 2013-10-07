# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['get_lock_id_for_branch_id', 'mirror']


import datetime

import pytz
from twisted.internet import defer


def get_lock_id_for_branch_id(branch_id):
    """Return the lock id that should be used for a branch with the passed id.
    """
    return 'worker-for-branch-%s@supermirror' % (branch_id,)

from lp.codehosting.puller.scheduler import LockError

UTC = pytz.timezone('UTC')


def mirror(logger, manager):
    """Mirror all current branches that need to be mirrored."""
    try:
        manager.lock()
    except LockError as exception:
        logger.info('Could not acquire lock: %s', exception)
        return defer.succeed(0)

    date_started = datetime.datetime.now(UTC)

    def recordSuccess(ignored):
        date_completed = datetime.datetime.now(UTC)
        return manager.recordActivity(date_started, date_completed)

    def unlock(passed_through):
        manager.unlock()
        return passed_through

    deferred = manager.run()
    deferred.addCallback(recordSuccess)
    deferred.addBoth(unlock)
    return deferred

