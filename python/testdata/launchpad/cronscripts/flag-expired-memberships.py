#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Flag expired team memberships and warn about impending expiration."""

import _pythonpath

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.teammembership import (
    DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT,
    ITeamMembershipSet,
    )
from lp.services.config import config
from lp.services.scripts.base import (
    LaunchpadCronScript,
    LaunchpadScriptFailure,
    )


class ExpireMemberships(LaunchpadCronScript):
    """A script for expired team memberships."""

    def flag_expired_memberships_and_send_warnings(self):
        """Flag expired team memberships and warn about impending expiration.

        Flag expired team memberships and send warnings for members whose
        memberships are going to expire in one week (or less) from now.
        """
        membershipset = getUtility(ITeamMembershipSet)
        self.txn.begin()
        reviewer = getUtility(ILaunchpadCelebrities).janitor
        membershipset.handleMembershipsExpiringToday(reviewer)
        self.txn.commit()

        min_date_for_warning = datetime.now(pytz.timezone('UTC')) + timedelta(
            days=DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT)
        self.txn.begin()
        for membership in membershipset.getMembershipsToExpire(
            min_date_for_warning):
            membership.sendExpirationWarningEmail()
            self.logger.debug("Sent warning email to %s in %s team."
                          % (membership.person.name, membership.team.name))
        self.txn.commit()

    def main(self):
        """Flag expired team memberships."""
        if self.args:
            raise LaunchpadScriptFailure(
                "Unhandled arguments %s" % repr(self.args))
        self.logger.info("Flagging expired team memberships.")
        self.flag_expired_memberships_and_send_warnings()
        self.logger.info("Finished flagging expired team memberships.")


if __name__ == '__main__':
    script = ExpireMemberships('flag-expired-memberships',
                               dbuser=config.expiredmembershipsflagger.dbuser)
    script.lock_and_run()
