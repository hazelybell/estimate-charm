# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code import audit trail interfaces."""

__metaclass__ = type
__all__ = [
    'ICodeImportEvent',
    'ICodeImportEventSet',
    'ICodeImportEventToken',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    )

from lp import _
from lp.code.enums import CodeImportEventType
from lp.services.fields import PublicPersonChoice


class ICodeImportEvent(Interface):
    """One event in the code-import audit trail."""

    id = Int(readonly=True, required=True)
    date_created = Datetime(
        title=_("Date Created"), required=True, readonly=True)

    event_type = Choice(
        title=_("Event"), required=True, readonly=True,
        vocabulary=CodeImportEventType,
        description=_("The type of this event."""))
    code_import = Choice(
        title=_("Code Import"), required=False, readonly=True,
        vocabulary='CodeImport',
        description=_("The code import affected by this event."""))
    person = PublicPersonChoice(
        title=_("Person"), required=False, readonly=True,
        vocabulary='Person',
        description=_("The person that triggered this event."""))
    machine = Choice(
        title=_("Machine"), required=False, readonly=True,
        vocabulary='CodeImportMachine',
        description=_("The import machine where this event occured."""))

    def items():
        """List of key-value tuples recording additional information.

        Keys are values from the CodeImportEventDataType enum, values are
        strings or None.
        """

class ICodeImportEventSet(Interface):
    """The set of all CodeImportEvent objects."""

    def getAll():
        """Iterate over all `CodeImportEvent` objects.

        For use only in tests.
        """

    def getEventsForCodeImport(code_import):
        """Iterate over `CodeImportEvent` objects associated to a CodeImport.
        """

    def newCreate(code_import, person):
        """Record the creation of a `CodeImport` object.

        Should only be called by CodeImportSet.new.

        :param code_import: Newly created `CodeImport` object.
        :param user: User that created the object, usually the view's user.
        :return: `CodeImportEvent` with type CREATE.
        """

    def beginModify(code_import):
        """Create the token to give to `newModify`.

        Should only be called by `CodeImport` methods.

        The token records the state of the code import before modification, it
        lets newModify find what changes were done.

        :param code_import: `CodeImport` that will be modified.
        :return: `CodeImportEventToken` to pass to `newModify`.
        """

    def newModify(code_import, person, token):
        """Record a modification to a `CodeImport` object.

        Should only be called by `CodeImport` methods.

        If no change is found between the code import and the data saved in
        the token, the modification is considered non-significant and no
        event object is created.

        :param code_import: Modified `CodeImport`.
        :param person: `Person` who requested the change.
        :param token: `CodeImportEventToken` created by `beginModify`.
        :return: `CodeImportEvent` of MODIFY type, or None.
        """

    def newRequest(code_import, person):
        """Record that user requested an immediate run of this import.

        Only called by `CodeImportJobWorkflow.requestJob`.

        :param code_import: `CodeImport` for which an immediate run was
            requested.
        :param person: `Person` who requested the code import to run.
        :return: `CodeImportEvent` of REQUEST type.
        """

    def newOnline(machine, user=None, message=None):
        """Record that an import machine went online.

        :param machine: `CodeImportMachine` whose state changed to ONLINE.
        :param user: `Person` that requested going online if done by a user.
        :param message: User-provided message.
        :return: `CodeImportEvent` of ONLINE type.
        """

    def newOffline(machine, reason, user=None, message=None):
        """Record that an import machine went offline.

        :param machine: `CodeImportMachine` whose state changed to OFFLINE.
        :param reason: `CodeImportMachineOfflineReason` enum value.
        :param user: `Person` that requested going offline if done by a user.
        :param message: User-provided message.
        :return: `CodeImportEvent` of OFFLINE type.
        """

    def newQuiesce(machine, user, message=None):
        """Record that user requested the machine to quiesce for maintenance.

        :param machine: `CodeImportMachine` whose state changed to QUIESCING.
        :param user: `Person` that requested quiescing.
        :param message: User-provided message.
        :return: `CodeImportEvent` of QUIESCE type.
        """

    def newStart(code_import, machine):
        """Record that a machine is about to start working on a code import.

        :param code_import: The `CodeImport` which is about to be worked on.
        :param machine: `CodeImportMachine` which is about to start the job.
        :return: `CodeImportEvent` of START type.
        """

    def newFinish(code_import, machine):
        """Record that a machine has finished working on a code import.

        :param code_import: The `CodeImport` which is no longer being worked
                            on.
        :param machine: `CodeImportMachine` which is no longer working on this
                        import.
        :return: `CodeImportEvent` of FINISH type.
        """

    def newKill(code_import, machine):
        """Record that a code import job was killed.

        :param code_import: The `CodeImport` killed job was working on.
        :param machine: `CodeImportMachine` on which the job was running.
        :return: `CodeImportEvent` of KILL type.
        """

    def newReclaim(code_import, machine, job_id):
        """Record that a code import job was reclaimed by the watchdog.

        :param code_import: The `CodeImport` killed job was working on.
        :param machine: `CodeImportMachine` on which the job was running.
        :param job_id: The database id of the reclaimed job.
        :return: `CodeImportEvent` of RECLAIM type.
        """


class ICodeImportEventToken(Interface):
    """Opaque structure returned by `ICodeImportEventSet.beginModify`."""

    items = Attribute(_("Private data."))
