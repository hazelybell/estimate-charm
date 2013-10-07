# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Date-related Launchpad components."""

__metaclass__ = type

from datetime import datetime

import pytz
from zope.interface import implements

from lp.app.interfaces.launchpad import IAging


SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
DAYS_PER_YEAR = 365
DAYS_PER_MONTH = 30
DAYS_PER_WEEK = 7


class AgingAdapter:
    """Adapt an IHasDateCreated to an IAging."""
    implements(IAging)

    def __init__(self, context):
        self.context = context

    def currentApproximateAge(self):
        """See `ITimeDelta`."""
        age = ""
        datecreated = self.context.datecreated
        right_now = datetime.now(pytz.timezone('UTC'))
        delta = right_now - datecreated
        if not delta.days:
            if delta.seconds < SECONDS_PER_HOUR:
                # under an hour
                minutes = delta.seconds / SECONDS_PER_MINUTE
                age = "%d minute" % minutes
                if minutes > 1:
                    age += "s"
            else:
                # over an hour
                hours = delta.seconds / SECONDS_PER_HOUR
                age = "%d hour" % hours
                if hours > 1:
                    age += "s"
        else:
            # one or more days old
            if delta.days >= DAYS_PER_YEAR:
                # one or more years old
                years = delta.days / DAYS_PER_YEAR
                age = "%d year" % years
                if years > 1:
                    age += "s"
            else:
                # under a year old
                if delta.days > DAYS_PER_MONTH:
                    months = delta.days / DAYS_PER_MONTH
                    age = "%d month" % months
                    if months > 1:
                        age += "s"
                else:
                    if delta.days > DAYS_PER_WEEK:
                        weeks = delta.days / DAYS_PER_WEEK
                        age = "%d week" % weeks
                        if weeks > 1:
                            age += "s"

        return age
