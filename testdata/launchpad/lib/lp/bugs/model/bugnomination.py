# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes related to bug nomination.

A bug nomination is a suggestion from a user that a bug be fixed in a
particular distro series or product series. A bug may have zero, one,
or more nominations.
"""

__metaclass__ = type
__all__ = [
    'BugNomination',
    'BugNominationSet']

from datetime import datetime

import pytz
from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.bugs.adapters.bugchange import BugTaskAdded
from lp.bugs.interfaces.bugnomination import (
    BugNominationStatus,
    BugNominationStatusError,
    IBugNomination,
    IBugNominationSet,
    )
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase


class BugNomination(SQLBase):
    implements(IBugNomination)
    _table = "BugNomination"

    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    decider = ForeignKey(
        dbName='decider', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False, default=None)
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_decided = UtcDateTimeCol(notNull=False, default=None)
    distroseries = ForeignKey(
        dbName='distroseries', foreignKey='DistroSeries',
        notNull=False, default=None)
    productseries = ForeignKey(
        dbName='productseries', foreignKey='ProductSeries',
        notNull=False, default=None)
    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)
    status = EnumCol(
        dbName='status', notNull=True, schema=BugNominationStatus,
        default=BugNominationStatus.PROPOSED)

    @property
    def target(self):
        """See IBugNomination."""
        return self.distroseries or self.productseries

    def approve(self, approver):
        """See IBugNomination."""
        if self.isApproved():
            # Approving an approved nomination is a no-op.
            return
        self.status = BugNominationStatus.APPROVED
        self.decider = approver
        self.date_decided = datetime.now(pytz.timezone('UTC'))
        targets = []
        if self.distroseries:
            # Figure out which packages are affected in this distro for
            # this bug.
            distribution = self.distroseries.distribution
            distroseries = self.distroseries
            for task in self.bug.bugtasks:
                if not task.distribution == distribution:
                    continue
                if task.sourcepackagename is not None:
                    targets.append(distroseries.getSourcePackage(
                        task.sourcepackagename))
                else:
                    targets.append(distroseries)
        else:
            targets.append(self.productseries)
        bugtasks = getUtility(IBugTaskSet).createManyTasks(
            self.bug, approver, targets)
        for bug_task in bugtasks:
            self.bug.addChange(BugTaskAdded(UTC_NOW, approver, bug_task))

    def decline(self, decliner):
        """See IBugNomination."""
        if self.isApproved():
            raise BugNominationStatusError(
                "Cannot decline an approved nomination.")
        self.status = BugNominationStatus.DECLINED
        self.decider = decliner
        self.date_decided = datetime.now(pytz.timezone('UTC'))

    def isProposed(self):
        """See IBugNomination."""
        return self.status == BugNominationStatus.PROPOSED

    def isDeclined(self):
        """See IBugNomination."""
        return self.status == BugNominationStatus.DECLINED

    def isApproved(self):
        """See IBugNomination."""
        return self.status == BugNominationStatus.APPROVED

    def canApprove(self, person):
        """See IBugNomination."""
        # Use the class method to check permissions because there is not
        # yet a bugtask instance with the this target.
        BugTask = self.bug.bugtasks[0].__class__
        if BugTask.userHasDriverPrivilegesContext(self.target, person):
            return True

        if self.distroseries is not None:
            distribution = self.distroseries.distribution
            # An uploader to any of the packages can approve the
            # nomination. Compile a list of possibilities, and check
            # them all.
            package_names = []
            for bugtask in self.bug.bugtasks:
                if (bugtask.distribution == distribution
                    and bugtask.sourcepackagename is not None):
                    package_names.append(bugtask.sourcepackagename)
            if len(package_names) == 0:
                # If the bug isn't targeted to a source package, allow
                # any component uploader to approve the nomination, like
                # a new package.
                return distribution.main_archive.verifyUpload(
                    person, None, None, None, strict_component=False) is None
            for name in package_names:
                component = self.distroseries.getSourcePackage(
                    name).latest_published_component
                if distribution.main_archive.verifyUpload(
                    person, name, component, self.distroseries) is None:
                    return True
        return False


class BugNominationSet:
    """See IBugNominationSet."""
    implements(IBugNominationSet)

    def get(self, id):
        """See IBugNominationSet."""
        try:
            return BugNomination.get(id)
        except SQLObjectNotFound:
            raise NotFoundError(id)
