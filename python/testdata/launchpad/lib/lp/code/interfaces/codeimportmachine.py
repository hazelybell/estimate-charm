# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code import machine interfaces."""

__metaclass__ = type

__all__ = [
    'ICodeImportMachine',
    'ICodeImportMachineSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    TextLine,
    )

from lp import _
from lp.code.enums import CodeImportMachineState


class ICodeImportMachine(Interface):
    """A machine that can perform imports."""

    id = Int(readonly=True, required=True)

    state = Choice(
        title=_('State'), required=True, vocabulary=CodeImportMachineState,
        default=CodeImportMachineState.OFFLINE,
        description=_("The state of the controller daemon on this machine."))

    hostname = TextLine(
        title=_('Host name'), required=True,
        description=_('The hostname of the machine.'))

    current_jobs = Attribute(
        'The current jobs that the machine is processing.')

    events = Attribute(
        'The events associated with this machine.')

    date_created = Datetime(
        title=_("Date Created"), required=True, readonly=True)

    heartbeat = Datetime(
        title=_("Heartbeat"),
        description=_("When the controller deamon last recorded it was"
                      " running."))

    def shouldLookForJob(worker_limit):
        """Should we look for a job to run on this machine?

        There are three reasons we might not look for a job:

        a) The machine is OFFLINE
        b) The machine is QUIESCING (in which case we might go OFFLINE)
        c) There are already enough jobs running on this machine.
        """

    def setOnline(user=None, message=None):
        """Record that the machine is online, marking it ready to accept jobs.

        Set state to ONLINE, and record the corresponding event.
        :param user: `Person` that requested going online if done by a user.
        :param message: User-provided message.
        """

    def setOffline(reason, user=None, message=None):
        """Record that the machine is offline.

        Set state to OFFLINE, and record the corresponding event.

        :param reason: `CodeImportMachineOfflineReason` enum value.
        :param user: `Person` that requested going online if done by a user.
        :param message: User-provided message.
        """

    def setQuiescing(user, message=None):
        """Initiate an orderly shut down without interrupting running jobs.

        Set state to QUIESCING, and record the corresponding event.

        :param user: `Person` that requested the machine to quiesce.
        :param message: User-provided message.
        """


class ICodeImportMachineSet(Interface):
    """The set of machines that can perform imports."""

    def getAll():
        """Return an iterable of all code machines."""

    def new(hostname, state=CodeImportMachineState.OFFLINE):
        """Create a new CodeImportMachine.

        The machine will initially be in the given 'state', which defaults to
        OFFLINE, but can also be ONLINE.
        """

    def getByHostname(hostname):
        """Retrieve the code import machine for a hostname.

        Returns a `ICodeImportMachine` provider or ``None`` if no such machine
        is present.
        """
