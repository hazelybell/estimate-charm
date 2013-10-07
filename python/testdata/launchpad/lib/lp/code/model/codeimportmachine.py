# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes including and related to CodeImportMachine."""

__metaclass__ = type

__all__ = [
    'CodeImportMachine',
    'CodeImportMachineSet',
    ]

from sqlobject import (
    SQLMultipleJoin,
    StringCol,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.code.enums import (
    CodeImportMachineOfflineReason,
    CodeImportMachineState,
    )
from lp.code.interfaces.codeimportevent import ICodeImportEventSet
from lp.code.interfaces.codeimportmachine import (
    ICodeImportMachine,
    ICodeImportMachineSet,
    )
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase


class CodeImportMachine(SQLBase):
    """See `ICodeImportMachine`."""

    _defaultOrder = ['hostname']

    implements(ICodeImportMachine)

    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)

    hostname = StringCol(default=None)
    state = EnumCol(enum=CodeImportMachineState, notNull=True,
        default=CodeImportMachineState.OFFLINE)
    heartbeat = UtcDateTimeCol(notNull=False)

    current_jobs = SQLMultipleJoin(
        'CodeImportJob', joinColumn='machine',
        orderBy=['date_started', 'id'])

    events = SQLMultipleJoin(
        'CodeImportEvent', joinColumn='machine',
        orderBy=['-date_created', '-id'])

    def shouldLookForJob(self, worker_limit):
        """See `ICodeImportMachine`."""
        job_count = self.current_jobs.count()

        if self.state == CodeImportMachineState.OFFLINE:
            return False
        self.heartbeat = UTC_NOW
        if self.state == CodeImportMachineState.QUIESCING:
            if job_count == 0:
                self.setOffline(
                    CodeImportMachineOfflineReason.QUIESCED)
            return False
        elif self.state == CodeImportMachineState.ONLINE:
            return job_count < worker_limit
        else:
            raise AssertionError(
                "Unknown machine state %r??" % self.state)

    def setOnline(self, user=None, message=None):
        """See `ICodeImportMachine`."""
        if self.state not in (CodeImportMachineState.OFFLINE,
                              CodeImportMachineState.QUIESCING):
            raise AssertionError(
                "State of machine %s was %s."
                % (self.hostname, self.state.name))
        self.state = CodeImportMachineState.ONLINE
        getUtility(ICodeImportEventSet).newOnline(self, user, message)

    def setOffline(self, reason, user=None, message=None):
        """See `ICodeImportMachine`."""
        if self.state not in (CodeImportMachineState.ONLINE,
                              CodeImportMachineState.QUIESCING):
            raise AssertionError(
                "State of machine %s was %s."
                % (self.hostname, self.state.name))
        self.state = CodeImportMachineState.OFFLINE
        getUtility(ICodeImportEventSet).newOffline(
            self, reason, user, message)

    def setQuiescing(self, user, message=None):
        """See `ICodeImportMachine`."""
        if self.state != CodeImportMachineState.ONLINE:
            raise AssertionError(
                "State of machine %s was %s."
                % (self.hostname, self.state.name))
        self.state = CodeImportMachineState.QUIESCING
        getUtility(ICodeImportEventSet).newQuiesce(self, user, message)


class CodeImportMachineSet(object):
    """See `ICodeImportMachineSet`."""

    implements(ICodeImportMachineSet)

    def getAll(self):
        """See `ICodeImportMachineSet`."""
        return CodeImportMachine.select()

    def getByHostname(self, hostname):
        """See `ICodeImportMachineSet`."""
        return CodeImportMachine.selectOneBy(hostname=hostname)

    def new(self, hostname, state=CodeImportMachineState.OFFLINE):
        """See `ICodeImportMachineSet`."""
        machine = CodeImportMachine(hostname=hostname, heartbeat=None)
        if state == CodeImportMachineState.ONLINE:
            machine.setOnline()
        elif state != CodeImportMachineState.OFFLINE:
            raise AssertionError(
                "Invalid machine creation state: %r." % state)
        return machine
