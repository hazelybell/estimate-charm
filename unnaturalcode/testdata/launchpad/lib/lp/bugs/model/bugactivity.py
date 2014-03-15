# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['BugActivity', 'BugActivitySet']

import re

from sqlobject import (
    ForeignKey,
    StringCol,
    )
from storm.store import Store
from zope.interface import implements

from lp.bugs.adapters.bugchange import (
    ATTACHMENT_ADDED,
    ATTACHMENT_REMOVED,
    BRANCH_LINKED,
    BRANCH_UNLINKED,
    BUG_WATCH_ADDED,
    BUG_WATCH_REMOVED,
    CHANGED_DUPLICATE_MARKER,
    CVE_LINKED,
    CVE_UNLINKED,
    MARKED_AS_DUPLICATE,
    REMOVED_DUPLICATE_MARKER,
    REMOVED_SUBSCRIBER,
    )
from lp.bugs.interfaces.bugactivity import (
    IBugActivity,
    IBugActivitySet,
    )
from lp.registry.interfaces.person import validate_person
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.sqlbase import SQLBase


class BugActivity(SQLBase):
    """Bug activity log entry."""

    implements(IBugActivity)

    _table = 'BugActivity'
    bug = ForeignKey(foreignKey='Bug', dbName='bug', notNull=True)
    datechanged = UtcDateTimeCol(notNull=True)
    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_person,
        notNull=True)
    whatchanged = StringCol(notNull=True)
    oldvalue = StringCol(default=None)
    newvalue = StringCol(default=None)
    message = StringCol(default=None)

    # The regular expression we use for matching bug task changes.
    bugtask_change_re = re.compile(
        '(?P<target>[a-z0-9][a-z0-9\+\.\-]+( \([A-Za-z0-9\s]+\))?): '
        '(?P<attribute>assignee|importance|milestone|status)')

    @property
    def target(self):
        """Return the target of this BugActivityItem.

        `target` is determined based on the `whatchanged` string.

        :return: The target name of the item if `whatchanged` is of the
        form <target_name>: <attribute>. Otherwise, return None.
        """
        match = self.bugtask_change_re.match(self.whatchanged)
        if match is None:
            return None
        else:
            return match.groupdict()['target']

    @property
    def attribute(self):
        """Return the attribute changed in this BugActivityItem.

        `attribute` is determined based on the `whatchanged` string.

        :return: The attribute name of the item if `whatchanged` is of
            the form <target_name>: <attribute>. If we know how to determine
            the attribute by normalizing whatchanged, we return that.
            Otherwise, return the original `whatchanged` string.
        """
        match = self.bugtask_change_re.match(self.whatchanged)
        if match is None:
            result = self.whatchanged
            # Now we normalize names, as necessary.  This is fragile, but
            # a reasonable incremental step.  These are consumed in
            # lp.bugs.scripts.bugnotification.get_activity_key.
            if result in (CHANGED_DUPLICATE_MARKER,
                          MARKED_AS_DUPLICATE,
                          REMOVED_DUPLICATE_MARKER):
                result = 'duplicateof'
            elif result in (ATTACHMENT_ADDED, ATTACHMENT_REMOVED):
                result = 'attachments'
            elif result in (BRANCH_LINKED, BRANCH_UNLINKED):
                result = 'linked_branches'
            elif result in (BUG_WATCH_ADDED, BUG_WATCH_REMOVED):
                result = 'watches'
            elif result in (CVE_LINKED, CVE_UNLINKED):
                result = 'cves'
            elif str(result).startswith(REMOVED_SUBSCRIBER):
                result = 'removed_subscriber'
            elif result == 'summary':
                result = 'title'
            return result
        else:
            return match.groupdict()['attribute']


class BugActivitySet:
    """See IBugActivitySet."""

    implements(IBugActivitySet)

    def new(self, bug, datechanged, person, whatchanged,
            oldvalue=None, newvalue=None, message=None):
        """See IBugActivitySet."""
        activity = BugActivity(
            bug=bug, datechanged=datechanged, person=person,
            whatchanged=whatchanged, oldvalue=oldvalue, newvalue=newvalue,
            message=message)
        Store.of(activity).flush()
        return activity
