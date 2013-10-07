#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Expire all old, Incomplete bugs tasks that are unassigned in Malone.

Only bug task for project that use Malone may be expired. The expiration
period is configured through config.malone.days_before_expiration.
"""

__metaclass__ = type

import _pythonpath

from zope.component import getUtility

from lp.bugs.scripts.bugexpire import BugJanitor
from lp.services.config import config
from lp.services.scripts.base import LaunchpadCronScript


class ExpireBugTasks(LaunchpadCronScript):
    """Expire all old, Incomplete bugs tasks that are unassigned in Malone.

    Only bug task for project that use Malone may be automatically set to
    the status of Invalid (expired). The expiration period is configured
    through config.malone.days_before_expiration.
    """
    usage = "usage: %prog [options]"
    description =  '    %s' % __doc__

    def add_my_options(self):
        self.parser.add_option('-u', '--ubuntu', action='store_true',
                               dest='ubuntu', default=False,
                               help='Only expire Ubuntu bug tasks.')
        self.parser.add_option('-l', '--limit', action='store', dest='limit',
                               type='int', metavar='NUMBER', default=None,
                               help='Limit expiry to NUMBER of bug tasks.')

    def main(self):
        """Run the BugJanitor."""
        target = None
        if self.options.ubuntu:
            # Avoid circular import.
            from lp.registry.interfaces.distribution import IDistributionSet
            target = getUtility(IDistributionSet).getByName('ubuntu')
        janitor = BugJanitor(
            log=self.logger, target=target, limit=self.options.limit)
        janitor.expireBugTasks(self.txn)


if __name__ == '__main__':
    script = ExpireBugTasks(
        'expire-bugtasks', dbuser=config.malone.expiration_dbuser)
    script.lock_and_run()
